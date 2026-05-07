"""Order execution: buy and sell via Polymarket CLOB API."""
import math
import time
import threading
import requests
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from config import (
    CLOB_HOST, CHAIN_ID,
    OUR_PRIVATE_KEY, OUR_WALLET, MIN_SHARES, ORDER_TTL_SECONDS,
)
import safe_sell

# Exposed so tests and callers can detect the "skipped because on-chain is empty"
# case without needing to parse log strings.
SELL_SKIP_INSUFFICIENT_BALANCE = "insufficient_onchain_balance"

_client = None
_client_lock = threading.Lock()

def _get_client() -> ClobClient:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = ClobClient(
                CLOB_HOST,
                key=OUR_PRIVATE_KEY,
                chain_id=CHAIN_ID,
                signature_type=0,
                funder=OUR_WALLET,
            )
            _client.set_api_creds(_client.create_or_derive_api_creds())
    return _client


def place_limit_buy(token_id: str, price: float, size_usd: float) -> dict | None:
    """
    Place a limit BUY order.
    size_usd: how much USD to spend.
    price: limit price per share.
    Returns {order_id, price, size_shares, cost_usd} or None.
    """
    if price <= 0.0 or price >= 1.0 or size_usd <= 0.0:
        print(f"[EXECUTOR] BUY rejected: invalid args price={price} size_usd={size_usd}")
        return None
    try:
        client = _get_client()
        shares = size_usd / price
        shares = max(shares, float(MIN_SHARES))
        shares = math.ceil(shares * 100) / 100

        order_args = OrderArgs(
            token_id=token_id,
            price=round(price, 2),
            size=shares,
            side="BUY",
        )
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)

        if response and response.get("success"):
            return {
                "order_id": response.get("orderID", ""),
                "price": price,
                "size_shares": shares,
                "cost_usd": shares * price,
            }
        else:
            error_msg = response.get("errorMsg", "Unknown") if response else "No response"
            print(f"[EXECUTOR] BUY rejected: {error_msg}")
            return None
    except Exception as e:
        print(f"[EXECUTOR] BUY failed: {e}")
        return None


def place_limit_sell(token_id: str, price: float, shares: float,
                     safety_margin: float | None = None) -> dict | None:
    """
    Place a limit SELL order.
    shares: number of shares to sell (from tracker — may be rounded).
    price:  limit price per share.
    safety_margin: shares to reserve from on-chain balance (None = default).

    Before sending the order, we ALWAYS re-query the real on-chain balance
    and clamp `shares` to it. This fixes the class of bugs where the tracker
    has 59.51 but on-chain has 59.509092 → CLOB rejects for "not enough
    balance". See safe_sell.py for the full rationale.

    Returns:
        {order_id, price, size_shares, revenue_usd}         on success
        {"error": SELL_SKIP_INSUFFICIENT_BALANCE, ...}      if safe size < MIN_SHARES
        None                                                 on exception / API error
    """
    try:
        # Precision-safe clamp against real on-chain balance.
        safe_size, onchain = safe_sell.compute_safe_sell_size(
            token_id=token_id,
            requested_shares=shares,
            safety_margin=safety_margin,
        )
        if safe_size < float(MIN_SHARES):
            print(
                f"[EXECUTOR] SELL skipped: onchain={onchain} requested={shares} "
                f"safe={safe_size} < MIN_SHARES={MIN_SHARES}"
            )
            return {
                "error": SELL_SKIP_INSUFFICIENT_BALANCE,
                "requested": shares,
                "onchain": onchain,
                "safe_size": safe_size,
            }
        # Final guard: floor once more (safe_sell already flooring, but defensive).
        shares = math.floor(safe_size * 100) / 100

        client = _get_client()
        order_args = OrderArgs(
            token_id=token_id,
            price=round(price, 2),
            size=shares,
            side="SELL",
        )
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)

        if response and response.get("success"):
            return {
                "order_id": response.get("orderID", ""),
                "price": price,
                "size_shares": shares,
                "revenue_usd": shares * price,
            }
        else:
            error_msg = response.get("errorMsg", "Unknown") if response else "No response"
            print(f"[EXECUTOR] SELL rejected: {error_msg}")
            return None
    except Exception as e:
        print(f"[EXECUTOR] SELL failed: {e}")
        return None


def check_order_status(order_id: str) -> str:
    """Check order status: LIVE, MATCHED, CANCELLED, UNKNOWN."""
    try:
        client = _get_client()
        order = client.get_order(order_id)
        if order:
            return order.get("status", "UNKNOWN")
    except Exception as e:
        print(f"[EXECUTOR] Status check failed: {e}")
    return "UNKNOWN"


