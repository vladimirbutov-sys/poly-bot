"""Dry-run mode for Variant 1: observes live denizz events, simulates tier-upgrade
decisions under BOTH legacy (buf.last_tier_bet) and Variant 1 (tracker.cost_usd)
paths, logs the DIFFERENCE without placing any orders.

Run as a SEPARATE process alongside the live bot. Reads live buy_buffers.json
and positions.json (read-only), polls denizz activity via data-api.

Output: _analytics/dry_run_variant1.jsonl (one JSON line per event)
"""
import sys, os, json, time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import filters
import tracker
from config import (
    PLAYERS, DATA_API, MIN_PLAYER_INVESTED, MIN_UPGRADE_USD,
    BOT_DIR,
)

OUTPUT_LOG = os.path.join(BOT_DIR, "_analytics", "dry_run_variant1.jsonl")
os.makedirs(os.path.dirname(OUTPUT_LOG), exist_ok=True)

POLL_INTERVAL = 10  # seconds between denizz activity polls
_seen_tx = set()


def _load_live_buffers() -> dict:
    """Read live buy_buffers.json (read-only)."""
    path = os.path.join(BOT_DIR, "buy_buffers.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"buffers": {}, "signaled": {}}


def _log_event(rec: dict):
    rec["ts"] = datetime.now(timezone.utc).isoformat()
    with open(OUTPUT_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _simulate_decisions(player_name: str, wallet: str, event: dict):
    """For a denizz BUY event, simulate tier-upgrade under both paths."""
    cid = event.get("conditionId", "")
    token_id = str(event.get("asset", ""))
    title = event.get("title", "")
    price = float(event.get("price", 0) or 0)
    usd = float(event.get("usdcSize", 0) or 0)

    if not cid or not token_id or usd < 1:
        return

    # Load live state (read-only)
    try:
        live_buffers = _load_live_buffers()
        live_data = tracker.load()
    except Exception as e:
        _log_event({"type": "ERROR", "stage": "load_state", "error": str(e)})
        return

    buf_key = f"{cid}_{token_id}"
    player_bufs = live_buffers.get("buffers", {}).get(player_name, {})
    buf = player_bufs.get(buf_key, {})
    buf_last_tier_bet = float(buf.get("last_tier_bet", 0.0) or 0.0)
    buf_total_spent = float(buf.get("total_usd", 0.0) or 0.0) + usd

    # Denizz's real invested on this token (data-api)
    try:
        real_invested = filters.get_player_invested_on_token(cid, wallet, token_id)
    except Exception:
        real_invested = 0.0
    effective_invested = max(buf_total_spent, real_invested)

    min_invested = MIN_PLAYER_INVESTED.get(player_name, 500)
    if effective_invested < min_invested:
        return  # Below signal threshold

    # Compute formula new_bet
    try:
        new_bet = filters.calculate_bet_size(player_name, effective_invested, price)
    except Exception as e:
        _log_event({"type": "ERROR", "stage": "calc_bet", "error": str(e)})
        return

    # Variant 1 cost (live tracker, filtered by status==open)
    v1_cost, v1_last_ts = tracker.get_cost_on_token(live_data, cid, token_id)

    # Decisions
    legacy_increment = round(new_bet - buf_last_tier_bet, 2)
    v1_increment = round(new_bet - v1_cost, 2)

    legacy_would_fire = legacy_increment >= MIN_UPGRADE_USD
    v1_would_fire = v1_increment >= MIN_UPGRADE_USD

    diverged = legacy_would_fire != v1_would_fire or abs(legacy_increment - v1_increment) > 1.0

    rec = {
        "type": "SIMULATE",
        "diverged": diverged,
        "title": title[:80],
        "cid": cid[:16],
        "token": token_id[:16],
        "price": price,
        "denizz_new_buy_usd": usd,
        "effective_invested": round(effective_invested, 2),
        "new_bet_formula": round(new_bet, 2),
        "legacy": {
            "already_bet": buf_last_tier_bet,
            "increment": legacy_increment,
            "would_fire": legacy_would_fire,
        },
        "variant1": {
            "already_bet": v1_cost,
            "increment": v1_increment,
            "would_fire": v1_would_fire,
            "tracker_age_sec": int(time.time()) - v1_last_ts if v1_last_ts else None,
        },
    }
    _log_event(rec)

    if diverged:
        print(f"[DRY-RUN DIVERGE] {title[:50]} | legacy_fire={legacy_would_fire} inc=${legacy_increment:.0f} "
              f"| v1_fire={v1_would_fire} inc=${v1_increment:.0f}")
    else:
        print(f"[DRY-RUN same ] {title[:50]} | inc=${legacy_increment:.0f} (both paths agree)")


def _poll_denizz_activity():
    """Poll recent denizz BUY events and simulate decisions."""
    wallet = PLAYERS.get("denizz", "").lower()
    if not wallet:
        print("ERROR: denizz not in PLAYERS")
        return

    r = requests.get(
        f"{DATA_API}/activity",
        params={"user": wallet, "limit": 50},
        timeout=15,
    )
    if not r.ok:
        return
    events = r.json() or []
    # Process oldest-first
    events.sort(key=lambda x: x.get("timestamp", 0))
    for e in events:
        tx = e.get("transactionHash", "")
        if not tx or tx in _seen_tx:
            continue
        _seen_tx.add(tx)
        side = (e.get("side") or "").upper()
        ev_type = (e.get("type") or "").upper()
        if ev_type == "TRADE" and side == "BUY":
            _simulate_decisions("denizz", wallet, e)


def main():
    print("=" * 60)
    print("DRY-RUN Variant 1 — observing denizz events")
    print(f"Output log: {OUTPUT_LOG}")
    print(f"Poll interval: {POLL_INTERVAL}s")
    print("Press Ctrl+C to stop.")
    print("=" * 60)

    # Mark existing events as seen (only simulate NEW events)
    wallet = PLAYERS.get("denizz", "").lower()
    try:
        r = requests.get(
            f"{DATA_API}/activity",
            params={"user": wallet, "limit": 50},
            timeout=15,
        )
        initial = r.json() or []
        for e in initial:
            tx = e.get("transactionHash", "")
            if tx:
                _seen_tx.add(tx)
        print(f"[DRY-RUN] Marked {len(_seen_tx)} existing events as seen — watching for new only")
    except Exception as e:
        print(f"[DRY-RUN] init error: {e}")

    while True:
        try:
            _poll_denizz_activity()
        except KeyboardInterrupt:
            print("\n[DRY-RUN] Stopped.")
            return
        except Exception as e:
            print(f"[DRY-RUN] poll error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
