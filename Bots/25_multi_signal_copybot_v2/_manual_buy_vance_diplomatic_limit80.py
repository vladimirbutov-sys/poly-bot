"""Passive limit BUY: JD Vance attend next US-Iran diplomatic meeting @ $0.80 for $60."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x7e5228c4aa228752fb75ec1ffcb315a5f2fef812d746ceb6601cee285366d1a8"
TOKEN = "21097065272712900144918513504038909932301820226410661672750103638507069150602"
TITLE = "Will J.D. Vance attend the next US x Iran diplomatic meeting?"
SLUG  = "who-will-attend-the-next-us-x-iran-diplomatic-meeting"
LIMIT_PRICE = 0.80
SIZE_USD = 60.0
WATCH_SEC = 60

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"bid/ask: ${bid:.3f}/${ask:.3f}  (limit ${LIMIT_PRICE} = passive, below bid)")

res = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not res or not res.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = res['order_id']
req = float(res.get('size_shares') or 0)
print(f"ORDER LIVE: {oid[:24]}... size={req}")
print(f"Watching {WATCH_SEC}s (no auto-cancel)...")

last = 0.0
start = time.time()
while time.time() - start < WATCH_SEC:
    d = executor.get_order_details(oid)
    s = d.get('status','UNKNOWN')
    m = float(d.get('size_matched',0) or 0)
    if m > last + 0.01:
        print(f"  [+{int(time.time()-start):>2}s] matched={m:.2f}")
        last = m
    if s == 'MATCHED':
        break
    time.sleep(6)

d = executor.get_order_details(oid)
final = d.get('status','UNKNOWN')
matched = float(d.get('size_matched',0) or 0)
print(f"Final: {final}  matched {matched}/{req}")

if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else LIMIT_PRICE
    actual_cost = round(matched * actual_price, 2)
    data = tracker.load()
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
        "_adopted_from": "manual_buy_2026-04-19_vance_diplomatic_limit80",
    }
    tracker.save(data)
    print(f"✓ Recorded: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")

if final != 'MATCHED':
    print(f"\nORDER LIVE on book @ ${LIMIT_PRICE}")
    print(f"  {req - matched:.2f} sh remaining — will fill when sellers drop to ${LIMIT_PRICE}")
