"""Cancel $0.12 limit, place new buy @ $0.13 for remaining ~263 sh."""
import sys, io, time, hashlib
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

CID   = "0xaa980c83777851bf22a3bd4eeee864d11ce7783096a22ce4af56ff9bf2e1d2cd"
TOKEN = "10065719129703851524738159766241582795004980250212999796913119632612444350346"
TITLE = "Will fewer than 25 ships transit the Strait of Hormuz between April 20-April 26?"
SLUG  = "will-fewer-than-25-ships-transit-the-strait-of-hormuz-between-april-20-april-26"
LIMIT_PRICE = 0.13

# Cancel existing buy order(s)
c = executor._get_client()
orders = [o for o in c.get_orders() if str(o.get('asset_id','')) == TOKEN]
remaining_shares = 0
for o in orders:
    if o.get('side') == 'BUY':
        oid = o.get('id','')
        orig = float(o.get('original_size', 0))
        matched = float(o.get('size_matched', 0))
        remaining_shares = orig - matched
        print(f"Cancelling {oid[:24]}... BUY @ ${o.get('price')}  remaining {remaining_shares:.2f}")
        executor.cancel_order(oid)
        time.sleep(2)

if remaining_shares < 1:
    print("No remaining shares to buy"); sys.exit(0)

# Place buy for remaining USD budget
size_usd = round(remaining_shares * 0.12, 2)  # use the allocated budget
print(f"\nReplacing with ${size_usd} @ ${LIMIT_PRICE}")

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"bid/ask: ${bid:.4f}/${ask:.4f}")

res = executor.place_limit_buy(token_id=TOKEN, price=LIMIT_PRICE, size_usd=size_usd)
if not res or not res.get('order_id'):
    print("PLACE FAILED"); sys.exit(1)
oid = res['order_id']
print(f"ORDER LIVE: {oid[:24]}... size={res.get('size_shares')}")

fill = executor.wait_for_fill_with_details(oid, timeout=120)
print(f"  {fill.get('status')}  matched {fill.get('size_matched'):.2f}/{fill.get('size_original'):.2f}")

matched = float(fill.get('size_matched', 0) or 0)
if matched > 0.5:
    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else LIMIT_PRICE
    actual_cost = round(matched * actual_price, 2)
    print(f"  VWAP ${actual_price:.4f}  cost ${actual_cost:.2f}")

    # Top-up the existing position
    data = tracker.load()
    found_key = None
    for k, p in data.get("positions", {}).items():
        if p.get("token_id") == TOKEN and p.get("status") == "open" and p.get("outcome") == "Yes":
            found_key = k; break
    if found_key:
        p = data["positions"][found_key]
        old_sh = float(p.get("size_shares", 0))
        old_cost = float(p.get("cost_usd", 0))
        new_sh = old_sh + matched
        new_cost = round(old_cost + actual_cost, 4)
        new_avg = new_cost / new_sh if new_sh > 0 else 0
        p["size_shares"] = round(new_sh, 4)
        p["cost_usd"] = new_cost
        p["avg_entry"] = round(new_avg, 6)
        p["parts_filled"] = p.get("parts_filled", 0) + 1
        p.setdefault("order_ids", []).append(oid)
        tracker.save(data)
        print(f"✓ Topped up {found_key}")
        print(f"  total: {new_sh:.2f} sh, cost ${new_cost:.2f}, avg ${new_avg:.4f}")
        print(f"  At YES: payoff ${new_sh:.2f} → PnL +${new_sh - new_cost:.2f}")
    else:
        print("WARN: existing YES position not found")
