"""Auto-redeem winning positions after market resolution.
Copied and adapted from tricky_bot."""
import time
import requests
import threading
from web3 import Web3
from eth_account import Account
from config import (
    POLYGON_RPC, GAMMA_API, OUR_PRIVATE_KEY, OUR_WALLET,
    CTF_CONTRACT, NEG_RISK_CTF, USDC_CONTRACT, REDEEM_CHECK_INTERVAL,
)
import tracker
import telegram_notify as tg

CTF_ABI = [
    {
        "name": "redeemPositions",
        "type": "function",
        "inputs": [
            {"name": "collateralToken", "type": "address"},
            {"name": "parentCollectionId", "type": "bytes32"},
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "outputs": [],
    },
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "id", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "payoutDenominator",
        "type": "function",
        "inputs": [{"name": "conditionId", "type": "bytes32"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "payoutNumerators",
        "type": "function",
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "index", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
    },
]

ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

NEG_RISK_ABI = [
    {
        "name": "redeemPositions",
        "type": "function",
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "indexSets", "type": "uint256[]"},
        ],
        "outputs": [],
    },
]

ZERO_BYTES32 = b'\x00' * 32


def _get_web3():
    return Web3(Web3.HTTPProvider(POLYGON_RPC))


def _is_resolved_onchain(condition_id, w3=None, ctf=None):
    try:
        if w3 is None:
            w3 = _get_web3()
        if ctf is None:
            ctf = w3.eth.contract(address=Web3.to_checksum_address(CTF_CONTRACT), abi=CTF_ABI)
        cid_bytes = bytes.fromhex(condition_id[2:] if condition_id.startswith("0x") else condition_id)
        return ctf.functions.payoutDenominator(cid_bytes).call() > 0
    except Exception as e:
        print(f"[REDEEM] On-chain check error: {e}")
        return False


def _get_neg_risk(condition_id):
    try:
        resp = requests.get(f"{GAMMA_API}/markets", params={"condition_id": condition_id}, timeout=10)
        if resp.status_code == 200:
            markets = resp.json()
            if markets:
                return markets[0].get("negRisk", False)
    except Exception:
        pass
    return False


def _get_neg_risk_market_id(condition_id="", token_id=""):
    """Get negRiskMarketID from Gamma API for neg_risk redeem."""
    url = f"{GAMMA_API}/markets" if not GAMMA_API.endswith("/markets") else GAMMA_API
    try:
        if token_id:
            resp = requests.get(url, params={"clob_token_ids": token_id}, timeout=10)
        else:
            resp = requests.get(url, params={"condition_id": condition_id}, timeout=10)
        if resp.status_code == 200:
            markets = resp.json()
            if markets:
                return markets[0].get("negRiskMarketID")
    except Exception as e:
        print(f"[REDEEM] Failed to get negRiskMarketID: {e}")
    return None


def _get_usdc_balance(w3):
    usdc = w3.eth.contract(address=Web3.to_checksum_address(USDC_CONTRACT), abi=ERC20_ABI)
    return usdc.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call()


def _check_token_balance(token_id, w3=None, ctf=None):
    try:
        if w3 is None:
            w3 = _get_web3()
        if ctf is None:
            ctf = w3.eth.contract(address=Web3.to_checksum_address(CTF_CONTRACT), abi=CTF_ABI)
        return ctf.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET), int(token_id)).call()
    except Exception:
        return 0


def _outcome_has_payout(condition_id, outcome, w3, ctf):
    """Check if our outcome (Yes/No) has non-zero payout after resolution.

    Returns True  → tokens are worth something, proceed with redeem.
    Returns False → tokens are worthless, skip the blockchain tx.
    Returns None  → couldn't determine (caller should proceed to be safe).

    In Polymarket's CTF binary markets:
      index 0 = YES (indexSet 1 = binary 01)
      index 1 = NO  (indexSet 2 = binary 10)
    """
    try:
        outcome_idx = 0 if str(outcome).lower() in ("yes", "1") else 1
        cid_bytes = bytes.fromhex(
            condition_id[2:] if condition_id.startswith("0x") else condition_id
        )
        payout_num = ctf.functions.payoutNumerators(cid_bytes, outcome_idx).call()
        return payout_num > 0
    except Exception as e:
        print(f"[REDEEM] payout check failed ({e}), proceeding with redeem")
        return None  # unknown — let caller decide


