"""Manual buy: $150 YES on US x Iran permanent peace deal by May 31, 2026 @ best ask."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x0e4a0c937b8934c2475613b6322b3f8edc8dedc24762e01e42b0e6f87424a089"
TOKEN = "72094069823942324362885404801938332659316240217382754851102758232469673300092"  # YES
TITLE = "US x Iran permanent peace deal by May 31, 2026?"
SLUG  = "us-x-iran-permanent-peace-deal-by-may-31-2026"
EVENT_SLUG = "us-x-iran-permanent-peace-deal-by"
OUTCOME = "Yes"
SIZE_USD = 150.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.4f} / ask ${ask:.4f}")
if not ask or ask <= 0:
    print("No ask — aborting"); sys.exit(1)

LIMIT_PRICE = round(ask, 4)
print(f"Placing market BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ ask ${LIMIT_PRICE}, size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result or not result.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = result['order_id']
print(f"ORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get('size_matched', 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if real and real['size'] > 0 else LIMIT_PRICE
    actual_cost = round(matched * actual_price, 2)
    print(f"  VWAP ${actual_price:.4f}  cost ${actual_cost:.2f}")

    data = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
    data.setdefault('positions', {})[new_key] = {
        "condition_id": CID, "token_id": TOKEN, "title": TITLE,
        "outcome": OUTCOME, "event_slug": EVENT_SLUG,
        "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
        "size_shares": round(matched, 2), "cost_usd": actual_cost,
        "tier": "manual", "strategy": "manual", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1,
        "order_ids": [oid],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-20_us_iran_peace_may31_150usd",
    }
    tracker.save(data)
    print(f"\u2713 Recorded: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
else:
    print("Nothing filled"); sys.exit(2)
