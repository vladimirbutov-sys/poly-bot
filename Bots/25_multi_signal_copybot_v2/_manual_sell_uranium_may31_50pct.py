"""Sell 50% of US obtains Iranian enriched uranium by May 31 NO @ limit $0.88 (cross bid $0.89)."""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

KEY   = "0x50ac68522b6cefd6e8de4691b451719b9b9d3b54aecbc30d3c78c3493641a51c"
TOKEN = "5345441419419147559625888104788940459264045849260872706421285679583531763371"
SHARES = 176.95  # 50% of 353.9025
LIMIT  = 0.88  # crosses best bid $0.89, fill at $0.89

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
    "reason": "manual_partial_50pct",
    "timestamp": datetime.now(timezone.utc).isoformat(),
})
if new_sh < 0.5:
    p["status"] = "sold"
    p["final_pnl"] = round(pnl, 4)
tracker.save(data)
print(f"\nOK sold {matched:.2f} sh @ ${actual_price:.4f} = ${revenue:.2f}")
print(f"  cost basis sold: ${cost_sold:.2f}  PnL ${pnl:+.2f}")
print(f"  Remaining: {new_sh:.2f} sh @ avg ${p.get('avg_entry'):.4f}, cost ${p.get('cost_usd'):.2f}")