def redeem_position(condition_id, is_neg_risk=False, token_id=""):
    # For neg_risk: use negRiskMarketID instead of conditionId
    redeem_cid = condition_id
    if is_neg_risk:
        neg_market_id = _get_neg_risk_market_id(condition_id, token_id)
        if neg_market_id:
            print(f"[REDEEM] Using negRiskMarketID: {neg_market_id[:16]}")
            redeem_cid = neg_market_id
        else:
            print("[REDEEM] WARNING: could not get negRiskMarketID")

    for attempt in range(3):
        try:
            w3 = _get_web3()
            account = Account.from_key(OUR_PRIVATE_KEY)
            nonce = w3.eth.get_transaction_count(account.address, 'pending')
            gas_price = int(w3.eth.gas_price * (1.2 + 0.3 * attempt))
            cid_bytes = bytes.fromhex(redeem_cid[2:] if redeem_cid.startswith("0x") else redeem_cid)
            index_sets = [1, 2]

            if is_neg_risk:
                contract = w3.eth.contract(address=Web3.to_checksum_address(NEG_RISK_CTF), abi=NEG_RISK_ABI)
                tx = contract.functions.redeemPositions(cid_bytes, index_sets).build_transaction({
                    "from": account.address, "nonce": nonce, "gas": 300000, "gasPrice": gas_price,
                })
            else:
                contract = w3.eth.contract(address=Web3.to_checksum_address(CTF_CONTRACT), abi=CTF_ABI)
                tx = contract.functions.redeemPositions(
                    Web3.to_checksum_address(USDC_CONTRACT), ZERO_BYTES32, cid_bytes, index_sets,
                ).build_transaction({
                    "from": account.address, "nonce": nonce, "gas": 300000, "gasPrice": gas_price,
                })

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)

            if receipt["status"] == 1:
                print(f"[REDEEM] Success: {tx_hash.hex()[:16]}...")
                return True
            else:
                print(f"[REDEEM] Reverted: {tx_hash.hex()[:16]}...")
                return False
        except Exception as e:
            if "underpriced" in str(e) and attempt < 2:
                time.sleep(5)
                continue
            print(f"[REDEEM] Failed: {e}")
            return False
    return False


def check_and_redeem():
    data = tracker.load()
    open_positions = tracker.get_open_positions(data)
    if not open_positions:
        return

    w3 = _get_web3()
    ctf = w3.eth.contract(address=Web3.to_checksum_address(CTF_CONTRACT), abi=CTF_ABI)
    checked = {}
    checked_neg = {}
    redeemed = set()

    for key, pos in list(open_positions.items()):
        condition_id = pos.get("condition_id", "")
        token_id = pos.get("token_id", "")
        title = pos.get("title", "?")

        if condition_id not in checked:
            checked[condition_id] = _is_resolved_onchain(condition_id, w3, ctf)

        if not checked[condition_id]:
            continue

        # For neg_risk: check NegRiskAdapter finalization
        is_neg_risk = pos.get("neg_risk", False)
        if is_neg_risk:
            neg_market_id = _get_neg_risk_market_id(token_id=token_id)
            if neg_market_id:
                if neg_market_id not in checked_neg:
                    checked_neg[neg_market_id] = _is_resolved_onchain(neg_market_id, w3, ctf)
                if not checked_neg[neg_market_id]:
                    continue
            else:
                continue

        print(f"[REDEEM] Resolved: {title[:50]}")
        balance = _check_token_balance(token_id, w3, ctf)

        if balance > 0 and condition_id not in redeemed:
            # Check if our tokens have any payout value before sending a tx.
            # For neg_risk markets we skip this check (complex outcome structure).
            if not is_neg_risk:
                has_payout = _outcome_has_payout(condition_id, pos.get("outcome", "Yes"), w3, ctf)
                if has_payout is False:
                    # Tokens exist but worth $0 — close silently, no tx, no Telegram
                    print(f"[REDEEM] Zero payout (outcome={pos.get('outcome')}), closing silently: {title[:50]}")
                    data = tracker.load()
                    tracker.resolve_position(data, key, won=False)
                    time.sleep(1)
                    continue

            if not is_neg_risk:
                is_neg_risk = _get_neg_risk(condition_id)
            usdc_before = _get_usdc_balance(w3)
            success = redeem_position(condition_id, is_neg_risk, token_id=token_id)
            redeemed.add(condition_id)

            if success:
                usdc_after = _get_usdc_balance(w3)
                gained = usdc_after - usdc_before
                won = gained > 0
                data = tracker.load()
                tracker.resolve_position(data, key, won=won)
                if won:
                    pnl = pos["size_shares"] - pos["cost_usd"]
                    tg.win(title, pnl)
                elif gained == 0:
                    # Redeem succeeded but got 0 USDC — expired worthless
                    # (neg_risk or payout check unavailable). Silent close.
                    print(f"[REDEEM] Expired worthless (0 payout): {title[:50]}")
                else:
                    tg.loss(title, pos["cost_usd"])
        elif balance == 0:
            data = tracker.load()
            tracker.resolve_position(data, key, won=False)

        time.sleep(15)  # wait for tx confirmation before next redeem (avoids nonce collisions)


def redeem_loop():
    print(f"[REDEEM] Started (every {REDEEM_CHECK_INTERVAL}s)")
    while True:
        try:
            check_and_redeem()
        except Exception as e:
            print(f"[REDEEM] Error: {e}")
        time.sleep(REDEEM_CHECK_INTERVAL)


def start_background():
    thread = threading.Thread(target=redeem_loop, daemon=True)
    thread.start()
    return thread
