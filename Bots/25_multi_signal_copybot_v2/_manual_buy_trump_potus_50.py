"""Buy $50 YES on 'Will Trump post POTUS this week on Truth Social'.

User's request 2026-04-19. Market window: Apr 13-19 11:59 PM ET.
"""
import sys, io, time, hashlib, math
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0xc6c25c2150b2e2c7758ee0ad8640324f60086367fc689f0bca618621c890a2c6"
TOKEN = "110355507989397906037727775153022013914547519484499148757530035419685817714754"
TITLE = "Will Trump post POTUS this week on Truth Social?"
SLUG  = "what-will-trump-post-this-week-april-13-april-19"
OUTCOME = "Yes"
SIZE_USD = 50.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.3f} / ask ${ask:.3f}  (spread {(ask-bid)*100:.1f}c — wide)")

LIMIT_PRICE = round(math.ceil((ask + 0.005) * 100) / 100, 2)
print(f"Placing BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ limit ${LIMIT_PRICE}, size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result:
    print("BUY order failed.")
    sys.exit(1)

oid = result['order_id']
req = float(result.get('size_shares') or 0)
print(f"ORDER LIVE: {oid[:24]}...  size={req}")

print("Waiting for fill (up to 180s)...")
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
    "_adopted_from": "manual_buy_2026-04-19_trump_potus",
}
tracker.save(data)
print(f"✓ Recorded: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
