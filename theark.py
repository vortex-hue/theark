from fastapi import FastAPI, HTTPException, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
import models
from models import AsyncSessionLocal, engine, Wallet
from pydantic import BaseModel
from typing import List, Any
from starlette.responses import JSONResponse
import aiohttp
import asyncio
from sqlalchemy.future import select
from typing import AsyncGenerator
from moralis import evm_api
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import json
from collections import defaultdict
import aiohttp

## sami ai analysis
from sami_ai import sami_ai


app = FastAPI()

MORALIS_API_URL = 'https://deep-index.moralis.io/api/v2/{address}/erc20/transfers'
MORALIS_API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6ImM5Y2ZiODg5LTgwYzMtNDViNy1hYzZjLTQ0YzM3MTVlNDRjZCIsIm9yZ0lkIjoiMzg1NDg4IiwidXNlcklkIjoiMzk2MDk3IiwidHlwZUlkIjoiNmNmMGE3NjEtZGFmZC00NzFhLThlZjktOGQ1MGViYzQ0NDNhIiwidHlwZSI6IlBST0pFQ1QiLCJpYXQiOjE3MTE4MDQxMjEsImV4cCI6NDg2NzU2NDEyMX0.xjVHBimcTvwTcK-vyhO_wJ4lGgHs6oM7rdR2YZTRz9A'
  # Make sure to import aiohttp at the top of your file
MORALIS_BASE_URL = 'https://deep-index.moralis.io/api/v2'

async def fetch_transactions(wallet_address: str) -> List[dict]:
    headers = {'Accept': 'application/json', 'X-API-Key': MORALIS_API_KEY}
    async with aiohttp.ClientSession() as session:
        async with session.get(MORALIS_API_URL.format(address=wallet_address), headers=headers) as response:
            if response.status == 200:
                data = await response.json()
                return data['result']
            raise HTTPException(status_code=404, detail="Wallet transactions not found")

async def filter_buys_and_sells(transactions: List[dict], wallet_address: str) -> (List[dict], List[dict]):
    buys = [tx for tx in transactions if tx.get('to_address', '').lower() == wallet_address.lower()]
    sells = [tx for tx in transactions if tx.get('from_address', '').lower() == wallet_address.lower()]
    return buys, sells

# Dependency to get the DB session
async def get_db() -> AsyncGenerator:
    async with AsyncSessionLocal() as db:
        yield db

## This schema is for the post request to add wallets
class WalletAddress(BaseModel):
    address: str

##pnl utils
async def fetch_wallet_net_worth(wallet_address: str) -> dict:
    url = f"https://deep-index.moralis.io/api/v2.2/wallets/{wallet_address}/net-worth?exclude_spam=true&exclude_unverified_contracts=true"
    
    headers = {
        "Accept": "application/json",
        "X-API-Key": MORALIS_API_KEY
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status == 200:
                return await response.json()
            else:
                # Handle HTTP errors or unexpected responses
                return {"error": f"Failed to fetch data, status code: {response.status}"}


async def find_wallet_with_highest_growth() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Wallet))
        wallets = result.scalars().all()

    # Initial scan data for debug or review
    scan_data = [wallet.address for wallet in wallets]
    with open('wallets_scan.json', 'w') as f:
        json.dump(scan_data, f)

    tasks = [fetch_wallet_net_worth(wallet.address) for wallet in wallets]
    net_worth_data_list = await asyncio.gather(*tasks)

    # Identify wallet with highest net worth
    highest_net_worth = -1
    highest_net_worth_wallet_data = {}

    for wallet, net_worth_data in zip(wallets, net_worth_data_list):
        if 'error' not in net_worth_data and "total_networth_usd" in net_worth_data:
            current_net_worth = float(net_worth_data["total_networth_usd"])
            if current_net_worth > highest_net_worth:
                highest_net_worth = current_net_worth
                highest_net_worth_wallet_data = {
                    "wallet_address": wallet.address,
                    "total_networth_usd": current_net_worth,
                    # Include more details as needed
                }

    # If a wallet with the highest net worth is found, fetch more details
    if highest_net_worth > -1:
        params = {
            "chain": "eth",
            "address": highest_net_worth_wallet_data["wallet_address"]
        }
        # Simulating API call to fetch additional details
        result = evm_api.wallets.get_wallet_token_balances_price(
                api_key=MORALIS_API_KEY,
                params=params,
            )
        
        final_data = {
            "wallet": highest_net_worth_wallet_data["wallet_address"],
            "net_worth": highest_net_worth_wallet_data["total_networth_usd"],
            "portfolio_data": result
        }

        # Dump final data to JSON
        with open('highest_growth_wallet.json', 'w') as f:
            json.dump(final_data, f)

        return final_data
    else:
        error_message = {"error": "No valid wallet data found."}
        # Optionally dump error data
        with open('no_valid_wallet_data.json', 'w') as f:
            json.dump(error_message, f)
        return error_message


