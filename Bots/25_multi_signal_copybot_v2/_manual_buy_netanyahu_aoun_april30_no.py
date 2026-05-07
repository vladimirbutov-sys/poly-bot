"""One-shot manual buy: Netanyahu-Aoun by April 30 NO for $50 at market.

Executed 2026-04-17 at user's explicit request.
Records actual VWAP fill price into tracker (uses get_actual_fill helper).
"""
import sys, io, time, hashlib
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0x6fa05bcbb53efaf95bf5053388f0eb040b1c4ebab2ece4c37cd74bbe3167e625"
TOKEN = "23330623927523224976798170032966383651796457473765550056022078478545665896004"
TITLE = "Will Netanyahu talk to Joseph Aoun by April 30?"
SLUG  = "will-netanyahu-talk-to-joseph-aoun-by"
OUTCOME = "No"
SIZE_USD = 50.0

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live orderbook: bid ${bid:.3f} / ask ${ask:.3f}")

LIMIT_PRICE = round(ask + 0.01, 2)
print(f"Placing BUY: {TITLE}")
print(f"  Side: {OUTCOME} @ limit ${LIMIT_PRICE} (ask+1c buffer), size ${SIZE_USD}")

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
