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
import orjson
import aiofiles
from collections import defaultdict
from typing import List, Dict, Any

# Dependency to get the DB session
async def get_db() -> AsyncGenerator:
    async with AsyncSessionLocal() as db:
        yield db

## This schema is for the post request to add wallets
class WalletAddress(BaseModel):
    address: str


## process all wallet buys and sells
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

                value = attributes.get("fee", {}).get("quantity", {}).get("float", 0)

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

