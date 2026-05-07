"""Read and normalize positions data from all bots."""
import json
import logging
import time
from pathlib import Path
from datetime import datetime, timezone

import requests

from config import BOTS

log = logging.getLogger("data_reader")

GAMMA_API = "https://gamma-api.polymarket.com"

# Cache: token_id -> {end_date, url}, refreshed every 10 min
_market_cache: dict[str, dict] = {}
_market_cache_ts: float = 0
_MARKET_CACHE_TTL = 600


def _read_json(path: Path) -> dict | list | None:
    """Safely read a JSON file. Returns dict, list, or None."""
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, (dict, list)):
                return data
            log.warning("Skipping %s: unexpected type %s", path.name, type(data).__name__)
            return None
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Failed to read %s: %s", path, e)
    return None


def _normalize_standard_bot(bot_id: str, data: dict) -> list[dict]:
    """Normalize positions from 98_sure_bot, 20_crock95_bot, 10_oil_swing_bot format.
    Format: {positions: {order_id: {...}}, stats: {...}}
    """
    rows = []
    positions = data.get("positions", {})
    for oid, pos in positions.items():
        # Overround bot: skip unfilled orders
        if bot_id == "27_overround_bot" and pos.get("status") != "filled":
            continue
        token_id = pos.get("token_id", "")
        title = pos.get("title", "")
        side = pos.get("side", "YES")

        # Overround bot: uses different field names
        if bot_id == "27_overround_bot":
            title = pos.get("question", "") or pos.get("event_title", "")
            token_id = pos.get("no_token", "")  # bot buys NO
            side = "NO"

        # Oil Swing Bot: fill in token_id and title from side
        if bot_id == "10_oil_swing_bot" and not token_id:
            s = pos.get("side", "")
            if s == "YES":
                token_id = "79605660806991457811890435537160628976099500543939220857753925926896831621219"
                title = title or "Crude Oil (CL) $100 by March — YES"
            elif s == "NO":
                token_id = "92274168594309301674860132535303917340223623966677593281435938105131107664927"
                title = title or "Crude Oil (CL) $100 by March — NO"

        rows.append({
            "bot": bot_id,
            "order_id": oid,
            "title": title,
            "token_id": token_id,
            "condition_id": pos.get("condition_id", ""),
            "entry_price": pos.get("entry_price", 0),
            "size_shares": pos.get("size_shares", 0) or pos.get("filled_shares", 0),
            "cost_usd": pos.get("cost_usd", 0),
            "status": pos.get("status", "open"),
            "timestamp": pos.get("timestamp", ""),
            "pnl": pos.get("pnl"),
            "sell_price": pos.get("sell_price"),
            "neg_risk": pos.get("neg_risk", False),
            "side": side,
            "end_date": pos.get("end_date", ""),
        })
    return rows


def read_all_positions() -> list[dict]:
    """Read positions from all bots, return normalized list."""
    all_positions = []

    for bot_id, bot_cfg in BOTS.items():
        if bot_cfg["type"] in ("scanner", "utility"):
            continue

        data_path = bot_cfg["path"] / bot_cfg["data_file"]
        data = _read_json(data_path)
        if not data:
            continue

        # Iran Daily Trader: different data format (open_positions list)
        if bot_id == "24_iran_daily_trader":
            all_positions.extend(_normalize_iran_daily_trader(bot_id, data))
        elif bot_id == "26_weather_bot" and isinstance(data, list):
            # Weather bot: list of position dicts
            for pos in data:
                if not isinstance(pos, dict):
                    continue
                status = pos.get("status", "open")
                if status not in ("open",):
                    continue
                all_positions.append({
                    "bot": bot_id,
                    "title": pos.get("question", "%s %s %s" % (
                        pos.get("city", "?"), pos.get("date", "?"), pos.get("target", "?"))),
                    "status": status,
                    "entry_price": pos.get("entry_price", 0),
                    "cost_usd": pos.get("cost", 0),
                    "pnl": pos.get("pnl", 0) or 0,
                    "timestamp": pos.get("timestamp", ""),
                    "category": "weather",
                    "token_id": pos.get("token_id", ""),
                    "condition_id": pos.get("condition_id", ""),
                    "order_id": pos.get("order_id", ""),
                    "size_shares": 0,
                    "neg_risk": False,
                })
        elif isinstance(data, list):
            log.warning("Skipping %s: data is list, expected dict", bot_id)
            continue
        else:
            all_positions.extend(_normalize_standard_bot(bot_id, data))

    return all_positions


