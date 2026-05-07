"""One-time script: approve contracts for neg_risk market trading."""
import sys
import time
from web3 import Web3
from eth_account import Account

from config import POLYGON_RPC, OUR_PRIVATE_KEY, CTF_CONTRACT, USDC_CONTRACT

w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
account = Account.from_key(OUR_PRIVATE_KEY)
wallet = account.address

# Contract addresses
NEG_RISK_ADAPTER = "0xC5d563A36AE78145C45a50134d48A1215220f80a"
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_EXCHANGE = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"

# ABIs
APPROVAL_ABI = [
    {
        "name": "setApprovalForAll",
        "type": "function",
        "inputs": [
            {"name": "operator", "type": "address"},
            {"name": "approved", "type": "bool"},
        ],
        "outputs": [],
    },
    {
        "name": "isApprovedForAll",
        "type": "function",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "operator", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

ERC20_APPROVE_ABI = [
    {
        "name": "approve",
        "type": "function",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "allowance",
        "type": "function",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

MAX_UINT256 = 2**256 - 1


def send_tx(tx):
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"  Tx sent: {tx_hash.hex()}")
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] == 1:
        print(f"  Success!")
    else:
        print(f"  REVERTED!")
        sys.exit(1)
    return receipt


def main():
    print(f"Wallet: {wallet}")
    gas_price = int(w3.eth.gas_price * 1.3)
    print(f"Gas price: {gas_price / 1e9:.1f} gwei")

    ctf = w3.eth.contract(
        address=Web3.to_checksum_address(CTF_CONTRACT), abi=APPROVAL_ABI,
    )
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_CONTRACT), abi=ERC20_APPROVE_ABI,
    )

    nonce = w3.eth.get_transaction_count(wallet, "pending")

    # 1. CTF setApprovalForAll -> NegRiskAdapter
    print("\n1. CTF -> NegRiskAdapter approval...")
    approved = ctf.functions.isApprovedForAll(wallet, Web3.to_checksum_address(NEG_RISK_ADAPTER)).call()
    if approved:
        print("  Already approved, skipping.")
    else:
        tx = ctf.functions.setApprovalForAll(
            Web3.to_checksum_address(NEG_RISK_ADAPTER), True
        ).build_transaction({
            "from": wallet, "nonce": nonce, "gas": 100000, "gasPrice": gas_price,
        })
        send_tx(tx)
        nonce += 1
        time.sleep(3)

    # 2. CTF setApprovalForAll -> CTF Exchange
    print("\n2. CTF -> CTF Exchange approval...")
    approved = ctf.functions.isApprovedForAll(wallet, Web3.to_checksum_address(CTF_EXCHANGE)).call()
    if approved:
        print("  Already approved, skipping.")
    else:
        tx = ctf.functions.setApprovalForAll(
            Web3.to_checksum_address(CTF_EXCHANGE), True
        ).build_transaction({
            "from": wallet, "nonce": nonce, "gas": 100000, "gasPrice": gas_price,
        })
        send_tx(tx)
        nonce += 1
        time.sleep(3)

    # 3. USDC approve -> NegRiskExchange
    print("\n3. USDC -> NegRiskExchange approval...")
    allowance = usdc.functions.allowance(wallet, Web3.to_checksum_address(NEG_RISK_EXCHANGE)).call()
    if allowance > 10**12:  # > 1M USDC
        print(f"  Already approved (allowance: {allowance / 1e6:.0f} USDC), skipping.")
    else:
        tx = usdc.functions.approve(
            Web3.to_checksum_address(NEG_RISK_EXCHANGE), MAX_UINT256
        ).build_transaction({
            "from": wallet, "nonce": nonce, "gas": 100000, "gasPrice": gas_price,
        })
        send_tx(tx)
        nonce += 1

    print("\nAll approvals done! neg_risk trading is ready.")


if __name__ == "__main__":
    main()
