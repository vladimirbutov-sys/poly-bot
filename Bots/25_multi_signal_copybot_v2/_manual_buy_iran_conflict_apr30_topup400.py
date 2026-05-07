"""Top-up: Iran x Israel/US conflict ends Apr 30 YES — $400 at limit $0.80.

User's request 2026-04-18. Best ask is $0.81; $0.80 sits on bid (passive),
waiting for sellers to come down. If not filled in 3 min, leave on book.
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0xa6ddb7146f48a12dbf73456d654211b01d7493829932c31b7fe85d82120d338f"
TOKEN = "103971336418419351548990142781195320713490282483637854831265186666012554199721"
TITLE = "Iran x Israel/US conflict ends by April 30?"
SLUG  = "iran-x-israelus-conflict-ends-by"
OUTCOME = "Yes"
LIMIT_PRICE = 0.80
SIZE_USD = 400.0
WATCH_SECONDS = 180

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.3f} / ask ${ask:.3f}")
print(f"Placing BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ limit ${LIMIT_PRICE} (passive — joins bid), size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result:
    print("BUY order failed.")
    sys.exit(1)

oid = result['order_id']
req_size = float(result.get('size_shares') or 0)
print(f"ORDER LIVE: {oid[:24]}...  size={req_size}")
print(f"Watching {WATCH_SECONDS}s for fill (no auto-cancel)...")
print()

last_matched = 0.0
start = time.time()
while time.time() - start < WATCH_SECONDS:
    details = executor.get_order_details(oid)
    status = details.get('status', 'UNKNOWN')
    matched = float(details.get('size_matched', 0) or 0)
    if matched > last_matched + 0.01:
        delta = matched - last_matched
        print(f"  [+{int(time.time()-start):>3}s] status={status} matched={matched:.2f} (+{delta:.2f})")
        last_matched = matched
    if status == 'MATCHED':
        print('  → FULLY MATCHED'); break
    time.sleep(8)

details = executor.get_order_details(oid)
final_status = details.get('status', 'UNKNOWN')
final_matched = float(details.get('size_matched', 0) or 0)
print()
print(f"Final: status={final_status}  matched={final_matched:.2f}/{req_size}")

if final_matched > 0.5:
    real = executor.get_actual_fill(oid)
    if real and real['size'] > 0:
        actual_price = real['vwap']
        actual_cost = real['cost_usd']
        print(f"  real VWAP: ${actual_price:.4f}  cost ${actual_cost:.2f}  (limit was ${LIMIT_PRICE})")
    else:
        actual_price = LIMIT_PRICE
        actual_cost = final_matched * LIMIT_PRICE
        print(f"  [WARN] no trade rows — falling back to limit ${actual_price}")

    data = tracker.load()
    new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
    data.setdefault('positions', {})[new_key] = {
        "condition_id": CID, "token_id": TOKEN, "title": TITLE,
        "outcome": OUTCOME, "event_slug": SLUG,
        "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
        "size_shares": round(final_matched, 2), "cost_usd": round(actual_cost, 2),
        "tier": "manual", "strategy": "manual", "signal_player": "manual",
        "parts_filled": 1, "parts_planned": 1,
        "order_ids": [oid],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "open", "sells": [], "final_pnl": 0,
        "_adopted_from": "manual_buy_2026-04-18_iran_conflict_apr30_topup400",
    }
    tracker.save(data)
    print(f"\n✓ Recorded: {final_matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")

if final_status != 'MATCHED':
    remaining = req_size - final_matched
    print()
    print(f"ORDER REMAINS LIVE: {oid}")
    print(f"  Remaining ~{remaining:.2f} sh @ ${LIMIT_PRICE} GTC on book")
    print(f"  bot's sync_with_onchain will catch later fills")
