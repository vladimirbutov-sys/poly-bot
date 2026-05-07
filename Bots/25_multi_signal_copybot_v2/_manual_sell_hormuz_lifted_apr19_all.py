"""Manual sell: 100% of Hormuz-lifted-Apr19 YES at market (cross bid).
Lottery ticket expiring in ~12h — analysis says fair value $0.02-0.04, sell while bid holds $0.068."""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "91598771792773760116390366584153669276526784848469387505098726980059231998980"
TITLE = "Hormuz blockade lifted by Apr 19"
KEY   = "0xmanual_de2ce517ecb15cb7d308a3779a04a60b"
SHARES_TO_SELL = 154.55
# Executor rounds to 2 decimals. Bid is $0.068 (3-decimal tick).
# Limit $0.06 crosses bid → fills at best bid $0.068.
LIMIT_PRICE = 0.06

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"YES bid/ask: ${bid:.4f}/${ask:.4f}  limit ${LIMIT_PRICE} (crosses bid)")
print(f"SELL: {TITLE}  {SHARES_TO_SELL} sh")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=SHARES_TO_SELL)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"Order placed: {oid[:24]}...")

fill = executor.wait_for_fill_with_details(oid, timeout=90)
print(f"  status={fill.get('status')}  matched={fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get("size_matched") or 0)
real = executor.get_actual_fill(oid)
if real and real["size"] > 0:
    print(f"  real VWAP: ${real['vwap']:.4f}  revenue ${real['cost_usd']:.2f}")

# Update tracker
data = tracker.load()
p = data.get("positions", {}).get(KEY)
if p is None:
    print(f"WARN: position key {KEY} not found in tracker"); sys.exit(0)

cur_sh = float(p.get("size_shares", 0))
cost = float(p.get("cost_usd", 0))
revenue = real["cost_usd"] if real and real["size"] > 0 else matched * LIMIT_PRICE
actual_price = real["vwap"] if real and real["size"] > 0 else LIMIT_PRICE
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
    "reason": "manual_exit_lottery_expiring",
    "timestamp": datetime.now(timezone.utc).isoformat(),
})
if new_sh < 0.5:
    p["status"] = "sold"
    p["final_pnl"] = round(pnl, 4)

tracker.save(data)
print(f"\n✓ Sold {matched:.2f} sh @ ${actual_price:.4f} = ${revenue:.2f}")
print(f"  Cost basis sold: ${cost_sold:.2f}  PnL ${pnl:+.2f}")
print(f"  Remaining: {new_sh:.2f} sh  status={p['status']}")
