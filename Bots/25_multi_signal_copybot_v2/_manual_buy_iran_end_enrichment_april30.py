"""One-shot manual buy: Iran-end-enrichment-by-April-30 YES for $40 at market.

Executed 2026-04-17 at user's explicit request.
Records actual VWAP fill price into tracker via get_actual_fill helper.
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0xe6939069d36ad63a9f7fcafa91b627a3f373a3264ab0347c1a5e042c5f7d1f08"
TOKEN = "59937347564572872290316062672979454904942576853251346531585432029105806826906"
TITLE = "Iran agrees to end enrichment of uranium by April 30?"
SLUG  = "iran-agrees-to-end-enrichment-of-uranium-by-april-30"
OUTCOME = "Yes"
SIZE_USD = 40.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.3f} / ask ${ask:.3f}")

# executor.place_limit_buy rounds price to 2 decimals — pass next 1c tick above ask
import math
LIMIT_PRICE = round(math.ceil((ask + 0.005) * 100) / 100, 2)
print(f"Placing BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ limit ${LIMIT_PRICE} (above ask ${ask:.3f}), size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result:
    print("BUY order failed.")
    sys.exit(1)

print(f"BUY placed: order_id={result.get('order_id')[:16]}...")
print(f"  shares: {result.get('size_shares')}, cost_usd (at limit): ${result.get('cost_usd'):.2f}")

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
    "_adopted_from": "manual_buy_2026-04-17",
}
tracker.save(data)
print(f"\n✓ Recorded as {new_key[:20]}...")
print(f"  shares: {matched:.2f}, cost: ${actual_cost:.2f}, entry: ${actual_price:.4f}")
