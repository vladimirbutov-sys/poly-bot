"""Buy: $75 NO Apr 27 + $75 NO Apr 28 diplomatic meeting markets."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

ORDERS = [
    {
        "cid":   "0xe208a07bd71069b04e3b89de92f71da8b155d45dc2e527dc46c3ceb2a63b307b",
        "token": "92079910675159907375467354284229768948316964233795313847482829094812147958054",
        "title": "US x Iran diplomatic meeting by April 27, 2026?",
        "limit": 0.95,
        "size":  75.0,
        "tag":   "apr27",
    },
    {
        "cid":   "0x9967297556e4fd7f7e1e688a2e44d6fdbc42b0700576a1e4e67aa37764ac640a",
        "token": "42277247300059455315872150222700537525647929202778246138550488342397262489345",
        "title": "US x Iran diplomatic meeting by April 28, 2026?",
        "limit": 0.92,
        "size":  75.0,
        "tag":   "apr28",
    },
]

for o in ORDERS:
    print(f"\n=== {o['title']} ===")
    print(f"BUY No @ ${o['limit']}, size ${o['size']}")
    result = executor.place_limit_buy(token_id=o['token'], price=o['limit'], size_usd=o['size'])
    if not result or not result.get('order_id'):
        print(f"PLACE FAILED for {o['tag']}")
        continue
    oid = result['order_id']
    print(f"  ORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")

    fill = executor.wait_for_fill_with_details(oid, timeout=120)
    matched = float(fill.get('size_matched', 0) or 0)
    print(f"  status={fill.get('status')} matched={matched:.2f}/{fill.get('size_original'):.2f}")
    if matched < 0.5:
        print(f"  Nothing filled for {o['tag']}")
        continue

    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if real and real['size'] > 0 else o['limit']
    actual_cost = round(matched * actual_price, 2)
    print(f"  VWAP ${actual_price:.4f} cost ${actual_cost:.2f}")

    data = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{o['cid']}_{o['token']}_{time.time()}".encode()).hexdigest()[:32]
    data.setdefault('positions', {})[new_key] = {
        "condition_id": o['cid'], "token_id": o['token'], "title": o['title'],
        "outcome": "No", "event_slug": "us-x-iran-diplomatic-meeting-by-329",
        "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
        "size_shares": round(matched, 2), "cost_usd": actual_cost,
        "tier": "manual", "strategy": "manual", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1, "order_ids": [oid],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": f"manual_buy_2026-04-25_diplomatic_{o['tag']}_no_75usd",
    }
    tracker.save(data)
    print(f"  OK Recorded {o['tag']}: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
    time.sleep(2)
