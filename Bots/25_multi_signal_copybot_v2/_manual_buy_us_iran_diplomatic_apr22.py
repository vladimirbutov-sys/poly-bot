"""Buy $125 YES on US x Iran diplomatic meeting by April 22, 2026.

User's request 2026-04-19. Limit @ $0.64 = current ask, no buffer.
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0xa573400b588079857899fce1e5a68da2d086f63fd35cbdd626df397e19e9995e"
TOKEN = "50740610408998204196749871302714482538726256929776684989295165941286472759432"
TITLE = "US x Iran diplomatic meeting by April 22, 2026?"
SLUG  = "us-x-iran-diplomatic-meeting-by-329"
OUTCOME = "Yes"
LIMIT_PRICE = 0.64   # = current ask
SIZE_USD = 125.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.3f} / ask ${ask:.3f}  (spread {(ask-bid)*100:.1f}c)")
print(f"Placing BUY @ limit ${LIMIT_PRICE}, size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result:
    print("BUY order failed"); sys.exit(1)

oid = result['order_id']
req = float(result.get('size_shares') or 0)
print(f"ORDER LIVE: {oid[:24]}... size={req}")

fill = executor.wait_for_fill_with_details(oid, timeout=180)
print(f"  status: {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

if fill.get('status') not in ('MATCHED','PARTIAL'):
    print(f"Not filled — status {fill.get('status')}")
    sys.exit(2)

matched = float(fill.get('size_matched') or 0)
real = executor.get_actual_fill(oid)
if real and real['size'] > 0:
    actual_price = real['vwap']
    actual_cost = real['cost_usd']
    print(f"  real VWAP: ${actual_price:.4f}  cost ${actual_cost:.2f}")
else:
    actual_price = float(fill.get('price') or LIMIT_PRICE)
    actual_cost = matched * actual_price

data = tracker.load()
new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
data.setdefault('positions', {})[new_key] = {
    "condition_id": CID, "token_id": TOKEN, "title": TITLE,
    "outcome": OUTCOME, "event_slug": SLUG,
    "entry_price": round(actual_price, 6), "avg_entry": round(actual_price, 6),
    "size_shares": round(matched, 2), "cost_usd": round(actual_cost, 2),
    "tier": "manual", "strategy": "manual", "signal_player": "manual",
    "parts_filled": 1, "parts_planned": 1,
    "order_ids": [oid],
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "open", "sells": [], "final_pnl": 0,
    "_adopted_from": "manual_buy_2026-04-19_us_iran_diplomatic_apr22",
}
tracker.save(data)
print(f"✓ Recorded: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")

if fill.get('status') == 'PARTIAL':
    print(f"\nPARTIAL — {req - matched:.2f} sh remaining on book at ${LIMIT_PRICE}")
