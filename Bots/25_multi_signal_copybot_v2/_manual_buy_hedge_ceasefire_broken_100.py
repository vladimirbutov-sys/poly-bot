"""HEDGE ADD-ON: $100 YES Trump announce ceasefire broken April 21 @ limit 0.11."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

CID   = "0xdda63e9a4419b36eed1559287ec645677d23cb95d96ce7d5c91d83cb6a8b268e"
TOKEN = "49280639040357558550052498419702634099516416168726782881690167140869178226036"
TITLE = "Will Trump announce that the US x Iran ceasefire has been broken by April 21, 2026?"
SLUG  = "will-trump-announce-that-the-us-x-iran-ceasefire-has-been-broken-by-april-21-2026"
OUTCOME = "Yes"
LIMIT_PRICE = 0.11
SIZE_USD = 100.0

print(f"HEDGE ADD-ON: {TITLE[:60]}")
print(f"  {OUTCOME} @ limit {LIMIT_PRICE}, size ${SIZE_USD}")

result = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=SIZE_USD)
if not result: print("FAIL"); sys.exit(1)
print(f"Order placed: {result.get('order_id')[:20]}  shares={result.get('size_shares')}")
fill = executor.wait_for_fill_with_details(result["order_id"], timeout=120)
print(f"  status={fill.get('status')}  matched={fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")
matched = float(fill.get("size_matched") or 0)
if matched < 0.5: print("Nothing filled"); sys.exit(2)

real = executor.get_actual_fill(result["order_id"])
actual_price = real["vwap"] if real and real["size"] > 0 else LIMIT_PRICE
actual_cost = real["cost_usd"] if real and real["size"] > 0 else matched * LIMIT_PRICE
print(f"  VWAP ${actual_price:.4f}  cost ${actual_cost:.2f}")

new_key = "0xhedge_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
data = tracker.load()
data.setdefault("positions", {})[new_key] = {
    "condition_id": CID, "token_id": TOKEN, "title": TITLE, "outcome": OUTCOME,
    "event_slug": SLUG, "entry_price": round(actual_price, 6),
    "avg_entry": round(actual_price, 6), "size_shares": round(matched, 2),
    "cost_usd": round(actual_cost, 2), "tier": "hedge", "strategy": "hedge",
    "signal_player": "manual", "parts_filled": 1, "parts_planned": 1,
    "order_ids": [result.get("order_id", "")],
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "open", "sells": [], "final_pnl": 0,
    "_adopted_from": "hedge_addon_2026-04-17",
}
tracker.save(data)
print(f"\n✓ Recorded HEDGE ADD-ON: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
