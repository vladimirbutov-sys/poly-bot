"""How many markets resolve BEFORE their end_date vs AFTER?"""
import sys, io, json
from datetime import datetime, timezone
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('../97_scanner/scanner_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

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
        closed = datetime.strptime(closed_str[:19], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        if 'T' in end_str:
            end = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
        else:
            end = datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)

        diff_hours = (closed - end).total_seconds() / 3600  # positive = resolved AFTER end_date

        records.append({
            'question': m.get('question', '')[:70],
            'category': m.get('category', 'unknown'),
            'volume': m.get('volume', 0) or 0,
            'neg_risk': m.get('neg_risk', False),
            'diff_hours': diff_hours,
            'end_date': end_str[:10],
            'closed_time': closed_str[:19],
            'high_outcome_won': m.get('high_outcome_won', None),
        })
    except (ValueError, TypeError):
        continue

total = len(records)
early = [r for r in records if r['diff_hours'] < 0]   # resolved BEFORE end_date
on_time = [r for r in records if 0 <= r['diff_hours'] <= 1]
after = [r for r in records if r['diff_hours'] > 0]

print(f"Total resolved markets with dates: {total}")
print()

# ============================================================
# PART 1: Early vs On-time vs Late
# ============================================================
print("=" * 80)
print("RESOLVED BEFORE end_date vs AFTER end_date")
print("=" * 80)

print(f"\n  Resolved BEFORE end_date:  {len(early):>5}  ({len(early)/total*100:.1f}%)")
print(f"  Resolved within 1h of end_date: {len(on_time):>5}  ({len(on_time)/total*100:.1f}%)")
print(f"  Resolved AFTER end_date:  {len(after):>5}  ({len(after)/total*100:.1f}%)")

# ============================================================
# PART 2: How early do early markets resolve?
# ============================================================
print("\n" + "=" * 80)
print("HOW EARLY DO 'EARLY' MARKETS RESOLVE? (end_date was in the future)")
print("=" * 80)

early_buckets = [
    ("0-1h before end_date", -1, 0),
    ("1-6h before", -6, -1),
    ("6-12h before", -12, -6),
    ("12-24h before", -24, -12),
    ("1-2 days before", -48, -24),
    ("2-7 days before", -168, -48),
    ("7-30 days before", -720, -168),
    ("30+ days before", -999999, -720),
]

print(f"\n{'When resolved':<25} | {'Count':>6} | {'% of early':>10} | {'% of total':>10}")
print("-" * 65)
for name, lo, hi in early_buckets:
    cnt = sum(1 for r in early if lo <= r['diff_hours'] < hi)
    pct_early = cnt / len(early) * 100 if early else 0
    pct_total = cnt / total * 100
    print(f"{name:<25} | {cnt:>6} | {pct_early:>9.1f}% | {pct_total:>9.1f}%")

if early:
    e_hours = sorted(r['diff_hours'] for r in early)
    print(f"\n  Median: {abs(e_hours[len(e_hours)//2]):.1f}h before end_date")
    print(f"  Average: {abs(sum(e_hours)/len(e_hours)):.1f}h before end_date")
    print(f"  Max early: {abs(min(e_hours)):.0f}h ({abs(min(e_hours))/24:.1f} days) before end_date")

# ============================================================
# PART 3: Early resolution by CATEGORY
# ============================================================
print("\n" + "=" * 80)
print("EARLY RESOLUTION BY CATEGORY")
print("=" * 80)

by_cat = defaultdict(lambda: {'total': 0, 'early': 0, 'early_hours': []})
for r in records:
    cat = r['category']
    by_cat[cat]['total'] += 1
    if r['diff_hours'] < 0:
        by_cat[cat]['early'] += 1
        by_cat[cat]['early_hours'].append(r['diff_hours'])

cats_sorted = sorted(by_cat.items(), key=lambda x: -x[1]['total'])

print(f"\n{'Category':<20} | {'Total':>6} | {'Early':>6} | {'Early %':>7} | {'Med early':>10} | {'Avg early':>10}")
print("-" * 80)
for cat, info in cats_sorted:
    pct = info['early'] / info['total'] * 100 if info['total'] else 0
    if info['early_hours']:
        eh = sorted(info['early_hours'])
        med = abs(eh[len(eh)//2])
        avg = abs(sum(eh) / len(eh))
        print(f"{cat:<20} | {info['total']:>6} | {info['early']:>6} | {pct:>6.1f}% | {med:>8.1f}h | {avg:>8.1f}h")
    else:
        print(f"{cat:<20} | {info['total']:>6} | {info['early']:>6} | {pct:>6.1f}% |        N/A |        N/A")

# ============================================================
# PART 4: Early resolution by VOLUME
# ============================================================
print("\n" + "=" * 80)
print("EARLY RESOLUTION BY VOLUME")
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

print(f"\n{'Volume':<15} | {'Total':>6} | {'Early':>6} | {'Early %':>7} | {'Med early':>10}")
print("-" * 65)
for name, lo, hi in vol_buckets:
    b_total = [r for r in records if lo <= r['volume'] < hi]
    b_early = [r for r in b_total if r['diff_hours'] < 0]
    n = len(b_total)
    ne = len(b_early)
    pct = ne / n * 100 if n else 0
    if b_early:
        eh = sorted(r['diff_hours'] for r in b_early)
        med = abs(eh[len(eh)//2])
        print(f"{name:<15} | {n:>6} | {ne:>6} | {pct:>6.1f}% | {med:>8.1f}h")
    else:
        print(f"{name:<15} | {n:>6} | {ne:>6} | {pct:>6.1f}% |        N/A")

# ============================================================
# PART 5: Early resolution by neg_risk
# ============================================================
print("\n" + "=" * 80)
print("EARLY RESOLUTION: neg_risk vs regular")
print("=" * 80)

for nr_val, label in [(False, "Regular (neg_risk=False)"), (True, "neg_risk=True")]:
    b_total = [r for r in records if r['neg_risk'] == nr_val]
    b_early = [r for r in b_total if r['diff_hours'] < 0]
    n = len(b_total)
    ne = len(b_early)
    pct = ne / n * 100 if n else 0
    if b_early:
        eh = sorted(r['diff_hours'] for r in b_early)
        med = abs(eh[len(eh)//2])
        avg = abs(sum(eh) / len(eh))
        print(f"\n  {label}: {ne}/{n} early ({pct:.1f}%), median {med:.1f}h, avg {avg:.1f}h before end_date")
    else:
        print(f"\n  {label}: {ne}/{n} early ({pct:.1f}%)")

# ============================================================
# PART 6: What does this mean for our bot?
# ============================================================
print("\n" + "=" * 80)
print("IMPACT ON OUR BOT (filter: end_date within 1 day)")
print("=" * 80)

# Markets that resolve early have end_date in the FUTURE at resolution time
# Our bot buys markets where end_date is within 1 day in the future
# If a market resolves 2 days before end_date, our bot might NOT have bought it yet
# (because end_date was still >1 day away when the market resolved)

# Question: of early-resolving markets, how many would we have missed because
# end_date was still too far away when they resolved?

print("\nEarly-resolving markets: how far was end_date when they resolved?")
print("(If end_date was >1 day away at resolution, our bot might have missed them)\n")

missed = sum(1 for r in early if r['diff_hours'] < -24)  # resolved >24h before end_date
caught = sum(1 for r in early if -24 <= r['diff_hours'] < 0)  # resolved within 24h of end_date

print(f"  Resolved >1 day before end_date (we might have already bought): {missed} ({missed/total*100:.1f}% of all)")
print(f"  Resolved <1 day before end_date (likely in our window):          {caught} ({caught/total*100:.1f}% of all)")

# But the real question: does it matter? These markets resolved successfully.
# The risk is: can a market resolve BEFORE we sell? Answer: yes, but it resolves
# to $1, so we get paid anyway.

print("\n  NOTE: Early resolution is GOOD for us — market resolves to $1,")
print("  we get paid faster. No risk from early resolution.")

# ============================================================
# PART 7: Examples of very early resolutions
# ============================================================
print("\n" + "=" * 80)
print("TOP 20 EARLIEST RESOLUTIONS (resolved long before end_date)")
print("=" * 80)

earliest = sorted(early, key=lambda x: x['diff_hours'])[:20]
print(f"\n{'Early by':>10} | {'End date':<12} | {'Resolved':<20} | {'Vol':>10} | {'Cat':<15} | Question")
print("-" * 120)
for r in earliest:
    days = abs(r['diff_hours']) / 24
    print(f"{days:>8.1f}d | {r['end_date']:<12} | {r['closed_time']:<20} | ${r['volume']:>9,.0f} | {r['category']:<15} | {r['question']}")
