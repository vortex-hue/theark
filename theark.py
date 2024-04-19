from fastapi import FastAPI, HTTPException, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
import models
from models import AsyncSessionLocal, engine, Wallet
from pydantic import BaseModel
from typing import List, Any, Dict
from starlette.responses import JSONResponse
import aiohttp
import requests
import asyncio
from sqlalchemy.future import select
from typing import AsyncGenerator
# from moralis import evm_api
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from collections import defaultdict
import aiohttp
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import humanize  # You might need to install this package if not already installed
import httpx
from fastapi.middleware.cors import CORSMiddleware
import orjson
import aiofiles



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

MORALIS_API_URL = 'https://deep-index.moralis.io/api/v2/{address}/erc20/transfers'
MORALIS_API_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6IjFjZGRmZWFiLTllYjgtNDM0NS05NjRmLWM0NjIxOTZhNGI2YyIsIm9yZ0lkIjoiMzgyMzY3IiwidXNlcklkIjoiMzkyODg4IiwidHlwZUlkIjoiNDdkNzNlNDQtMzQ3MS00MDlmLTkxY2QtNDllMTJjNmI2YjY4IiwidHlwZSI6IlBST0pFQ1QiLCJpYXQiOjE3MTAxOTA2MTUsImV4cCI6NDg2NTk1MDYxNX0.bmYG9dUG2grEjbaBXk26nZ3ZtQ0ftyn4C8CadLF8IKk'
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
    url = f"https://deep-index.moralis.io/api/v2.2/wallets/{wallet_address}/net-worth?chains%5B0%5D=eth&chains%5B1%5D=avalanche&chains%5B2%5D=polygon&chains%5B3%5D=bsc&chains%5B4%5D=fantom&chains%5B5%5D=base&exclude_spam=true&exclude_unverified_contracts=true"
    
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

