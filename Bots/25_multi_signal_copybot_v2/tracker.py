"""Position and P&L tracking. Persists to positions.json.

Balance source: since 2026-04-09 the "available balance" for new bets is
read directly from the on-chain USDC balance, not from positions.json's
internal current_balance counter. The counter is still maintained for
historical P&L reporting but is no longer authoritative for trading
decisions — on-chain is the single source of truth.
"""
import json
import os
import time
import threading
from datetime import datetime, timezone
from config import POSITIONS_FILE, BANKROLL, MAX_DRAWDOWN_PCT, MAX_CONCURRENT

# === On-chain balance cache ===
_onchain_cache = {"ts": 0, "value": None}
_ONCHAIN_CACHE_TTL = 30  # seconds

# === Concurrency lock for positions.json (BLOCKER-1 fix, 2026-04-17) ===
# RLock (re-entrant): allows same thread to lock multiple times (e.g. load() inside
# code that already holds the lock). Prevents lost-update race when multiple
# exit_manager threads do load→mutate→save concurrently on sell bursts.
_io_lock = threading.RLock()


# === Position-closed callbacks (Variant B lifecycle hook) ===
# Any caller that fully closes a position (record_sell below 0.1 shares,
# resolve_position won/lost, sync_with_onchain disappeared, exit_manager
# skip-onchain-empty) fires _fire_on_close. main.py registers a handler to
# clean up _signaled_keys / _signal_buffers / buy_buffers.json so stale state
# can't block the next legitimate signal on the same market.
_on_close_callbacks: list = []


def register_on_close(fn):
    """Register a callback fired whenever a position becomes fully closed.

    Callback signature: fn(condition_id: str, token_id: str,
                           signal_player: str, reason: str) -> None
    Exceptions inside callbacks are caught and logged — they must never
    break the sell/resolve/sync flow.
    """
    if fn not in _on_close_callbacks:
        _on_close_callbacks.append(fn)


def _fire_on_close(cid: str, token_id: str, signal_player: str, reason: str):
    """Invoke every registered on-close callback. Fail-safe."""
    for fn in list(_on_close_callbacks):
        try:
            fn(cid, token_id, signal_player, reason)
        except Exception as e:
            print(f"[LIFECYCLE] on_close callback error ({reason}): {e}")


def _fetch_onchain_usdc_balance():
    """Fetch the live USDC balance (bridged USDC.e) from Polygon.

    Wallet is NOT shared with other bots (per user confirmation 2026-04-09),
    so the full on-chain USDC is available to this bot.
    """
    try:
        from web3 import Web3
        from config import POLYGON_RPC, OUR_WALLET, USDC_CONTRACT
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        erc20_abi = [{
            "inputs": [{"name": "account", "type": "address"}],
            "name": "balanceOf",
            "outputs": [{"name": "", "type": "uint256"}],
            "stateMutability": "view",
            "type": "function",
        }]
        c = w3.eth.contract(address=Web3.to_checksum_address(USDC_CONTRACT), abi=erc20_abi)
        raw = c.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call()
        return raw / 1e6
    except Exception as e:
        print(f"[TRACKER] on-chain balance fetch failed: {e}")
        return None


def get_onchain_balance(force_refresh=False):
    """Return cached on-chain USDC balance. Cache TTL 30s.
    Returns None on failure (caller should fall back to internal counter)."""
    global _onchain_cache
    now = time.time()
    if (not force_refresh
            and _onchain_cache["value"] is not None
            and now - _onchain_cache["ts"] < _ONCHAIN_CACHE_TTL):
        return _onchain_cache["value"]
    value = _fetch_onchain_usdc_balance()
    if value is not None:
        _onchain_cache = {"ts": now, "value": value}
    return value


def _default_data():
    return {
        "positions": {},
        "stats": {
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "sells": 0,
            "total_pnl": 0.0,
            "peak_balance": BANKROLL,
            "current_balance": BANKROLL,
        }
    }


