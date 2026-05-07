"""Collect Iran/US-related positions and fetch hourly price history.

Task A of 4-part Polymarket analysis. Filters positions by Iran/Israel/US
theme keywords and fetches hourly price history from Polymarket CLOB.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(r"C:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot_v2")
POSITIONS_FILE = ROOT / "positions.json"
OUT_FILE = ROOT / "_analytics" / "data" / "iran_positions_and_prices.json"

KEYWORDS = [
    "iran",
    "israel",
    "hormuz",
    "peace deal",
    "ceasefire",
    "conflict ends",
    "blockade",
    "military action",
    "diplomatic meeting",
    "nuclear",
    "uranium",
    "hamas",
    "vance",
]

EXCLUDE_SLUGS = [
    "russia", "ukraine", "pakistan", "venezuela", "maduro",
    "trump-potus", "trump-potus-post",
]

EXCLUDE_TITLE_SUBSTR = [
    "Russia", "Ukraine", "Pakistan", "Venezuela", "Maduro",
]


def matches_iran_theme(pos):
    title = (pos.get("title") or "").lower()
    slug = (pos.get("event_slug") or "").lower()
    blob = f"{title} {slug}"

    # Explicit exclusions first (but only if no Iran/Israel/etc. keyword present)
    has_core_kw = any(k in blob for k in ["iran", "israel", "hormuz", "hamas", "uranium", "vance"])

    for ex in EXCLUDE_SLUGS:
        if ex in slug and not has_core_kw:
            return False
    for ex in EXCLUDE_TITLE_SUBSTR:
        if ex.lower() in title and not has_core_kw:
            return False

    for kw in KEYWORDS:
        if kw in blob:
            return True
    return False


def fetch_price_history(token_id, start_ts=None, end_ts=None, retries=3):
    """Try a few param combinations for the CLOB prices-history endpoint."""
    base = "https://clob.polymarket.com/prices-history"
    attempts = []

    if start_ts and end_ts:
        attempts.append({"market": str(token_id), "startTs": int(start_ts), "endTs": int(end_ts), "fidelity": 60})
    attempts.append({"market": str(token_id), "interval": "1w", "fidelity": 60})
    attempts.append({"market": str(token_id), "interval": "max", "fidelity": 60})
    attempts.append({"market": str(token_id), "interval": "1m", "fidelity": 60})

    last_err = None
    for params in attempts:
        for attempt in range(retries):
            try:
                r = requests.get(base, params=params, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    pts = data.get("history") or []
                    if pts:
                        return pts, None
                    # empty history
                    last_err = f"empty history for params={params}"
                    break
                else:
                    last_err = f"HTTP {r.status_code}: {r.text[:200]}"
                    if r.status_code in (429, 502, 503, 504):
                        time.sleep(1.5 * (attempt + 1))
                        continue
                    break
            except Exception as e:
                last_err = f"exception: {e}"
                time.sleep(1.0 * (attempt + 1))
        # loop to next param variant

    return [], last_err


def main():
    with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    all_positions = data.get("positions", {})
    matched = []
    for key, pos in all_positions.items():
        if matches_iran_theme(pos):
            rec = {
                "position_key": key,
                "token_id": pos.get("token_id"),
                "condition_id": pos.get("condition_id"),
                "title": pos.get("title"),
                "event_slug": pos.get("event_slug"),
                "outcome": pos.get("outcome"),
                "entry_price": pos.get("entry_price"),
                "avg_entry": pos.get("avg_entry"),
                "size_shares": pos.get("size_shares"),
                "cost_usd": pos.get("cost_usd"),
                "timestamp": pos.get("timestamp"),
                "status": pos.get("status"),
                "sells": pos.get("sells", []),
                "final_pnl": pos.get("final_pnl"),
                "tier": pos.get("tier"),
                "signal_player": pos.get("signal_player"),
                "parts_filled": pos.get("parts_filled"),
                "parts_planned": pos.get("parts_planned"),
            }
            matched.append(rec)

    print(f"Matched positions: {len(matched)}")

    # Unique token_ids with earliest timestamp
    tokens = {}
    for p in matched:
        tid = p["token_id"]
        if not tid:
            continue
        ts_str = p.get("timestamp")
        if ts_str:
            try:
                ts = int(datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp())
            except Exception:
                ts = None
        else:
            ts = None
        if tid not in tokens or (ts is not None and (tokens[tid] is None or ts < tokens[tid])):
            tokens[tid] = ts

    now_ts = int(datetime.now(timezone.utc).timestamp())

    price_history = {}
    failures = {}
    for i, (tid, start_ts) in enumerate(tokens.items()):
        print(f"[{i+1}/{len(tokens)}] Fetching token {tid[:20]}...")
        # widen range slightly
        s = (start_ts - 3600) if start_ts else None
        pts, err = fetch_price_history(tid, start_ts=s, end_ts=now_ts)
        if not pts:
            failures[tid] = err or "no data"
            price_history[tid] = []
            print(f"   FAILED: {err}")
        else:
            out_pts = []
            for pt in pts:
                t = pt.get("t")
                pr = pt.get("p")
                if t is None:
                    continue
                out_pts.append({
                    "ts": int(t),
                    "ts_iso": datetime.fromtimestamp(int(t), tz=timezone.utc).isoformat(),
                    "price": pr,
                })
            price_history[tid] = out_pts
            print(f"   OK: {len(out_pts)} points (first={out_pts[0]['ts_iso'] if out_pts else '-'}, last={out_pts[-1]['ts_iso'] if out_pts else '-'})")
        time.sleep(0.3)

    # Summary
    open_positions = [p for p in matched if p["status"] == "open"]
    closed_positions = [p for p in matched if p["status"] == "sold"]
    total_cost_open = sum((p.get("cost_usd") or 0) for p in open_positions)
    total_realized_pnl = sum((p.get("final_pnl") or 0) for p in closed_positions)

    summary = {
        "total_positions": len(matched),
        "open_positions": len(open_positions),
        "closed_positions": len(closed_positions),
        "total_cost_open": round(total_cost_open, 4),
        "total_realized_pnl": round(total_realized_pnl, 4),
        "unique_tokens": len(tokens),
        "price_fetch_failures": len(failures),
    }

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "positions": matched,
        "price_history": price_history,
        "failures": failures,
        "summary": summary,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))
    print(f"\nSaved to: {OUT_FILE}")

    # Concise list for report
    print("\n=== POSITIONS ===")
    for p in matched:
        mark = ""
        tid = p["token_id"]
        if tid and price_history.get(tid):
            last = price_history[tid][-1]["price"]
            mark = f" last_mkt={last}"
        print(f"- [{p['status']:<6}] {p['title'][:60]:<60} outcome={p['outcome']:<3} cost=${p.get('cost_usd',0):.2f} pnl={p.get('final_pnl') if p['status']=='sold' else 'N/A'}{mark}")


if __name__ == "__main__":
    main()