## API ENDPOINT THAT I'LL EXPOSE TO THE PUBLIC

@app.get("/monitor_wallet/{wallet_address}")
async def monitor_wallet(wallet_address: str):
    transactions = await fetch_transactions(wallet_address)
    buys, sells = await filter_buys_and_sells(transactions, wallet_address)
    return {"buys": buys, "sells": sells}

@app.post("/wallet/")
async def create_wallet(wallet_address: WalletAddress, db: AsyncSession = Depends(get_db)):
    async with db.begin():
        result = await db.execute(select(models.Wallet).filter(models.Wallet.address == wallet_address.address))
        db_wallet = result.scalars().first()
    
    if db_wallet:
        raise HTTPException(status_code=400, detail="Wallet already exists")
    else:
        db_wallet = models.Wallet(address=wallet_address.address)
        db.add(db_wallet)
        await db.commit()
        await db.refresh(db_wallet)
        return db_wallet

@app.get("/wallets/")
async def read_wallets(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Wallet))
    db_wallets = result.scalars().all()
    return db_wallets


@app.get("/wallets/highest-pnl")
async def get_wallet_with_highest_pnl(db: Session = Depends(get_db)):
    result = await find_wallet_with_highest_growth()
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@app.get("/highest_growth_wallet")
async def read_former_highest_growth_wallet() -> Any:
    try:
        # Open the json file, load its content and then return it
        with open("highest_growth_wallet.json", "r") as file:
            data = json.load(file)
        return JSONResponse(content=data)
    except FileNotFoundError:
        # If the file is not found, return an error message
        return JSONResponse(content={"error": "File not found"}, status_code=404)


@app.get("/wallet-overview/{wallet_address}")
async def wallet_overview(wallet_address: str):
    net_worth = await fetch_wallet_net_worth(wallet_address)
    params = {
                "chain": "eth",
                "address": wallet_address
            }
    result = evm_api.wallets.get_wallet_token_balances_price(
                api_key=MORALIS_API_KEY,
                params=params,
            )
    output = {
        "networth": net_worth,
        "portfolio-data" : result
    }
    
    if "error" in net_worth:
        raise HTTPException(status_code=400, detail=net_worth["error in getting the networth"])
    return output


@app.get("/top-current-trading-volume/")
async def top_crypto_by_volume():
    api_key = MORALIS_API_KEY

    result = evm_api.market_data.get_top_crypto_currencies_by_trading_volume(
    api_key=api_key,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=net_worth["error in getting the top volumes"])
    return result


@app.get("/top-crypto-by-market-cap")
async def get_top_crypto_currencies_by_market_cap():
    api_key = MORALIS_API_KEY

    result = evm_api.market_data.get_top_crypto_currencies_by_market_cap(
    api_key=api_key,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=net_worth["error in getting the top volumes"])
    return result


@app.get("/top-erc20-tokens-by-price-action")
async def get_top_erc20_tokens_by_price_action():
    api_key = MORALIS_API_KEY

    result = evm_api.market_data.get_top_erc20_tokens_by_price_movers(
    api_key=api_key,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=net_worth["error in getting the top crypto price movers"])
    return result



@app.get("/top-erc20-tokens-by-market-cap")
async def get_top_erc20_tokens_by_market_cap():
    api_key = MORALIS_API_KEY

    result = evm_api.market_data.get_top_erc20_tokens_by_market_cap(
    api_key=api_key,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=net_worth["error in getting the top crypto price movers"])
    return result