def load():
    with _io_lock:
        if os.path.exists(POSITIONS_FILE):
            try:
                with open(POSITIONS_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, KeyError):
                pass
        return _default_data()


def save(data):
    with _io_lock:
        tmp = POSITIONS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, POSITIONS_FILE)


def get_open_positions(data) -> dict:
    return {
        key: pos for key, pos in data["positions"].items()
        if pos.get("status") == "open"
    }


def count_open(data) -> int:
    return len(get_open_positions(data))


def get_available_balance(data, reserve_usd=None) -> float:
    """Balance available for new bets (minus reserve).

    Primary source: on-chain USDC balance (fresh, accurate, self-correcting).
    Fallback: internal current_balance counter if on-chain fetch fails.

    The on-chain read is cached for 30 seconds to avoid hammering RPC.
    """
    if reserve_usd is None:
        try:
            from mode_manager import mode_manager
            reserve_usd = mode_manager.get_reserve()
        except Exception:
            from config import RESERVE_USD_LIVE
            reserve_usd = RESERVE_USD_LIVE

    onchain = get_onchain_balance()
    if onchain is not None:
        return max(0, onchain - reserve_usd)

    # Fallback — internal counter (may be drifted, but safer than trading blind)
    tracker_internal = data["stats"].get("current_balance", 0)
    print(f"[TRACKER] WARNING: on-chain balance unavailable, falling back to internal ${tracker_internal:.2f}")
    return max(0, tracker_internal - reserve_usd)


def has_position_on_event(data, event_slug: str) -> bool:
    """DEPRECATED — kept for compatibility. Use has_position_on_condition instead."""
    for pos in data["positions"].values():
        if pos.get("status") == "open" and pos.get("event_slug") == event_slug:
            return True
    return False


def add_in_flight(condition_id: str, token_id: str, amount_usd: float) -> bool:
    """Variant 1: add pending order amount to open position's in_flight_usd.
    Called before execute_part1 to prevent cascade double-entry."""
    data = load()
    tok_str = str(token_id)
    for key, pos in data.get("positions", {}).items():
        if pos.get("status") != "open":
            continue
        if pos.get("condition_id") != condition_id:
            continue
        if str(pos.get("token_id")) != tok_str:
            continue
        pos["in_flight_usd"] = round(float(pos.get("in_flight_usd", 0) or 0) + amount_usd, 6)
        save(data)
        return True
    return False


def clear_in_flight(condition_id: str, token_id: str, amount_usd: float) -> bool:
    """Variant 1: subtract amount from in_flight_usd when order fills or times out."""
    data = load()
    tok_str = str(token_id)
    for key, pos in data.get("positions", {}).items():
        if pos.get("status") != "open":
            continue
        if pos.get("condition_id") != condition_id:
            continue
        if str(pos.get("token_id")) != tok_str:
            continue
        cur = float(pos.get("in_flight_usd", 0) or 0)
        pos["in_flight_usd"] = round(max(0.0, cur - amount_usd), 6)
        save(data)
        return True
    return False


def get_cost_on_token(data, condition_id: str, token_id: str) -> tuple:
    """Variant 1: sum cost_usd + in_flight_usd of ALL open positions on (cid, token).

    Returns (total_cost_usd, last_record_ts).
    last_record_ts = max timestamp of record_position calls for this (cid, token)
    — used for grace-period check (skip data-api refresh if <N sec ago).
    Returns (0.0, 0) if no open position.
    """
    total = 0.0
    latest_ts = 0
    tok_str = str(token_id)
    for pos in data.get("positions", {}).values():
        if pos.get("status") != "open":
            continue
        if pos.get("condition_id") != condition_id:
            continue
        if str(pos.get("token_id")) != tok_str:
            continue
        total += float(pos.get("cost_usd", 0) or 0)
        total += float(pos.get("in_flight_usd", 0) or 0)
        rts = int(pos.get("last_record_ts", 0) or 0)
        if rts > latest_ts:
            latest_ts = rts
    return (round(total, 2), latest_ts)


