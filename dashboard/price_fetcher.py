"""Fetch current prices from Gamma API with caching + on-chain USDC balance."""
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from config import GAMMA_API, WALLET_ADDRESS, USDC_CONTRACT, USDC_NATIVE_CONTRACT, POLYGON_RPC

log = logging.getLogger("price_fetcher")

# Cache: {token_id: (price, timestamp)}
_cache: dict[str, tuple[float | None, float]] = {}
CACHE_TTL = 120  # 2 minutes


def _fetch_one(token_id: str) -> tuple[str, float | None]:
    """Fetch current price for a single token_id."""
    # Check cache first
    cached = _cache.get(token_id)
    if cached and (time.time() - cached[1]) < CACHE_TTL:
        return token_id, cached[0]

    try:
        resp = requests.get(
            GAMMA_API,
            params={"clob_token_ids": token_id, "limit": 1},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            if data and len(data) > 0:
                market = data[0]
                tokens_str = market.get("clobTokenIds", "") or ""
                prices_str = market.get("outcomePrices", "") or ""
                if tokens_str and prices_str:
                    tokens = json.loads(tokens_str) if isinstance(tokens_str, str) else tokens_str
                    prices = json.loads(prices_str) if isinstance(prices_str, str) else prices_str
                    for t, p in zip(tokens, prices):
                        if t == token_id:
                            price = float(p)
                            _cache[token_id] = (price, time.time())
                            return token_id, price
    except Exception as e:
        log.debug("Price fetch error for %s: %s", token_id[:16], e)

    _cache[token_id] = (None, time.time())
    return token_id, None


def fetch_prices(token_ids: list[str], on_progress=None) -> dict[str, float | None]:
    """Fetch prices for multiple tokens in parallel.
    on_progress(done, total) called after each fetch.
    Returns {token_id: price_or_None}.
    """
    if not token_ids:
        return {}

    results = {}
    done = 0
    total = len(token_ids)

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_fetch_one, tid): tid for tid in token_ids}
        for future in as_completed(futures):
            tid, price = future.result()
            results[tid] = price
            done += 1
            if on_progress:
                on_progress(done, total)

    return results


def get_cached_price(token_id: str) -> float | None:
    """Get price from cache only (no API call)."""
    cached = _cache.get(token_id)
    if cached and (time.time() - cached[1]) < CACHE_TTL:
        return cached[0]
    return None


def clear_cache():
    """Clear all cached prices."""
    _cache.clear()


# ── On-chain USDC balance ──
_usdc_cache: tuple[float | None, float] = (None, 0)
USDC_CACHE_TTL = 300  # 5 minutes


def fetch_usdc_balance() -> float | None:
    """Fetch total USDC balance from Polygon (USDC.e + native USDC).
    Both have 6 decimals.
    """
    global _usdc_cache
    if _usdc_cache[0] is not None and (time.time() - _usdc_cache[1]) < USDC_CACHE_TTL:
        return _usdc_cache[0]

    if not WALLET_ADDRESS:
        return None

    try:
        # ERC-20 balanceOf(address) selector = 0x70a08231
        addr_padded = WALLET_ADDRESS.lower().replace("0x", "").zfill(64)
        call_data = "0x70a08231" + addr_padded

        total = 0.0

        # Check both USDC contracts
        for contract in [USDC_CONTRACT, USDC_NATIVE_CONTRACT]:
            try:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_call",
                    "params": [{"to": contract, "data": call_data}, "latest"],
                    "id": 1,
                }
                resp = requests.post(POLYGON_RPC, json=payload, timeout=10)
                if resp.ok:
                    result = resp.json().get("result", "0x0")
                    raw = int(result, 16)
                    total += raw / 1e6
            except Exception:
                pass

        _usdc_cache = (total, time.time())
        return total
    except Exception as e:
        log.warning("USDC balance fetch error: %s", e)

    return _usdc_cache[0]  # return stale if available
