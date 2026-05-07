"""Deep dive into political markets resolution patterns."""
import sys, io, json, re
from datetime import datetime, timezone
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('../97_scanner/scanner_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

records = []
for mid, m in data['markets'].items():
    cat = m.get('category', '')
    if cat not in ('politics', 'geopolitics'):
        continue
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
    except:
        continue

    diff_hours = (closed - end).total_seconds() / 3600
    question = m.get('question', '')
    q_lower = question.lower()

    # Sub-categorize political markets
    subtype = 'other_political'
    if re.search(r'\bannounce\b', q_lower):
        subtype = 'announcement'
    elif re.search(r'\b(sign|executive order|veto)\b', q_lower):
        subtype = 'executive_action'
    elif re.search(r'\b(vote|pass|approve|confirm|ratif)\b', q_lower):
        subtype = 'vote/legislation'
    elif re.search(r'\b(say|tweet|post|mention|comment|speak|statement|remark|word)\b', q_lower):
        subtype = 'speech/statement'
    elif re.search(r'\b(meet|summit|visit|call|talk)\b', q_lower):
        subtype = 'meeting/event'
    elif re.search(r'\b(tariff|sanction|ban|restrict|embargo)\b', q_lower):
        subtype = 'policy/tariff'
    elif re.search(r'\b(resign|fire|appoint|nominate|hire|replace)\b', q_lower):
        subtype = 'personnel'
    elif re.search(r'\b(poll|approval|rating|survey)\b', q_lower):
        subtype = 'polls/ratings'
    elif re.search(r'\b(strike|attack|war|ceasefire|peace|invasion|bomb)\b', q_lower):
        subtype = 'military/conflict'
    elif re.search(r'\b(election|primary|caucus|runoff)\b', q_lower):
        subtype = 'election'

    # Key features
    has_date = bool(re.search(r'(on\s+\w+\s+\d{1,2}|\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b|today|tonight|this week|by\s+\w+\s+\d{1,2}|before\s+\w+\s+\d{1,2}|march|april|february|january)', q_lower))
    has_before_by = bool(re.search(r'\b(before|by)\s+\w+\s+\d', q_lower))
    has_during = bool(re.search(r'\b(during|at the)\b', q_lower))
    neg_risk = m.get('neg_risk', False)
    volume = m.get('volume', 0) or 0
    max_price = m.get('max_price_seen', 0) or 0
    num_outcomes = m.get('num_outcomes', 2)
    res_source = m.get('resolution_source', '') or ''

    records.append({
        'question': question[:80],
        'category': cat,
        'subtype': subtype,
        'diff_hours': diff_hours,
        'diff_days': diff_hours / 24,
        'early': diff_hours < 0,
        'volume': volume,
        'neg_risk': neg_risk,
        'max_price': max_price,
        'num_outcomes': num_outcomes,
        'has_date': has_date,
        'has_before_by': has_before_by,
        'has_during': has_during,
        'res_source': res_source[:50],
        'end_date': end_str[:10],
        'closed_time': closed_str[:19],
    })

total = len(records)
print(f"Total politics + geopolitics resolved: {total}")
print(f"  politics: {sum(1 for r in records if r['category']=='politics')}")
print(f"  geopolitics: {sum(1 for r in records if r['category']=='geopolitics')}")

# ============================================================
# ALL political markets sorted by delay
# ============================================================
print("\n" + "=" * 110)
print("ALL POLITICAL MARKETS — sorted by resolution delay")
print("=" * 110)

print(f"\n{'Delay':>8} | {'Vol':>9} | {'End date':<11} | {'Resolved':<20} | {'Sub-type':<18} | {'NR':>3} | Question")
print("-" * 130)
for r in sorted(records, key=lambda x: x['diff_hours']):
    nr = 'Y' if r['neg_risk'] else 'N'
    d = r['diff_hours']
    if d < 0:
        delay_str = f"-{abs(d):.0f}h"
    elif d < 24:
        delay_str = f"{d:.0f}h"
    else:
        delay_str = f"{d/24:.1f}d"
    print(f"{delay_str:>8} | ${r['volume']:>8,.0f} | {r['end_date']:<11} | {r['closed_time']:<20} | {r['subtype']:<18} | {nr:>3} | {r['question']}")

# ============================================================
# By subtype
# ============================================================
print("\n" + "=" * 110)
print("BY SUBTYPE")
print("=" * 110)

by_sub = defaultdict(list)
for r in records:
    by_sub[r['subtype']].append(r)

print(f"\n{'Subtype':<20} | {'Total':>6} | {'Early':>6} | {'Avg delay':>10} | {'Med delay':>10} | {'Max delay':>10} | {'>24h':>6} | {'>48h':>6}")
print("-" * 100)
for sub, items in sorted(by_sub.items(), key=lambda x: -len(x[1])):
    n = len(items)
    n_early = sum(1 for r in items if r['early'])
    delays = sorted(r['diff_hours'] for r in items)
    avg = sum(delays) / n
    med = delays[n // 2]
    mx = max(delays)
    gt24 = sum(1 for d in delays if d > 24)
    gt48 = sum(1 for d in delays if d > 48)
    print(f"{sub:<20} | {n:>6} | {n_early:>6} | {avg:>8.1f}h | {med:>8.1f}h | {mx:>8.1f}h | {gt24:>4} ({gt24/n*100:.0f}%) | {gt48:>4} ({gt48/n*100:.0f}%)")

# ============================================================
# By neg_risk
# ============================================================
print("\n" + "=" * 110)
print("neg_risk vs regular (political)")
print("=" * 110)

for nr in [False, True]:
    items = [r for r in records if r['neg_risk'] == nr]
    if not items:
        continue
    n = len(items)
    delays = sorted(r['diff_hours'] for r in items)
    n_early = sum(1 for r in items if r['early'])
    avg = sum(delays) / n
    med = delays[n // 2]
    gt24 = sum(1 for d in delays if d > 24)
    print(f"\n  neg_risk={nr}: n={n}, early={n_early}, avg={avg:.1f}h, median={med:.1f}h, >24h={gt24} ({gt24/n*100:.0f}%)")

# ============================================================
# By volume
# ============================================================
print("\n" + "=" * 110)
print("BY VOLUME (political)")
print("=" * 110)

vol_buckets = [
    ("$0-5k", 0, 5000),
    ("$5k-50k", 5000, 50000),
    ("$50k-500k", 50000, 500000),
    ("$500k+", 500000, 1e12),
]

print(f"\n{'Volume':<15} | {'Total':>6} | {'Avg delay':>10} | {'Med delay':>10} | {'>24h':>6} | {'>48h':>6}")
print("-" * 70)
for name, lo, hi in vol_buckets:
    items = [r for r in records if lo <= r['volume'] < hi]
    n = len(items)
    if n < 2:
        continue
    delays = sorted(r['diff_hours'] for r in items)
    avg = sum(delays) / n
    med = delays[n // 2]
    gt24 = sum(1 for d in delays if d > 24)
    gt48 = sum(1 for d in delays if d > 48)
    print(f"{name:<15} | {n:>6} | {avg:>8.1f}h | {med:>8.1f}h | {gt24:>4} ({gt24/n*100:.0f}%) | {gt48:>4} ({gt48/n*100:.0f}%)")

# ============================================================
# Has date/during keyword
# ============================================================
print("\n" + "=" * 110)
print("DATE/EVENT KEYWORD IN QUESTION (political)")
print("=" * 110)

for feat, label in [('has_date', 'has date reference'), ('has_during', 'has "during/at the"'), ('has_before_by', 'has "before/by"')]:
    for val in [True, False]:
        items = [r for r in records if r[feat] == val]
        n = len(items)
        if n < 3:
            continue
        delays = sorted(r['diff_hours'] for r in items)
        n_early = sum(1 for r in items if r['early'])
        avg = sum(delays) / n
        med = delays[n // 2]
        gt24 = sum(1 for d in delays if d > 24)
        print(f"  {label}={val}: n={n}, early={n_early} ({n_early/n*100:.0f}%), avg={avg:.1f}h, med={med:.1f}h, >24h={gt24} ({gt24/n*100:.0f}%)")

# ============================================================
# UNRESOLVED political markets (still open)
# ============================================================
print("\n" + "=" * 110)
print("UNRESOLVED POLITICAL MARKETS (still open, 97%+ price)")
print("=" * 110)

unresolved = []
now = datetime.now(timezone.utc)
for mid, m in data['markets'].items():
    cat = m.get('category', '')
    if cat not in ('politics', 'geopolitics'):
        continue
    if m.get('resolved'):
        continue
    max_p = m.get('max_price_seen', 0) or 0
    if max_p < 0.97:
        continue
    end_str = m.get('end_date', '')
    volume = m.get('volume', 0) or 0
    question = m.get('question', '')

    end_date = None
    if end_str:
        try:
            if 'T' in end_str:
                end_date = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
            else:
                end_date = datetime.strptime(end_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        except:
            pass

    days_to_end = None
    if end_date:
        days_to_end = (end_date - now).total_seconds() / 86400

    unresolved.append({
        'question': question[:80],
        'volume': volume,
        'end_date': end_str[:10] if end_str else 'N/A',
        'days_to_end': days_to_end,
        'neg_risk': m.get('neg_risk', False),
        'category': cat,
        'max_price': max_p,
    })

print(f"\nTotal unresolved political 97%+: {len(unresolved)}")
print(f"\n{'Days to end':>11} | {'Vol':>9} | {'MaxP':>5} | {'NR':>3} | {'End date':<11} | Question")
print("-" * 130)
for r in sorted(unresolved, key=lambda x: x['days_to_end'] if x['days_to_end'] is not None else 9999):
    d2e = f"{r['days_to_end']:.1f}d" if r['days_to_end'] is not None else "N/A"
    nr = 'Y' if r['neg_risk'] else 'N'
    print(f"{d2e:>11} | ${r['volume']:>8,.0f} | {r['max_price']:.2f} | {nr:>3} | {r['end_date']:<11} | {r['question']}")