def get_order_details(order_id: str) -> dict:
    """Return full order info including partial fill size.

    Returns dict with keys:
        status:        LIVE/MATCHED/CANCELLED/UNKNOWN
        size_matched:  shares filled so far (float)
        size_original: original order size
        price:         limit price
        filled_pct:    size_matched / size_original
    """
    result = {
        "status": "UNKNOWN",
        "size_matched": 0.0,
        "size_original": 0.0,
        "price": 0.0,
        "filled_pct": 0.0,
    }
    try:
        client = _get_client()
        order = client.get_order(order_id)
        if not order:
            return result
        result["status"] = order.get("status", "UNKNOWN")
        # Polymarket API returns sizes as strings. Common fields:
        # size_matched, size, original_size, price
        size_matched = float(order.get("size_matched", 0) or 0)
        size_original = float(
            order.get("original_size")
            or order.get("size")
            or 0
        )
        result["size_matched"] = size_matched
        result["size_original"] = size_original
        result["price"] = float(order.get("price", 0) or 0)
        if size_original > 0:
            result["filled_pct"] = size_matched / size_original
    except Exception as e:
        print(f"[EXECUTOR] get_order_details failed: {e}")
    return result


def cancel_order(order_id: str) -> bool:
    try:
        client = _get_client()
        resp = client.cancel(order_id)
        return resp is not None
    except Exception as e:
        print(f"[EXECUTOR] Cancel failed: {e}")
        return False


def wait_for_fill(order_id: str, timeout: int = ORDER_TTL_SECONDS) -> str:
    """Wait for fill. Returns: MATCHED, CANCELLED, TIMEOUT, or 'PARTIAL'.

    On TIMEOUT, cancels the remaining portion but ALSO checks if any shares
    were partially filled before cancel. If filled_pct > 0.5% → returns
    'PARTIAL' (caller should use wait_for_fill_details() to get sizes).
    """
    start = time.time()
    while time.time() - start < timeout:
        status = check_order_status(order_id)
        if status == "MATCHED":
            return "MATCHED"
        elif status == "CANCELLED":
            return "CANCELLED"
        elif status not in ("LIVE", "UNKNOWN"):
            return status
        time.sleep(10)

    # Timeout reached — check for partial fill BEFORE cancelling
    details = get_order_details(order_id)
    size_matched = details.get("size_matched", 0)
    filled_pct = details.get("filled_pct", 0)
    print(f"[EXECUTOR] Timeout {order_id[:16]}, size_matched={size_matched:.2f}/{details.get('size_original',0):.2f} ({filled_pct*100:.1f}%), cancelling remainder")
    cancel_order(order_id)
    if filled_pct > 0.005:  # anything above 0.5% is a real partial fill
        return "PARTIAL"
    return "TIMEOUT"


def wait_for_fill_with_details(order_id: str, timeout: int = ORDER_TTL_SECONDS) -> dict:
    """Like wait_for_fill() but always returns a dict with full fill details.

    Preferred for new callers. Returns:
        {
            'status': MATCHED/PARTIAL/CANCELLED/TIMEOUT,
            'size_matched': float,
            'size_original': float,
            'price': float,
            'filled_pct': float,
        }
    """
    start = time.time()
    while time.time() - start < timeout:
        details = get_order_details(order_id)
        status = details.get("status", "UNKNOWN")
        if status == "MATCHED":
            return {**details, "status": "MATCHED"}
        elif status == "CANCELLED":
            return {**details, "status": "CANCELLED"}
        elif status not in ("LIVE", "UNKNOWN"):
            return details
        time.sleep(10)

    # Timeout — check partial
    details = get_order_details(order_id)
    filled_pct = details.get("filled_pct", 0)
    cancel_order(order_id)
    if filled_pct > 0.005:
        return {**details, "status": "PARTIAL"}
    return {**details, "status": "TIMEOUT"}


def get_actual_fill(order_id: str) -> dict | None:
    """Return VWAP of all confirmed trades for this order.

    Polymarket's get_order returns the LIMIT price, not the actual VWAP. For
    accurate cost_usd / avg_entry in tracker, callers (manual buy scripts)
    must use the trade-level price, which can be lower than limit if the
    order took offers below the limit.

    Returns dict {size, cost_usd, vwap} or None if no trades found.
    """
    try:
        from py_clob_client.clob_types import TradeParams
        from config import OUR_WALLET
        client = _get_client()
        # Query by maker_address only — `id` filter on TradeParams matches
        # trade-id, not order-id, so it returns nothing useful for us.
        tp = TradeParams(maker_address=OUR_WALLET.lower())
        trades = client.get_trades(tp) or []
        total_size = 0.0
        total_cost = 0.0
        for t in trades:
            if t.get("taker_order_id") != order_id:
                continue
            sz = float(t.get("size") or 0)
            px = float(t.get("price") or 0)
            total_size += sz
            total_cost += sz * px
        if total_size <= 0:
            return None
        return {
            "size": total_size,
            "cost_usd": total_cost,
            "vwap": total_cost / total_size,
        }
    except Exception as e:
        print(f"[EXECUTOR] get_actual_fill failed: {e}")
        return None