def _normalize_iran_daily_trader(bot_id: str, data: dict) -> list[dict]:
    """Normalize Iran+Hezbollah Daily Trader positions to standard format.
    Uses position_status field (order_placed / filled / closed).
    """
    rows = []
    for pos in data.get("open_positions", []):
        event_type = pos.get("event_type", "iran")
        day = pos.get("day", 0)
        labels = {"iran": "IRAN", "hez": "HEZ", "gulf": "GULF"}
        label = labels.get(event_type, event_type.upper())
        yes_entry = pos.get("yes_entry", 0)
        yes_exit = round(yes_entry + 0.09, 2)

        # NEW: prefer position_status field
        ps = pos.get("position_status")
        if ps is None:
            # Backward-compat: infer from old fields
            has_sell = bool(pos.get("yes_sell_order_id"))
            has_no = bool(pos.get("no_buy_order_id"))
            yes_filled = has_sell or has_no
            yes_sold = pos.get("yes_sold", False)
            if pos.get("closed") or yes_sold:
                ps = "closed"
            elif yes_filled:
                ps = "filled"
            else:
                ps = "order_placed"

        # Map to display status
        if ps == "closed":
            status = "sold" if pos.get("yes_sold") else "closed"
            title = f"{label} Apr {day} — YES @{yes_entry*100:.0f}c [SOLD @{pos.get('yes_sell_price',0)*100:.0f}c]"
            cost_to_show = 0
        elif ps == "filled":
            status = "filled"
            title = f"{label} Apr {day} — YES @{yes_entry*100:.0f}c [FILLED, sell @{yes_exit*100:.0f}c]"
            cost_to_show = pos.get("yes_cost", 0)
        else:  # order_placed
            status = "limit_order"
            title = f"{label} Apr {day} — LIMIT BUY YES @{yes_entry*100:.0f}c (waiting)"
            cost_to_show = 0  # not invested yet (only reserved)

        rows.append({
            "bot": bot_id,
            "order_id": pos.get("yes_buy_order_id", ""),
            "title": title,
            "token_id": "",
            "condition_id": "",
            "entry_price": yes_entry,
            "size_shares": pos.get("yes_shares", 0),
            "cost_usd": cost_to_show,
            "reserved_usd": pos.get("yes_cost", 0) if ps == "order_placed" else 0,
            "position_status": ps,
            "status": status,
            "timestamp": pos.get("entry_time", ""),
            "pnl": pos.get("pnl", 0) if pos.get("closed") else None,
            "sell_price": pos.get("yes_sell_price") if pos.get("yes_sold") else None,
            "neg_risk": False,
            "side": "YES",
            "end_date": "",
        })

        if pos.get("no_buy_order_id"):
            no_status = "filled" if pos.get("no_filled") else "pending"
            if pos.get("no_sold"):
                no_status = "sold"
            rows.append({
                "bot": bot_id,
                "order_id": pos.get("no_buy_order_id", ""),
                "title": f"{label} Apr {day} — NO @6c [{no_status}]",
                "token_id": "",
                "condition_id": "",
                "entry_price": pos.get("no_entry", 0.06),
                "size_shares": pos.get("no_shares", 0),
                "cost_usd": pos.get("no_cost", 0),
                "status": no_status,
                "timestamp": pos.get("entry_time", ""),
                "pnl": None,
                "sell_price": pos.get("no_sell_price") if pos.get("no_sold") else None,
                "neg_risk": False,
                "side": "NO",
                "end_date": "",
            })

    hedge_spent = data.get("hedge_total_spent", 0)
    hedge_shares = data.get("hedge_total_shares", 0)
    hedge_orders = data.get("hedge_order_ids", [])
    # If hedge orders exist but nothing was actually filled (no chain verification here),
    # treat as limit_order — money is reserved, not invested
    if hedge_spent > 0:
        # Heuristic: if there are unsold orders → likely limit (reserved)
        is_filled = data.get("hedge_filled", False)
        if is_filled:
            status = "filled"
            cost_to_show = hedge_spent
            reserved = 0
            title = f"HEDGE conflict-ends Apr15 — {hedge_shares:.0f} shares [FILLED]"
        else:
            status = "limit_order"
            cost_to_show = 0
            reserved = hedge_spent
            title = f"HEDGE conflict-ends Apr15 — {hedge_shares:.0f} shares (limit @ 4c)"
        rows.append({
            "bot": bot_id,
            "order_id": "hedge",
            "title": title,
            "token_id": "",
            "condition_id": "",
            "entry_price": round(hedge_spent / hedge_shares, 3) if hedge_shares > 0 else 0.04,
            "size_shares": hedge_shares,
            "cost_usd": cost_to_show,
            "reserved_usd": reserved,
            "position_status": "filled" if is_filled else "order_placed",
            "status": status,
            "timestamp": "",
            "pnl": None,
            "sell_price": None,
            "neg_risk": False,
            "side": "YES",
            "end_date": "",
        })

    return rows


