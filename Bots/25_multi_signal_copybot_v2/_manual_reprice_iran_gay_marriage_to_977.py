"""Reprice: cancel SELL @ 0.98 and place SELL @ 0.977 (crosses best bid -> instant fill)."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "107171737619314142212827016886886005382319261850070382453179959313987657965300"
CID = "0xb0a9e9c70cd5bff7feb2b7038ff7e37412b07a8bcfc2e4aff1568aff77641cc4"
NEW_PRICE = 0.977
SHARES = 102.24
OLD_OID = "0xb1df51e49312b346d8578e478b4fdb1c13a07ad49da7dc5b8a87691c24eab9e8"

# Step 1: cancel old
print(f"Cancelling old order {OLD_OID[:24]}... @ 0.98")
try:
    ok = executor.cancel_order(OLD_OID)
    print(f"  cancel result: {ok}")
except Exception as e:
    print(f"  cancel error: {e}")

time.sleep(2)

# Step 2: place new at 0.977 (crosses best bid)
bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}, placing SELL {SHARES} sh @ ${NEW_PRICE}")
res = executor.place_limit_sell(token_id=TOKEN, price=NEW_PRICE, shares=SHARES)
if not res or not res.get("order_id"):
    print("PLACE FAILED:", res)
    sys.exit(1)
oid = res["order_id"]
print(f"  order: {oid[:24]}...")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
matched = float(fill.get("size_matched") or 0)
print(f"  status={fill.get('status')}  matched={matched:.2f}/{fill.get('size_original'):.2f}")
if matched < 0.5:
    print("Nothing filled — order rests on book")
    sys.exit(0)

real = executor.get_actual_fill(oid)
actual_price = real['vwap'] if (real and real['size'] > 0) else NEW_PRICE
revenue = real['cost_usd'] if (real and real['size'] > 0) else matched * NEW_PRICE
print(f"  VWAP ${actual_price:.4f}  revenue ${revenue:.2f}")

# Update tracker
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
    "reason": "manual_reprice_to_market",
    "timestamp": datetime.now(timezone.utc).isoformat(),
})
if new_sh < 0.5:
    p["status"] = "sold"
    p["final_pnl"] = round(pnl, 4)
tracker.save(data)
print(f"\nOK sold {matched:.2f} sh @ ${actual_price:.4f} = ${revenue:.2f}")
print(f"  cost basis sold: ${cost_sold:.2f}  PnL ${pnl:+.2f}  status={p['status']}")
