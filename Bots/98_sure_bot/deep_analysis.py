"""Deep analysis: why so few bets and how to increase daily profit."""
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

import scanner
import filters
import tracker
from config import PRICE_THRESHOLD, MAX_PRICE, BET_SIZE

# ═══════════════════════════════════════════════════════════════
# 1. SCAN CURRENT MARKET — what's available right now?
# ═══════════════════════════════════════════════════════════════
print("Scanning market... (takes ~10 sec)")
candidates = scanner.scan()
print(f"\n{'='*80}")
print(f"1. CURRENT MARKET SNAPSHOT")
print(f"{'='*80}")
print(f"Total candidates (price {PRICE_THRESHOLD:.3f}-{MAX_PRICE:.3f}): {len(candidates)}")

# Category breakdown
cat_counts = Counter(c.get("category", "other") for c in candidates)
print(f"\nBy category:")
for cat, cnt in cat_counts.most_common(15):
    print(f"  {cat:25s}: {cnt:5d}")

# Price distribution
print(f"\nBy price range:")
price_ranges = [
    ("96.0-96.5%", 0.960, 0.965),
    ("96.5-97.0%", 0.965, 0.970),
    ("97.0-97.5%", 0.970, 0.975),
    ("97.5-98.0%", 0.975, 0.980),
    ("98.0-98.5%", 0.980, 0.985),
    ("98.5-99.0%", 0.985, 0.990),
    ("99.0-99.3%", 0.990, 0.993),
]
for label, lo, hi in price_ranges:
    cnt = sum(1 for c in candidates if lo <= c["price"] < hi)
    bar = "#" * (cnt // 10)
    print(f"  {label}: {cnt:5d} {bar}")

# ═══════════════════════════════════════════════════════════════
# 2. FILTER BREAKDOWN — why are candidates rejected?
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"2. FILTER BREAKDOWN — why candidates are rejected")
print(f"{'='*80}")

data = tracker.load()
open_cids = tracker.get_open_condition_ids(data)

filter_reasons = Counter()
passed_candidates = []
rejected_by_category = defaultdict(lambda: Counter())

for c in candidates:
    passed, reason = filters.run_all_filters(c, open_cids, data)
    if passed:
        passed_candidates.append(c)
    else:
        # Extract filter name from reason
        filter_name = reason.split(":")[0].strip() if ":" in reason else reason[:40]
        filter_reasons[filter_name] += 1
        rejected_by_category[c.get("category", "other")][filter_name] += 1

print(f"\nPassed all filters: {len(passed_candidates)}")
print(f"Rejected: {len(candidates) - len(passed_candidates)}")

print(f"\nRejection reasons (top 15):")
for reason, cnt in filter_reasons.most_common(15):
    pct = cnt / len(candidates) * 100
    print(f"  {reason:50s}: {cnt:5d} ({pct:5.1f}%)")

# Passed candidates detail
if passed_candidates:
    print(f"\n--- CANDIDATES THAT PASSED ALL FILTERS ({len(passed_candidates)}) ---")
    for c in passed_candidates[:20]:
        print(f"  {c['price']:.3f} | {c.get('category','?'):15s} | vol ${c.get('volume_total',0):>10,.0f} | {c['question'][:60]}")
    if len(passed_candidates) > 20:
        print(f"  ... and {len(passed_candidates) - 20} more")

# ═══════════════════════════════════════════════════════════════
# 3. POLITICS CANDIDATES — detail
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"3. POLITICS CANDIDATES — detailed breakdown")
print(f"{'='*80}")

pol_candidates = [c for c in candidates if c.get("category", "").lower() in ("politics", "geopolitics")]
print(f"Total politics candidates: {len(pol_candidates)}")

pol_filter_reasons = Counter()
pol_passed = []
for c in pol_candidates:
    passed, reason = filters.run_all_filters(c, open_cids, data)
    if passed:
        pol_passed.append(c)
    else:
        pol_filter_reasons[reason.split(":")[0].strip() if ":" in reason else reason[:50]] += 1