def calculate_wallet_pnl(wallets: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    pnl_data = {}

    # Iterate over each wallet
    for wallet in wallets:
        wallet_address = wallet["wallet_address"]
        pnl_data[wallet_address] = {
            "total_pnl_usd": 0.0,
            "positions": []
        }

        # Process each position in the wallet
        for position in wallet["portfolio_data"]["data"]:
            attributes = position["attributes"]
            # Initialize PnL for the position
            position_pnl = {
                "id": position["id"],
                "name": attributes["name"],
                "pnl_usd": 0.0
            }

            # Check if changes and value information are available
            changes = attributes.get("changes")
            if changes and 'absolute_1d' in changes:
                position_pnl["pnl_usd"] = changes["absolute_1d"]
                pnl_data[wallet_address]["total_pnl_usd"] += changes["absolute_1d"]

            pnl_data[wallet_address]["positions"].append(position_pnl)

    return pnl_data
 

## API ENDPOINT THAT I'LL EXPOSE TO THE PUBLIC

@app.get("/portfolio/{wallet_address}")
async def monitor_wallet(wallet_address: str):
    url = f"https://api.zerion.io/v1/wallets/{wallet_address}/positions/?filter[deposit, loan, locked, staked, reward, wallet, airdrop, margin]=no_filter&currency=usd&filter[deposit, loan, locked, staked, reward, wallet, airdrop, margin]=,&filter[trash]=only_non_trash&sort=-value"

    headers = {
        "accept": "application/json",
        "authorization": "Basic emtfZGV2Xzc1Y2MyNGI2NjFkYzRiZmQ5YWU1ZDI4MDQ3MTM2NmRjOg=="
    }

    response = requests.get(url, headers=headers)
    data = json.loads(response.text)
    
    return JSONResponse(content=data)

 
# ## market stream
# def process_market_stream(all_wallets_transactions):
    token_volumes = {}
    now = datetime.now(timezone.utc)  # Current UTC time

    for wallet_data in all_wallets_transactions:
        transactions = wallet_data.get("transactions", {}).get("portfolio_data", {}).get("data", [])
        for transaction in transactions:
            # Debugging output to check the type of 'transaction'
            print(f"Type of transaction: {type(transaction)}")
            if not isinstance(transaction, dict):
                print("Error: transaction is not a dictionary.")
                continue  # Skip to the next transaction if the current one is not a dictionary

            attributes = transaction.get("attributes", {})
            if 'operation_type' in attributes and attributes['operation_type'] == 'receive':
                # Extracting token information
                token_info = attributes.get('fee', {}).get('fungible_info', {})
                token_symbol = token_info.get('symbol', 'ETH')  # Default to ETH if not specified
                token_name = token_info.get('name', 'Ethereum')  # Default to Ethereum if not specified

                timestamp = datetime.strptime(attributes['mined_at'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                
                if token_symbol not in token_volumes:
                    token_volumes[token_symbol] = {
                        "buy_volume": 0,
                        "sell_volume": 0,
                        "transactions": []
                    }

                # Calculate transaction value
                quantity = attributes.get('fee', {}).get('quantity', {}).get('float', 0)
                price = attributes.get('fee', {}).get('price', 0)
                value = attributes.get('value')

                token_volumes[token_symbol]["buy_volume"] += quantity
                token_volumes[token_symbol]["sell_volume"] += quantity

                # Appending transaction with additional details
                token_volumes[token_symbol]["transactions"].append({
                    "type": "receive",
                    "token_name": token_name,
                    "token_symbol": token_symbol,
                    "token_logo": token_info.get('icon', {}).get('url', ""),
                    "contract_address": attributes['sent_from'],
                    "time_ago": humanize.naturaltime(now - timestamp),
                    "smw_buyer_address": attributes['sent_to'],
                    "possible_spam": attributes.get('flags', {}).get('is_trash', False),
                    "verified_contract": token_info.get('flags', {}).get('verified', False),
                    "transaction_hash": attributes.get('hash', 'N/A'),  # Default to 'N/A' if hash is not available
                    "value": value
                })

    with open('zerion_market_stream_transactions.json', 'w', encoding='utf-8') as f:
        json.dump(token_volumes, f, ensure_ascii=False, indent=4)
    
    return token_volumes  # Return or further processing


def process_market_stream(all_wallets_transactions):
    token_volumes = {}
    now = datetime.now(timezone.utc)  # Current UTC time

    for wallet_data in all_wallets_transactions:
        transactions = wallet_data.get("transactions", {}).get("portfolio_data", {}).get("data", [])
        for transaction in transactions:
            if not isinstance(transaction, dict):
                print("Error: transaction is not a dictionary.")
                continue  # Skip to the next transaction if the current one is not a dictionary

            attributes = transaction.get("attributes", {})
            operation_type = attributes.get("operation_type", "").lower()

            if operation_type in ['receive', 'send']:
                token_info = attributes.get('fee', {}).get('fungible_info', {})
                token_symbol = token_info.get('symbol', 'ETH')  # Default to ETH if not specified
                token_name = token_info.get('name', 'Ethereum')  # Default to Ethereum if not specified

                timestamp = datetime.strptime(attributes['mined_at'], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                
                if token_symbol not in token_volumes:
                    token_volumes[token_symbol] = {
                        "buy_volume": 0,
                        "sell_volume": 0,
                        "transactions": []
                    }

                quantity = attributes.get('fee', {}).get('quantity', {}).get('float', 0)
                price = attributes.get('fee', {}).get('price')
                if price is None:
                    print(f"Warning: Price is None for transaction {attributes.get('hash', 'N/A')}")
                    price = 0  # Default price to 0 if none provided

                value = quantity * price

                if operation_type == 'receive':
                    token_volumes[token_symbol]["buy_volume"] += value
                    transaction_type = "buy"
                else:
                    token_volumes[token_symbol]["sell_volume"] += value
                    transaction_type = "sell"

                token_volumes[token_symbol]["transactions"].append({
                    "type": transaction_type,
                    "token_name": token_name,
                    "token_symbol": token_symbol,
                    "token_logo": token_info.get('icon', {}).get('url', ""),
                    "contract_address": attributes['sent_from'],
                    "time_ago": humanize.naturaltime(now - timestamp),
                    "smw_buyer_address": attributes['sent_to'],
                    "possible_spam": attributes.get('flags', {}).get('is_trash', False),
                    "verified_contract": token_info.get('flags', {}).get('verified', False),
                    "transaction_hash": attributes.get('hash', 'N/A'),
                    "value": value
                })

    with open('zerion_market_stream_transactions.json', 'w', encoding='utf-8') as f:
        json.dump(token_volumes, f, ensure_ascii=False, indent=4)
    
    return token_volumes  # Return the processed data


@app.get("/recent_buy_sell")
async def fetch_transactions_for_wallet(address: str):
    url = f"https://api.zerion.io/v1/wallets/{address}/transactions/?currency=usd&filter%5Btrash%5D=no_filter"
    
    headers = {
        "accept": "application/json",
        "authorization": "Basic emtfZGV2Xzc1Y2MyNGI2NjFkYzRiZmQ5YWU1ZDI4MDQ3MTM2NmRjOg=="
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                raise HTTPException(status_code=response.status, detail=f"Failed to fetch data from Zerion API. Status code: {response.status}")
            
            data = await response.json()  # Directly parsing response to JSON
            print("STARTING TRANSACTION SCANNING>>>>>")
            
            # Assuming the correct key path to the transactions is checked
            transactions_data = data.get('data', [])
            print(transactions_data)
            
            if not transactions_data:
                print("No transactions found in the data received from API.")
                return {
                    "wallet_address": address,
                    "transactions": [],
                    "error": "No transactions available or wrong data path in response."
                }
            
            transactions_list = []
            for txn in transactions_data:
                attributes = txn.get("attributes", {})
                fee_info = attributes.get("fee", {}).get("fungible_info", {})
                transactions_list.append({
                    "type": txn.get("type"),
                    "transaction_id": txn.get("id"),
                    "operation_type": attributes.get("operation_type"),
                    "transaction_hash": attributes.get("hash"),
                    "mined_at_block": attributes.get("mined_at_block"),
                    "mined_at": attributes.get("mined_at"),
                    "sent_from": attributes.get("sent_from"),
                    "sent_to": attributes.get("sent_to"),
                    "status": attributes.get("status"),
                    "nonce": attributes.get("nonce"),
                    "fee_info": fee_info.get("name"),
                    "token_symbol": fee_info.get("symbol"),
                    "token_icon_url": fee_info.get("icon", {}).get("url"),
                    "value": attributes.get("value", 0)
                })

            return {
                "wallet_address": address,
                "transactions": transactions_list
            }


async def fetch_transact(address):
    url = f"https://api.zerion.io/v1/wallets/{address}/transactions/"
    
    headers = {
        "accept": "application/json",
        "authorization": "Basic emtfZGV2Xzc1Y2MyNGI2NjFkYzRiZmQ5YWU1ZDI4MDQ3MTM2NmRjOg=="
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            response_text = await response.text()
            print("STARTING TRANSACTION SCANNING>>>>>")
            data = json.loads(response_text)
            return {
                "wallet_address": address,
                "portfolio_data": data
            }
            

@app.get("/market-streams-smw")
async def scan_and_process_wallets():
    # async with AsyncSessionLocal() as db:
    #     # Fetch all wallets
    #     result = await db.execute(select(Wallet))
    #     wallets = result.scalars().all()

    # # Store transactions for all wallets
    # all_wallets_transactions = []

    # for wallet in wallets:
    #     transactions = await fetch_transact(wallet.address)
    #     all_wallets_transactions.append({
    #         "wallet_address": wallet.address,
    #         "transactions": transactions
    #     })

    # Save the scanned data to a JSON file
    # with open('zerion_test_wallets_transactions.json', 'w', encoding='utf-8') as f:
    #     json.dump(all_wallets_transactions, f, ensure_ascii=False, indent=4)
    with open('zerion_test_wallets_transactions.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    # Process the data for market stream (this is an example, adjust according to your specific requirements)
    market_stream_data = process_market_stream(data)

    # Assuming process_market_stream returns data in the desired format, you could then save or use it as needed
    # For demonstration, let's just return this processed data
    return market_stream_data




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
    with open('test_scan.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    result = calculate_wallet_pnl(data)
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



@app.get("/portfolio-overview/{wallet_address}")
async def wallet_overview(wallet_address: str):
    url = f"https://api.zerion.io/v1/wallets/{wallet_address}/portfolio?currency=usd"

    headers = {
        "accept": "application/json",
        "authorization": "Basic emtfZGV2Xzc1Y2MyNGI2NjFkYzRiZmQ5YWU1ZDI4MDQ3MTM2NmRjOg=="
    }

    response = requests.get(url, headers=headers)

    
    if "error" in response:
        raise HTTPException(status_code=400, detail=net_worth["error in getting the networth"])
    data = json.loads(response.text)
    
    return JSONResponse(content=data)


async def fetch_wallet_data(wallet):
    url = f"https://api.zerion.io/v1/wallets/{wallet.address}/positions/?filter[wallet]=no_filter&currency=usd&filter[wallet]=,&filter[trash]=only_non_trash&sort=-value"

    headers = {
        "accept": "application/json",
        "authorization": "Basic emtfZGV2Xzc1Y2MyNGI2NjFkYzRiZmQ5YWU1ZDI4MDQ3MTM2NmRjOg=="
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            response_text = await response.text()
            print("STARTING>>>>>")
            data = json.loads(response_text)
            return {
                "wallet_address": wallet.address,
                "portfolio_data": data
            }


# ## the functionality to process the wallets

## first working trial
# def process_and_aggregate_crypto_data(wallets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
#     aggregated_data = defaultdict(lambda: {
#         "token_address": "",
#         "symbol": "",
#         "name": "",
#         "logo_url": "",
#         "decimals": 0,
#         "holdings_quantity": 0.0,
#         "displayable": False,
#         "is_trash": True,
#         "holders_count": 0,
#         "holders_addresses": []
#     })

#     # Iterate over each wallet and its positions
#     for wallet in wallets:
#         positions = wallet["portfolio_data"]["data"]
#         for position in positions:
#             attributes = position["attributes"]
#             fungible_info = attributes.get("fungible_info")
#             if not fungible_info or 'implementations' not in fungible_info or not fungible_info['implementations']:
#                 continue  # Skip if required information is missing

#             # Extract information from the first implementation
#             implementation = fungible_info['implementations'][0]
#             token_address = implementation['address']
#             agg = aggregated_data[token_address]  # Reference for brevity

#             # Aggregate the data
#             agg['token_address'] = token_address
#             agg['symbol'] = fungible_info.get('symbol', '')
#             agg['name'] = fungible_info.get('name', '')
#             agg['logo_url'] = fungible_info['icon']['url'] if 'icon' in fungible_info and fungible_info['icon'] else None
#             agg['decimals'] = implementation['decimals']
#             agg['displayable'] = attributes['flags']['displayable']
#             agg['is_trash'] = attributes['flags']['is_trash']
#             quantity_float = attributes['quantity']['float']
#             agg['holdings_quantity'] += quantity_float
#             wallet_address = wallet["wallet_address"]
#             if wallet_address not in agg['holders_addresses']:
#                 agg['holders_addresses'].append(wallet_address)
#                 agg['holders_count'] += 1

#     # Convert the result into a sorted list
#     result = sorted(aggregated_data.values(), key=lambda x: x['holders_count'], reverse=True)
#     return result
from collections import defaultdict
from typing import List, Dict, Any

def process_and_aggregate_crypto_data(wallets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    aggregated_data = defaultdict(lambda: {
        "chain_id": "",
        "token_address": "",
        "symbol": "",
        "name": "",
        "logo_url": "",
        "decimals": 0,
        "holdings_quantity": 0.0,
        "holdings_usd": 0.0,
        "displayable": False,
        "is_trash": True,
        "holders_count": 0,
        "holders_addresses": []
    })

    # Iterate over each wallet and its positions
    for wallet in wallets:
        positions = wallet["portfolio_data"]["data"]
        for position in positions:
            attributes = position["attributes"]
            fungible_info = attributes.get("fungible_info")
            if not fungible_info or 'implementations' not in fungible_info or not fungible_info['implementations']:
                continue  # Skip if required information is missing

            # Extract information from the first implementation
            implementation = fungible_info['implementations'][0]
            token_address = implementation['address']
            chain_id = implementation['chain_id']
            agg = aggregated_data[token_address]  # Reference for brevity

            # Aggregate the data
            agg['chain_id'] = chain_id
            agg['token_address'] = token_address
            agg['symbol'] = fungible_info.get('symbol', '')
            agg['name'] = fungible_info.get('name', '')
            agg['logo_url'] = fungible_info['icon']['url'] if 'icon' in fungible_info and fungible_info['icon'] else None
            agg['decimals'] = implementation['decimals']
            agg['displayable'] = attributes['flags']['displayable']
            agg['is_trash'] = attributes['flags']['is_trash']
            quantity_float = attributes['quantity']['float']
            agg['holdings_quantity'] += quantity_float
            wallet_address = wallet["wallet_address"]
            if wallet_address not in agg['holders_addresses']:
                agg['holders_addresses'].append(wallet_address)
                agg['holders_count'] += 1

            # Calculate USD value if 'value' is available
            value_usd = attributes.get('value')
            if value_usd is not None:
                agg['holdings_usd'] += value_usd

    # Convert the result into a sorted list
    result = sorted(aggregated_data.values(), key=lambda x: x['holders_count'], reverse=True)
    return result

@app.get("/top")
async def top_holding():
    async with AsyncSessionLocal() as db:  # Assuming AsyncSessionLocal is an async session maker
        result = await db.execute(select(Wallet))
        wallets = result.scalars().all()

    # Use asyncio.gather to run fetch_wallet_data concurrently for all wallets
    tasks = [fetch_wallet_data(wallet)  for wallet in wallets]
    scanned_data = await asyncio.gather(*tasks)

    # Convert the scanned_data to JSON and save it to a file
    with open('10_wallet_position_holdings_scan.json', 'w', encoding='utf-8') as f:
        json.dump(scanned_data, f, ensure_ascii=False, indent=4)
    
   # Ensure scanned_data contains the results, not coroutines
    with open('10_wallet_position_holdings_scan.json', 'r', encoding='utf-8') as f:
        data = f
    
    
    ## process the data 
    processed_data = process_and_aggregate_crypto_data(data)
    
    ## save in json
    with open('10_wallets_final_zerion_top_holdings_data.json', 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=4)

    # Return the processed data
    return processed_data


# Cache variable
cache_data = None
data_loaded = False

@app.on_event("startup")
async def load_data():
    global cache_data, data_loaded
    try:
        async with aiofiles.open("test_processed_data_prod.json", "r") as file:
            content = await file.read()
            cache_data = orjson.loads(content)
        data_loaded = True  # Set true if data is loaded successfully
    except FileNotFoundError:
        cache_data = {"error": "File not found", "status_code": 404}
        data_loaded = False  # Indicate that data loading failed

@app.get("/top-holdings")
async def smw_top_holdings_token():
    if not data_loaded:
        # If data was not loaded successfully, return the error message.
        return JSONResponse(content=cache_data, status_code=404)
    return JSONResponse(content=cache_data)

    
@app.get("/process-saved-data")
async def process_saved_data():
    # Read the previously scanned data from a file
    with open('10_wallet_position_holdings_scan.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Process the data
    processed_data = process_and_aggregate_crypto_data(data)
    
    # Save the processed data to a new JSON file
    with open('10_wallets_final_zerion_top_holdings_data.json', 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=4)

    # Return the processed data
    return processed_data

# scheduler = AsyncIOScheduler()
# async def call_top_holders():
#     await top_holders()
  
# # Schedule the task to run once daily
# scheduler.add_job(call_top_holders, 'interval', days=1, next_run_time=datetime.now())

# # Start the scheduler
# scheduler.start()

# # Optional: Shutdown the scheduler when the application stops
# @app.on_event("shutdown")
# def shutdown_event():
#     scheduler.shutdown()

# @app.get('/top-holdings')
# async def get_former_processed_scan():
#     output_file = 'processed_data_prod.json'  
    
#     ## return the processed data
#     if output_file:  # Ensure output_file is not None
#         with open(output_file, 'r', encoding='utf-8') as file:
#             scanned_data = json.load(file)
#             # Now you can return or use scanned_data as needed
#             return scanned_data
        
