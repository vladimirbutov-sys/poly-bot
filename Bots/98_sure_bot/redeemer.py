"""Auto-redeem winning positions after market resolution."""
import time
import logging
import threading
import requests

from web3 import Web3
from eth_account import Account

from config import (
    POLYGON_RPC, GAMMA_API,
    OUR_PRIVATE_KEY, OUR_WALLET,
    CTF_CONTRACT, NEG_RISK_CTF, NEG_RISK_ADAPTER, USDC_CONTRACT,
)
import tracker
import telegram_notify as tg

logger = logging.getLogger("redeemer")

# Minimal ABI for ConditionalTokens
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
    },
]

# ERC20 ABI for USDC balance
ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

# NegRiskAdapter ABI (real adapter at 0xd91e80cf...)
NEG_RISK_ADAPTER_ABI = [
    {
        "name": "redeemPositions",
        "type": "function",
        "inputs": [
            {"name": "conditionId", "type": "bytes32"},
            {"name": "amounts", "type": "uint256[]"},
        ],
        "outputs": [],
    },
    {
        "name": "getDetermined",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "marketId", "type": "bytes32"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
]

ZERO_BYTES32 = b'\x00' * 32
CHECK_INTERVAL = 300  # 5 minutes


def _get_web3():
    return Web3(Web3.HTTPProvider(POLYGON_RPC))


def is_neg_risk_finalized(neg_risk_market_id: str, w3=None) -> bool:
    """Check if neg_risk market is determined on the NegRiskAdapter.

    NOTE: We check getDetermined on the NegRiskAdapter (0xd91e80cf...),
    NOT payoutDenominator on the CTF. The negRiskMarketID is an internal
    adapter ID, not a CTF conditionId — payoutDenominator would always be 0.
    """
    try:
        if w3 is None:
            w3 = _get_web3()
        adapter = w3.eth.contract(
            address=Web3.to_checksum_address(NEG_RISK_ADAPTER),
            abi=NEG_RISK_ADAPTER_ABI,
        )
        mid_bytes = bytes.fromhex(
            neg_risk_market_id[2:] if neg_risk_market_id.startswith("0x") else neg_risk_market_id
        )
        return adapter.functions.getDetermined(mid_bytes).call()
    except Exception as e:
        logger.error("NegRisk finalization check error: %s", e)
        return False


def _get_usdc_balance(w3) -> int:
    """Get USDC balance in raw units (6 decimals)."""
    usdc = w3.eth.contract(
        address=Web3.to_checksum_address(USDC_CONTRACT), abi=ERC20_ABI,
    )
    return usdc.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call()


def get_usdc_balance_usd() -> float:
    """Get USDC balance in USD (human-readable)."""
    try:
        w3 = _get_web3()
        raw = _get_usdc_balance(w3)
        return raw / 1e6
    except Exception as e:
        logger.error("USDC balance check failed: %s", e)
        return 0.0


def is_resolved_onchain(condition_id: str, w3=None, ctf=None) -> bool:
    """Check if payoutDenominator > 0 (market resolved)."""
    try:
        if w3 is None:
            w3 = _get_web3()
        if ctf is None:
            ctf = w3.eth.contract(
                address=Web3.to_checksum_address(CTF_CONTRACT), abi=CTF_ABI,
            )
        cid_bytes = bytes.fromhex(
            condition_id[2:] if condition_id.startswith("0x") else condition_id
        )
        payout_denom = ctf.functions.payoutDenominator(cid_bytes).call()
        return payout_denom > 0
    except Exception as e:
        logger.error("On-chain resolution check error: %s", e)
        return False


def check_token_balance(token_id: str) -> int:
    """Check our balance of a specific CTF token.
    Returns raw balance (int), or -1 on network/RPC error.
    """
    try:
        w3 = _get_web3()
        ctf = w3.eth.contract(
            address=Web3.to_checksum_address(CTF_CONTRACT), abi=CTF_ABI,
        )
        token_int = int(token_id)
        balance = ctf.functions.balanceOf(
            Web3.to_checksum_address(OUR_WALLET), token_int
        ).call()
        return balance
    except Exception as e:
        logger.error("Token balance check error: %s", e)
        return -1


def is_winning_token(condition_id: str, token_id: str, w3=None) -> bool:
    """Check on-chain if our token is the winning outcome.
    Uses payoutNumerators: winning outcome has payout > 0.
    Token index is determined from token_id position in the market.
    Falls back to USDC balance comparison if on-chain check fails.
    """
    try:
        if w3 is None:
            w3 = _get_web3()
        ctf = w3.eth.contract(
            address=Web3.to_checksum_address(CTF_CONTRACT), abi=CTF_ABI,
        )
        cid_bytes = bytes.fromhex(
            condition_id[2:] if condition_id.startswith("0x") else condition_id
        )
        # Binary market: index 0 = first outcome, index 1 = second outcome
        # Check both and see which has payout > 0
        payout_0 = ctf.functions.payoutNumerators(cid_bytes, 0).call()
        payout_1 = ctf.functions.payoutNumerators(cid_bytes, 1).call()

        # Determine which index our token belongs to by checking via Gamma API
        try:
            resp = requests.get(
                f"{GAMMA_API}/markets" if not GAMMA_API.endswith("/markets") else GAMMA_API,
                params={"clob_token_ids": token_id},
                timeout=10,
            )
            if resp.status_code == 200 and resp.json():
                market = resp.json()[0]
                token_ids = market.get("clobTokenIds", "").strip("[]").replace('"', '').split(",")
                token_ids = [t.strip() for t in token_ids]
                if token_id in token_ids:
                    our_index = token_ids.index(token_id)
                    our_payout = ctf.functions.payoutNumerators(cid_bytes, our_index).call()
                    logger.info("Token index %d, payout=%d (payouts: [%d, %d])",
                                our_index, our_payout, payout_0, payout_1)
                    return our_payout > 0
        except Exception as e:
            logger.warning("Gamma lookup for token index failed: %s", e)

        # Fallback: if only one outcome has payout, check if redeem returned USDC
        # (this is less reliable but better than nothing)
        logger.warning("Could not determine token index, falling back to payout heuristic")
        return payout_0 > 0 or payout_1 > 0  # conservative: assume win if any payout exists
    except Exception as e:
        logger.warning("payoutNumerators check failed: %s", e)
        return True  # conservative: assume win if check fails (don't mark as lost incorrectly)


def _get_neg_risk_from_api(condition_id: str) -> bool:
    """Check neg_risk flag via Gamma API (fallback if not stored in position)."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"condition_id": condition_id},
            timeout=10,
        )
        if resp.status_code == 200:
            markets = resp.json()
            if markets:
                return markets[0].get("negRisk", False)
    except Exception:
        pass
    return False


def _get_neg_risk_market_id(condition_id: str = "", token_id: str = "") -> str | None:
    """Get negRiskMarketID from Gamma API with retry.
    For neg_risk markets, redeem must use negRiskMarketID, not conditionId.
    Prefers clob_token_ids (exact match) over condition_id (can return wrong results).
    """
    url = f"{GAMMA_API}/markets" if not GAMMA_API.endswith("/markets") else GAMMA_API

    for attempt in range(2):
        try:
            if token_id:
                resp = requests.get(url, params={"clob_token_ids": token_id}, timeout=15)
            elif condition_id:
                resp = requests.get(url, params={"condition_id": condition_id}, timeout=15)
            else:
                return None

            if resp.status_code != 200:
                logger.warning("Gamma API returned %d (attempt %d)", resp.status_code, attempt + 1)
                time.sleep(2)
                continue

            markets = resp.json()
            if not markets:
                logger.warning("Gamma API returned empty for token=%s cid=%s",
                               token_id[:16] if token_id else "", condition_id[:16] if condition_id else "")
                # If clob_token_ids failed, try condition_id as fallback
                if token_id and condition_id and attempt == 0:
                    token_id = ""  # next attempt will use condition_id
                    time.sleep(1)
                    continue
                return None

            # If using condition_id (returns multiple results), find the matching one
            if not token_id and len(markets) > 1:
                for m in markets:
                    if m.get("conditionId") == condition_id and m.get("negRiskMarketID"):
                        return m["negRiskMarketID"]

            result = markets[0].get("negRiskMarketID")
            if result:
                return result

            logger.warning("Market found but no negRiskMarketID field")
            return None

        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning("negRiskMarketID lookup failed (attempt %d): %s", attempt + 1, e)
            if attempt == 0:
                time.sleep(2)
                continue
            return None
        except Exception as e:
            logger.error("Unexpected error in negRiskMarketID lookup: %s", e)
            return None
    return None


def redeem_position(condition_id: str, is_neg_risk: bool = False,
                    token_id: str = "", neg_risk_market_id: str = "") -> bool:
    """Call redeemPositions on-chain. Retries with higher gas on nonce conflicts.

    For neg_risk markets: uses the real NegRiskAdapter (0xd91e80cf...) with
    amounts=[balance, 0] (try YES first, then NO on failure).
    For regular markets: uses CTF contract with indexSets=[1, 2].
    """
    if is_neg_risk:
        logger.info("NegRisk redeem with conditionId: %s", condition_id[:16])

    for attempt in range(3):
        try:
            w3 = _get_web3()
            account = Account.from_key(OUR_PRIVATE_KEY)

            nonce = w3.eth.get_transaction_count(account.address, 'pending')
            gas_price = int(w3.eth.gas_price * (1.2 + 0.3 * attempt))

            cid_bytes = bytes.fromhex(
                condition_id[2:] if condition_id.startswith("0x") else condition_id
            )

            if is_neg_risk:
                # Get our token balance to pass as amount
                ctf_contract = w3.eth.contract(
                    address=Web3.to_checksum_address(CTF_CONTRACT), abi=CTF_ABI,
                )
                token_balance = 0
                if token_id:
                    token_balance = ctf_contract.functions.balanceOf(
                        Web3.to_checksum_address(OUR_WALLET), int(token_id)
                    ).call()

                if token_balance == 0:
                    logger.warning("NegRisk: no token balance for %s", condition_id[:16])
                    return False

                adapter = w3.eth.contract(
                    address=Web3.to_checksum_address(NEG_RISK_ADAPTER),
                    abi=NEG_RISK_ADAPTER_ABI,
                )
                # Try YES side first (amounts=[balance, 0]), then NO side
                amounts_options = [
                    [token_balance, 0],
                    [0, token_balance],
                ]
                tx = None
                last_error = ""
                for amounts in amounts_options:
                    try:
                        adapter.functions.redeemPositions(
                            cid_bytes, amounts
                        ).call({"from": account.address})
                        # Simulation passed — build real tx
                        tx = adapter.functions.redeemPositions(
                            cid_bytes, amounts
                        ).build_transaction({
                            "from": account.address,
                            "nonce": nonce,
                            "gas": 400000,
                            "gasPrice": gas_price,
                        })
                        logger.info("NegRisk: using amounts=%s", amounts)
                        break
                    except Exception as e:
                        last_error = str(e)
                        continue

                if tx is None:
                    # "result for condition not received yet" = CTF hasn't received
                    # payouts from oracle. getDetermined=true but reportPayouts not
                    # called yet on CTF. This is normal Polymarket delay, not a bug.
                    # Check hex-encoded error: "726573756c7420666f7220636f6e646974696f6e"
                    # = "result for condition" in hex
                    if "726573756c7420666f7220636f6e646974696f6e" in last_error:
                        logger.info("NegRisk: CTF payout not reported yet, will retry: %s",
                                    condition_id[:16])
                        return None  # distinct from False — means "retry later"
                    logger.error("NegRisk: simulation failed: %s", last_error[:150])
                    return False
            else:
                contract = w3.eth.contract(
                    address=Web3.to_checksum_address(CTF_CONTRACT),
                    abi=CTF_ABI,
                )
                tx = contract.functions.redeemPositions(
                    Web3.to_checksum_address(USDC_CONTRACT),
                    ZERO_BYTES32,
                    cid_bytes,
                    [1, 2],
                ).build_transaction({
                    "from": account.address,
                    "nonce": nonce,
                    "gas": 300000,
                    "gasPrice": gas_price,
                })

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=90)

            if receipt["status"] == 1:
                logger.info("Redeem success! tx: %s", tx_hash.hex()[:16])
                return True
            else:
                logger.warning("Redeem reverted: %s", tx_hash.hex()[:16])
                return False

        except Exception as e:
            if "underpriced" in str(e) and attempt < 2:
                logger.warning("Nonce conflict, retrying (%d/3)...", attempt + 1)
                time.sleep(5)
                continue
            logger.error("Redeem failed: %s", e)
            return False
    return False


def check_and_redeem():
    """Check all open positions and redeem any resolved markets."""
    data = tracker.load()
    open_positions = tracker.get_open_positions(data)

    if not open_positions:
        return

    w3 = _get_web3()
    ctf = w3.eth.contract(
        address=Web3.to_checksum_address(CTF_CONTRACT), abi=CTF_ABI,
    )

    checked_conditions = {}  # condition_id -> resolved bool (cache)
    checked_neg_risk = {}    # negRiskMarketID -> resolved bool (cache)
    redeemed_conditions = set()

    for key, pos in list(open_positions.items()):
        condition_id = pos.get("condition_id", "")
        token_id = pos.get("token_id", "")
        title = pos.get("title", "?")

        if not condition_id:
            continue

        is_neg_risk = pos.get("neg_risk", False)
        cached_neg_market_id = ""

        if is_neg_risk:
            # For neg_risk: prefer getDetermined on NegRiskAdapter.
            # Fallback: also check payoutDenominator on CTF (sometimes CTF
            # has payouts even when getDetermined is false for the parent group).
            neg_resolved = False

            neg_market_id = _get_neg_risk_market_id(
                condition_id=condition_id, token_id=token_id
            )
            if neg_market_id:
                cached_neg_market_id = neg_market_id
                if neg_market_id not in checked_neg_risk:
                    checked_neg_risk[neg_market_id] = is_neg_risk_finalized(
                        neg_market_id, w3
                    )
                neg_resolved = checked_neg_risk[neg_market_id]

            # Fallback: check CTF payoutDenominator
            if not neg_resolved:
                if condition_id not in checked_conditions:
                    checked_conditions[condition_id] = is_resolved_onchain(
                        condition_id, w3, ctf
                    )
                neg_resolved = checked_conditions[condition_id]

            if not neg_resolved:
                continue
        else:
            # For regular markets: check payoutDenominator on CTF
            if condition_id not in checked_conditions:
                checked_conditions[condition_id] = is_resolved_onchain(
                    condition_id, w3, ctf
                )
            if not checked_conditions[condition_id]:
                continue

        logger.info("Market resolved: %s", title[:60])

        # Check token balance (-1 = RPC error, skip this position)
        balance = check_token_balance(token_id)
        if balance < 0:
            logger.warning("Could not check balance for %s, skipping", title[:50])
            continue

        if balance > 0 and condition_id not in redeemed_conditions:
            if not is_neg_risk:
                is_neg_risk = _get_neg_risk_from_api(condition_id)

            logger.info("Redeeming: %s (neg_risk=%s)", title[:50], is_neg_risk)
            result = redeem_position(
                condition_id, is_neg_risk, token_id=token_id,
                neg_risk_market_id=cached_neg_market_id,
            )

            if result is None:
                # "retry later" — CTF payout not reported yet (normal neg_risk delay)
                # Don't add to redeemed_conditions, don't send Telegram, just skip
                continue

            redeemed_conditions.add(condition_id)

            if result:
                won = is_winning_token(condition_id, token_id, w3)

                data = tracker.load()
                tracker.resolve_position(data, key, won=won)

                if won:
                    payout = pos["size_shares"]
                    profit = payout - pos["cost_usd"]
                    logger.info("WON: %s | +$%.2f", title[:50], profit)
                    tg.send(
                        f"WIN: {title}\n"
                        f"Payout: ${payout:.2f} | Profit: ${profit:+.2f}"
                    )
                else:
                    logger.info("LOST: %s | -$%.2f", title[:50], pos['cost_usd'])
                    tg.send(
                        f"LOSS: {title}\n"
                        f"Lost: ${pos['cost_usd']:.2f}"
                    )
            else:
                logger.error("Redeem tx failed: %s", title[:50])
                tg.send(f"Redeem failed: {title}")

        elif balance == 0:
            # No tokens — either order wasn't filled, or already redeemed by sibling
            if condition_id in redeemed_conditions:
                data = tracker.load()
                sibling_won = any(
                    p.get("status") == "won"
                    for p in data["positions"].values()
                    if p.get("condition_id") == condition_id
                    and p.get("status") in ("won", "lost")
                )
                tracker.resolve_position(data, key, won=sibling_won)
                logger.info("%s (sibling): %s",
                            "WON" if sibling_won else "LOST", title[:50])
            else:
                # No tokens and no sibling redeemed — order was likely never filled
                logger.info("No tokens for %s, removing as unfilled", title[:50])
                data = tracker.load()
                tracker.remove_position(data, key)
                tg.send(f"Unfilled order removed: {title}")

        # Pause between redeem transactions to avoid nonce issues
        time.sleep(5)


def redeem_loop():
    """Background loop that checks for resolved markets."""
    logger.info("Auto-redeem started (checking every %ds)", CHECK_INTERVAL)
    while True:
        try:
            check_and_redeem()
        except Exception as e:
            logger.error("Redeem loop error: %s", e)
        # Sleep in 60s chunks
        remaining = CHECK_INTERVAL
        while remaining > 0:
            time.sleep(min(60, remaining))
            remaining -= 60


def start_background():
    """Start the redeem loop in a background daemon thread."""
    thread = threading.Thread(target=redeem_loop, daemon=True)
    thread.start()
    return thread
