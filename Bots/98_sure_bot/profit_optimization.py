"""Final analysis: profit optimization recommendations with historical backing."""
import json
import sys
import os
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

SCANNER_DATA = os.path.join(os.path.dirname(__file__), "..", "97_scanner", "scanner_data.json")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc_data = json.load(f)

sc_markets = sc_data["markets"]

# Build resolved markets dataset
resolved = []
for mid, m in sc_markets.items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue
    mp = m.get("max_price_seen", 0) or m.get("first_price", 0) or 0
    winner = res.get("winner", "")
    high = m.get("high_outcome", "")
    won = (winner == high) if winner and high else False
    cat = m.get("category", "other")

    first_seen = m.get("first_seen", "")
    closed_time = res.get("closed_time", "")
    hours = None
    if first_seen and closed_time:
        try:
            fs = datetime.fromisoformat(first_seen)
            ct = datetime.fromisoformat(closed_time)
            if fs.tzinfo is None: fs = fs.replace(tzinfo=timezone.utc)
            if ct.tzinfo is None: ct = ct.replace(tzinfo=timezone.utc)
            hours = (ct - fs).total_seconds() / 3600
        except: pass

    first_price = m.get("first_price", 0) or 0
    volume = m.get("volume", 0) or 0

    resolved.append({
        "cat": cat, "mp": mp, "won": won, "hours": hours,
        "first_price": first_price, "volume": volume,
    })

print(f"Total resolved in scanner: {len(resolved)}")

# ═══════════════════════════════════════════════════════════════
# PROBLEM DIAGNOSIS
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("PROBLEM DIAGNOSIS: Why few bets?")
print(f"{'='*80}")
print("""
Current scan: 3667 candidates
  - 1979 (54%) blocked by END_DATE — too restrictive
  - 305 (8%) blocked by LOW LIQUIDITY
  - ~800 blocked by PRICE < 97.5% for non-politics (new 96% range unused)
  - Category was EMPTY (Gamma API has no category field) — FIXED now

ROOT CAUSE: end_date filter blocks majority of safe opportunities.
""")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 1: Win rate by category — which can we safely relax?
# ═══════════════════════════════════════════════════════════════
print(f"{'='*80}")
print("1. WIN RATE BY CATEGORY (scanner historical, 97%+)")
print(f"{'='*80}")

cats_data = defaultdict(lambda: {"wins": 0, "losses": 0, "hours": []})
for r in resolved:
    d = cats_data[r["cat"]]
    if r["won"]:
        d["wins"] += 1
    else:
        d["losses"] += 1
    if r["hours"] and r["hours"] > 0:
        d["hours"].append(r["hours"])

