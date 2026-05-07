"""Manual sell: 50% of Trump POTUS this week NO @ best market bid."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "8645739410699309255723712337953202603299613672752563309810773074070571201206"
TITLE = "Will Trump post \"POTUS\" this week on Truth Social?"
PCT = 0.50
WATCH_SECONDS = 120

data = tracker.load()
position_key = None
total_shares = 0.0
for k, p in (data.get("positions") or {}).items():
    if p.get("token_id") == TOKEN and p.get("status") == "open":
        position_key = k
        total_shares = float(p.get("size_shares") or 0)
        break

if not position_key:
    print("No open position"); sys.exit(1)

bid, ask = filters.get_orderbook_prices(TOKEN)
if not bid or bid <= 0:
    print("No bid available"); sys.exit(1)

shares_to_sell = round(total_shares * PCT, 2)
LIMIT_PRICE = round(bid, 4)
print(f"Position: {total_shares} sh NO")
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"Selling 50%: {shares_to_sell} sh @ limit ${LIMIT_PRICE} (= best bid, hits immediately)")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=shares_to_sell)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"\nORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=WATCH_SECONDS)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get("size_matched", 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real["vwap"] if real and real["size"] > 0 else LIMIT_PRICE
    revenue = real["cost_usd"] if real and real["size"] > 0 else matched * LIMIT_PRICE

    data = tracker.load()
    p = data["positions"][position_key]
    cur_sh = float(p.get("size_shares", 0))
    cur_cost = float(p.get("cost_usd", 0))
    cost_sold = cur_cost * (matched / cur_sh) if cur_sh > 0 else 0
    pnl = revenue - cost_sold
    p["size_shares"] = round(cur_sh - matched, 4)
    p["cost_usd"] = round(cur_cost - cost_sold, 4)
    p.setdefault("sells", []).append({
        "shares": round(matched, 4),
        "price": round(actual_price, 6),
        "revenue": round(revenue, 4),
        "pnl": round(pnl, 4),
        "reason": "manual_50pct_market_bid",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if p["size_shares"] < 0.5:
        p["status"] = "sold"
    tracker.save(data)
    print(f"\n[OK] sold {matched:.2f} sh @ ${actual_price:.4f} revenue ${revenue:.2f} PnL ${pnl:+.2f}")
    print(f"  remaining in position: {p['size_shares']:.2f} sh, cost ${p['cost_usd']:.2f}")
else:
    print("Nothing filled")
