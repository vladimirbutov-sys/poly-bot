"""Market sell 100% April 20 US-Iran diplomatic YES (cross bid)."""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "47920444843544199788140822779940327807471887987012983049577499676453164086333"
KEY   = "0xmanual_ca134c6e5c7bb30183b18c41542b9fbb"
LIMIT_PRICE = 0.02  # crosses bid $0.03 (3-decimal tick market)

data = tracker.load()
p = data.get("positions", {}).get(KEY)
shares = float(p.get("size_shares", 0))
print(f"Position: {shares:.2f} sh (cost ${p.get('cost_usd')}, avg ${p.get('avg_entry')})")

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"YES bid/ask: ${bid:.4f}/${ask:.4f}  limit ${LIMIT_PRICE} (crosses bid)")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=shares)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"Order placed: {oid[:24]}...")

fill = executor.wait_for_fill_with_details(oid, timeout=90)
print(f"  status={fill.get('status')}  matched={fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get("size_matched") or 0)
real = executor.get_actual_fill(oid)
actual_price = real['vwap'] if (real and real['size'] > 0) else LIMIT_PRICE
revenue = real['cost_usd'] if (real and real['size'] > 0) else matched * LIMIT_PRICE
print(f"  VWAP ${actual_price:.4f}  revenue ${revenue:.2f}")

cur_sh = float(p.get("size_shares", 0))
cost = float(p.get("cost_usd", 0))
cost_sold = cost * (matched / cur_sh) if cur_sh > 0 else 0
pnl = revenue - cost_sold
new_sh = cur_sh - matched

p["size_shares"] = round(new_sh, 4)
p["cost_usd"] = round(cost - cost_sold, 4)
p.setdefault("sells", []).append({
    "shares": round(matched, 4),
    "price": round(actual_price, 6),
    "revenue": round(revenue, 4),
    "pnl": round(pnl, 4),
    "reason": "manual_exit_market",
    "timestamp": datetime.now(timezone.utc).isoformat(),
})
if new_sh < 0.5:
    p["status"] = "sold"
    p["final_pnl"] = round(pnl, 4)

tracker.save(data)
print(f"\n✓ Sold {matched:.2f} sh @ ${actual_price:.4f} = ${revenue:.2f}")
print(f"  Cost basis sold: ${cost_sold:.2f}  PnL ${pnl:+.2f}")
print(f"  Status: {p['status']}")