def has_position_on_condition(data, condition_id: str) -> bool:
    """Check if we already have an open position on this specific condition_id (sub-market)."""
    for pos in data["positions"].values():
        if pos.get("status") == "open" and pos.get("condition_id") == condition_id:
            return True
    return False


def has_open_position_on_token(data, token_id: str) -> bool:
    """Check if we have an OPEN position on this specific token (same outcome /
    same side of a binary market).

    Added 2026-04-21 — has_position_on_condition is too coarse for binary
    markets: an open YES position must not block a fresh signal on NO (and
    vice-versa). See _analytics/2026-04-21_subm_double_entry_guard_too_coarse.md
    """
    if not token_id:
        return False
    tid = str(token_id)
    for pos in data["positions"].values():
        if pos.get("status") == "open" and str(pos.get("token_id", "")) == tid:
            return True
    return False


def reset_buffer_after_manual_sell(condition_id: str, token_id: str,
                                    player_name: str = "denizz") -> bool:
    """Clear the signaled/buffer state for a (cid, token) after a manual exit.

    The copy-bot keeps per-player state in buy_buffers.json to avoid
    double-entering on the same signal. When a human sells a position
    manually via one of the _sell_*.py scripts, that state becomes stale:
    the buffer still remembers `notified=True` and `last_tier_bet=$X`, so
    when the player places new BUYs on the same market the bot classifies
    them as `Already signaled (same tier)` and silently skips.

    This helper resets the buffer entry for (cid, token) so the next BUY
    event re-enters through the fresh-signal path. Safe to call even if
    the buffer entry doesn't exist.

    NOTE: If the bot is currently running, its in-memory copy of the
    buffer will overwrite this file on the next save. Callers should
    either (a) pair this with a bot restart or (b) accept that the
    reset only takes effect after the bot process cycles.

    Returns True if a buffer entry was found and reset.
    """
    buf_file = os.path.join(os.path.dirname(POSITIONS_FILE), "buy_buffers.json")
    if not os.path.exists(buf_file):
        return False
    try:
        with open(buf_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[TRACKER] reset_buffer read err: {e}")
        return False

    buf_key = f"{condition_id}_{token_id}"
    player_bufs = data.get("buffers", {}).get(player_name, {})
    existed = buf_key in player_bufs

    if existed:
        player_bufs[buf_key] = {
            "total_usd": 0.0,
            "buys": [],
            "notified": False,
            "last_tier_bet": 0.0,
        }

    # Also drop from signaled_keys (if the dict form is used)
    sk = data.get("signaled_keys", {})
    if isinstance(sk, dict):
        player_sk = sk.get(player_name)
        if isinstance(player_sk, dict) and buf_key in player_sk:
            del player_sk[buf_key]
        elif isinstance(player_sk, list) and buf_key in player_sk:
            player_sk.remove(buf_key)

    tmp = buf_file + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, buf_file)
    except Exception as e:
        print(f"[TRACKER] reset_buffer write err: {e}")
        return False

    if existed:
        print(f"[TRACKER] reset_buffer_after_manual_sell: cleared {buf_key[:40]}... for {player_name}")
    return existed


