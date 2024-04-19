from fastapi import FastAPI, HTTPException, Depends, Request, status
from fastapi.middleware.cors import CORSMiddleware
from utils import *
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
import asyncio

app = FastAPI()

# My CORS Settings to allow request from all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Cache variable
cache_data = None
data_loaded = False
market_stream = None


# Create an instance of the scheduler
scheduler = AsyncIOScheduler()


@app.on_event("startup")
async def load_data():
    global cache_data, data_loaded, market_stream
    try:
        async with aiofiles.open("top_holdings_processed.json", "r") as file:
            content = await file.read()
            cache_data = orjson.loads(content)
        data_loaded = True  # Set true if data is loaded successfully
        async with aiofiles.open("zerion_market_stream_transactions.json", "r") as file:
            content = await file.read()
            market_stream = orjson.loads(content)
    except FileNotFoundError:
        cache_data = {"error": "File not found", "status_code": 404}
        market_stream = {"error": "File not found", "status_code": 404}
        data_loaded = False  # Indicate that data loading failed


@app.on_event("startup")
def start_scheduler():
    # Add job for fetching data at noon (12:00 PM) every day
    scheduler.add_job(
        fetch_data_market_stream,
        trigger=CronTrigger(hour=12, minute=0),
        name="Fetch market data at noon"
    )

    # Add job for fetching data at midnight (00:00 AM) every day
    scheduler.add_job(
        process_data_market_stream,
        trigger=CronTrigger(hour=0, minute=0),
        name="Fetch market data at midnight"
    )

    # Add job for processing data at one minute past noon (12:01 PM) every day
    scheduler.add_job(
        fetch_data_market_stream,
        trigger=CronTrigger(hour=12, minute=1),
        name="Process market data shortly after noon"
    )

    # Add job for processing data at one minute past midnight (00:01 AM) every day
    scheduler.add_job(
        process_data_market_stream,
        trigger=CronTrigger(hour=0, minute=1),
        name="Process market data shortly after midnight"
    )
    
    scheduler.add_job(
        fetch_top_holding,
        trigger=IntervalTrigger(minutes=120),
        name="Fetch market data every 120 minutes"
    )

    # Schedule process_data_market_stream to run every 2 minutes, slightly offset
    scheduler.add_job(
        process_saved_data,
        trigger=IntervalTrigger(minutes=130, seconds=310),  # Adding a 30-second offset
        name="Process market data every 130 minutes, offset by 30 seconds"
    )

    # Start the scheduler
    scheduler.start()

@app.on_event("shutdown")
def shutdown_scheduler():
    scheduler.shutdown()



## Functionalities

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


async def fetch_top_holding():
    async with AsyncSessionLocal() as db:  # Assuming AsyncSessionLocal is an async session maker
        result = await db.execute(select(Wallet))
        wallets = result.scalars().all()

    # Use asyncio.gather to run fetch_wallet_data concurrently for all wallets
    tasks = [fetch_wallet_data(wallet)  for wallet in wallets]
    scanned_data = await asyncio.gather(*tasks)

    # Convert the scanned_data to JSON and save it to a file
    with open('wallet_position_holdings_scan.json', 'w', encoding='utf-8') as f:
        json.dump(scanned_data, f, ensure_ascii=False, indent=4)

    # Return the processed data
    return scanned_data

    
async def process_saved_data():
    # Read the previously scanned data from a file
    with open('wallet_position_holdings_scan.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # Process the data
    processed_data = process_and_aggregate_crypto_data(data)
    
    # Save the processed data to a new JSON file
    with open('top_holdings_processed.json', 'w', encoding='utf-8') as f:
        json.dump(processed_data, f, ensure_ascii=False, indent=4)

    # Return the processed data
    return processed_data



async def fetch_data_market_stream():
    async with AsyncSessionLocal() as db:
        # Fetch all wallets
        result = await db.execute(select(Wallet))
        wallets = result.scalars().all()

    # Store transactions for all wallets
    all_wallets_transactions = []

    for wallet in wallets:
        transactions = await fetch_transact(wallet.address)
        all_wallets_transactions.append({
            "wallet_address": wallet.address,
            "transactions": transactions
        })

    # Save the scanned data to a JSON file
    with open('zerion_wallets_transactions.json', 'w', encoding='utf-8') as f:
        json.dump(all_wallets_transactions, f, ensure_ascii=False, indent=4)

async def process_data_market_stream():
    with open('zerion_wallets_transactions.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    market_stream_data = process_market_stream(data)
    return market_stream_data







## API ENDPOINT THAT I'LL EXPOSE TO THE PUBLIC

@app.get("/portfolio-holdings/{wallet_address}")
async def monitor_wallet(wallet_address: str):
    url = f"https://api.zerion.io/v1/wallets/{wallet_address}/positions/?filter[deposit, loan, locked, staked, reward, wallet, airdrop, margin]=no_filter&currency=usd&filter[deposit, loan, locked, staked, reward, wallet, airdrop, margin]=,&filter[trash]=only_non_trash&sort=-value"

    headers = {
        "accept": "application/json",
        "authorization": "Basic emtfZGV2Xzc1Y2MyNGI2NjFkYzRiZmQ5YWU1ZDI4MDQ3MTM2NmRjOg=="
    }

    response = requests.get(url, headers=headers)
    data = json.loads(response.text)
    
    return JSONResponse(content=data)

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
                    "value": attributes.get("fee", {}).get("quantity", {}).get("float", 0)
                })

            return {
                "wallet_address": address,
                "transactions": transactions_list
            }


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



@app.get("/market-streams-smw")
async def scan_and_process_wallets():
    if not data_loaded:
        # If data was not loaded successfully, return the error message.
        return JSONResponse(content=market_stream, status_code=404)
    return JSONResponse(content=market_stream)


@app.get("/top-holdings")
async def smw_top_holdings_token():
    if not data_loaded:
        # If data was not loaded successfully, return the error message.
        return JSONResponse(content=cache_data, status_code=404)
    return JSONResponse(content=cache_data)


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





