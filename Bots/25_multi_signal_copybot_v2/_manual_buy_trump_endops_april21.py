"""Manual buy: $100 YES Trump announces end of military operations against Iran by April 21 @ limit 0.35."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

CID   = "0x1507c50c86fb307e4f1acd9d740b2be66d98773f90d161e94907d8ef2c5699b3"
TOKEN = "25506560533857883018874067035230296855545609452839300134236877827349253759444"
TITLE = "Trump announces end of military operations against Iran by April 21st?"
SLUG  = "trump-announces-end-of-military-operations-against-iran-by"
OUTCOME = "Yes"
LIMIT_PRICE = 0.35
SIZE_USD = 100.0

print(f"BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ limit {LIMIT_PRICE}, size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result:
    print("place_limit_buy failed"); sys.exit(1)
print(f"Order placed: {result.get('order_id')[:20]}...  shares={result.get('size_shares')}")
print("Waiting for fill (up to 120s)...")
fill = executor.wait_for_fill_with_details(result["order_id"], timeout=120)
print(f"  status={fill.get('status')}  matched={fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get("size_matched") or 0)
if matched < 0.5:
    print("Nothing filled"); sys.exit(2)

real = executor.get_actual_fill(result["order_id"])
if real and real["size"] > 0:
    actual_price = real["vwap"]
    actual_cost = real["cost_usd"]
    print(f"  real VWAP: ${actual_price:.4f}  cost ${actual_cost:.2f}  (limit was ${LIMIT_PRICE})")
else:
    actual_price = LIMIT_PRICE
    actual_cost = matched * LIMIT_PRICE

new_key = "0xmanual_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
data = tracker.load()
data.setdefault("positions", {})[new_key] = {
    "condition_id": CID, "token_id": TOKEN, "title": TITLE, "outcome": OUTCOME,
    "event_slug": SLUG, "entry_price": round(actual_price, 6),
    "avg_entry": round(actual_price, 6), "size_shares": round(matched, 2),
    "cost_usd": round(actual_cost, 2), "tier": "manual", "strategy": "manual",
    "signal_player": "manual", "parts_filled": 1, "parts_planned": 1,
    "order_ids": [result.get("order_id", "")],
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "open", "sells": [], "final_pnl": 0,
    "_adopted_from": "manual_buy_2026-04-17",
}
tracker.save(data)
print(f"\n✓ Recorded: {new_key[:28]}...  {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