def consolidate_duplicates(data) -> int:
    """Merge any open positions sharing the same (condition_id, token_id) into
    a single record. Idempotent — safe to run repeatedly.

    Self-healing fix for the duplicate-tracker bug: when the bot copied multiple
    BUY events from a player on the same market, each call to record_position
    used to create a new record because the dedup branch only fired for part>1.
    Result: 2-3 tracker rows on one on-chain position. Sell logic then iterated
    each duplicate separately and tried to sell shares that didn't exist.

    Strategy:
      - Group open positions by (cid, token).
      - In each group with >1 records: pick the OLDEST record (by timestamp)
        as primary, sum all sizes/costs into it, recompute weighted avg_entry,
        merge order_ids and sells lists, mark the others as "merged".
      - Returns number of records merged away.
    """
    from collections import defaultdict
    groups = defaultdict(list)
    for key, pos in data.get("positions", {}).items():
        if pos.get("status") != "open":
            continue
        cid = pos.get("condition_id") or ""
        tok = str(pos.get("token_id") or "")
        if not cid or not tok:
            continue
        groups[(cid, tok)].append((key, pos))

    merged_count = 0
    for (cid, tok), records in groups.items():
        if len(records) <= 1:
            continue
        # Sort by timestamp ascending, oldest first
        records.sort(key=lambda kp: kp[1].get("timestamp", "") or "")
        primary_key, primary = records[0]
        old_sh_p = float(primary.get("size_shares", 0) or 0)
        old_cost_p = float(primary.get("cost_usd", 0) or 0)
        merged_order_ids = list(primary.get("order_ids") or [primary_key])
        merged_sells = list(primary.get("sells") or [])
        merged_manual = list(primary.get("manual_additions") or [])

        for dup_key, dup in records[1:]:
            dup_sh = float(dup.get("size_shares", 0) or 0)
            dup_cost = float(dup.get("cost_usd", 0) or 0)
            old_sh_p += dup_sh
            old_cost_p += dup_cost
            for oid in (dup.get("order_ids") or [dup_key]):
                if oid not in merged_order_ids:
                    merged_order_ids.append(oid)
            for s in (dup.get("sells") or []):
                merged_sells.append(s)
            for m in (dup.get("manual_additions") or []):
                merged_manual.append(m)
            # Demote duplicate
            dup["status"] = "merged_into_primary"
            dup["merged_into"] = primary_key
            dup["merged_at"] = datetime.now(timezone.utc).isoformat()
            merged_count += 1

        primary["size_shares"] = round(old_sh_p, 6)
        primary["cost_usd"] = round(old_cost_p, 6)
        primary["avg_entry"] = round(old_cost_p / old_sh_p, 6) if old_sh_p > 0 else primary.get("avg_entry", 0)
        primary["order_ids"] = merged_order_ids
        if merged_sells:
            primary["sells"] = merged_sells
        if merged_manual:
            primary["manual_additions"] = merged_manual
        primary.setdefault("dedup_history", []).append({
            "at": datetime.now(timezone.utc).isoformat(),
            "merged_keys": [r[0] for r in records[1:]],
            "new_size": primary["size_shares"],
            "new_cost": primary["cost_usd"],
            "new_avg": primary["avg_entry"],
        })
    return merged_count


