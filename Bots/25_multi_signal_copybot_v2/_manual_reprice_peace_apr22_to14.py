"""Cancel 15c sell order and re-post at 14c."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "10355316169421062771540371697837923442956106006258739802114788264214901200573"
OLD_ORDER = "0x8cbb132f837392b0e4c02f4805db64074fc53f65c0604b20fd2d61d3558408d2"
NEW_PRICE = 0.14
WATCH_SECONDS = 90

# 1. Check how much was matched on the old order before cancel
details = executor.get_order_details(OLD_ORDER)
old_matched = float(details.get("size_matched", 0) or 0)
old_size = float(details.get("size_original", 0) or 0)
old_status = details.get("status", "?")
print(f"Old order: {old_status}  matched {old_matched:.2f}/{old_size}")

# 2. Cancel
ok = executor.cancel_order(OLD_ORDER)
print(f"Cancel: {ok}")
time.sleep(2)

# 3. Record any partial fill from the old order
if old_matched > 0.5:
    real = executor.get_actual_fill(OLD_ORDER)
    actual_price = real["vwap"] if real and real["size"] > 0 else 0.15
    revenue = real["cost_usd"] if real and real["size"] > 0 else old_matched * 0.15
    data = tracker.load()
    for k, p in (data.get("positions") or {}).items():
        if p.get("token_id") == TOKEN and p.get("status") == "open":
            cur_sh = float(p.get("size_shares", 0))
            cur_cost = float(p.get("cost_usd", 0))
            cost_sold = cur_cost * (old_matched / cur_sh) if cur_sh > 0 else 0
            pnl = revenue - cost_sold
            p["size_shares"] = round(cur_sh - old_matched, 4)
            p["cost_usd"] = round(cur_cost - cost_sold, 4)
            p.setdefault("sells", []).append({
                "shares": round(old_matched, 4),
                "price": round(actual_price, 6),
                "revenue": round(revenue, 4),
                "pnl": round(pnl, 4),
                "reason": "manual_20pct_limit15_partial_before_reprice",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            tracker.save(data)
            print(f"  recorded partial: {old_matched:.2f} sh @ ${actual_price:.4f}")
            break

# 4. Compute remaining shares to re-post
remaining = round(old_size - old_matched, 2)
bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"\nLive bid/ask: ${bid:.3f}/${ask:.3f}")
print(f"Re-posting {remaining} sh @ ${NEW_PRICE}")

result = executor.place_limit_sell(token_id=TOKEN, price=NEW_PRICE, shares=remaining)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"ORDER LIVE: {oid[:24]}... size={result.get('size_shares')}")
print(f"Watching {WATCH_SECONDS}s...\n")

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
print(f"\nFinal: {final_status}  matched {final_matched:.2f}/{remaining}")

if final_matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real["vwap"] if real and real["size"] > 0 else NEW_PRICE
    revenue = real["cost_usd"] if real and real["size"] > 0 else final_matched * NEW_PRICE
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
                "reason": "manual_20pct_reprice_limit14_gtc",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            tracker.save(data)
            print(f"[OK] sold {final_matched:.2f} sh @ ${actual_price:.4f} revenue ${revenue:.2f} PnL ${pnl:+.2f}")
            break

if final_status != "MATCHED":
    print(f"\nORDER REMAINS LIVE (GTC): {oid}")
    print(f"  Remaining ~{remaining - final_matched:.2f} sh @ ${NEW_PRICE}")
