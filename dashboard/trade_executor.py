"""Execute sell orders via CLOB API."""
import math
import logging

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType, BalanceAllowanceParams, AssetType

from config import CLOB_HOST, CHAIN_ID, PRIVATE_KEY, WALLET_ADDRESS

log = logging.getLogger("trade_executor")

_client = None


def _get_client() -> ClobClient:
    global _client
    if _client is None:
        if not PRIVATE_KEY or not WALLET_ADDRESS:
            raise RuntimeError("Wallet keys not configured. Check .env file.")
        _client = ClobClient(
            CLOB_HOST,
            key=PRIVATE_KEY,
            chain_id=CHAIN_ID,
            signature_type=0,
            funder=WALLET_ADDRESS,
        )
        _client.set_api_creds(_client.create_or_derive_api_creds())
    return _client


def get_token_balance(token_id: str) -> float:
    """Get real on-chain token balance (in shares) via CLOB API."""
    try:
        client = _get_client()
        params = BalanceAllowanceParams(
            asset_type=AssetType.CONDITIONAL,
            token_id=token_id,
        )
        result = client.get_balance_allowance(params)
        raw = int(result.get("balance", 0))
        return raw / 1e6
    except Exception as e:
        log.warning("Balance check failed: %s", e)
        return -1


def get_open_sell_orders(token_id: str) -> list[dict]:
    """Find existing open SELL orders for a token."""
    try:
        client = _get_client()
        orders = client.get_orders()
        return [o for o in orders
                if o.get("asset_id") == token_id
                and o.get("side") == "SELL"
                and o.get("status") == "LIVE"]
    except Exception as e:
        log.warning("Failed to check open orders: %s", e)
        return []


def cancel_open_sells(token_id: str) -> int:
    """Cancel all open SELL orders for a token. Returns count cancelled."""
    client = _get_client()
    orders = get_open_sell_orders(token_id)
    cancelled = 0
    for order in orders:
        try:
            client.cancel(order["id"])
            cancelled += 1
            log.info("Cancelled old sell order %s", order["id"][:16])
        except Exception as e:
            log.warning("Failed to cancel order %s: %s", order.get("id", "?")[:16], e)
    return cancelled


def sell_position(token_id: str, price: float, shares: float) -> dict:
    """Place a GTC limit sell order.
    Cancels any existing sell orders for this token first.
    Returns {"success": True, "order_id": ...} or {"success": False, "error": ...}.
    """
    try:
        client = _get_client()

        # Check real on-chain balance before selling
        real_balance = get_token_balance(token_id)
        if real_balance >= 0 and shares > real_balance:
            log.warning("SELL size %.2f > on-chain balance %.2f, adjusting", shares, real_balance)
            shares = real_balance
        if real_balance == 0:
            return {"success": False, "error": "На кошельке 0 шеров этого токена (позиция уже продана/redeem?)"}

        # Cancel existing sell orders for this token (prevent "not enough balance")
        cancelled = cancel_open_sells(token_id)
        if cancelled:
            log.info("Cancelled %d existing sell orders before new sell", cancelled)

        # Round shares down (can't sell more than we have)
        shares = math.floor(shares * 100) / 100
        if shares < 5:
            return {"success": False, "error": f"Мало шеров ({shares:.2f}). Минимум CLOB: 5"}

        # CLOB price limits
        price = max(0.01, min(round(price, 2), 0.99))

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=shares,
            side="SELL",
        )

        signed = client.create_order(order_args)
        response = client.post_order(signed, OrderType.GTC)

        if response and response.get("success"):
            order_id = response.get("orderID", "")
            log.info("SELL placed: %s | %.2f shares @ %.3f", order_id[:16], shares, price)
            return {"success": True, "order_id": order_id, "price": price, "shares": shares}
        else:
            error = response.get("errorMsg", "Unknown") if response else "No response"
            log.warning("SELL rejected: %s", error)
            return {"success": False, "error": error}

    except Exception as e:
        log.error("SELL failed: %s", e)
        return {"success": False, "error": str(e)}
