"""Sell 100% of US-Iran nuclear deal by April 30? at best market price.

Limit = floor(best_bid, 2 dec). Fills immediately against the bid stack.
"""
import sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

NEEDLE = "US-Iran nuclear deal by April 30"

data = tracker.load()
full_key, pos = None, None
for k, p in data["positions"].items():
    if NEEDLE in (p.get("title", "") or "") and p.get("status") == "open":
        full_key, pos = k, p
        break
if not pos:
    print("Position not found or not open"); sys.exit(1)

token = pos.get("token_id", "")
shares = float(pos.get("size_shares", 0) or 0)
prices = filters.get_orderbook_prices(token)
best_bid = float(prices[0])
limit = math.floor(best_bid * 100) / 100

print(f"Position  : {pos.get('title')}")
print(f"  Shares  : {shares}  avg ${pos.get('avg_entry')}")
print(f"  Best bid: ${best_bid}   → selling @ limit ${limit}")

result = executor.place_limit_sell(token_id=token, price=limit, shares=shares)
if isinstance(result, dict) and result.get("error") == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
    print(f"SKIP: onchain {result.get('onchain')}"); sys.exit(2)
if not result:
    print("place_limit_sell returned None"); sys.exit(3)

print(f"Order placed: {result.get('order_id')[:20]}...")
print("Waiting for fill (up to 120s)...")
fill = executor.wait_for_fill_with_details(result["order_id"], timeout=120)
status = fill.get("status", "UNKNOWN")
matched = float(fill.get("size_matched") or 0)
print(f"  status={status}  matched={matched:.2f}/{result.get('size_shares')}")

if matched < 0.5:
    print("Nothing filled"); sys.exit(4)

revenue = round(matched * limit, 2)
data = tracker.load()
tracker.record_sell(data, full_key, matched, limit, revenue,
                    "manual_100%_us_iran_nuclear_deal_april30")
avg = float(pos.get("avg_entry", 0) or 0)
pnl = revenue - matched * avg
print(f"\nSOLD {matched:.2f} @ ${limit} = ${revenue:.2f}  PnL: ${pnl:+.2f}")
print("(actual fill may be slightly better — you hit bids ≥ $0.311)")
