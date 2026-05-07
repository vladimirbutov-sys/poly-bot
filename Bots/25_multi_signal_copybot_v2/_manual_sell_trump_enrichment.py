"""Sell 100% Trump enrichment Yes at market (limit = floor(best_bid))."""
import sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

KEY_PREFIX = "0xa4a11a780adc5e824f19f8f0809ba2c8bd00a1"

data = tracker.load()
full_key, pos = None, None
for k, p in data["positions"].items():
    if k.startswith(KEY_PREFIX):
        full_key, pos = k, p
        break
if not pos or pos.get("status") != "open":
    print("Not found or closed"); sys.exit(1)

token = pos.get("token_id", "")
shares = float(pos.get("size_shares", 0) or 0)
prices = filters.get_orderbook_prices(token)
best_bid = float(prices[0])
limit = math.floor(best_bid * 100) / 100

print(f"Position: {pos.get('title')}")
print(f"  Shares : {shares}   tracker-avg ${pos.get('avg_entry')}")
print(f"  Best bid: ${best_bid}  → limit ${limit}")

result = executor.place_limit_sell(token_id=token, price=limit, shares=shares)
if isinstance(result, dict) and result.get("error") == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
    print(f"SKIP onchain {result.get('onchain')}"); sys.exit(2)
if not result:
    print("place_limit_sell returned None"); sys.exit(3)

print(f"Order: {result.get('order_id')[:20]}...")
print("Waiting (120s)...")
fill = executor.wait_for_fill_with_details(result["order_id"], timeout=120)
status = fill.get("status", "UNKNOWN")
matched = float(fill.get("size_matched") or 0)
print(f"  status={status}  matched={matched:.2f}/{result.get('size_shares')}")

if matched < 0.5:
    print("Nothing filled"); sys.exit(4)

revenue = round(matched * limit, 2)
data = tracker.load()
tracker.record_sell(data, full_key, matched, limit, revenue,
                    "manual_100%_trump_enrichment_market")
avg = float(pos.get("avg_entry", 0) or 0)
pnl_tracker = revenue - matched * avg
print(f"\nSOLD {matched:.2f} @ ${limit} = ${revenue:.2f}")
print(f"  PnL (tracker math, with inflated avg): ${pnl_tracker:+.2f}")
print(f"  PnL (real, if true avg ~$0.151):       ~${revenue - matched * 0.151:+.2f}")
print("  (Actual execution may be slightly above $limit — book crossed top bids.)")
