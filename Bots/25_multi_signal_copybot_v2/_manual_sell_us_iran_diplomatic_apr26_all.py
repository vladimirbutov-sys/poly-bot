"""Sell 100%: US x Iran diplomatic meeting by April 26 NO 125 sh @ limit $0.86 (cross bid $0.87)."""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

KEY   = "0xmanual_ece3bfe6d61a905696f90c22237f5930"
TOKEN = "1779256133940495628599037184919928752636482208365471696872270700614989767882"
SHARES = 125.0
LIMIT  = 0.86  # crosses best bid $0.87, fill at $0.87

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"bid/ask: ${bid:.4f}/${ask:.4f}  limit ${LIMIT}  shares {SHARES}")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT, shares=SHARES)
if not result or not result.get("order_id"):
    print("PLACE FAILED"); sys.exit(1)
oid = result["order_id"]
print(f"order: {oid[:24]}...")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
matched = float(fill.get("size_matched") or 0)
print(f"  status={fill.get('status')}  matched={matched:.2f}/{fill.get('size_original'):.2f}")
if matched < 0.5:
    print("Nothing filled"); sys.exit(2)

real = executor.get_actual_fill(oid)
actual_price = real['vwap'] if (real and real['size'] > 0) else LIMIT
revenue = real['cost_usd'] if (real and real['size'] > 0) else matched * LIMIT
print(f"  VWAP ${actual_price:.4f}  revenue ${revenue:.2f}")

data = tracker.load()
p = data.get("positions", {}).get(KEY)
if p is None:
    print(f"WARN: tracker key {KEY} not found"); sys.exit(0)
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
print(f"\nOK sold {matched:.2f} sh @ ${actual_price:.4f} = ${revenue:.2f}")
print(f"  cost basis sold: ${cost_sold:.2f}  PnL ${pnl:+.2f}  status={p['status']}")
