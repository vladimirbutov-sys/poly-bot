"""Event-based rebuy trigger (V9).

Fires when state-based tier-upgrade returns 0 (denizz did reversal:
partially sold then buys back). Uses formula applied to denizz's NEW BUY
amount (not net_invested) — captures conviction of the refresh event.

Conditions (all must be true):
    1. REBUY_TRIGGER_ENABLED
    2. not _rebuy_killed() (cumulative rebuy PnL above threshold)
    3. our_cost > 0 (we're already in position; this is a top-up, not entry)
    4. new_buy_usd >= MIN_PLAYER_INVESTED (fresh buy is meaningful)
    5. not _throttled(cid, token, REBUY_THROTTLE_SEC)

Sizing:
    rebuy = calculate_bet_formula_only(new_buy_usd, price)
          = (A * ln(new_buy_usd) + B) capped at MAX_BET
            × PRICE_BET_MULT × PRICE_RISK_MULT
    rebuy = min(rebuy, MAX_POSITION_USD - our_cost)
    rebuy >= MIN_BET_USD_LIVE or SKIP

Logs every decision to REBUY_LOG_PATH (append-only JSONL).
"""
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

_rebuy_last_ts_lock = threading.Lock()
_rebuy_last_ts: dict = {}     # (cid, token) -> unix_ts
_rebuy_exec_count_lock = threading.Lock()
_rebuy_exec_count: int = 0    # number of EXECUTED rebuys since bot start (or, after
                              # _init_exec_count_from_log() runs at module load,
                              # cumulative across restarts based on rebuy_log.jsonl)