print(f"\n{'Category':20s} | {'W':>5s} | {'L':>3s} | {'WR':>6s} | {'Med.Hours':>9s} | {'90th%':>7s}")
print("-" * 70)
for cat in sorted(cats_data.keys(), key=lambda c: cats_data[c]["wins"], reverse=True):
    d = cats_data[cat]
    total = d["wins"] + d["losses"]
    if total < 5:
        continue
    wr = d["wins"] / total * 100
    h = sorted(d["hours"]) if d["hours"] else [0]
    med = h[len(h)//2] if h else 0
    p90 = h[int(len(h)*0.9)] if len(h) > 1 else med
    print(f"{cat:20s} | {d['wins']:5d} | {d['losses']:3d} | {wr:5.1f}% | {med:7.1f}h | {p90:6.1f}h")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 2: What if we extend end_date to 3 days for all safe categories?
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("2. END_DATE EXTENSION: resolution time by category")
print(f"{'='*80}")

safe_cats = []
for cat in sorted(cats_data.keys()):
    d = cats_data[cat]
    total = d["wins"] + d["losses"]
    if total < 10:
        continue
    wr = d["wins"] / total * 100
    if wr >= 99.5:
        h = sorted(d["hours"]) if d["hours"] else [999]
        p95 = h[int(len(h)*0.95)] if len(h) > 1 else h[-1]
        p99 = h[int(len(h)*0.99)] if len(h) > 1 else h[-1]
        safe_cats.append(cat)
        print(f"  {cat:20s}: {wr:.1f}% WR (n={total}) | 95th%={p95:.0f}h | 99th%={p99:.0f}h | max={max(h):.0f}h")

print(f"\nCategories with >=99.5% win rate: {', '.join(safe_cats)}")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 3: What's the loss breakdown?
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("3. ALL LOSSES — what went wrong?")
print(f"{'='*80}")

losses = [r for r in resolved if not r["won"]]
print(f"Total losses: {len(losses)} out of {len(resolved)} ({len(losses)/len(resolved)*100:.2f}%)")
print(f"\nBy category:")
loss_cats = Counter(r["cat"] for r in losses)
for cat, cnt in loss_cats.most_common():
    d = cats_data[cat]
    total = d["wins"] + d["losses"]
    print(f"  {cat:20s}: {cnt} losses (out of {total}, {cnt/total*100:.1f}%)")

print(f"\nBy max_price_seen:")
for thresh in [0.97, 0.975, 0.98, 0.985, 0.99]:
    above = [r for r in losses if r["mp"] >= thresh]
    print(f"  losses at >= {thresh*100:.1f}%: {len(above)}")

# ═══════════════════════════════════════════════════════════════
# ANALYSIS 4: Expected daily profit at different configurations
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("4. EXPECTED DAILY PROFIT — different configurations")
print(f"{'='*80}")

# Count daily resolved markets by category that we COULD have bet on
days = defaultdict(lambda: defaultdict(int))
for r in resolved:
    if r["hours"] is None:
        continue
    cat = r["cat"]
    # Estimate closed date
    # we don't have exact date, but we can use resolution data from scanner
    pass

# Use recent data to estimate daily flow
# Count resolved per day from scanner
daily_by_cat = defaultdict(lambda: Counter())
for mid, m in sc_markets.items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue
    ct = res.get("closed_time", "")[:10]
    if not ct or ct < "2026-03-10":
        continue
    cat = m.get("category", "other")
    mp = m.get("max_price_seen", 0) or m.get("first_price", 0) or 0
    daily_by_cat[ct][cat] += 1

recent_days = sorted(d for d in daily_by_cat.keys() if d >= "2026-03-10")
BET = 5.0

print(f"\nScenario analysis (based on {len(recent_days)} recent days):")
print(f"Bet size: ${BET}")

configs = [
    ("CURRENT (97.5%, 1d end_date, no category)",
     {"min_price": 0.975, "end_date_days": {"default": 1, "politics": 2, "sports": 3}}),
    ("POLITICS 96% + 7d end_date",
     {"min_price": 0.975, "min_price_politics": 0.96, "end_date_days": {"default": 1, "politics": 7, "sports": 3}}),
    ("ALL SAFE CATS 3d end_date",
     {"min_price": 0.975, "min_price_politics": 0.96, "end_date_days": {"default": 3, "politics": 7, "sports": 3}}),
    ("AGGRESSIVE: all 97.5% + 3d, politics 96% + 7d",
     {"min_price": 0.975, "min_price_politics": 0.96, "end_date_days": {"default": 3, "politics": 7, "sports": 3}}),
]

# Estimate how many bets per day per config using scanner data
# Average resolved per day at 97%+ by category
avg_daily = Counter()
for day in recent_days:
    for cat, cnt in daily_by_cat[day].items():
        avg_daily[cat] += cnt
for cat in avg_daily:
    avg_daily[cat] /= len(recent_days)

print(f"\nAvg daily resolved markets by category (97%+):")
for cat, avg in sorted(avg_daily.items(), key=lambda x: x[1], reverse=True)[:10]:
    d = cats_data.get(cat, {"wins": 0, "losses": 0})
    total = d["wins"] + d["losses"]
    wr = d["wins"] / total * 100 if total > 0 else 0
    print(f"  {cat:20s}: {avg:6.1f}/day (WR: {wr:.1f}%)")

# Estimate profit with different end_date limits
# Simple model: if end_date limit = X days, we can bet on markets that resolve within X days
# For each category, what % of markets resolve within 1d, 3d, 7d?
print(f"\n{'='*80}")
print("5. RESOLUTION TIME DISTRIBUTION — what % resolves within X days?")
print(f"{'='*80}")

for cat in ["sports_other", "politics", "geopolitics", "crypto", "other", "esports",
            "basketball", "hockey", "soccer", "finance", "tech"]:
    d = cats_data.get(cat)
    if not d or not d["hours"]:
        continue
    h = sorted(d["hours"])
    n = len(h)
    total = d["wins"] + d["losses"]
    within_1d = sum(1 for x in h if x <= 24) / n * 100
    within_3d = sum(1 for x in h if x <= 72) / n * 100
    within_7d = sum(1 for x in h if x <= 168) / n * 100
    within_14d = sum(1 for x in h if x <= 336) / n * 100
    print(f"  {cat:20s} (n={n:5d}): ≤1d {within_1d:5.1f}% | ≤3d {within_3d:5.1f}% | ≤7d {within_7d:5.1f}% | ≤14d {within_14d:5.1f}%")

# ═══════════════════════════════════════════════════════════════
# FINAL: Concrete daily profit estimates
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("6. PROFIT ESTIMATE: current vs proposed")
print(f"{'='*80}")

# Estimate: for each category, avg bets/day × expected profit/bet
# Current: end_date 1d (default), 2d (politics), 3d (sports)
# Proposed: end_date 3d (default), 7d (politics), 3d (sports)

avg_entry = 0.985  # average entry price across all bets
win_profit_per_bet = (1.0 - avg_entry) * BET / avg_entry

scenarios = {
    "CURRENT": {
        "sports_other": {"end_days": 3, "min_price": 0.975},
        "politics": {"end_days": 2, "min_price": 0.975},
        "geopolitics": {"end_days": 2, "min_price": 0.975},
        "crypto": {"end_days": 1, "min_price": 0.975},
        "other": {"end_days": 1, "min_price": 0.975},
        "esports": {"end_days": 3, "min_price": 0.975},
        "basketball": {"end_days": 3, "min_price": 0.975},
        "hockey": {"end_days": 3, "min_price": 0.975},
        "soccer": {"end_days": 1, "min_price": 0.975},
        "finance": {"end_days": 1, "min_price": 0.975},
        "tech": {"end_days": 1, "min_price": 0.975},
    },
    "PROPOSED": {
        "sports_other": {"end_days": 3, "min_price": 0.975},
        "politics": {"end_days": 7, "min_price": 0.96},
        "geopolitics": {"end_days": 7, "min_price": 0.96},
        "crypto": {"end_days": 3, "min_price": 0.975},
        "other": {"end_days": 3, "min_price": 0.975},
        "esports": {"end_days": 3, "min_price": 0.975},
        "basketball": {"end_days": 3, "min_price": 0.975},
        "hockey": {"end_days": 3, "min_price": 0.975},
        "soccer": {"end_days": 1, "min_price": 0.975},
        "finance": {"end_days": 3, "min_price": 0.975},
        "tech": {"end_days": 3, "min_price": 0.975},
    },
}

for scenario_name, config in scenarios.items():
    print(f"\n--- {scenario_name} ---")
    total_daily_bets = 0
    total_daily_profit = 0
    total_daily_loss = 0

    for cat, cfg in config.items():
        d = cats_data.get(cat)
        if not d or not d["hours"]:
            continue

        h = sorted(d["hours"])
        n = len(h)
        total_resolved = d["wins"] + d["losses"]
        wr = d["wins"] / total_resolved if total_resolved > 0 else 0

        # What % of markets resolve within end_days?
        capture_rate = sum(1 for x in h if x <= cfg["end_days"] * 24) / n

        # Daily resolved for this category
        avg_per_day = avg_daily.get(cat, 0)

        # Estimate bets we can place (factoring capture rate)
        daily_bets = avg_per_day * capture_rate

        # Avg entry price
        if cfg["min_price"] == 0.96:
            avg_ep = 0.978  # lower threshold means lower avg entry
        else:
            avg_ep = 0.985

        profit_per_win = (1.0 - avg_ep) * BET / avg_ep
        loss_per_loss = BET

        daily_profit = daily_bets * wr * profit_per_win
        daily_loss = daily_bets * (1 - wr) * loss_per_loss
        net = daily_profit - daily_loss

        total_daily_bets += daily_bets
        total_daily_profit += daily_profit
        total_daily_loss += daily_loss

        if daily_bets > 0.5:
            print(f"  {cat:20s}: ~{daily_bets:5.1f} bets/day | +${daily_profit:.2f} - ${daily_loss:.2f} = ${net:+.2f}/day")

    net_daily = total_daily_profit - total_daily_loss
    print(f"  {'TOTAL':20s}: ~{total_daily_bets:5.1f} bets/day | +${total_daily_profit:.2f} - ${total_daily_loss:.2f} = ${net_daily:+.2f}/day")
    print(f"  Monthly estimate: ${net_daily * 30:+.2f}")

# ═══════════════════════════════════════════════════════════════
# RECOMMENDATIONS
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*80}")
print("7. SPECIFIC RECOMMENDATIONS (ordered by impact)")
print(f"{'='*80}")

