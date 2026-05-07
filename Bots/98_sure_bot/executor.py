"""Order execution via Polymarket CLOB API with slippage control and partial fill handling."""
import math
import time
import logging

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

from config import (
    CLOB_HOST, CHAIN_ID,
    OUR_PRIVATE_KEY, OUR_WALLET,
    BET_SIZE, MIN_SHARES, ORDER_TTL_SECONDS,
    SLIPPAGE_RULES, MAX_PRICE, MAX_PRICE_DIVERGENCE,
    BUFFER_RULES, MIN_ASK_DEPTH, ORDER_CHECK_INTERVAL,
)

logger = logging.getLogger("executor")

_client = None


def _get_client() -> ClobClient:
    """Lazy-init CLOB client."""
    global _client
    if _client is None:
        _client = ClobClient(
            CLOB_HOST,
            key=OUR_PRIVATE_KEY,
            chain_id=CHAIN_ID,
            signature_type=0,  # EOA wallet
            funder=OUR_WALLET,
        )
        _client.set_api_creds(_client.create_or_derive_api_creds())
    return _client


def get_clob_price(token_id: str) -> float | None:
    """
    Get the real midpoint price from the CLOB order book.
    Returns None if the request fails.
    """
    try:
        client = _get_client()
        midpoint = client.get_midpoint(token_id)
        if midpoint is not None:
            # API may return dict {'mid': '0.99'} or raw string
            if isinstance(midpoint, dict):
                midpoint = midpoint.get("mid")
            if midpoint is not None:
                return float(midpoint)
    except Exception as e:
        logger.warning("CLOB price check failed: %s", e)
    return None


def get_orderbook(token_id: str) -> dict | None:
    """
    Fetch the full order book for a token from CLOB.
    Returns dict with 'best_ask', 'best_bid', 'ask_depth_usd', 'bid_depth_usd'
    or None on failure.
    """
    try:
        client = _get_client()
        book = client.get_order_book(token_id)
        if not book:
            return None

        asks = book.asks if hasattr(book, 'asks') else []
        bids = book.bids if hasattr(book, 'bids') else []

        if not asks:
            return {"best_ask": None, "best_bid": None, "ask_depth_usd": 0, "bid_depth_usd": 0}

        best_ask = float(asks[0].price)
        ask_depth_usd = sum(float(a.price) * float(a.size) for a in asks)

        best_bid = float(bids[0].price) if bids else None
        bid_depth_usd = sum(float(b.price) * float(b.size) for b in bids) if bids else 0

        return {
            "best_ask": best_ask,
            "best_bid": best_bid,
            "ask_depth_usd": round(ask_depth_usd, 2),
            "bid_depth_usd": round(bid_depth_usd, 2),
        }
    except Exception as e:
        logger.warning("Orderbook fetch failed: %s", e)
        return None


def verify_price(token_id: str, gamma_price: float) -> tuple[bool, float | None]:
    """
    Verify that the Gamma API price matches the real CLOB price.
    Returns (ok, clob_price). ok=False means price is stale/wrong.
    If CLOB is unavailable, returns (True, None) — don't block on network errors.
    """
    clob_price = get_clob_price(token_id)
    if clob_price is None:
        return True, None  # can't verify — let it through

    divergence = abs(gamma_price - clob_price)
    if divergence > MAX_PRICE_DIVERGENCE:
        logger.warning(
            "STALE PRICE: Gamma=%.3f, CLOB=%.3f, diff=%.3f (max %.3f) — SKIPPING",
            gamma_price, clob_price, divergence, MAX_PRICE_DIVERGENCE,
        )
        return False, clob_price

    return True, clob_price


def get_limit_price(market_price: float) -> float | None:
    """
    Calculate the limit order price based on slippage rules.
    Returns the max price we're willing to pay, or None if we should skip.
    """
    if market_price > MAX_PRICE:
        return None  # ROI too small

    for low, high, slippage in SLIPPAGE_RULES:
        if low <= market_price < high:
            limit = market_price + slippage
            # Don't exceed MAX_PRICE even with slippage
            if limit > MAX_PRICE:
                limit = MAX_PRICE
            return round(limit, 3)

    # Price is outside all defined ranges
    return None


def get_limit_from_ask(best_ask: float) -> float | None:
    """
    Calculate limit price based on CLOB best_ask + small buffer.
    Uses BUFFER_RULES (smaller than SLIPPAGE_RULES since we know the real price).
    Returns limit price or None if price is outside acceptable range.
    """
    if best_ask > MAX_PRICE:
        return None  # ROI too small

    for low, high, buffer in BUFFER_RULES:
        if low <= best_ask < high:
            limit = best_ask + buffer
            if limit > MAX_PRICE:
                limit = MAX_PRICE
            return round(limit, 3)

    # Price outside all ranges
    return None