def read_bot_stats() -> dict:
    """Read stats from each bot. Returns {bot_id: stats_dict}."""
    result = {}

    for bot_id, bot_cfg in BOTS.items():
        if bot_cfg["type"] in ("scanner", "utility"):
            # Special handling for arb_bot (different data format)
            if bot_id == "arb_bot":
                data_path = bot_cfg["path"] / bot_cfg["data_file"]
                data = _read_json(data_path)
                if data:
                    history = data.get("history", [])
                    # Classify by type field (new format) or fallback to merge_tx (old format)
                    merged = [h for h in history if h.get("type") == "merged" or
                              (not h.get("type") and h.get("merge_tx"))]
                    partial = [h for h in history if h.get("type", "").startswith("partial")]
                    stuck = [h for h in history if h.get("type") == "partial_stuck"]
                    merge_failed = [h for h in history if h.get("type") == "merge_failed"]
                    # Win = successful merge with profit > 0
                    wins = len([h for h in merged if h.get("profit", 0) > 0])
                    # Loss = partial fills (sold back) + merge failures + merged with profit <= 0
                    merged_losses = [h for h in merged if h.get("profit", 0) <= 0]
                    partial_sold = [h for h in history if h.get("type") == "partial_sell"]
                    losses = len(partial_sold) + len(stuck) + len(merge_failed) + len(merged_losses)
                    # PnL = ALL realized outcomes (merges + partial sell losses)
                    realized_pnl = sum(h.get("profit", 0) for h in history
                                       if h.get("type") in ("merged", "partial_sell", "partial_stuck", "merge_failed")
                                       or h.get("merge_tx"))
                    # Open = only stuck positions (partial_stuck = can't sell, tokens on chain)
                    # partial_sell positions are CLOSED (already sold back), NOT open
                    open_count = len(stuck) + len(merge_failed)
                    invested_stuck = sum(h.get("cost", 0) for h in stuck + merge_failed)
                    result[bot_id] = {
                        "current_balance": 0,
                        "total_pnl": realized_pnl,
                        "total_bets": len(history),
                        "wins": wins,
                        "losses": losses,
                        "open": open_count,
                        "invested": invested_stuck,
                    }
                else:
                    result[bot_id] = {
                        "current_balance": 0, "total_pnl": 0, "total_bets": 0,
                        "wins": 0, "losses": 0, "open": 0, "invested": 0,
                    }
            continue

        data_path = bot_cfg["path"] / bot_cfg["data_file"]
        data = _read_json(data_path)
        if not data:
            result[bot_id] = {
                "current_balance": 0, "total_pnl": 0, "total_bets": 0,
                "wins": 0, "losses": 0, "open": 0, "invested": 0,
            }
            continue

        # Iran Daily Trader: new format (YES+NO combo + hedge)
        if bot_id == "24_iran_daily_trader":
            open_pos = [p for p in data.get("open_positions", []) if not p.get("closed")]
            # Only count "filled" as invested; "order_placed" is reserved
            def _ps(p):
                ps = p.get("position_status")
                if ps:
                    return ps
                # Backward-compat
                if p.get("closed") or p.get("yes_sold"):
                    return "closed"
                if p.get("yes_sell_order_id") or p.get("no_buy_order_id"):
                    return "filled"
                return "order_placed"
            filled_pos = [p for p in open_pos if _ps(p) == "filled"]
            order_pos = [p for p in open_pos if _ps(p) == "order_placed"]
            yes_invested = sum(p.get("yes_cost", 0) for p in filled_pos)
            no_invested = sum(p.get("no_cost", 0) for p in filled_pos if p.get("no_filled"))
            reserved = sum(p.get("yes_cost", 0) for p in order_pos)
            hedge_spent = data.get("hedge_total_spent", 0)
            hedge_filled = data.get("hedge_filled", False)
            # Hedge: if not filled, count as reserved (limit order)
            if hedge_filled:
                hedge_invested = hedge_spent
                hedge_reserved = 0
            else:
                hedge_invested = 0
                hedge_reserved = hedge_spent
            entered = len(data.get("entered_keys", []))
            result[bot_id] = {
                "current_balance": 0,
                "total_pnl": data.get("total_pnl", 0),
                "total_bets": entered,
                "wins": 0,
                "losses": 0,
                "open": len(open_pos),
                "filled_count": len(filled_pos),
                "order_count": len(order_pos),
                "reserved": reserved + hedge_reserved,
                "invested": yes_invested + no_invested + hedge_invested,
            }
            continue

        if isinstance(data, list):
            # Weather bot format: list of position dicts
            open_pos = [p for p in data if isinstance(p, dict) and p.get("status") == "open"]
            all_resolved = [p for p in data if isinstance(p, dict) and p.get("status") == "resolved"]
            wins = sum(1 for p in all_resolved if (p.get("pnl") or 0) > 0)
            losses = len(all_resolved) - wins
            total_pnl = sum(p.get("pnl", 0) or 0 for p in all_resolved)
            invested = sum(p.get("cost", 0) or 0 for p in open_pos)
            result[bot_id] = {
                "current_balance": 0, "total_pnl": total_pnl, "total_bets": len(data),
                "wins": wins, "losses": losses, "open": len(open_pos), "invested": invested,
            }
            continue
        stats = data.get("stats", {})
        positions = data.get("positions", {})
        # Count only filled positions (actually held), not pending open orders
        active_statuses = ("open", "filled") if bot_id != "27_overround_bot" else ("filled",)
        open_positions = [p for p in positions.values() if p.get("status") in active_statuses]
        invested = sum(p.get("cost_usd", 0) for p in open_positions)
        result[bot_id] = {
            "current_balance": stats.get("current_balance", 0),
            "total_pnl": stats.get("total_pnl", 0),
            "total_bets": stats.get("total_bets", 0),
            "wins": stats.get("wins", 0),
            "losses": stats.get("losses", 0),
            "open": len(open_positions),
            "invested": invested,
        }

    return result


