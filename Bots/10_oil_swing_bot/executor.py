"""Order execution: buy and sell via Polymarket CLOB API."""
import math
import time
import requests
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from config import (
    CLOB_HOST, CHAIN_ID,
    OUR_PRIVATE_KEY, OUR_WALLET, MIN_SHARES, ORDER_TTL_SECONDS,
)

_client = None


def _get_client() -> ClobClient:
    global _client
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


def get_orderbook_prices(token_id: str) -> tuple | None:
    """Get (best_bid, best_ask) from CLOB orderbook."""
    try:
        resp = requests.get(
            f"{CLOB_HOST}/book",
            params={"token_id": token_id},
            timeout=10,
        )
        if resp.status_code == 200:
            book = resp.json()
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            best_bid = max(float(b["price"]) for b in bids) if bids else 0.0
            best_ask = min(float(a["price"]) for a in asks) if asks else 1.0
            return best_bid, best_ask
    except Exception as e:
        print(f"[EXECUTOR] Orderbook error: {e}")
    return None


def place_limit_buy(token_id: str, price: float, size_usd: float) -> dict | None:
    """Place a limit BUY order. Returns {order_id, price, size_shares, cost_usd} or None."""
    try:
        client = _get_client()
        shares = size_usd / price
        shares = max(shares, float(MIN_SHARES))
        shares = math.ceil(shares * 100) / 100

        order_args = OrderArgs(
            token_id=token_id,
            price=round(price, 3),
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
            print(f"[EXECUTOR] BUY rejected: {error_msg} | full: {response}")
            return None
    except Exception as e:
        print(f"[EXECUTOR] BUY failed: {type(e).__name__}: {e}")
        return None


def place_limit_sell(token_id: str, price: float, shares: float) -> dict | None:
    """Place a limit SELL order. Returns {order_id, price, size_shares, revenue_usd} or None."""
    try:
        client = _get_client()
        shares = max(shares, float(MIN_SHARES))
        shares = math.floor(shares * 100) / 100

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


def cancel_order(order_id: str) -> bool:
    try:
        client = _get_client()
        resp = client.cancel(order_id)
        return resp is not None
    except Exception as e:
        print(f"[EXECUTOR] Cancel failed: {e}")
        return False


def wait_for_fill(order_id: str, timeout: int = ORDER_TTL_SECONDS) -> str:
    """Wait for fill. Returns: MATCHED, CANCELLED, TIMEOUT."""
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

    print(f"[EXECUTOR] Timeout {order_id[:16]}, cancelling")
    cancel_order(order_id)
    return "TIMEOUT"