async def fetch_wallet_data(wallet):
    params = {
        "chain": "eth",
        "address": wallet.address
    }
    # Since the actual API call is not async, wrap it in a thread pool executor
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool, 
            evm_api.wallets.get_wallet_token_balances_price, 
            MORALIS_API_KEY, 
            params
        )
    return {
        "wallet_address": wallet.address,
        "portfolio_data": result
    }
    
    

## the functionality to process the wallets
def process_and_aggregate_crypto_data(data_file_path, output_file_path=None):
    """
    Loads wallet data from a JSON file, aggregates cryptocurrency information,
    and outputs the processed data to a JSON file or prints it.

    :param data_file_path: Path to the JSON file containing wallet data.
    :param output_file_path: Optional path to save the processed data as JSON.
    """
    def load_data(file_path):
        with open(file_path, 'r') as file:
            return json.load(file)

    def aggregate_crypto_data(wallets_data):
        aggregated_data = defaultdict(lambda: {
            "token_address": "",
            "symbol": "",
            "name": "",
            "logo": "",
            "thumbnail": "",
            "decimals": 0,
            "smw_holdings_usd": 0,
            "possible_spam": False,
            "verified_contract": False,
            "smw_holders": 0,
            "usd_price": 0,
            "smw_holders_address": [],
            "native_token": False,
            "portfolio_average_percentage": 0
        })
        
        for wallet in wallets_data:
            for token in wallet['portfolio_data']['result']:
                token_address = token['token_address']
                agg = aggregated_data[token_address]  # Reference for brevity
                agg['token_address'] = token_address
                agg['symbol'] = token.get('symbol', '')
                agg['name'] = token.get('name', '')
                agg['logo'] = token.get('logo', '')
                agg['thumbnail'] = token.get('thumbnail', '')
                agg['decimals'] = token.get('decimals', 0)
                agg['possible_spam'] = token.get('possible_spam', False)
                agg['verified_contract'] = token.get('verified_contract', False)
                agg['usd_price'] = token.get('usd_price', 0)
                agg['native_token'] = token.get('native_token', False)
                
                if wallet['wallet_address'] not in agg['smw_holders_address']:
                    agg['smw_holders_address'].append(wallet['wallet_address'])
                    agg['smw_holders'] += 1
                
                usd_value = token.get("usd_value", 0)
                if usd_value is None:
                  usd_value = 0
                agg['smw_holdings_usd'] += usd_value
                agg['portfolio_average_percentage'] += token.get('portfolio_percentage', 0)

        for agg in aggregated_data.values():
            if agg['smw_holders'] > 0:
                agg['portfolio_average_percentage'] /= agg['smw_holders']

        return sorted(aggregated_data.values(), key=lambda x: x['smw_holders'], reverse=True)

    # Load and process the data
    wallets_data = load_data(data_file_path)
    processed_data = aggregate_crypto_data(wallets_data)
    output_json = json.dumps(processed_data, indent=4, ensure_ascii=False)

    if output_file_path:
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write(output_json)
    else:
        print(output_json)


@app.get("/top-holders")
async def top_holders():
    async with AsyncSessionLocal() as db:  # Assuming AsyncSessionLocal is an async session maker
        result = await db.execute(select(Wallet))
        wallets = result.scalars().all()

    # Use asyncio.gather to run fetch_wallet_data concurrently for all wallets
    tasks = [fetch_wallet_data(wallet) for wallet in wallets]
    scanned_data = await asyncio.gather(*tasks)

    # Convert the scanned_data to JSON and save it to a file
    with open('scanned_data_test.json', 'w', encoding='utf-8') as f:
        json.dump(scanned_data, f, ensure_ascii=False, indent=4)
    
    ## process the data
    data_file = 'scanned_data_test.json'  
    output_file = 'processed_data_test.json'  
    process_and_aggregate_crypto_data(data_file, output_file)
    
    ## return the processed data
    if output_file:  # Ensure output_file is not None
        with open(output_file, 'r', encoding='utf-8') as file:
            scanned_data = json.load(file)
            # Now you can return or use scanned_data as needed
            return scanned_data
    

@app.get('/top-holdings')
async def get_former_processed_scan():
    output_file = 'processed_data_test.json'  
    
    ## return the processed data
    if output_file:  # Ensure output_file is not None
        with open(output_file, 'r', encoding='utf-8') as file:
            scanned_data = json.load(file)
            # Now you can return or use scanned_data as needed
            return scanned_data