def record_position(data, order_id: str, condition_id: str, token_id: str,
                     title: str, outcome: str, event_slug: str,
                     entry_price: float, size_shares: float, cost_usd: float,
                     tier: str, part: int = 1, signal_player: str = ""):
    """Record a new position (or aggregate into existing on same cid+token).

    Always aggregates when an open record on (condition_id, token_id) already
    exists, regardless of `part`. This fixes the duplicate-record bug where
    multiple copy-buys from the same player at part=1 created N tracker rows.
    """
    # Self-heal any pre-existing duplicates before deciding
    consolidate_duplicates(data)

    existing_key = None
    for key, pos in data["positions"].items():
        if (pos.get("condition_id") == condition_id
                and str(pos.get("token_id")) == str(token_id)
                and pos.get("status") == "open"):
            existing_key = key
            break

    if existing_key:
        # Aggregate into existing open record (regardless of `part`)
        pos = data["positions"][existing_key]
        old_cost = float(pos.get("cost_usd", 0) or 0)
        old_shares = float(pos.get("size_shares", 0) or 0)
        pos["size_shares"] = round(old_shares + size_shares, 6)
        pos["cost_usd"] = round(old_cost + cost_usd, 6)
        pos["avg_entry"] = round(pos["cost_usd"] / pos["size_shares"], 6) if pos["size_shares"] > 0 else 0
        pos["parts_filled"] = int(pos.get("parts_filled", 1)) + 1
        pos["last_record_ts"] = int(time.time())  # Variant 1: grace-period marker
        order_ids = pos.get("order_ids") or [existing_key]
        if order_id not in order_ids:
            order_ids.append(order_id)
        pos["order_ids"] = order_ids
        # Preserve signal_player from the first entry; only set if empty
        if signal_player and not pos.get("signal_player"):
            pos["signal_player"] = signal_player
    else:
        # New position
        # tier "HP" marks the high-price override strategy (single-part, fixed size)
        parts_planned = 1 if tier == "HP" else 3
        strategy = "HP" if tier == "HP" else "standard"
        data["positions"][order_id] = {
            "condition_id": condition_id,
            "token_id": token_id,
            "title": title,
            "outcome": outcome,
            "event_slug": event_slug,
            "entry_price": entry_price,
            "avg_entry": entry_price,
            "size_shares": size_shares,
            "cost_usd": cost_usd,
            "tier": tier,
            "strategy": strategy,
            "signal_player": signal_player,
            "parts_filled": 1,
            "parts_planned": parts_planned,
            "order_ids": [order_id],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "last_record_ts": int(time.time()),  # Variant 1: grace-period marker
            "status": "open",
        }

    stats = data["stats"]
    stats["total_bets"] += 1
    stats["current_balance"] -= cost_usd
    save(data)


