"""HEDGE: $50 YES Israel conduct military action against Iran by April 21 @ limit 0.06."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

CID   = "0x9dd27666ad05dbe8ac5547e79d634fc306578b60b71f96ab4347f020b46e9413"
TOKEN = "69918305790707613956950983542932789139135850481457755083498968292192269931106"
TITLE = "Will Israel conduct military action against Iran by April 21, 2026?"
SLUG  = "will-israel-conduct-military-action-against-iran-by-april-21-2026"
OUTCOME = "Yes"
LIMIT_PRICE = 0.06
SIZE_USD = 50.0

print(f"HEDGE BUY: {TITLE[:60]}")
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
    "_adopted_from": "hedge_iran_deal_failure_2026-04-17",
}
tracker.save(data)
print(f"\n✓ Recorded HEDGE: {matched:.2f} sh @ ${actual_price:.4f} = ${actual_cost:.2f}")