print(f"Passed: {len(pol_passed)}")
print(f"Rejected: {len(pol_candidates) - len(pol_passed)}")
if pol_filter_reasons:
    print(f"\nPolitics rejection reasons:")
    for reason, cnt in pol_filter_reasons.most_common():
        print(f"  {reason:50s}: {cnt}")

# Show politics by price range
print(f"\nPolitics by price range:")
for label, lo, hi in price_ranges:
    subset = [c for c in pol_candidates if lo <= c["price"] < hi]
    if not subset:
        continue
    passed_cnt = sum(1 for c in subset if filters.run_all_filters(c, open_cids, data)[0])
    print(f"  {label}: {len(subset):4d} total, {passed_cnt:4d} pass filters")

# ═══════════════════════════════════════════════════════════════
# 4. ALREADY-BOUGHT blocking analysis
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"4. ALREADY-BOUGHT: how many good candidates are blocked?")
print(f"{'='*80}")

# Run filters WITHOUT already_bought check
would_pass_without_dupe = 0
already_bought_blocks = []
for c in candidates:
    passed, reason = filters.run_all_filters(c, open_cids, data)
    if not passed and "Already have open position" in reason:
        # Would it pass without dupe check?
        passed2, _ = filters.run_all_filters(c, set(), data)
        if passed2:
            would_pass_without_dupe += 1
            already_bought_blocks.append(c)

print(f"Candidates blocked ONLY by already-bought: {would_pass_without_dupe}")
if already_bought_blocks:
    for c in already_bought_blocks[:10]:
        print(f"  {c['price']:.3f} | {c.get('category','?'):15s} | {c['question'][:60]}")

# ═══════════════════════════════════════════════════════════════
# 5. HISTORICAL SCANNER — daily opportunity volume
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"5. HISTORICAL: daily resolved markets by category (scanner data)")
print(f"{'='*80}")

SCANNER_DATA = os.path.join(os.path.dirname(__file__), "..", "97_scanner", "scanner_data.json")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc_data = json.load(f)

sc_markets = sc_data["markets"]

# Resolved markets by day
daily_resolved = defaultdict(lambda: Counter())
daily_profit_potential = defaultdict(float)

for mid, m in sc_markets.items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue
    closed_time = res.get("closed_time", "")[:10]
    if not closed_time:
        continue
    cat = m.get("category", "other")
    max_price = m.get("max_price_seen", 0) or m.get("first_price", 0) or 0
    winner = res.get("winner", "")
    high = m.get("high_outcome", "")
    won = (winner == high) if winner and high else False

    daily_resolved[closed_time][cat] += 1

    # Potential profit if we bought at max_price_seen
    if won and max_price > 0.96:
        profit = (1.0 - max_price) * BET_SIZE / max_price  # profit per $5 bet
        daily_profit_potential[closed_time] += profit

# Last 14 days
all_days = sorted(daily_resolved.keys())
recent_days = [d for d in all_days if d >= "2026-03-05"]

print(f"\nDaily resolved markets (last 14 days):")
for day in recent_days[-14:]:
    cats = daily_resolved[day]
    total = sum(cats.values())
    profit = daily_profit_potential.get(day, 0)
    top_cats = ", ".join(f"{c}:{n}" for c, n in cats.most_common(3))
    print(f"  {day}: {total:4d} resolved | profit potential ${profit:6.2f} | {top_cats}")

# Average daily resolved
if recent_days:
    avg_resolved = sum(sum(daily_resolved[d].values()) for d in recent_days) / len(recent_days)
    avg_profit = sum(daily_profit_potential.get(d, 0) for d in recent_days) / len(recent_days)
    print(f"\n  Average: {avg_resolved:.0f} markets/day, ${avg_profit:.2f} profit potential/day")

# ═══════════════════════════════════════════════════════════════
# 6. WHAT-IF: different thresholds and filters
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"6. WHAT-IF: profit potential at different thresholds")
print(f"{'='*80}")

