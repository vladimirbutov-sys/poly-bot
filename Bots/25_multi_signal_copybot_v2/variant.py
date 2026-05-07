"""Bot operating variant (A/B) — hot-reloadable filter for buy events.

Variant A: legacy behaviour. No additional filtering on buy-events.

Variant B: copy denizz buys only when the LIVE best ask of OUR side is in
[VARIANT_B_PRICE_FLOOR, VARIANT_B_PRICE_CEIL]. Applies to every buy-event
path: Path A, top-up / tier-upgrade / MERGE, rebuy trigger, hedge buy.

Sells, follow-sell, stop-loss are NEVER affected by the variant.

Hot-reload:
    The file `_bot_variant.txt` (path from `config.VARIANT_FILE`) overrides
    `config.BOT_VARIANT` when it contains a single character "A" or "B"
    (case-insensitive). The file is re-checked at most once per
    `config.VARIANT_RELOAD_INTERVAL_SEC` seconds. Missing / empty / invalid
    file falls back to the config default.

Use:
    >>> from variant import get_active_variant, should_skip_buy_for_variant
    >>> get_active_variant()
    'A'
    >>> skip, reason = should_skip_buy_for_variant(token_id="...", title="...")
"""
from __future__ import annotations

import os
import time
from threading import Lock
from typing import Literal, Optional, Tuple

import config

Variant = Literal["A", "B"]

# Internal cache for hot-reload throttling.
_cache_lock = Lock()
_cache_value: Optional[Variant] = None
_cache_source: str = "init"  # "init" | "config" | "file" | "fallback"
_cache_ts: float = 0.0
_last_logged_value: Optional[Variant] = None


def _read_file_variant() -> Tuple[Optional[Variant], str]:
    """Read `_bot_variant.txt` if it exists. Return (value, source).

    Returns (None, reason) if file does not exist, is empty, or contains an
    invalid token. Returns ("A"|"B", "file") on success.
    """
    project_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(project_dir, config.VARIANT_FILE)
    if not os.path.exists(path):
        return None, "no_file"
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip().upper()
    except (OSError, UnicodeError) as e:
        return None, f"read_error:{type(e).__name__}"
    if raw in ("A", "B"):
        return raw, "file"  # type: ignore[return-value]
    return None, "invalid_content"


def get_active_variant(force_reload: bool = False) -> Variant:
    """Return current operating variant ("A" | "B").

    Reads `_bot_variant.txt` if it exists; otherwise falls back to
    `config.BOT_VARIANT`. The result is cached for
    `config.VARIANT_RELOAD_INTERVAL_SEC` seconds.

    Args:
        force_reload: bypass the cache and re-read immediately.

    Returns:
        "A" or "B".
    """
    global _cache_value, _cache_source, _cache_ts, _last_logged_value

    now = time.time()
    interval = max(1, int(config.VARIANT_RELOAD_INTERVAL_SEC))

    with _cache_lock:
        if (not force_reload
                and _cache_value is not None
                and (now - _cache_ts) < interval):
            return _cache_value

        file_value, file_source = _read_file_variant()
        if file_value is not None:
            new_value: Variant = file_value
            new_source = file_source
        else:
            cfg = str(getattr(config, "BOT_VARIANT", "A")).strip().upper()
            if cfg in ("A", "B"):
                new_value = cfg  # type: ignore[assignment]
                new_source = "config"
            else:
                new_value = "A"
                new_source = f"fallback(invalid config={cfg!r})"

        # Log only on real change to avoid log spam every 30s.
        if new_value != _last_logged_value:
            print(f"[VARIANT] active={new_value} source={new_source}"
                  f"{' (file_status=' + file_source + ')' if file_value is None else ''}")
            _last_logged_value = new_value

        _cache_value = new_value
        _cache_source = new_source
        _cache_ts = now
        return new_value


def get_variant_status() -> dict:
    """Return a snapshot of current variant state for diagnostics."""
    v = get_active_variant()
    return {
        "active": v,
        "source": _cache_source,
        "cached_for_sec": max(0, int(time.time() - _cache_ts)),
        "config_default": getattr(config, "BOT_VARIANT", "A"),
        "file_status": _read_file_variant()[1],
        "floor": config.VARIANT_B_PRICE_FLOOR,
        "ceil": config.VARIANT_B_PRICE_CEIL,
    }


def _get_live_ask(token_id: str) -> Optional[float]:
    """Fetch live best ask for a token. Returns None on error."""
    try:
        # Late import to avoid circular dependency at module load.
        import filters
        bid, ask = filters.get_orderbook_prices(token_id)
        if ask is None:
            return None
        ask_f = float(ask)
        if ask_f <= 0:
            return None
        return ask_f
    except Exception as e:
        print(f"[VARIANT] WARN: live ask fetch failed for {token_id[:16]}...: "
              f"{type(e).__name__}: {e}")
        return None


def should_skip_buy_for_variant(
    token_id: str,
    title: str = "",
    *,
    live_ask: Optional[float] = None,
) -> Tuple[bool, str]:
    """Decide whether a pending BUY event must be skipped per the active variant.

    Variant A: never skip. Returns (False, "").

    Variant B: skip if live best ask of `token_id` is outside
    [VARIANT_B_PRICE_FLOOR, VARIANT_B_PRICE_CEIL]. If the live ask cannot be
    fetched (RPC/network failure), variant B FAIL-SAFE: skip the buy and log
    the reason — better to miss a trade than to size incorrectly.

    Args:
        token_id: CTF/CLOB token id we'd be buying.
        title: human-readable market title for log messages.
        live_ask: pre-fetched best ask in [0,1]; if omitted, fetched on demand.

    Returns:
        (skip, reason) where reason is empty for variant A and a short
        human-readable phrase for variant B.
    """
    v = get_active_variant()
    if v == "A":
        return False, ""

    floor = float(config.VARIANT_B_PRICE_FLOOR)
    ceil = float(config.VARIANT_B_PRICE_CEIL)

    if live_ask is None:
        live_ask = _get_live_ask(token_id)

    if live_ask is None:
        # Fail-safe under variant B: skip when we can't price the leg.
        msg = (f"variant=B live ask unavailable — SKIPPED (fail-safe) "
               f"| {title[:60]}")
        return True, msg

    if live_ask < floor or live_ask > ceil:
        msg = (f"variant=B price {live_ask:.4f} outside "
               f"[{floor:.2f}, {ceil:.2f}] — SKIPPED | {title[:60]}")
        return True, msg

    return False, ""