def _fetch_market_info(token_id: str) -> dict:
    """Fetch end_date and URL for a market from Gamma API by token_id."""
    if token_id in _market_cache:
        return _market_cache[token_id]
    info = {"end_date": None, "url": None}
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"clob_token_ids": token_id, "limit": 1},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data and isinstance(data, list):
            m = data[0]
            info["end_date"] = m.get("endDate", "")
            # Build Polymarket URL from event slug + market slug
            market_slug = m.get("slug", "")
            events = m.get("events", [])
            if events and isinstance(events, list):
                event_slug = events[0].get("slug", "")
                if event_slug and market_slug:
                    info["url"] = f"https://polymarket.com/event/{event_slug}/{market_slug}"
                elif event_slug:
                    info["url"] = f"https://polymarket.com/event/{event_slug}"
            elif market_slug:
                info["url"] = f"https://polymarket.com/market/{market_slug}"
    except Exception as e:
        log.debug("Failed to fetch market info for token %s: %s", token_id[:20], e)
    _market_cache[token_id] = info
    return info


def _fetch_market_info_batch(token_ids: list[str]) -> None:
    """Fetch market info for multiple token_ids, using cache."""
    global _market_cache_ts
    now = time.time()
    if now - _market_cache_ts < _MARKET_CACHE_TTL:
        return  # Cache still fresh
    _market_cache_ts = now

    for tid in token_ids:
        if tid and tid not in _market_cache:
            _fetch_market_info(tid)


_bg_fetch_done = False