# From scanner historical data — win rate and profit by threshold
for thresh in [0.96, 0.965, 0.97, 0.975, 0.98, 0.985]:
    resolved_above = []
    for mid, m in sc_markets.items():
        res = m.get("resolution")
        if not res or not isinstance(res, dict) or not res.get("closed"):
            continue
        mp = m.get("max_price_seen", 0) or m.get("first_price", 0) or 0
        if mp < thresh:
            continue
        winner = res.get("winner", "")
        high = m.get("high_outcome", "")
        won = (winner == high) if winner and high else False
        cat = m.get("category", "other")
        resolved_above.append({"won": won, "price": mp, "cat": cat})

    if not resolved_above:
        continue

    wins = sum(1 for r in resolved_above if r["won"])
    losses = len(resolved_above) - wins
    wr = wins / len(resolved_above) * 100

    # Expected profit per $5 bet
    avg_price = sum(r["price"] for r in resolved_above) / len(resolved_above)
    win_profit = (1.0 - avg_price) * BET_SIZE / avg_price
    loss_cost = BET_SIZE
    expected = wr/100 * win_profit - (1 - wr/100) * loss_cost

    # Losses by category
    loss_cats = Counter(r["cat"] for r in resolved_above if not r["won"])
    loss_info = ", ".join(f"{c}:{n}" for c, n in loss_cats.most_common(5)) if loss_cats else "none"

    print(f"  >= {thresh*100:.1f}%: {wins}W/{losses}L ({wr:.1f}%) | avg entry {avg_price:.3f} | E[profit]/bet ${expected:+.3f} | losses: {loss_info}")

# ═══════════════════════════════════════════════════════════════
# 7. END_DATE constraint analysis
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"7. END_DATE CONSTRAINT: how many candidates blocked?")
print(f"{'='*80}")

end_date_blocked = 0
end_date_blocked_details = Counter()
for c in candidates:
    # Check only end_date filter
    passed_ed, reason_ed = filters.check_end_date(c)
    if not passed_ed:
        end_date_blocked += 1
        cat = c.get("category", "other")
        end_date_blocked_details[cat] += 1

print(f"Total blocked by end_date: {end_date_blocked} of {len(candidates)}")
print(f"By category:")
for cat, cnt in end_date_blocked_details.most_common(10):
    # How many of these would pass other filters?
    pass_others = 0
    for c in candidates:
        if c.get("category", "other") != cat:
            continue
        passed_ed, _ = filters.check_end_date(c)
        if passed_ed:
            continue
        # Would it pass everything else?
        # Temporarily set end_date to tomorrow to bypass
        orig_ed = c.get("end_date", "")
        c["end_date"] = (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat()
        passed_all, _ = filters.run_all_filters(c, open_cids, data)
        c["end_date"] = orig_ed  # restore
        if passed_all:
            pass_others += 1
    print(f"  {cat:25s}: {cnt:5d} blocked | {pass_others:4d} would pass other filters")

# ═══════════════════════════════════════════════════════════════
# 8. BET SIZE analysis
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"8. BET SIZE: current $5 — is it optimal?")
print(f"{'='*80}")

with open('positions.json', 'r', encoding='utf-8') as f:
    pos_data = json.load(f)

open_p = [p for p in pos_data['positions'].values() if p.get('status') == 'open']
balance = pos_data['stats']['current_balance']
invested = sum(p.get('cost_usd', 0) for p in open_p)

print(f"Balance: ${balance:.2f}")
print(f"Invested: ${invested:.2f}")
print(f"Total portfolio: ${balance + invested:.2f}")
print(f"Open positions: {len(open_p)}")
print(f"Avg position size: ${invested/len(open_p):.2f}" if open_p else "")
print(f"Capital utilization: {invested/(balance+invested)*100:.0f}%")

# If we reduced bet size to $3, we could place more bets
for bet in [3, 4, 5, 7, 10]:
    max_bets = int((balance + invested) / bet)
    print(f"  At ${bet}/bet: max {max_bets} simultaneous positions")

# ═══════════════════════════════════════════════════════════════
# 9. VERDICT — specific recommendations
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print(f"9. RECOMMENDATIONS")
print(f"{'='*80}")
print(f"\nAnalysis complete. See sections above for detailed data.")
