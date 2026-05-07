"""WTI crude oil price monitor using Yahoo Finance."""
import time
import yfinance as yf
from datetime import datetime, timezone


_cache = {"price": None, "time": 0}
CACHE_TTL = 30  # refresh every 30 seconds max


def get_wti_price() -> float | None:
    """Get current WTI crude oil price. Returns price or None on error."""
    now = time.time()
    if _cache["price"] and (now - _cache["time"]) < CACHE_TTL:
        return _cache["price"]

    try:
        ticker = yf.Ticker("CL=F")
        data = ticker.fast_info
        price = data.get("lastPrice", None) or data.get("last_price", None)

        if price and price > 0:
            _cache["price"] = float(price)
            _cache["time"] = now
            return float(price)

        # Fallback: get latest from history
        hist = ticker.history(period="1d", interval="1m")
        if not hist.empty:
            price = float(hist["Close"].iloc[-1])
            _cache["price"] = price
            _cache["time"] = now
            return price

    except Exception as e:
        print(f"[WTI] Price fetch error: {e}")

    return _cache["price"]  # return stale if available


def get_wti_history_hourly(hours: int = 24) -> list:
    """Get recent hourly WTI prices. Returns list of (datetime, price)."""
    try:
        ticker = yf.Ticker("CL=F")
        hist = ticker.history(period=f"{hours}h", interval="1h")
        result = []
        for t, row in hist.iterrows():
            dt = t.to_pydatetime()
            result.append((dt, float(row["Close"])))
        return result
    except Exception as e:
        print(f"[WTI] History fetch error: {e}")
        return []
