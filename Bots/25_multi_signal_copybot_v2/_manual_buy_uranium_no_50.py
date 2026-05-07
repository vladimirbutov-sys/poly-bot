"""Manual buy: $50 NO US obtains Iranian enriched uranium by May 31 @ limit 0.68."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

CID   = "0xbcacd5a055f5a9ced6f69f122216c073dd6987d08253fc07bbcc168fa5b81d55"
TOKEN = "5345441419419147559625888104788940459264045849260872706421285679583531763371"
TITLE = "US obtains Iranian enriched uranium by May 31?"
SLUG  = "us-obtains-iranian-enriched-uranium-by-may-31"
OUTCOME = "No"
LIMIT_PRICE = 0.68
SIZE_USD = 50.0

print(f"BUY: {TITLE}")
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
print(f"\n✓ Recorded: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