def _init_exec_count_from_log() -> int:
    """Initialize _rebuy_exec_count by counting EXECUTED entries in rebuy_log.

    Without this, the counter resets on every bot restart, so the smoke-cap
    re-engages with each restart even though we've validated the rebuy logic
    long ago. Loading from disk makes the cap genuinely a "first N rebuys
    after deploy" mechanism — to re-engage it, manually clear/rotate the log.

    Logic itself stays untouched: REBUY_INITIAL_MAX_USD and REBUY_INITIAL_N
    constants still gate via _initial_cap_active(); only the seed value of
    the counter changed from 0 to "actual EXECUTED count from log".
    """
    global _rebuy_exec_count
    try:
        from config import REBUY_LOG_PATH
    except ImportError:
        return 0
    if not os.path.exists(REBUY_LOG_PATH):
        return 0
    n = 0
    try:
        with open(REBUY_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except Exception:
                    continue   # skip malformed lines
                if entry.get("decision") == "EXECUTED":
                    n += 1
    except Exception as e:
        print(f"[REBUY] init failed reading log: {e}")
        return 0
    with _rebuy_exec_count_lock:
        _rebuy_exec_count = n
    print(f"[REBUY] init: loaded _rebuy_exec_count={n} from {os.path.basename(REBUY_LOG_PATH)} "
          f"(smoke-cap auto-disabled if n >= REBUY_INITIAL_N)")
    return n


# Run at module import — bot's main.py imports rebuy on startup.
_init_exec_count_from_log()


def _throttled(cid: str, token_id: str, window_sec: int) -> bool:
    """True if a rebuy on (cid, token) happened within last window_sec."""
    key = (cid, token_id)
    with _rebuy_last_ts_lock:
        last = _rebuy_last_ts.get(key)
        if last is None:
            return False
        return (time.time() - last) < window_sec


def _mark_throttle(cid: str, token_id: str) -> None:
    key = (cid, token_id)
    with _rebuy_last_ts_lock:
        _rebuy_last_ts[key] = time.time()


def _cumulative_rebuy_pnl() -> float:
    """Sum realized + unrealized PnL of all tier='rebuy' positions.
    For unrealized: use last known price from position record (avg_entry)
    as conservative fallback (we don't want to fire kill-switch on
    transient CLOB flakes)."""
    try:
        import tracker
    except ImportError:
        return 0.0
    total = 0.0
    data = tracker.load()
    for pos in data.get("positions", {}).values():
        if pos.get("tier") != "rebuy":
            continue
        if pos.get("status") == "sold":
            total += float(pos.get("final_pnl", 0) or 0)
        elif pos.get("status") == "open":
            cost = float(pos.get("cost_usd", 0) or 0)
            shares = float(pos.get("size_shares", 0) or 0)
            entry = float(pos.get("avg_entry", 0) or 0)
            # Conservative: assume position still at entry price (no mark-to-market
            # in kill-switch decision; only realized PnL matters for trigger).
            # If shares == 0 but not 'sold' — treat as closed, sells aggregate
            for s in pos.get("sells", []) or []:
                total += float(s.get("pnl", 0) or 0)
            # Unrealized portion of still-held shares: assume 0 PnL for safety
            # (can refine later with real-time CLOB mid).
            _ = (cost, shares, entry)
    return total


def _rebuy_killed() -> bool:
    """True if cumulative realized rebuy PnL below REBUY_PNL_KILL_SWITCH_USD."""
    try:
        from config import REBUY_PNL_KILL_SWITCH_USD
    except ImportError:
        return False
    return _cumulative_rebuy_pnl() < float(REBUY_PNL_KILL_SWITCH_USD)


def _initial_cap_active() -> Optional[float]:
    """Returns REBUY_INITIAL_MAX_USD if we're still in smoke-test window
    (first N rebuys), else None. Count tracks successful EXECUTED only."""
    try:
        from config import REBUY_INITIAL_MAX_USD, REBUY_INITIAL_N
    except ImportError:
        return None
    with _rebuy_exec_count_lock:
        if _rebuy_exec_count >= int(REBUY_INITIAL_N):
            return None
    return float(REBUY_INITIAL_MAX_USD)


def _log(event: dict) -> None:
    """Append a rebuy decision to REBUY_LOG_PATH."""
    try:
        from config import REBUY_LOG_PATH
    except ImportError:
        return
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    try:
        with open(REBUY_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as e:
        print(f"[REBUY] log write error: {e}")


def try_rebuy(*, cid: str, token_id: str, title: str, outcome: str,
              event_slug: str, entry_price: float, new_buy_usd: float,
              our_cost: float, denizz_net_invested: float,
              player_name: str) -> bool:
    """Top-level entry: returns True if rebuy executed, False otherwise.
    Never raises — logs errors to REBUY_LOG_PATH with decision='ERROR'."""
    try:
        from config import (REBUY_TRIGGER_ENABLED, REBUY_THROTTLE_SEC,
                            MIN_PLAYER_INVESTED, MIN_BET_USD_LIVE,
                            MAX_POSITION_USD)
    except ImportError as e:
        _log({"decision": "ERROR", "reason": f"config import: {e}"})
        return False

    base_event = {
        "cid": cid, "token_id": token_id, "title": title,
        "outcome": outcome, "event_slug": event_slug,
        "price": round(entry_price, 4),
        "denizz_new_buy_usd": round(new_buy_usd, 2),
        "denizz_net_invested": round(denizz_net_invested, 2),
        "our_cost": round(our_cost, 2),
        "player": player_name,
    }

    if not REBUY_TRIGGER_ENABLED:
        _log({**base_event, "decision": "SKIP_DISABLED"})
        return False

    if _rebuy_killed():
        pnl = _cumulative_rebuy_pnl()
        _log({**base_event, "decision": "SKIP_KILL_SWITCH",
              "cumulative_pnl": round(pnl, 2)})
        print(f"[REBUY] BLOCKED: kill-switch active (cum PnL ${pnl:.2f}) | {title[:40]}")
        return False

    if our_cost <= 0:
        _log({**base_event, "decision": "SKIP_NO_POSITION"})
        return False

    min_invested = float(MIN_PLAYER_INVESTED.get(player_name, 500))
    if new_buy_usd < min_invested:
        _log({**base_event, "decision": "SKIP_SMALL_BUY",
              "threshold": min_invested})
        return False

    if _throttled(cid, token_id, int(REBUY_THROTTLE_SEC)):
        _log({**base_event, "decision": "SKIP_THROTTLE"})
        return False

    # Size
    try:
        import filters
        rebuy = filters.calculate_bet_formula_only(new_buy_usd, entry_price)
    except Exception as e:
        _log({**base_event, "decision": "ERROR", "reason": f"sizing: {e}"})
        return False

    proposed_rebuy = rebuy
    remaining_cap = float(MAX_POSITION_USD) - our_cost
    rebuy = min(rebuy, max(0.0, remaining_cap))

    # Smoke-test cap
    initial_cap = _initial_cap_active()
    if initial_cap is not None and rebuy > initial_cap:
        rebuy = initial_cap

    if rebuy < float(MIN_BET_USD_LIVE):
        _log({**base_event, "decision": "SKIP_TOO_SMALL",
              "proposed": round(proposed_rebuy, 2), "final": round(rebuy, 2),
              "remaining_cap": round(remaining_cap, 2),
              "initial_cap": initial_cap})
        return False

    # Available bankroll check
    try:
        import tracker
        data = tracker.load()
        available = tracker.get_available_balance(data)
    except Exception:
        available = 0.0
    if rebuy > available:
        _log({**base_event, "decision": "SKIP_NO_BANKROLL",
              "proposed": round(rebuy, 2), "available": round(available, 2)})
        return False

    # Execute via entry_manager
    try:
        import entry_manager
    except ImportError as e:
        _log({**base_event, "decision": "ERROR", "reason": f"entry_manager import: {e}"})
        return False

    _mark_throttle(cid, token_id)

    log_payload = {
        **base_event, "decision": "EXECUTED",
        "proposed": round(proposed_rebuy, 2),
        "final": round(rebuy, 2),
        "remaining_cap": round(remaining_cap, 2),
        "initial_cap": initial_cap,
    }
    _log(log_payload)
    print(f"[REBUY] EXECUTED ${rebuy:.2f} @ {entry_price:.3f} "
          f"(new_buy ${new_buy_usd:.0f}, our_cost ${our_cost:.2f}) | {title[:40]}")

    def _do_execute():
        try:
            entry_manager.execute_part1(
                token_id, entry_price, rebuy, cid, title, outcome,
                event_slug, tier="rebuy", signal_player=player_name,
            )
        except Exception as e:
            print(f"[REBUY] execute error: {e}")
            return
        with _rebuy_exec_count_lock:
            global _rebuy_exec_count
            _rebuy_exec_count += 1

    threading.Thread(target=_do_execute, daemon=True).start()
    return True
