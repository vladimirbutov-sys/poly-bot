"""Passive limit BUY on US x Iran peace deal Apr 22 YES @ $0.13 for $75.

User's request 2026-04-19. Current bid is $0.15 — limit below bid sits on
book waiting for price drop. GTC (no auto-cancel).
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0xbbc6689d0f6d57ea42168836712237c7308b3e0118c8914d31b6126d0f3254c5"
TOKEN = "10355316169421062771540371697837923442956106006258739802114788264214901200573"
TITLE = "US x Iran permanent peace deal by April 22, 2026?"
SLUG  = "us-x-iran-permanent-peace-deal-by"
OUTCOME = "Yes"
LIMIT_PRICE = 0.13
SIZE_USD = 75.0
WATCH_SECONDS = 90

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.3f} / ask ${ask:.3f}")
print(f"Placing PASSIVE BUY @ limit ${LIMIT_PRICE} (below bid), size ${SIZE_USD}")
print(f"  Will fill ONLY when sellers drop to ${LIMIT_PRICE} or below")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result:
    print("BUY order failed"); sys.exit(1)

oid = result['order_id']
req = float(result.get('size_shares') or 0)
print(f"ORDER LIVE: {oid[:24]}... size={req}")
print(f"Watching {WATCH_SECONDS}s (no auto-cancel)...")

last_matched = 0.0
start = time.time()
while time.time() - start < WATCH_SECONDS:
    details = executor.get_order_details(oid)
    status = details.get('status', 'UNKNOWN')
    matched = float(details.get('size_matched', 0) or 0)
    if matched > last_matched + 0.01:
        print(f"  [+{int(time.time()-start):>2}s] matched {matched:.2f}")
        last_matched = matched
    if status == 'MATCHED':
        print('  → FULLY MATCHED'); break
    time.sleep(6)

details = executor.get_order_details(oid)
final_status = details.get('status', 'UNKNOWN')
final_matched = float(details.get('size_matched', 0) or 0)
print(f"\nFinal: {final_status}  matched {final_matched:.2f}/{req}")

if final_matched > 0.5:
    real = executor.get_actual_fill(oid)
    if real and real['size'] > 0:
        actual_price = real['vwap']
        actual_cost = real['cost_usd']
    else:
        actual_price = LIMIT_PRICE
        actual_cost = final_matched * LIMIT_PRICE

    data = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
    data.setdefault('positions', {})[new_key] = {
        "condition_id": CID, "token_id": TOKEN, "title": TITLE,
        "outcome": OUTCOME, "event_slug": SLUG,
        "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
        "size_shares": round(final_matched, 2),
        "cost_usd": round(final_matched * actual_price, 2),  # compute from shares × actual price (avoid partial-visibility)
        "tier": "manual", "strategy": "manual", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1,
        "order_ids": [oid],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-19_peace_apr22_limit13",
    }
    tracker.save(data)
    print(f"✓ Recorded: {final_matched:.2f} sh @ ${actual_price:.4f} = ${final_matched * actual_price:.2f}")

if final_status != 'MATCHED':
    print()
    print(f"ORDER REMAINS LIVE: {oid}")
    print(f"  {req - final_matched:.2f} sh @ ${LIMIT_PRICE} GTC — waits for price drop")
    print(f"  Bot's sync_with_onchain will catch later fills.")
