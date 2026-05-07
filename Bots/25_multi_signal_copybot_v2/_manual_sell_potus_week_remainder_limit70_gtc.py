"""Passive GTC sell: remainder of 50% target on Trump POTUS NO @ $0.70."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "8645739410699309255723712337953202603299613672752563309810773074070571201206"
LIMIT_PRICE = 0.70
SHARES_TO_SELL = 105.52  # remainder to reach 50% of original 222.97
WATCH_SECONDS = 60

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"Live bid/ask: ${bid:.4f}/${ask:.4f}")
print(f"Placing PASSIVE GTC SELL: {SHARES_TO_SELL} sh NO @ ${LIMIT_PRICE}")
print(f"  (sits on ask side below current ${ask:.4f} — waits for buyer)")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=SHARES_TO_SELL)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"\nORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")
print(f"Watching {WATCH_SECONDS}s (no auto-cancel)...\n")

last_matched = 0.0
start = time.time()
while time.time() - start < WATCH_SECONDS:
    d = executor.get_order_details(oid)
    status = d.get("status", "UNKNOWN")
    matched = float(d.get("size_matched", 0) or 0)
    if matched > last_matched + 0.01:
        print(f"  [+{int(time.time()-start):>2}s] matched {matched:.2f}")
        last_matched = matched
    if status == "MATCHED":
        print("  FULLY MATCHED"); break
    time.sleep(6)

d = executor.get_order_details(oid)
final_status = d.get("status", "UNKNOWN")
final_matched = float(d.get("size_matched", 0) or 0)
print(f"\nFinal: {final_status}  matched {final_matched:.2f}/{SHARES_TO_SELL}")

if final_matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real["vwap"] if real and real["size"] > 0 else LIMIT_PRICE
    revenue = real["cost_usd"] if real and real["size"] > 0 else final_matched * LIMIT_PRICE
    data = tracker.load()
    for k, p in (data.get("positions") or {}).items():
        if p.get("token_id") == TOKEN and p.get("status") == "open":
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
                "reason": "manual_50pct_remainder_limit70_gtc",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if p["size_shares"] < 0.5:
                p["status"] = "sold"
            tracker.save(data)
            print(f"[OK] sold {final_matched:.2f} sh @ ${actual_price:.4f} PnL ${pnl:+.2f}")
            print(f"  remaining: {p['size_shares']:.2f} sh, cost ${p['cost_usd']:.2f}")
            break

if final_status != "MATCHED":
    print(f"\nORDER REMAINS LIVE (GTC): {oid}")
    print(f"  {SHARES_TO_SELL - final_matched:.2f} sh @ ${LIMIT_PRICE} waiting for buyer")
    print(f"  sync_with_onchain will catch later fills.")
