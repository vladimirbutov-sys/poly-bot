"""Top-up: Trump-end-military-operations-Apr21 YES — $60 at market.

User's request 2026-04-17. Existing position 614 sh @ avg $0.241 already
held; this adds ~170 sh more.
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x1507c50c86fb307e4f1acd9d740b2be66d98773f90d161e94907d8ef2c5699b3"
TOKEN = "25506560533857883018874067035230296855545609452839300134236877827349253759444"
TITLE = "Trump announces end of military operations against Iran by April 21st?"
SLUG  = "trump-announces-end-of-military-operations-against-iran-by"
OUTCOME = "Yes"
SIZE_USD = 60.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.3f} / ask ${ask:.3f}")

import math
LIMIT_PRICE = round(math.ceil((ask + 0.005) * 100) / 100, 2)
print(f"Placing BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ limit ${LIMIT_PRICE} (above ask ${ask:.3f}), size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result:
    print("BUY order failed.")
    sys.exit(1)

print(f"BUY placed: order_id={result.get('order_id')[:16]}...")
print(f"  shares: {result.get('size_shares')}, cost (at limit): ${result.get('cost_usd'):.2f}")

print("Waiting for fill (up to 300s)...")
fill = executor.wait_for_fill_with_details(result["order_id"], timeout=300)
print(f"  fill status: {fill.get('status')} | matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

if fill.get("status") not in ("MATCHED", "PARTIAL"):
    print(f"Order did not fill (status={fill.get('status')}). Not recording.")
    sys.exit(2)

matched = float(fill.get("size_matched") or 0)
real = executor.get_actual_fill(result["order_id"])
if real and real["size"] > 0:
    actual_price = real["vwap"]
    actual_cost = real["cost_usd"]
    print(f"  real VWAP: ${actual_price:.4f}  cost ${actual_cost:.2f}  (limit was ${LIMIT_PRICE})")
else:
    actual_price = float(fill.get("price") or LIMIT_PRICE)
    actual_cost = matched * actual_price
    print(f"  [WARN] no trade rows — falling back to limit ${actual_price}")

data = tracker.load()
new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]

data.setdefault("positions", {})[new_key] = {
    "condition_id": CID,
    "token_id": TOKEN,
    "title": TITLE,
    "outcome": OUTCOME,
    "event_slug": SLUG,
    "entry_price": round(actual_price, 6),
    "avg_entry": round(actual_price, 6),
    "size_shares": round(matched, 2),
    "cost_usd": round(actual_cost, 2),
    "tier": "manual",
    "strategy": "manual",
    "signal_player": "manual",
    "parts_filled": 1,
    "parts_planned": 1,
    "order_ids": [result.get("order_id", "")],
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "open",
    "sells": [],
    "final_pnl": 0,
    "_adopted_from": "manual_buy_2026-04-17_trump_end_military_topup60",
}
tracker.save(data)
print(f"\n✓ Recorded as {new_key[:24]}...")
print(f"  shares: {matched:.2f}, cost: ${actual_cost:.2f}, entry: ${actual_price:.4f}")
print("  consolidate_duplicates will merge with existing bot position next cycle")
