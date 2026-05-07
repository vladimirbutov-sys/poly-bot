"""Passive GTC limit BUY: $100 YES on Iran x Israel/US conflict ends by April 15 @ $0.90."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x5c2e6aef8af5931e9bfa3750364626d754531d2fada2885d45c356b175962a25"
TOKEN = "91851388830923641218615793149765322805282194001900444983744404881757241655792"  # YES
TITLE = "Iran x Israel/US conflict ends by April 15?"
SLUG  = "iran-x-israelus-conflict-ends-by-april-15-618-586-982"
EVENT_SLUG = "iran-x-israelus-conflict-ends-by"
OUTCOME = "Yes"
LIMIT_PRICE = 0.90
SIZE_USD = 100.0
WATCH_SECONDS = 90

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"Placing GTC BUY: {TITLE}")
print(f"  {OUTCOME} @ limit ${LIMIT_PRICE}, size ${SIZE_USD}")
if LIMIT_PRICE >= ask:
    print(f"  -> at/above ask, will fill instantly")
else:
    print(f"  -> below ask, sits on book as new best bid")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result or not result.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = result['order_id']
req_size = float(result.get('size_shares') or 0)
print(f"ORDER LIVE: {oid[:24]}... size={req_size}")
print(f"Watching {WATCH_SECONDS}s (no auto-cancel)...\n")

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
        "_adopted_from": "manual_buy_2026-04-20_iran_israel_conflict_apr15_limit90_100usd",
    }
    tracker.save(data)
    print(f"\u2713 Recorded: {final_matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")

if final_status != 'MATCHED':
    print(f"\nORDER REMAINS LIVE (GTC): {oid}")
    print(f"  {req_size - final_matched:.2f} sh @ ${LIMIT_PRICE} waiting for seller")
    print(f"  Bot's sync_with_onchain will catch later fills and add via onchain_sync_up.")
