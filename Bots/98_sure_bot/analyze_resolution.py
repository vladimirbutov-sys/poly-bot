"""Analyze: how end_date and market category affect resolution speed."""
import sys, io, json
from datetime import datetime, timezone
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('../97_scanner/scanner_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# --- Collect resolved markets with valid dates ---
records = []
for m in data['markets'].values():
    if not m.get('resolved') or not m.get('resolution'):
        continue
    res = m['resolution']
    closed_str = res.get('closed_time', '')
    end_str = m.get('end_date', '')
    if not closed_str or not end_str:
        continue
    try:
        # Parse closed_time
        closed = datetime.strptime(closed_str[:19], '%Y-%m-%d %H:%M:%S')
        closed = closed.replace(tzinfo=timezone.utc)
        # Parse end_date
        if 'T' in end_str:
            end_str_clean = end_str.replace('Z', '+00:00')
            end = datetime.fromisoformat(end_str_clean)
        else:
            end = datetime.strptime(end_str, '%Y-%m-%d')
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        delay_hours = (closed - end).total_seconds() / 3600

        records.append({
            'question': m.get('question', '')[:60],
            'category': m.get('category', 'unknown'),
            'neg_risk': m.get('neg_risk', False),
            'volume': m.get('volume', 0) or 0,
            'delay_hours': delay_hours,
            'end_date': end_str[:10],
            'closed_time': closed_str[:19],
            'high_outcome_won': m.get('high_outcome_won', None),
            'num_outcomes': m.get('num_outcomes', 2),
        })
    except (ValueError, TypeError):
        continue

print(f"Total resolved with valid dates: {len(records)}")
print()

# ============================================================
# PART 1: Resolution delay distribution (overall)
# ============================================================
print("=" * 80)
print("PART 1: HOW FAST DO MARKETS RESOLVE AFTER end_date?")
print("=" * 80)

delay_buckets = [
    ("Before end_date (early)", -999999, 0),
    ("0-1 hours", 0, 1),
    ("1-6 hours", 1, 6),
    ("6-12 hours", 6, 12),
    ("12-24 hours", 12, 24),
    ("1-2 days", 24, 48),
    ("2-3 days", 48, 72),
    ("3-7 days", 72, 168),
    ("7-14 days", 168, 336),
    ("14+ days", 336, 999999),
]

print(f"\n{'Delay bucket':<25} | {'Count':>6} | {'%':>6} | {'Cumulative %':>12}")
print("-" * 60)
cumul = 0
for name, lo, hi in delay_buckets:
    cnt = sum(1 for r in records if lo <= r['delay_hours'] < hi)
    pct = cnt / len(records) * 100 if records else 0
    cumul += pct
    print(f"{name:<25} | {cnt:>6} | {pct:>5.1f}% | {cumul:>10.1f}%")

# Median and average
delays = sorted(r['delay_hours'] for r in records)
avg_delay = sum(delays) / len(delays)
median_delay = delays[len(delays) // 2]
p90 = delays[int(len(delays) * 0.9)]
p95 = delays[int(len(delays) * 0.95)]
p99 = delays[int(len(delays) * 0.99)]
print(f"\nAvg: {avg_delay:.1f}h | Median: {median_delay:.1f}h | P90: {p90:.1f}h | P95: {p95:.1f}h | P99: {p99:.1f}h")

# ============================================================
# PART 2: Resolution delay BY CATEGORY
# ============================================================
print("\n" + "=" * 80)
print("PART 2: RESOLUTION SPEED BY MARKET CATEGORY")
print("=" * 80)

by_cat = defaultdict(list)
for r in records:
    by_cat[r['category']].append(r['delay_hours'])

# Sort by count descending
cats_sorted = sorted(by_cat.items(), key=lambda x: -len(x[1]))

print(f"\n{'Category':<20} | {'Count':>6} | {'Avg h':>7} | {'Med h':>7} | {'P90 h':>7} | {'>24h':>6} | {'>72h':>6} | {'>7d':>6}")
print("-" * 95)
for cat, delays_cat in cats_sorted:
    delays_cat.sort()
    n = len(delays_cat)
    avg = sum(delays_cat) / n
    med = delays_cat[n // 2]
    p90 = delays_cat[int(n * 0.9)] if n >= 10 else delays_cat[-1]
    slow_24 = sum(1 for d in delays_cat if d > 24)
    slow_72 = sum(1 for d in delays_cat if d > 72)
    slow_7d = sum(1 for d in delays_cat if d > 168)
    print(f"{cat:<20} | {n:>6} | {avg:>7.1f} | {med:>7.1f} | {p90:>7.1f} | {slow_24:>4} ({slow_24/n*100:>2.0f}%) | {slow_72:>4} ({slow_72/n*100:>2.0f}%) | {slow_7d:>4} ({slow_7d/n*100:>2.0f}%)")

# ============================================================
# PART 3: Resolution delay BY VOLUME BUCKET
# ============================================================
print("\n" + "=" * 80)
print("PART 3: RESOLUTION SPEED BY MARKET VOLUME")
print("=" * 80)

vol_buckets = [
    ("$0-500", 0, 500),
    ("$500-1k", 500, 1000),
    ("$1k-5k", 1000, 5000),
    ("$5k-10k", 5000, 10000),
    ("$10k-50k", 10000, 50000),
    ("$50k-100k", 50000, 100000),
    ("$100k+", 100000, 1e12),
]

print(f"\n{'Volume':<15} | {'Count':>6} | {'Avg h':>7} | {'Med h':>7} | {'P90 h':>7} | {'>24h':>6} | {'>72h':>6} | {'>7d':>6}")
print("-" * 95)
for name, lo, hi in vol_buckets:
    b = [r['delay_hours'] for r in records if lo <= r['volume'] < hi]
    if not b:
        print(f"{name:<15} | {0:>6} |")
        continue
    b.sort()
    n = len(b)
    avg = sum(b) / n
    med = b[n // 2]
    p90 = b[int(n * 0.9)] if n >= 10 else b[-1]
    slow_24 = sum(1 for d in b if d > 24)
    slow_72 = sum(1 for d in b if d > 72)
    slow_7d = sum(1 for d in b if d > 168)
    print(f"{name:<15} | {n:>6} | {avg:>7.1f} | {med:>7.1f} | {p90:>7.1f} | {slow_24:>4} ({slow_24/n*100:>2.0f}%) | {slow_72:>4} ({slow_72/n*100:>2.0f}%) | {slow_7d:>4} ({slow_7d/n*100:>2.0f}%)")

# ============================================================
# PART 4: Resolution delay BY neg_risk
# ============================================================
print("\n" + "=" * 80)
print("PART 4: RESOLUTION SPEED — neg_risk vs regular")
print("=" * 80)

for nr_val, label in [(True, "neg_risk=True"), (False, "neg_risk=False")]:
    b = [r['delay_hours'] for r in records if r['neg_risk'] == nr_val]
    if not b:
        continue
    b.sort()
    n = len(b)
    avg = sum(b) / n
    med = b[n // 2]
    p90 = b[int(n * 0.9)]
    slow_24 = sum(1 for d in b if d > 24)
    slow_72 = sum(1 for d in b if d > 72)
    slow_7d = sum(1 for d in b if d > 168)
    print(f"\n{label} (n={n}):")
    print(f"  Avg: {avg:.1f}h | Median: {med:.1f}h | P90: {p90:.1f}h")
    print(f"  >24h: {slow_24} ({slow_24/n*100:.1f}%) | >72h: {slow_72} ({slow_72/n*100:.1f}%) | >7d: {slow_7d} ({slow_7d/n*100:.1f}%)")

# ============================================================
# PART 5: CATEGORY + VOLUME cross-analysis (stuck markets)
# ============================================================
print("\n" + "=" * 80)
print("PART 5: STUCK MARKETS (>72h) — BY CATEGORY")
print("=" * 80)

stuck = [r for r in records if r['delay_hours'] > 72]
print(f"\nTotal stuck >72h: {len(stuck)} out of {len(records)} ({len(stuck)/len(records)*100:.1f}%)")

stuck_by_cat = defaultdict(list)
for r in stuck:
    stuck_by_cat[r['category']].append(r)

print(f"\n{'Category':<20} | {'Stuck':>6} | {'Total':>6} | {'Stuck %':>7} | {'Avg vol':>10} | {'Med vol':>10}")
print("-" * 75)
for cat, _ in cats_sorted:
    total_in_cat = len(by_cat[cat])
    stuck_in_cat = stuck_by_cat.get(cat, [])
    n_stuck = len(stuck_in_cat)
    pct = n_stuck / total_in_cat * 100 if total_in_cat else 0
    avg_vol = sum(r['volume'] for r in stuck_in_cat) / n_stuck if n_stuck else 0
    vols = sorted(r['volume'] for r in stuck_in_cat)
    med_vol = vols[len(vols) // 2] if vols else 0
    print(f"{cat:<20} | {n_stuck:>6} | {total_in_cat:>6} | {pct:>6.1f}% | ${avg_vol:>9,.0f} | ${med_vol:>9,.0f}")

# ============================================================
# PART 6: Top 20 slowest markets
# ============================================================
print("\n" + "=" * 80)
print("PART 6: TOP 20 SLOWEST MARKETS")
print("=" * 80)

slowest = sorted(records, key=lambda x: -x['delay_hours'])[:20]
print(f"\n{'Delay':>8} | {'Vol':>10} | {'Cat':<15} | {'Question'}")
print("-" * 100)
for r in slowest:
    d = r['delay_hours']
    days = d / 24
    print(f"{days:>6.1f}d | ${r['volume']:>9,.0f} | {r['category']:<15} | {r['question']}")

# ============================================================
# PART 7: Category + end_date proximity analysis
# ============================================================
print("\n" + "=" * 80)
print("PART 7: DO MARKETS WITH CLOSER end_date RESOLVE FASTER?")
print("=" * 80)

# For our bot: we only buy markets where end_date is within 1 day
# Let's see how resolution delay differs by how far end_date was from now

# Proxy: use first_hours_to_end from scanner data? No, let's just bucket by
# the gap between end_date and when market was created/first_seen

# Better: bucket by volume AND category for markets with end_date <= 1 day in future
# (simulating our bot's filter)

# Actually, let's just look at: for each category, what % resolves within 24h, 48h, 72h
print(f"\n{'Category':<20} | {'n':>5} | {'<6h':>7} | {'<12h':>7} | {'<24h':>7} | {'<48h':>7} | {'<72h':>7}")
print("-" * 80)
for cat, delays_cat in cats_sorted:
    if len(delays_cat) < 10:
        continue
    n = len(delays_cat)
    lt6 = sum(1 for d in delays_cat if d <= 6) / n * 100
    lt12 = sum(1 for d in delays_cat if d <= 12) / n * 100
    lt24 = sum(1 for d in delays_cat if d <= 24) / n * 100
    lt48 = sum(1 for d in delays_cat if d <= 48) / n * 100
    lt72 = sum(1 for d in delays_cat if d <= 72) / n * 100
    print(f"{cat:<20} | {n:>5} | {lt6:>6.1f}% | {lt12:>6.1f}% | {lt24:>6.1f}% | {lt48:>6.1f}% | {lt72:>6.1f}%")
