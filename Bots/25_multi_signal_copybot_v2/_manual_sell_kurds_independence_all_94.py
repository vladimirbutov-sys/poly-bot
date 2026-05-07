"""Sell 100% Kurds independence NO @ limit $0.94 (sweep all bids >= 0.94)."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "70121850046492348784549902420135388646858612857008496798342833461244578139670"
CID = "0x15fcf94587789dcd26efd4a31a1dbc8ff80c3c0bbfed1ca7eb90a054fda6efbf"
SHARES = 309.27
LIMIT = 0.94
OLD_OID = "0x4d1758b0e7dbfbe3050e69"  # partial, find by token

# Step 1: cancel old SELL @ 0.97
print("Cancelling existing sell orders on this token...")
c = executor._get_client()
for o in c.get_orders():
    if str(o.get("asset_id","")) == TOKEN and o.get("side") == "SELL":
        oid_full = o.get("id","")
        print(f"  cancelling {oid_full[:24]}... @ {o.get('price')}")
        try:
            executor.cancel_order(oid_full)
        except Exception as e:
            print(f"    cancel error: {e}")
time.sleep(2)

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"\nbid/ask: ${bid:.4f}/${ask:.4f}, placing SELL {SHARES} sh @ ${LIMIT}")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT, shares=SHARES)
if not result or not result.get("order_id"):
    print("PLACE FAILED:", result)
    sys.exit(1)
oid = result["order_id"]
print(f"  order: {oid[:24]}...")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
matched = float(fill.get("size_matched") or 0)
print(f"  status={fill.get('status')}  matched={matched:.2f}/{fill.get('size_original'):.2f}")
if matched < 0.5:
    print("Nothing filled — order rests on book")
    sys.exit(0)

real = executor.get_actual_fill(oid)
actual_price = real['vwap'] if (real and real['size'] > 0) else LIMIT
revenue = real['cost_usd'] if (real and real['size'] > 0) else matched * LIMIT
print(f"  VWAP ${actual_price:.4f}  revenue ${revenue:.2f}")

data = tracker.load()
KEY = None
for k, p in data.get("positions", {}).items():
    if p.get("condition_id") == CID and p.get("status") == "open":
        KEY = k
        break

if KEY is None:
    print("WARN: no open tracker position to update")
    sys.exit(0)

p = data["positions"][KEY]
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