def warm_cache_background() -> None:
    """Warm the market info cache in a background thread at startup using parallel requests."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    def _worker():
        global _bg_fetch_done
        try:
            # Collect token_ids from all trading bots
            all_token_ids = []
            for bot_id, bot_cfg in BOTS.items():
                if bot_cfg["type"] in ("scanner", "utility"):
                    continue
                data_path = bot_cfg["path"] / bot_cfg["data_file"]
                data = _read_json(data_path)
                if not data:
                    continue
                # Handle both dict format (98_sure_bot) and list format (weather_bot)
                if isinstance(data, dict):
                    positions = data.get("positions", {}).values()
                elif isinstance(data, list):
                    positions = [p for p in data if isinstance(p, dict)]
                else:
                    continue
                for p in positions:
                    tid = p.get("token_id", "")
                    if tid and tid not in _market_cache:
                        all_token_ids.append(tid)

            if not all_token_ids:
                return

            log.info("Warming market cache for %d tokens (parallel)...", len(all_token_ids))
            with ThreadPoolExecutor(max_workers=10) as pool:
                pool.map(_fetch_market_info, all_token_ids)
            _bg_fetch_done = True
            log.info("Market cache warmed: %d entries", len(_market_cache))
        except Exception as e:
            log.error("Cache warm failed: %s", e)

    threading.Thread(target=_worker, daemon=True).start()


def get_market_info(token_id: str) -> dict:
    """Get market info (end_date, url) for a token_id. Fetches on cache miss."""
    if token_id and token_id not in _market_cache:
        _fetch_market_info(token_id)
    return _market_cache.get(token_id, {"end_date": None, "url": None})


def read_sure_bot_stats() -> dict | None:
    """Read detailed stats for 98_sure_bot including timing metrics."""
    bot_cfg = BOTS.get("98_sure_bot")
    if not bot_cfg:
        return None

    data_path = bot_cfg["path"] / bot_cfg["data_file"]
    data = _read_json(data_path)
    if not data:
        return None

    stats = data.get("stats", {})
    positions = data.get("positions", {})

    open_p = [p for p in positions.values() if p.get("status") == "open"]
    won_p = [p for p in positions.values() if p.get("status") == "won"]
    lost_p = [p for p in positions.values() if p.get("status") == "lost"]
    total_resolved = len(won_p) + len(lost_p)
    win_rate = len(won_p) / total_resolved * 100 if total_resolved > 0 else 0

    invested = sum(p.get("cost_usd", 0) for p in open_p)

    # Avg time to redeem (buy -> resolved_at)
    redeem_hours = []
    for p in positions.values():
        if p.get("resolved_at") and p.get("timestamp"):
            try:
                ts = datetime.fromisoformat(p["timestamp"])
                ra = datetime.fromisoformat(p["resolved_at"])
                diff_h = (ra - ts).total_seconds() / 3600
                if diff_h > 0:
                    redeem_hours.append(diff_h)
            except (ValueError, TypeError):
                pass

    avg_redeem_h = sum(redeem_hours) / len(redeem_hours) if redeem_hours else None

    # Avg time from buy to end_date (uses background-warmed cache)
    buy_to_end_hours = []
    for p in positions.values():
        tid = p.get("token_id", "")
        ts_str = p.get("timestamp", "")
        if not tid or not ts_str:
            continue
        info = _market_cache.get(tid, {})
        end_date_str = info.get("end_date") if info else None
        if not end_date_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
            ed = datetime.fromisoformat(end_date_str)
            # Make both offset-aware or offset-naive for comparison
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ed.tzinfo is None:
                ed = ed.replace(tzinfo=timezone.utc)
            diff_h = (ed - ts).total_seconds() / 3600
            if diff_h > 0:
                buy_to_end_hours.append(diff_h)
        except (ValueError, TypeError):
            pass

    avg_buy_to_end_h = sum(buy_to_end_hours) / len(buy_to_end_hours) if buy_to_end_hours else None

    return {
        "total_bets": stats.get("total_bets", 0),
        "wins": stats.get("wins", 0),
        "losses": stats.get("losses", 0),
        "total_pnl": stats.get("total_pnl", 0),
        "current_balance": stats.get("current_balance", 0),
        "win_rate": win_rate,
        "open": len(open_p),
        "invested": invested,
        "resolved": total_resolved,
        "avg_redeem_hours": avg_redeem_h,
        "redeem_count": len(redeem_hours),
        "avg_buy_to_end_hours": avg_buy_to_end_h,
        "buy_to_end_count": len(buy_to_end_hours),
    }


def read_scanner_stats() -> dict | None:
    """Read 97_scanner stats using streaming parser to avoid loading 177MB+ into memory."""
    import ijson

    bot_cfg = BOTS.get("97_scanner")
    if not bot_cfg:
        return None

    data_path = bot_cfg["path"] / bot_cfg["data_file"]
    if not data_path.exists():
        return None

    scans = 0
    started = ""
    total = 0
    resolved = 0
    won = 0
    lost = 0

    try:
        with open(data_path, "rb") as f:
            # Stream top-level keys without loading full file
            parser = ijson.items(f, "scans")
            for val in parser:
                scans = val
                break

        with open(data_path, "rb") as f:
            parser = ijson.items(f, "started")
            for val in parser:
                started = val
                break

        # Stream each market one by one — constant memory
        # markets is a dict {key: {market_data}}, use kvitems
        with open(data_path, "rb") as f:
            for key, market in ijson.kvitems(f, "markets"):
                total += 1
                res = market.get("resolution") if isinstance(market, dict) else None
                if res and isinstance(res, dict) and res.get("closed"):
                    resolved += 1
                    winner = res.get("winner", "")
                    high_outcome = market.get("high_outcome", "")
                    if winner and high_outcome and winner == high_outcome:
                        won += 1
                    else:
                        lost += 1

    except ImportError:
        # Fallback: ijson not installed — load full file but warn
        log.warning("ijson not installed, loading full scanner_data.json into memory")
        data = _read_json(data_path)
        if not data:
            return None
        markets = data.get("markets", {})
        total = len(markets)
        scans = data.get("scans", 0)
        started = data.get("started", "")
        for m in markets.values():
            res = m.get("resolution")
            if res and isinstance(res, dict) and res.get("closed"):
                resolved += 1
                winner = res.get("winner", "")
                high_outcome = m.get("high_outcome", "")
                if winner and high_outcome and winner == high_outcome:
                    won += 1
                else:
                    lost += 1
    except Exception as e:
        log.error("Scanner stats error: %s", e)
        return None

    return {
        "total_markets": total,
        "resolved": resolved,
        "won": won,
        "lost": lost,
        "win_rate": (won / resolved * 100) if resolved > 0 else 0,
        "scans": scans,
        "started": started,
    }


def read_oil_calibration() -> dict | None:
    """Read theta_calibration.json from oil swing bot."""
    bot_cfg = BOTS.get("10_oil_swing_bot")
    if not bot_cfg:
        return None
    data = _read_json(bot_cfg["path"] / "theta_calibration.json")
    if not data or "days" not in data:
        return None
    return data


def mark_position_selling(bot_id: str, order_id: str, sell_order_id: str,
                          sell_price: float, sell_shares: float) -> bool:
    """Mark a position as 'selling' in the bot's positions.json.
    Returns True on success.
    """
    bot_cfg = BOTS.get(bot_id)
    if not bot_cfg:
        return False

    data_path = bot_cfg["path"] / bot_cfg.get("data_file", "positions.json")
    data = _read_json(data_path)
    if not data:
        return False

    pos = data.get("positions", {}).get(order_id)
    if not pos:
        log.warning("Position %s not found in %s", order_id[:16], bot_id)
        return False

    pos["status"] = "selling"
    pos["sell_order_id"] = sell_order_id
    pos["sell_price"] = sell_price
    pos["sell_shares"] = sell_shares
    pos["sell_timestamp"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()

    try:
        import os
        tmp = str(data_path) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, str(data_path))
        log.info("Marked %s as selling in %s", order_id[:16], bot_id)
        return True
    except OSError as e:
        log.error("Failed to update %s: %s", data_path, e)
        return False


def read_tuner_report() -> dict | None:
    """Read tuner_report.json from oil swing bot (Smart Tuner output)."""
    bot_cfg = BOTS.get("10_oil_swing_bot")
    if not bot_cfg:
        return None
    data = _read_json(bot_cfg["path"] / "tuner_report.json")
    if not data or "regime" not in data:
        return None
    return data


def read_arb_bot() -> dict | None:
    """Read Arb Bot stats: scan log + execution history."""
    bot_cfg = BOTS.get("arb_bot")
    if not bot_cfg:
        return None

    bot_path = bot_cfg["path"]

    # 1. Stats (arb_stats.json)
    stats = _read_json(bot_path / "arb_stats.json") or {
        "total_arbs": 0, "total_profit": 0.0, "total_volume": 0.0, "history": []
    }

    # 2. Scan log (scan_log.json) — last 500 entries
    scan_log = _read_json(bot_path / "scan_log.json") or []
    if isinstance(scan_log, list):
        scan_log = scan_log[-500:]

    total_scans = len(scan_log)
    scans_with_opps = sum(1 for s in scan_log if s.get("num_opportunities", 0) > 0)
    skipped_reasons = {}
    for s in scan_log:
        r = s.get("skipped_reason")
        if r:
            skipped_reasons[r] = skipped_reasons.get(r, 0) + 1

    first_scan = scan_log[0].get("timestamp", "") if scan_log else ""
    last_scan = scan_log[-1].get("timestamp", "") if scan_log else ""

    # 3. DRY_RUN status
    env_path = bot_path / ".env"
    dry_run = False
    if env_path.exists():
        try:
            text = env_path.read_text(encoding="utf-8")
            dry_run = "DRY_RUN=1" in text
        except Exception:
            pass

    history = stats.get("history", [])
    merged = [h for h in history if h.get("merge_tx")]

    return {
        "total_arbs": len(merged),
        "total_attempts": len(history),
        "total_profit": sum(h.get("profit", 0) for h in merged),
        "total_cost": sum(h.get("cost", 0) for h in history),
        "total_recovered": sum(h.get("profit", 0) + h.get("cost", 0) for h in merged),
        "total_volume": stats.get("total_volume", 0.0),
        "history": history,
        "total_scans": total_scans,
        "scans_with_opps": scans_with_opps,
        "skipped_reasons": skipped_reasons,
        "first_scan": first_scan,
        "last_scan": last_scan,
        "dry_run": dry_run,
    }


def read_iran_signal_bot() -> dict | None:
    """Read Iran Signal Bot data: recent signals, positions, hedge state."""
    bot_cfg = BOTS.get("9_iran_signal")
    if not bot_cfg:
        return None

    bot_path = bot_cfg["path"]
    data_dir = bot_path / "data"

    # 1. Recent signals from signals.jsonl (last 20)
    signals = []
    signals_file = data_dir / "signals.jsonl"
    if signals_file.exists():
        try:
            lines = signals_file.read_text(encoding="utf-8").strip().split("\n")
            for line in lines[-20:]:
                line = line.strip()
                if line:
                    try:
                        signals.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            signals.reverse()  # newest first
        except Exception as e:
            log.warning("Failed to read signals.jsonl: %s", e)

    # 2. Positions from positions.json
    positions_data = _read_json(data_dir / "positions.json")
    positions = {}
    total_invested = 0
    if positions_data:
        positions = positions_data.get("positions", {})
        total_invested = sum(p.get("size_usd", 0) for p in positions.values())

    # 3. Hedge state
    hedge_data = _read_json(data_dir / "hedge_state.json")
    hedge_enabled = False
    hedge_daily = 0
    hedge_orders_today = 0
    pending_proposals = 0
    if hedge_data:
        hedge_enabled = hedge_data.get("enabled", False)
        hedge_daily = hedge_data.get("daily_total_usd", 0)
        hedge_orders_today = len(hedge_data.get("hedge_log", []))
        pending_proposals = len(hedge_data.get("pending", {}))

    # 4. Market cache stats
    iran_markets = _read_json(data_dir / "iran_markets.json")
    n_markets = 0
    if iran_markets:
        if isinstance(iran_markets, dict) and "markets" in iran_markets:
            n_markets = len(iran_markets["markets"])
        elif isinstance(iran_markets, list):
            n_markets = len(iran_markets)

    # 5. Signal counts (last 24h and 1h)
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    signals_1h = 0
    signals_24h = 0
    high_24h = 0
    medium_24h = 0
    for s in signals:
        ts_str = s.get("timestamp", s.get("_timestamp", ""))
        try:
            ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age = now - ts
            if age < timedelta(hours=1):
                signals_1h += 1
            if age < timedelta(hours=24):
                signals_24h += 1
                conf = s.get("confidence", "").upper()
                if conf == "HIGH":
                    high_24h += 1
                elif conf == "MEDIUM":
                    medium_24h += 1
        except (ValueError, TypeError):
            pass

    return {
        "signals_recent": signals[:10],
        "signals_1h": signals_1h,
        "signals_24h": signals_24h,
        "high_24h": high_24h,
        "medium_24h": medium_24h,
        "positions": positions,
        "total_invested": total_invested,
        "n_positions": len(positions),
        "hedge_enabled": hedge_enabled,
        "hedge_daily_usd": hedge_daily,
        "hedge_orders_today": hedge_orders_today,
        "pending_proposals": pending_proposals,
        "n_markets": n_markets,
    }


def read_multi_signal_bot() -> dict | None:
    """Read Multi-Signal Copy-Bot state: positions, stats, mode."""
    bot_cfg = BOTS.get("25_multi_signal_copybot")
    if not bot_cfg:
        return None

    data_path = bot_cfg["path"] / bot_cfg["data_file"]
    data = _read_json(data_path)
    if not data:
        return {
            "mode": "test",
            "bankroll": 0,
            "current_balance": 0,
            "total_pnl": 0,
            "total_bets": 0,
            "wins": 0,
            "losses": 0,
            "open": 0,
            "invested": 0,
            "positions": [],
        }

    stats = data.get("stats", {})
    positions = data.get("positions", {})
    open_positions = [p for p in positions.values() if p.get("status") == "open"]
    closed_positions = [p for p in positions.values() if p.get("status") in ("won", "lost", "sold")]
    invested = sum(p.get("cost_usd", 0) for p in open_positions)

    # Read mode from bot's config.py
    mode = "test"
    try:
        bot_path = bot_cfg["path"]
        config_path = bot_path / "config.py"
        if config_path.exists():
            text = config_path.read_text(encoding="utf-8")
            for line in text.splitlines():
                line = line.strip()
                if line.startswith("BOT_MODE"):
                    if '"live"' in line or "'live'" in line:
                        mode = "live"
                    break
    except Exception:
        pass

    # Build open positions list for display
    open_list = []
    for oid, pos in positions.items():
        if pos.get("status") == "open":
            open_list.append({
                "title": pos.get("title", ""),
                "entry_price": pos.get("entry_price", 0),
                "size_shares": pos.get("size_shares", 0),
                "cost_usd": pos.get("cost_usd", 0),
                "signal_player": pos.get("signal_player", ""),
                "side": pos.get("side", "YES"),
                "timestamp": pos.get("timestamp", ""),
            })

    return {
        "mode": mode,
        "bankroll": stats.get("current_balance", stats.get("peak_balance", 0)),
        "current_balance": stats.get("current_balance", 0),
        "total_pnl": stats.get("total_pnl", 0),
        "total_bets": stats.get("total_bets", 0),
        "wins": stats.get("wins", 0),
        "losses": stats.get("losses", 0),
        "open": len(open_positions),
        "invested": invested,
        "positions": open_list,
    }


def read_iran_daily_trader() -> dict | None:
    """Read Iran+Hezbollah Daily Trader state: positions, hedge, P&L."""
    bot_cfg = BOTS.get("24_iran_daily_trader")
    if not bot_cfg:
        return None

    bot_path = bot_cfg["path"]
    data_dir = bot_path / "data"

    # 1. State file (new format)
    state = _read_json(data_dir / "state.json")
    if not state:
        state = {}

    # 2. Trades from trades.jsonl (last 30)
    trades = []
    trades_file = data_dir / "trades.jsonl"
    if trades_file.exists():
        try:
            lines = trades_file.read_text(encoding="utf-8").strip().split("\n")
            for line in lines[-30:]:
                line = line.strip()
                if line:
                    try:
                        trades.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            trades.reverse()
        except Exception as e:
            log.warning("Failed to read trades.jsonl: %s", e)

    # 3. Open positions (new format)
    open_positions = [p for p in state.get("open_positions", []) if not p.get("closed")]
    iran_positions = [p for p in open_positions if p.get("event_type") == "iran"]
    hez_positions = [p for p in open_positions if p.get("event_type") == "hez"]

    # 4. P&L
    total_pnl = state.get("total_pnl", 0)
    wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
    losses = sum(1 for t in trades if t.get("pnl", 0) < 0)
    total_trades = wins + losses

    # 5. Invested
    total_yes_invested = sum(p.get("yes_cost", 0) for p in open_positions)
    total_no_invested = sum(p.get("no_cost", 0) for p in open_positions if p.get("no_filled"))

    # 6. Hedge
    hedge_spent = state.get("hedge_total_spent", 0)
    hedge_shares = state.get("hedge_total_shares", 0)
    yes_fills = state.get("yes_fills_count", 0)

    # 7. Entered keys
    entered = state.get("entered_keys", [])

    return {
        "open_positions": len(open_positions),
        "iran_positions": iran_positions,
        "hez_positions": hez_positions,
        "total_invested": total_yes_invested + total_no_invested + hedge_spent,
        "yes_invested": total_yes_invested,
        "no_invested": total_no_invested,
        "total_pnl": total_pnl,
        "wins": wins,
        "losses": losses,
        "win_rate": (wins / total_trades * 100) if total_trades > 0 else 0,
        "total_trades": total_trades,
        "trades_recent": trades[:10],
        "hedge_spent": hedge_spent,
        "hedge_shares": hedge_shares,
        "yes_fills_count": yes_fills,
        "entered_keys": entered,
    }
