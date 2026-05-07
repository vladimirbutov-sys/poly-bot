"""Top-up $20 YES on Strait of Hormuz traffic returns to normal by April 30 @ ask $0.29."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x924a2942747dd75703321a7c8d809c68f6a514c3b0f2a2e64274e02310634669"
TOKEN = "77893140510362582253172593084218413010407941075415081594586195705930819989216"
TITLE = "Strait of Hormuz traffic returns to normal by end of April?"
SLUG  = "strait-of-hormuz-traffic-returns-to-normal-by-april-30"
LIMIT_PRICE = 0.29
SIZE_USD = 20.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"bid/ask: ${bid:.3f}/${ask:.3f}  limit ${LIMIT_PRICE}")

res = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not res or not res.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = res['order_id']
print(f"ORDER LIVE: {oid[:24]}... size={res.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get('size_matched', 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else LIMIT_PRICE
    actual_cost = round(matched * actual_price, 2)
    print(f"  VWAP ${actual_price:.4f}  cost ${actual_cost:.2f}")

    data = tracker.load()
    # Try to find existing YES position to top-up
    found_key = None
    for k, p in data.get("positions", {}).items():
        if p.get("token_id") == TOKEN and p.get("status") == "open" and p.get("outcome") == "Yes":
            found_key = k; break

    if found_key:
        p = data["positions"][found_key]
        old_sh = float(p.get("size_shares", 0))
        old_cost = float(p.get("cost_usd", 0))
        new_sh = old_sh + matched
        new_cost = round(old_cost + actual_cost, 4)
        new_avg = new_cost / new_sh if new_sh > 0 else 0
        p["size_shares"] = round(new_sh, 4)
        p["cost_usd"] = new_cost
        p["avg_entry"] = round(new_avg, 6)
        p["parts_filled"] = p.get("parts_filled", 0) + 1
        p.setdefault("order_ids", []).append(oid)
        tracker.save(data)
        print(f"✓ Topped up {found_key}")
        print(f"  total: {new_sh:.2f} sh, cost ${new_cost:.2f}, avg ${new_avg:.4f}")
    else:
        print("WARN: existing YES position not found, creating new entry")
        new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
        data.setdefault('positions', {})[new_key] = {
            "condition_id": CID, "token_id": TOKEN, "title": TITLE,
            "outcome": "Yes", "event_slug": SLUG,
            "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
            "size_shares": round(matched, 2), "cost_usd": actual_cost,
            "tier": "manual", "strategy": "manual", "signal_player": "manual",
            "parts_filled": 1, "parts_planned": 1,
            "order_ids": [oid],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "open", "sells": [], "final_pnl": 0,
            "_adopted_from": "manual_buy_2026-04-20_hormuz_normal_apr30_topup20",
        }
        tracker.save(data)
        print(f"✓ Created: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