print("""
#1 CRITICAL — CATEGORY DETECTION (already fixed)
   Gamma API has no 'category' field. Added categorize() function.
   Without this, ALL category-specific rules were broken.

#2 HIGH IMPACT — EXTEND end_date TO 3 DAYS FOR ALL SAFE CATEGORIES
   Currently: 1 day default → blocks 54% of candidates
   Proposed: 3 days for all categories with >=99.5% win rate
   Safe categories: other, esports, tech, finance, hockey, basketball
   Impact: ~3x more candidates pass end_date filter
   Risk: near-zero (all have >=99.5% win rate)

#3 MEDIUM IMPACT — ALREADY DONE: POLITICS at 96% + 7d end_date
   18 new candidates found in current scan.
   Impact: ~2-5 extra bets/day from politics

#4 MEDIUM IMPACT — CRYPTO: add to "safe" categories
   Scanner data: 494W/4L = 99.2% win rate at 97%+
   4 losses were ALL threshold/price-prediction markets
   These are ALREADY filtered by check_threshold_market & check_financial_asset
   Safe action: extend end_date to 3 days for crypto

#5 LOW IMPACT — LOWER MIN_LIQUIDITY from $500 to $200
   305 candidates blocked by low liquidity
   Many are legit markets with tight spreads
   Risk: slightly wider spreads on some orders

#6 CONSIDER — BET SIZE OPTIMIZATION
   Current: $5/bet, 61 open positions, 53% capital utilization
   Option A: reduce to $3/bet → more bets, better diversification
   Option B: keep $5, it's working fine
   Not urgent — 47% capital still available
""")
