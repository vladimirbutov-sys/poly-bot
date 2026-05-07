"""Manual sell: 20% of US x Iran peace Apr 22 YES @ limit $0.15 (GTC)."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "10355316169421062771540371697837923442956106006258739802114788264214901200573"
TITLE = "US x Iran permanent peace deal by April 22, 2026?"
LIMIT_PRICE = 0.15
PCT = 0.20
WATCH_SECONDS = 60

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

shares_to_sell = round(total_shares * PCT, 2)
bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Position: {total_shares} sh")
print(f"Selling 20%: {shares_to_sell} sh @ limit ${LIMIT_PRICE}")
print(f"Live bid/ask: ${bid:.3f}/${ask:.3f}  (15c above ask — sits on book GTC)")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=shares_to_sell)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"\nORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")
print(f"Watching {WATCH_SECONDS}s (no auto-cancel)...\n")

last_matched = 0.0
start = time.time()
while time.time() - start < WATCH_SECONDS:
    details = executor.get_order_details(oid)
    status = details.get("status", "UNKNOWN")
    matched = float(details.get("size_matched", 0) or 0)
    if matched > last_matched + 0.01:
        print(f"  [+{int(time.time()-start):>2}s] matched {matched:.2f}")
        last_matched = matched
    if status == "MATCHED":
        print("  FULLY MATCHED"); break
    time.sleep(6)

details = executor.get_order_details(oid)
final_status = details.get("status", "UNKNOWN")
final_matched = float(details.get("size_matched", 0) or 0)
print(f"\nFinal: {final_status}  matched {final_matched:.2f}/{shares_to_sell}")

if final_matched > 0.5:
    real = executor.get_actual_fill(oid)
    if real and real["size"] > 0:
        actual_price = real["vwap"]
        revenue = real["cost_usd"]
    else:
        actual_price = LIMIT_PRICE
        revenue = final_matched * LIMIT_PRICE

    data = tracker.load()
    p = data["positions"][position_key]
    cur_sh = float(p.get("size_shares", 0))
    cur_cost = float(p.get("cost_usd", 0))
    cost_sold = cur_cost * (final_matched / cur_sh) if cur_sh > 0 else 0
    pnl = revenue - cost_sold
    p["size_shares"] = round(cur_sh - final_matched, 4)
    p["cost_usd"] = round(cur_cost - cost_sold, 4)
    p.setdefault("sells", []).append({
        "shares": round(final_matched, 4),
        "price": round(actual_price, 6),
        "revenue": round(revenue, 4),
        "pnl": round(pnl, 4),
        "reason": "manual_20pct_limit15_gtc",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    tracker.save(data)
    print(f"\n[OK] Recorded: sold {final_matched:.2f} sh @ ${actual_price:.4f} revenue ${revenue:.2f} PnL ${pnl:+.2f}")

if final_status != "MATCHED":
    print()
    print(f"ORDER REMAINS LIVE (GTC): {oid}")
    print(f"  Remaining ~{shares_to_sell - final_matched:.2f} sh @ ${LIMIT_PRICE}")
    print(f"  sync_with_onchain will catch later fills.")
