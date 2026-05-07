"""One-shot manual buy: Litani No for $30 @ limit 0.67.

Executed 2026-04-15 at user's explicit request.
After successful fill, records the position into positions.json so the
bot tracks/manages it going forward.
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

CID   = "0x9049d96597900ba0f3013604dc7adc3dd6e7e4764c5a0c16318605c40ac1ee96"
TOKEN = "61105898512331423456932766287679410148969111620575334880263459667275737814007"
TITLE = "Israeli forces cross the Litani River by June 30?"
SLUG  = "israeli-forces-cross-the-litani-river-by-june-30"
OUTCOME = "No"
LIMIT_PRICE = 0.67
SIZE_USD = 30.0

print(f"Placing BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ limit {LIMIT_PRICE}, size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)

if not result:
    print("BUY order failed. Aborting — no tracker write.")
    sys.exit(1)

print(f"BUY placed: order_id={result.get('order_id')[:16]}...")
print(f"  shares: {result.get('size_shares')}, cost_usd: {result.get('cost_usd'):.2f}")

# Wait for fill (up to 5 min)
print("Waiting for fill (up to 300s)...")
fill = executor.wait_for_fill_with_details(result["order_id"], timeout=300)
print(f"  fill status: {fill.get('status')} | matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

if fill.get("status") not in ("MATCHED", "PARTIAL"):
    print(f"Order did not fill (status={fill.get('status')}). Not recording.")
    sys.exit(2)

# Record in tracker so bot manages it
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
# Build a unique key
new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]

data.setdefault("positions", {})[new_key] = {
    "condition_id": CID,
    "token_id": TOKEN,
    "title": TITLE,
    "outcome": OUTCOME,
    "event_slug": SLUG,
    "entry_price": actual_price,
    "avg_entry": actual_price,
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
    "_adopted_from": "manual_buy_2026-04-15",
}
tracker.save(data)
print(f"\n✓ Recorded in tracker as {new_key[:20]}...")
print(f"  shares: {matched:.2f}, cost: ${actual_cost:.2f}, entry: ${actual_price}")
