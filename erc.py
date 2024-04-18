from web3 import Web3
import json
import time  # Importing the time module for the sleep function

# Connect to the Ethereum network
infura_url = 'https://mainnet.infura.io/v3/ed19c8d712b84f68871fb51d0094faa6'
web3 = Web3(Web3.HTTPProvider(infura_url))

if web3.is_connected():
    print("Connected to Ethereum network!")
else:
    print("Failed to connect to Ethereum network.")

# ERC20 Token Transfer Event ABI
transfer_event_abi = json.loads('[{"anonymous":false,"inputs":[{"indexed":true,"name":"from","type":"address"},{"indexed":true,"name":"to","type":"address"},{"indexed":false,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"}]')
transfer_event_signature = web3.keccak(text="Transfer(address,address,uint256)").hex()

def handle_event(event):
    receipt = web3.eth.get_transaction_receipt(event['transactionHash'])
    transfer_events = receipt['logs']
    for evt in transfer_events:
        if evt['topics'][0].hex() == transfer_event_signature:
            if evt['topics'][1].hex() == '0x0000000000000000000000000000000000000000':
                print(f"New token minted: {evt['topics'][2].hex()} with value {web3.toInt(hexstr=evt['data'])}")

# Subscribe to the Transfer events where `from` is the zero address
def log_loop(event_filter, poll_interval):
    while True:
        for event in event_filter.get_new_entries():
            handle_event(event)
        time.sleep(poll_interval)

def main():
    # Correctly format the zero address for topic filtering
    zero_address_topic = web3.to_hex(web3.to_bytes(hexstr='0x0000000000000000000000000000000000000000').rjust(32, b'\0'))
    block_filter = web3.eth.filter({'fromBlock': 'latest', 'topics': [transfer_event_signature, zero_address_topic]})
    log_loop(block_filter, 2)

if __name__ == "__main__":
    main()