def calculate_bet_size(price: float, bet_amount: float = None) -> float | None:
    """
    Calculate how much to spend in USD.
    Uses bet_amount if provided, otherwise falls back to BET_SIZE.
    Returns None if amount can't buy MIN_SHARES (5) at this price.
    """
    amount = bet_amount if bet_amount is not None else BET_SIZE
    min_cost = MIN_SHARES * price
    if min_cost > amount:
        return None

    return round(amount, 2)


def place_limit_buy(token_id: str, limit_price: float, size_usd: float) -> dict | None:
    """
    Place a limit buy order on the CLOB.
    size_usd: how much to spend in USD.
    limit_price: max price per share.
    Returns order info dict or None on failure.
    """
    try:
        client = _get_client()

        # Calculate shares: size_usd / price
        shares = size_usd / limit_price
        shares = max(shares, float(MIN_SHARES))
        shares = math.ceil(shares * 100) / 100  # round up to 2 decimals

        order_args = OrderArgs(
            token_id=token_id,
            price=round(limit_price, 2),
            size=shares,
            side="BUY",
        )

        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)

        if response and response.get("success"):
            actual_cost = shares * limit_price
            order_id = response.get("orderID", "")
            logger.info("Order placed: %s | %.2f shares @ %.3f = $%.2f",
                        order_id[:16], shares, limit_price, actual_cost)
            return {
                "order_id": order_id,
                "price": limit_price,
                "size_shares": shares,
                "cost_usd": actual_cost,
            }
        else:
            error_msg = response.get("errorMsg", "Unknown error") if response else "No response"
            logger.warning("Order rejected: %s", error_msg)
            return None

    except Exception as e:
        logger.error("Order failed: %s", e)
        return None


def check_order_status(order_id: str) -> dict:
    """
    Check order status and fill details.
    Returns dict with 'status', 'size_matched' (filled shares), 'original_size'.
    """
    try:
        client = _get_client()
        order = client.get_order(order_id)
        if order:
            return {
                "status": order.get("status", "UNKNOWN"),
                "size_matched": float(order.get("size_matched", 0) or 0),
                "original_size": float(order.get("original_size", 0) or order.get("size", 0) or 0),
            }
    except Exception as e:
        logger.error("Status check failed for %s: %s", order_id[:16], e)
    return {"status": "UNKNOWN", "size_matched": 0, "original_size": 0}


def cancel_order(order_id: str) -> bool:
    """Cancel an open order."""
    try:
        client = _get_client()
        resp = client.cancel(order_id)
        return resp is not None
    except Exception as e:
        logger.error("Cancel failed for %s: %s", order_id[:16], e)
        return False


def wait_for_fill(order_id: str, timeout: int = ORDER_TTL_SECONDS) -> dict:
    """
    Wait for order to be filled or timeout.
    Handles partial fills: after timeout, checks how many shares were actually bought.
    Returns dict: {
        'final_status': str,  # MATCHED / PARTIAL / CANCELLED / TIMEOUT
        'filled_shares': float,
        'original_shares': float,
    }
    """
    start = time.time()
    check_interval = ORDER_CHECK_INTERVAL

    while time.time() - start < timeout:
        info = check_order_status(order_id)
        status = info["status"]

        if status == "MATCHED":
            return {
                "final_status": "MATCHED",
                "filled_shares": info["size_matched"] or info["original_size"],
                "original_shares": info["original_size"],
            }
        elif status == "CANCELLED":
            return {
                "final_status": "CANCELLED",
                "filled_shares": info["size_matched"],
                "original_shares": info["original_size"],
            }
        elif status not in ("LIVE", "UNKNOWN"):
            return {
                "final_status": status,
                "filled_shares": info["size_matched"],
                "original_shares": info["original_size"],
            }

        time.sleep(check_interval)

    # Timeout — check what was filled before cancelling
    info = check_order_status(order_id)
    filled = info["size_matched"]

    logger.info("Order %s timed out after %ds, filled %.2f / %.2f shares",
                order_id[:16], timeout, filled, info["original_size"])

    # Cancel remaining unfilled portion
    cancel_order(order_id)

    if filled > 0 and filled < info["original_size"]:
        return {
            "final_status": "PARTIAL",
            "filled_shares": filled,
            "original_shares": info["original_size"],
        }
    elif filled >= info["original_size"] and filled > 0:
        return {
            "final_status": "MATCHED",
            "filled_shares": filled,
            "original_shares": info["original_size"],
        }
    else:
        return {
            "final_status": "TIMEOUT",
            "filled_shares": 0,
            "original_shares": info["original_size"],
        }