def record_sell(data, position_key: str, sell_shares: float, sell_price: float,
                sell_revenue: float, reason: str):
    """Record a partial or full sell."""
    pos = data["positions"].get(position_key)
    if not pos or pos["status"] != "open":
        return

    pos["size_shares"] -= sell_shares
    sell_pnl = sell_revenue - (sell_shares * pos["avg_entry"])

    pos.setdefault("sells", []).append({
        "shares": sell_shares,
        "price": sell_price,
        "revenue": sell_revenue,
        "pnl": sell_pnl,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    stats = data["stats"]
    stats["sells"] += 1
    stats["total_pnl"] += sell_pnl
    stats["current_balance"] += sell_revenue

    # If fully sold, close position
    fully_closed = False
    if pos["size_shares"] < 0.1:
        pos["status"] = "sold"
        pos["final_pnl"] = sum(s["pnl"] for s in pos.get("sells", []))
        fully_closed = True

    stats["peak_balance"] = max(stats["peak_balance"], stats["current_balance"])
    save(data)

    # Fire lifecycle callback AFTER persistence so observers see committed state.
    if fully_closed:
        _fire_on_close(
            pos.get("condition_id", "") or "",
            str(pos.get("token_id", "") or ""),
            pos.get("signal_player", "") or "",
            f"record_sell:{reason}",
        )


def resolve_position(data, key: str, won: bool):
    """Mark a position as won or lost (market resolved)."""
    pos = data["positions"].get(key)
    if not pos or pos["status"] != "open":
        return

    stats = data["stats"]
    if won:
        payout = pos["size_shares"]  # $1 per share
        pnl = payout - pos["cost_usd"]
        # Add back any partial sell P&L already counted
        already_counted = sum(s["pnl"] for s in pos.get("sells", []))
        net_new_pnl = pnl - already_counted
        pos["status"] = "won"
        stats["wins"] += 1
    else:
        remaining_cost = pos["size_shares"] * pos["avg_entry"]
        pnl = -remaining_cost
        already_counted = sum(s["pnl"] for s in pos.get("sells", []))
        net_new_pnl = pnl
        pos["status"] = "lost"
        stats["losses"] += 1

    pos["final_pnl"] = pnl + sum(s["pnl"] for s in pos.get("sells", []))
    stats["total_pnl"] += net_new_pnl
    if won:
        stats["current_balance"] += pos["size_shares"]  # payout $1 per remaining share
    # lost: no payout, cost was already deducted at record_position
    stats["peak_balance"] = max(stats["peak_balance"], stats["current_balance"])
    save(data)

    # Fire lifecycle callback after resolve.
    _fire_on_close(
        pos.get("condition_id", "") or "",
        str(pos.get("token_id", "") or ""),
        pos.get("signal_player", "") or "",
        "resolved_won" if won else "resolved_lost",
    )


def check_drawdown(data) -> bool:
    """Returns True if should stop trading.

    Uses on-chain USDC as primary balance (same as get_available_balance).
    Total equity = on-chain cash + cost basis of all open positions.
    """
    stats = data["stats"]
    peak = stats.get("peak_balance", BANKROLL)

    onchain = get_onchain_balance()
    if onchain is not None:
        balance = onchain
    else:
        balance = stats.get("current_balance", BANKROLL)

    invested = sum(
        p.get("cost_usd", 0)
        for p in data.get("positions", {}).values()
        if p.get("status") == "open"
    )
    total_value = balance + invested
    # Dynamic peak — keep bumping as we grow
    if total_value > peak:
        stats["peak_balance"] = total_value
        peak = total_value
    if peak <= 0:
        return True
    drawdown = (peak - total_value) / peak
    return drawdown >= MAX_DRAWDOWN_PCT


def find_by_condition(data, condition_id: str) -> tuple:
    """Find an open position by condition_id. Returns (key, position) or (None, None)."""
    for key, pos in data.get("positions", {}).items():
        if pos.get("condition_id") == condition_id and pos.get("status") == "open":
            return key, pos
    return None, None


def can_open_new(data) -> tuple:
    """Check if we can open a new position."""
    if get_available_balance(data) < 10:
        return False, "Insufficient balance (below reserve)"
    return True, ""


# Number of consecutive sync cycles a position must show on-chain=0
# before we close it. Protects against transient data-api / RPC failures
# that briefly return empty/zero. With check_exits at 60s, this gives
# ~3 minutes of confirmation latency before destructive close.
DISAPPEAR_CONFIRMATIONS_REQUIRED = 3


def sync_with_onchain(data) -> dict:
    """Sync tracker share counts with on-chain reality.

    On-chain is the single source of truth for how many shares we hold.
    Tracker only stores metadata (signal_player, entry_price, tier, etc).

    For each open position:
      - Fetch real share count from data API
      - If on-chain > tracker: adjust tracker up (extra shares from manual buy or duplicate bot)
      - If on-chain < tracker: adjust tracker down (manual sell or external action)
      - If on-chain == 0: increment _disappear_confirmations; close only after
        DISAPPEAR_CONFIRMATIONS_REQUIRED consecutive zero readings (guards
        against transient API failures returning empty results).

    Returns dict with sync results for logging.
    """
    import requests
    from config import DATA_API, OUR_WALLET

    # Fetch all our on-chain positions
    onchain = {}
    offset = 0
    fetch_succeeded = False  # True if any HTTP 200 response received (even if empty)
    while True:
        try:
            resp = requests.get(
                f"{DATA_API}/positions",
                params={"user": OUR_WALLET.lower(), "sizeThreshold": 0,
                        "limit": 500, "offset": offset},
                timeout=15,
            )
            if resp.status_code != 200:
                break
            fetch_succeeded = True
            batch = resp.json()
            if not batch:
                break
            for p in batch:
                cid = p.get("conditionId", "")
                asset = p.get("asset", "")
                if cid and asset:
                    onchain[(cid, asset)] = float(p.get("size", 0) or 0)
            if len(batch) < 500:
                break
            offset += 500
        except Exception as e:
            print(f"[SYNC] Fetch error: {e}")
            return {"error": str(e)}

    # GUARD LAYER 1 — abort closure logic if API returned suspiciously empty.
    # If fetch failed entirely (no HTTP 200) OR returned 0 positions while
    # tracker has multiple open positions → likely API issue, not real
    # disappearance. Skip the closure phase entirely; we can re-sync later.
    open_position_count = sum(
        1 for p in data.get("positions", {}).values() if p.get("status") == "open"
    )
    api_likely_failed = (not fetch_succeeded) or (
        len(onchain) == 0 and open_position_count > 1
    )
    if api_likely_failed:
        print(
            f"[SYNC] WARNING: data-api returned {len(onchain)} positions but tracker has "
            f"{open_position_count} open. Skipping sync to avoid false closures."
        )
        return {"adjusted": 0, "closed": 0, "adopted": 0, "results": [],
                "skipped_reason": "api_likely_failed"}

    adjusted = 0
    closed = 0
    results = []
    closed_fires = []  # (cid, token, signal_player, reason) tuples to fire after save

    for key, pos in data.get("positions", {}).items():
        if pos.get("status") != "open":
            continue

        cid = pos.get("condition_id", "")
        token = str(pos.get("token_id", ""))
        tracker_shares = float(pos.get("size_shares", 0) or 0)
        onchain_shares = onchain.get((cid, token), 0)
        title = pos.get("title", "")[:50]

        diff = onchain_shares - tracker_shares

        # Reset disappear-confirmation counter if balance is healthy now
        if onchain_shares >= 0.5 and pos.get("_disappear_confirmations", 0) > 0:
            results.append(
                f"DISAPPEAR_RECOVERED {title}: counter reset (balance back to {onchain_shares:.2f})"
            )
            pos["_disappear_confirmations"] = 0

        if abs(diff) < 0.5:
            continue  # within tolerance

        if onchain_shares < 0.5:
            # GUARD LAYER 2 — require N consecutive confirmations before closing.
            confs = int(pos.get("_disappear_confirmations", 0)) + 1
            pos["_disappear_confirmations"] = confs
            if confs < DISAPPEAR_CONFIRMATIONS_REQUIRED:
                results.append(
                    f"DISAPPEAR_PENDING {title}: {confs}/{DISAPPEAR_CONFIRMATIONS_REQUIRED} "
                    f"(was {tracker_shares:.0f} sh, on-chain 0)"
                )
                continue
            # Confirmed: position truly gone on-chain — mark as sold
            pos["status"] = "sold"
            pos["size_shares"] = 0
            pos.pop("_disappear_confirmations", None)  # cleanup
            pos.setdefault("sells", []).append({
                "shares": tracker_shares,
                "price": 0,
                "revenue": 0,
                "pnl": 0,
                "reason": "onchain_sync_disappeared",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            closed += 1
            results.append(
                f"CLOSED {title} (was {tracker_shares:.0f} sh, "
                f"on-chain 0 confirmed {DISAPPEAR_CONFIRMATIONS_REQUIRED}x)"
            )
            closed_fires.append((
                cid,
                token,
                pos.get("signal_player", "") or "",
                "onchain_sync_disappeared",
            ))
        else:
            # Adjust shares to match on-chain
            old_avg = float(pos.get("avg_entry", 0) or pos.get("entry_price", 0) or 0)
            if diff > 0:
                # On-chain has MORE — extra shares (manual buy or bot duplicate)
                extra_cost = diff * old_avg  # estimate cost at avg entry
                pos["cost_usd"] = round(float(pos.get("cost_usd", 0)) + extra_cost, 2)
                pos.setdefault("manual_additions", []).append({
                    "shares_added": round(diff, 2),
                    "estimated_cost": round(extra_cost, 2),
                    "reason": "onchain_sync_up",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                results.append(f"UP {title}: {tracker_shares:.0f} -> {onchain_shares:.0f} (+{diff:.0f})")
            else:
                # On-chain has LESS — shares were sold externally
                sold_shares = abs(diff)
                sold_revenue = sold_shares * old_avg  # estimate
                pos.setdefault("sells", []).append({
                    "shares": sold_shares,
                    "price": old_avg,
                    "revenue": sold_revenue,
                    "pnl": 0,
                    "reason": "onchain_sync_down",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                pos["cost_usd"] = round(float(pos.get("cost_usd", 0)) - (sold_shares * old_avg), 2)
                results.append(f"DOWN {title}: {tracker_shares:.0f} -> {onchain_shares:.0f} ({diff:.0f})")

            pos["size_shares"] = round(onchain_shares, 2)
            # Recalc avg entry
            if pos["size_shares"] > 0 and pos["cost_usd"] > 0:
                pos["avg_entry"] = round(pos["cost_usd"] / pos["size_shares"], 6)
            adjusted += 1

    # --- Reverse scan: on-chain → state ---
    # Add positions that exist on-chain but NOT in tracker at all.
    # This catches: manual buys, v1 leftovers, external additions.
    existing_keys = set()
    for pos in data.get("positions", {}).values():
        # Include ALL tracked positions (any status) to prevent re-adopting
        # positions that were manually closed/marked lost — otherwise on-chain
        # remnants would be re-adopted as new 0xsync_X entries on every sync cycle.
        existing_keys.add((pos.get("condition_id", ""), str(pos.get("token_id", ""))))

    adopted = 0
    for (cid, token), shares in onchain.items():
        if shares < 10:  # Bug 4 fix: skip dust (weather/sports <10 shares = noise)
            continue
        if (cid, token) in existing_keys:
            continue

        # Fetch market info for title/outcome
        title = ""
        outcome = ""
        event_slug = ""
        avg_price = 0
        # Bug 7 fix: search the full onchain fetch we already have (via data API),
        # not a separate limited request that misses most positions
        try:
            resp = requests.get(
                f"{DATA_API}/positions",
                params={"user": OUR_WALLET.lower(), "limit": 500, "sizeThreshold": 1},
                timeout=15,
            )
            for p in resp.json():
                if p.get("conditionId") == cid and p.get("asset") == token:
                    title = p.get("title", "")
                    outcome = p.get("outcome", "")
                    event_slug = p.get("eventSlug", "")
                    avg_price = float(p.get("avgPrice", 0) or 0)
                    break
        except Exception:
            pass

        import hashlib
        new_key = "0xsync_" + hashlib.md5(f"{cid}_{token}".encode()).hexdigest()[:34]
        cost_est = round(shares * avg_price, 2) if avg_price > 0 else 0

        data.setdefault("positions", {})[new_key] = {
            "condition_id": cid,
            "token_id": token,
            "title": title,
            "outcome": outcome,
            "event_slug": event_slug,
            "entry_price": avg_price,
            "avg_entry": avg_price,
            "size_shares": round(shares, 2),
            "cost_usd": cost_est,
            "tier": "B",
            "signal_player": "unknown",
            "parts_filled": 1,
            "parts_planned": 1,
            "order_ids": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "open",
            "sells": [],
            "final_pnl": 0,
            "_adopted_from": "onchain_sync",
        }
        adopted += 1
        safe_title = title[:45] if title else f"cid={cid[:20]}"
        results.append(f"ADOPTED {safe_title} ({shares:.0f} sh, ~${cost_est:.0f})")

    if adjusted > 0 or closed > 0 or adopted > 0:
        save(data)
        print(f"[SYNC] Synced: {adjusted} adjusted, {closed} closed, {adopted} adopted from on-chain")
        for r in results:
            print(f"[SYNC]   {r}")

    # Fire lifecycle callbacks after save, for every disappeared position.
    for cid_f, tok_f, sp_f, reason_f in closed_fires:
        _fire_on_close(cid_f, tok_f, sp_f, reason_f)

    return {"adjusted": adjusted, "closed": closed, "adopted": adopted, "details": results}
