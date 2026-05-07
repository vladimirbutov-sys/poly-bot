"""Manual sell: 35% of Hormuz traffic YES @ limit 0.53 (not below)."""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

TOKEN = "77893140510362582253172593084218413010407941075415081594586195705930819989216"
TITLE = "Strait of Hormuz traffic returns to normal by end of April?"
LIMIT_PRICE = 0.53
SHARES_TO_SELL = 327.60

print(f"SELL: {TITLE}")
print(f"  {SHARES_TO_SELL} sh @ limit {LIMIT_PRICE}")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=SHARES_TO_SELL)
if not result:
    print("place_limit_sell failed"); sys.exit(1)
print(f"Order placed: {result.get('order_id')[:20]}...")
print("Waiting for fill (up to 120s)...")
fill = executor.wait_for_fill_with_details(result["order_id"], timeout=120)
print(f"  status={fill.get('status')}  matched={fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get("size_matched") or 0)
real = executor.get_actual_fill(result["order_id"])
if real and real["size"] > 0:
    print(f"  real VWAP: ${real['vwap']:.4f}  revenue ${real['cost_usd']:.2f}")

# Update tracker — find main Hormuz position and record the sell
data = tracker.load()
for k, p in data.get("positions", {}).items():
    if (p.get("token_id") == TOKEN and p.get("status") == "open"
            and abs(float(p.get("size_shares", 0)) - 935.986) < 1):
        cur_sh = float(p.get("size_shares", 0))
        new_sh = cur_sh - matched
        # Prorate cost
        cost = float(p.get("cost_usd", 0))
        revenue = real["cost_usd"] if real and real["size"] > 0 else matched * LIMIT_PRICE
        cost_sold = cost * (matched / cur_sh) if cur_sh > 0 else 0
        pnl = revenue - cost_sold
        p["size_shares"] = round(new_sh, 4)
        p["cost_usd"] = round(cost - cost_sold, 4)
        p.setdefault("sells", []).append({
            "shares": round(matched, 4),
            "price": real["vwap"] if real and real["size"] > 0 else LIMIT_PRICE,
            "revenue": round(revenue, 4),
            "pnl": round(pnl, 4),
            "reason": "manual_35pct_lock_profit",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if new_sh < 0.5:
            p["status"] = "sold"
        print(f"\n✓ Updated position: sold {matched:.2f} sh, remaining {new_sh:.2f}, PnL ${pnl:+.2f}")
        break
tracker.save(data)
