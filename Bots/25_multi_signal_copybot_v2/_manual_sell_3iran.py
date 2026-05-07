"""Manual sell 100% of 3 Iran-related positions at best bid (floor 2-dec).

Executed 2026-04-15 at user's explicit request.
"""
import sys, io, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TARGETS = [
    ("0xc88d07ae880ae83a16e524e06b28342132138e", "Surrender stockpile"),
    ("0x9b7c0787904e16e1b5053ea5ee1ab66b8eb8c9", "End enrichment"),
    ("0xa4a11a780adc5e824f19f8f0809ba2c8bd00a1", "Trump agree enrichment"),
]

data = tracker.load()
results = []

for key_prefix, label in TARGETS:
    # Find full key
    full_key = None
    pos = None
    for k, p in data["positions"].items():
        if k.startswith(key_prefix):
            full_key = k
            pos = p
            break
    if not pos or pos.get("status") != "open":
        print(f"[{label}] position not found or not open — SKIP")
        results.append((label, "not_open", 0, 0))
        continue

    token = pos.get("token_id")
    shares = float(pos.get("size_shares", 0) or 0)
    if shares < 0.5:
        print(f"[{label}] dust shares {shares} — SKIP")
        results.append((label, "dust", 0, 0))
        continue

    # Re-query orderbook just before selling
    prices = filters.get_orderbook_prices(token)
    if not prices:
        print(f"[{label}] no orderbook — SKIP")
        results.append((label, "no_book", 0, 0))
        continue
    best_bid = float(prices[0])
    # Floor to 2-decimals so our ask ≤ bid → guaranteed fill
    limit_price = math.floor(best_bid * 100) / 100
    if limit_price <= 0.01:
        print(f"[{label}] limit too low ({limit_price}) — SKIP")
        results.append((label, "too_low", 0, 0))
        continue

    print(f"\n=== [{label}] {shares} sh @ ${limit_price} (bid={best_bid}) ===")
    result = executor.place_limit_sell(token_id=token, price=limit_price, shares=shares)

    if isinstance(result, dict) and result.get("error") == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
        print(f"  SKIP: onchain balance {result.get('onchain')} < MIN_SHARES")
        results.append((label, "onchain_empty", 0, 0))
        continue
    if not result:
        print(f"  place_limit_sell returned None — FAIL")
        results.append((label, "place_failed", 0, 0))
        continue

    print(f"  order_id: {result.get('order_id')[:16]}...")
    fill = executor.wait_for_fill_with_details(result["order_id"], timeout=120)
    status = fill.get("status", "UNKNOWN")
    matched = float(fill.get("size_matched") or 0)
    print(f"  status: {status}  matched: {matched:.2f} / {result.get('size_shares')}")

    if matched < 0.5:
        print(f"  nothing filled")
        results.append((label, status, 0, 0))
        continue

    revenue = round(matched * limit_price, 2)
    data = tracker.load()
    tracker.record_sell(data, full_key,
                        matched, limit_price, revenue,
                        f"manual_100%_{label.replace(' ','_')}")
    pnl = revenue - matched * float(pos.get("avg_entry", 0) or 0)
    print(f"  SOLD {matched:.2f} @ ${limit_price} = ${revenue:.2f}  PnL slice: ${pnl:+.2f}")
    results.append((label, "sold", matched, revenue))

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
total_rev = 0
for label, st, sh, rev in results:
    print(f"  {label:30}  {st:15}  {sh:8.2f} sh  ${rev:8.2f}")
    total_rev += rev
print(f"  {'TOTAL':30}  {'':15}  {'':8}  ${total_rev:8.2f}")
