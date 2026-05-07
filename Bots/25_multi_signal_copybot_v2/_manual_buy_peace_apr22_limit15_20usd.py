"""Limit BUY $20 YES on US x Iran permanent peace deal by April 22 @ $0.15."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0xbbc6689d0f6d57ea42168836712237c7308b3e0118c8914d31b6126d0f3254c5"
TOKEN = "10355316169421062771540371697837923442956106006258739802114788264214901200573"  # YES
TITLE = "US x Iran permanent peace deal by April 22, 2026?"
SLUG  = "us-x-iran-permanent-peace-deal-by-april-22-2026"
EVENT_SLUG = "us-x-iran-permanent-peace-deal-by"
OUTCOME = "Yes"
LIMIT_PRICE = 0.15
SIZE_USD = 20.0
WATCH_SECONDS = 60

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"BUY {OUTCOME} @ limit ${LIMIT_PRICE}, size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result or not result.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = result['order_id']
req_size = float(result.get('size_shares') or 0)
print(f"ORDER LIVE: {oid[:24]}... size={req_size}")

last_matched = 0.0
start = time.time()
while time.time() - start < WATCH_SECONDS:
    d = executor.get_order_details(oid)
    status = d.get('status', 'UNKNOWN')
    matched = float(d.get('size_matched', 0) or 0)
    if matched > last_matched + 0.01:
        print(f"  [+{int(time.time()-start):>2}s] matched {matched:.2f}")
        last_matched = matched
    if status == 'MATCHED':
        print("  FULLY MATCHED"); break
    time.sleep(6)

d = executor.get_order_details(oid)
final_status = d.get('status', 'UNKNOWN')
final_matched = float(d.get('size_matched', 0) or 0)
print(f"\nFinal: {final_status}  matched {final_matched:.2f}/{req_size}")

if final_matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if real and real['size'] > 0 else LIMIT_PRICE
    actual_cost = round(final_matched * actual_price, 2)
    print(f"  VWAP ${actual_price:.4f} cost ${actual_cost:.2f}")

    data = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
    data.setdefault('positions', {})[new_key] = {
        "condition_id": CID, "token_id": TOKEN, "title": TITLE,
        "outcome": OUTCOME, "event_slug": EVENT_SLUG,
        "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
        "size_shares": round(final_matched, 2), "cost_usd": actual_cost,
        "tier": "manual", "strategy": "manual", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1, "order_ids": [oid],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-21_peace_apr22_limit15_20usd",
    }
    tracker.save(data)
    print(f"\u2713 Recorded: {final_matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")

if final_status != 'MATCHED':
    print(f"\nORDER REMAINS LIVE (GTC): {oid}")
    print(f"  Remaining ~{req_size - final_matched:.2f} sh @ ${LIMIT_PRICE}")
