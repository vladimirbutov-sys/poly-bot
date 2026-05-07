"""
Find features that predict early resolution vs late resolution.
Focus on markets with price >= 0.97 (our target).

Group 1 (GOOD): end_date >1 day in future, but resolved BEFORE end_date
Group 2 (BAD):  end_date >=1 day, resolved AT or AFTER end_date

Goal: find feature combinations that separate Group 1 from Group 2.
"""
import sys, io, json, re
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('../97_scanner/scanner_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# ============================================================
# Collect all resolved markets with max_price >= 0.97
# ============================================================
records = []
for mid, m in data['markets'].items():
    if not m.get('resolved') or not m.get('resolution'):
        continue
    max_p = m.get('max_price_seen', 0) or 0
    if max_p < 0.97:
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

    diff_hours = (closed - end).total_seconds() / 3600  # negative = early

    # Parse game_start_time
    gst_str = m.get('game_start_time', '')
    has_game_start = bool(gst_str)
    game_before_end = False
    game_hours_to_end = None
    if gst_str:
        try:
            gst = datetime.fromisoformat(gst_str.replace('Z', '+00:00'))
            if gst.tzinfo is None:
                gst = gst.replace(tzinfo=timezone.utc)
            game_hours_to_end = (end - gst).total_seconds() / 3600
            game_before_end = gst < end
        except:
            pass

    question = m.get('question', '')
    q_lower = question.lower()

    # Feature: has specific date in question (like "on March 17")
    has_date_in_q = bool(re.search(r'(on\s+\w+\s+\d{1,2}|on\s+\d{4}-\d{2}-\d{2}|today|tonight|this\s+week)', q_lower))

    # Feature: is sports (has game_start_time or sports category)
    category = m.get('category', 'unknown')
    is_sports = category in ('sports_other', 'soccer', 'basketball', 'hockey',
                              'american_football', 'tennis', 'fighting', 'cricket', 'esports')

    # Feature: has line (over/under, spread)
    has_line = m.get('line') is not None and m.get('line') != 0

    # Feature: is neg_risk
    neg_risk = m.get('neg_risk', False)

    # Feature: number of outcomes
    num_outcomes = m.get('num_outcomes', 2)

    # Feature: volume
    volume = m.get('volume', 0) or 0

    # Feature: liquidity
    liquidity = m.get('liquidity', 0) or 0

    # Feature: hours from end_date to now (how far out is end_date)
    # Use first_seen as proxy for "when we'd buy"
    first_seen_str = m.get('first_seen', '')
    hours_end_from_first = m.get('first_hours_to_end', None)

    # Feature: keywords
    has_win = bool(re.search(r'\bwin\b', q_lower))
    has_over_under = bool(re.search(r'\b(over|under|o/u)\b', q_lower))
    has_spread = bool(re.search(r'\bspread\b', q_lower))
    has_will = q_lower.startswith('will ')
    has_vs = bool(re.search(r'\bvs\.?\b', q_lower))
    has_match = bool(re.search(r'\bmatch\b', q_lower))
    has_draw = bool(re.search(r'\bdraw\b', q_lower))
    has_price_target = bool(re.search(r'\b(reach|dip to|close above|close below|hit)\b', q_lower))
    has_temperature = bool(re.search(r'\btemperature\b', q_lower))
    has_announce = bool(re.search(r'\bannounce\b', q_lower))

    # Sports type
    sports_type = m.get('sports_type', '') or ''

    records.append({
        'question': question[:70],
        'category': category,
        'diff_hours': diff_hours,
        'early': diff_hours < 0,
        'volume': volume,
        'liquidity': liquidity,
        'neg_risk': neg_risk,
        'num_outcomes': num_outcomes,
        'has_game_start': has_game_start,
        'game_before_end': game_before_end,
        'game_hours_to_end': game_hours_to_end,
        'has_line': has_line,
        'is_sports': is_sports,
        'has_date_in_q': has_date_in_q,
        'has_win': has_win,
        'has_over_under': has_over_under,
        'has_spread': has_spread,
        'has_vs': has_vs,
        'has_match': has_match,
        'has_draw': has_draw,
        'has_price_target': has_price_target,
        'has_temperature': has_temperature,
        'has_announce': has_announce,
        'sports_type': sports_type,
        'hours_end_from_first': hours_end_from_first,
    })

total = len(records)
early_all = [r for r in records if r['early']]
late_all = [r for r in records if not r['early']]

print(f"Total resolved markets (97%+): {total}")
print(f"  Early (before end_date): {len(early_all)} ({len(early_all)/total*100:.1f}%)")
print(f"  Late (at/after end_date): {len(late_all)} ({len(late_all)/total*100:.1f}%)")

# ============================================================
# FEATURE ANALYSIS: for each feature, show early vs late rate
# ============================================================
print("\n" + "=" * 90)
print("FEATURE ANALYSIS: which features predict EARLY resolution?")
print("=" * 90)

features = [
    ('category', None),  # special handling
    ('has_game_start', True),
    ('is_sports', True),
    ('has_line', True),
    ('neg_risk', True),
    ('neg_risk', False),
    ('has_date_in_q', True),
    ('has_win', True),
    ('has_over_under', True),
    ('has_spread', True),
    ('has_vs', True),
    ('has_match', True),
    ('has_draw', True),
    ('has_price_target', True),
    ('has_temperature', True),
    ('has_announce', True),
]

print(f"\n{'Feature':<30} | {'Total':>6} | {'Early':>6} | {'Early%':>7} | {'Late':>6} | {'Late%':>7} | {'Signal':>8}")
print("-" * 100)

for feat_name, feat_val in features:
    if feat_name == 'category':
        continue
    subset = [r for r in records if r[feat_name] == feat_val]
    n = len(subset)
    if n < 5:
        continue
    n_early = sum(1 for r in subset if r['early'])
    n_late = n - n_early
    early_pct = n_early / n * 100
    base_rate = len(early_all) / total * 100
    signal = early_pct - base_rate
    label = f"{feat_name}={feat_val}"
    marker = "+++" if signal > 15 else "++" if signal > 5 else "+" if signal > 0 else "--" if signal < -5 else "-"
    print(f"{label:<30} | {n:>6} | {n_early:>6} | {early_pct:>6.1f}% | {n_late:>6} | {n_late/n*100:>6.1f}% | {marker:>8}")

# Category breakdown
print(f"\n{'--- By category ---':<30} |")
print(f"{'Feature':<30} | {'Total':>6} | {'Early':>6} | {'Early%':>7} | {'Late':>6} | {'Late%':>7}")
print("-" * 80)
by_cat = defaultdict(lambda: [0, 0])
for r in records:
    by_cat[r['category']][0] += 1
    if r['early']:
        by_cat[r['category']][1] += 1

for cat, (cnt, ecnt) in sorted(by_cat.items(), key=lambda x: -x[1][0]):
    if cnt < 5:
        continue
    print(f"category={cat:<22} | {cnt:>6} | {ecnt:>6} | {ecnt/cnt*100:>6.1f}% | {cnt-ecnt:>6} | {(cnt-ecnt)/cnt*100:>6.1f}%")

# ============================================================
# COMBINATION ANALYSIS
# ============================================================
print("\n" + "=" * 90)
print("COMBINATION ANALYSIS: best feature combos for early resolution")
print("=" * 90)

combos = [
    ("is_sports + has_game_start", lambda r: r['is_sports'] and r['has_game_start']),
    ("is_sports + NO game_start", lambda r: r['is_sports'] and not r['has_game_start']),
    ("NOT sports + has_game_start", lambda r: not r['is_sports'] and r['has_game_start']),
    ("NOT sports + NO game_start", lambda r: not r['is_sports'] and not r['has_game_start']),
    ("has_game_start + game<end", lambda r: r['has_game_start'] and r['game_before_end']),
    ("has_game_start + game>=end", lambda r: r['has_game_start'] and not r['game_before_end']),
    ("sports + game<end + vol>1k", lambda r: r['is_sports'] and r['game_before_end'] and r['volume'] >= 1000),
    ("sports + game<end + vol<1k", lambda r: r['is_sports'] and r['game_before_end'] and r['volume'] < 1000),
    ("esports", lambda r: r['category'] == 'esports'),
    ("sports_other", lambda r: r['category'] == 'sports_other'),
    ("sports_other + game<end", lambda r: r['category'] == 'sports_other' and r['game_before_end']),
    ("soccer + game<end", lambda r: r['category'] == 'soccer' and r['game_before_end']),
    ("crypto", lambda r: r['category'] == 'crypto'),
    ("crypto + has_date_in_q", lambda r: r['category'] == 'crypto' and r['has_date_in_q']),
    ("politics", lambda r: r['category'] == 'politics'),
    ("other + has_date_in_q", lambda r: r['category'] == 'other' and r['has_date_in_q']),
    ("other + NO date_in_q", lambda r: r['category'] == 'other' and not r['has_date_in_q']),
    ("has_vs (matchup)", lambda r: r['has_vs']),
    ("has_win", lambda r: r['has_win']),
    ("has_over_under", lambda r: r['has_over_under']),
    ("has_announce", lambda r: r['has_announce']),
    ("neg_risk + sports", lambda r: r['neg_risk'] and r['is_sports']),
    ("neg_risk + NOT sports", lambda r: r['neg_risk'] and not r['is_sports']),
    ("temperature", lambda r: r['has_temperature']),
    ("price_target (reach/dip)", lambda r: r['has_price_target']),
]

print(f"\n{'Combo':<35} | {'Total':>6} | {'Early':>6} | {'Early%':>7} | {'Avg delay':>10} | {'Med delay':>10} | {'>72h stuck':>10}")
print("-" * 115)
for name, fn in combos:
    subset = [r for r in records if fn(r)]
    n = len(subset)
    if n < 3:
        continue
    n_early = sum(1 for r in subset if r['early'])
    delays = sorted(r['diff_hours'] for r in subset)
    avg_d = sum(delays) / n
    med_d = delays[n // 2]
    stuck = sum(1 for d in delays if d > 72)
    print(f"{name:<35} | {n:>6} | {n_early:>6} | {n_early/n*100:>6.1f}% | {avg_d:>8.1f}h | {med_d:>8.1f}h | {stuck:>4} ({stuck/n*100:.0f}%)")

# ============================================================
# GAME_START_TIME deep dive
# ============================================================
print("\n" + "=" * 90)
print("GAME_START_TIME ANALYSIS")
print("How far is game_start before end_date? And how does this predict early resolution?")
print("=" * 90)

with_game = [r for r in records if r['has_game_start'] and r['game_hours_to_end'] is not None]
print(f"\nMarkets with game_start_time: {len(with_game)}")

game_buckets = [
    ("game 0-2h before end", 0, 2),
    ("game 2-6h before end", 2, 6),
    ("game 6-12h before end", 6, 12),
    ("game 12-24h before end", 12, 24),
    ("game 1-2d before end", 24, 48),
    ("game 2-7d before end", 48, 168),
    ("game AFTER end_date", -999, 0),
]

print(f"\n{'game_start vs end_date':<30} | {'Total':>6} | {'Early':>6} | {'Early%':>7} | {'Med delay':>10} | {'>72h':>6}")
print("-" * 85)
for name, lo, hi in game_buckets:
    subset = [r for r in with_game if lo <= r['game_hours_to_end'] < hi]
    n = len(subset)
    if n < 3:
        continue
    n_early = sum(1 for r in subset if r['early'])
    delays = sorted(r['diff_hours'] for r in subset)
    med_d = delays[n // 2]
    stuck = sum(1 for d in delays if d > 72)
    print(f"{name:<30} | {n:>6} | {n_early:>6} | {n_early/n*100:>6.1f}% | {med_d:>8.1f}h | {stuck:>4} ({stuck/n*100:.0f}%)")

# ============================================================
# HOURS TO END analysis
# ============================================================
print("\n" + "=" * 90)
print("END_DATE DISTANCE: how far is end_date and does it matter?")
print("=" * 90)

with_h2e = [r for r in records if r['hours_end_from_first'] is not None]

h2e_buckets = [
    ("0-6h to end", 0, 6),
    ("6-12h to end", 6, 12),
    ("12-24h to end", 12, 24),
    ("1-2d to end", 24, 48),
    ("2-3d to end", 48, 72),
    ("3-7d to end", 72, 168),
    ("7-14d to end", 168, 336),
    ("14d+ to end", 336, 99999),
]

print(f"\n{'Hours to end (first seen)':<25} | {'Total':>6} | {'Early':>6} | {'Early%':>7} | {'Med delay':>10} | {'>72h':>6}")
print("-" * 80)
for name, lo, hi in h2e_buckets:
    subset = [r for r in with_h2e if lo <= r['hours_end_from_first'] < hi]
    n = len(subset)
    if n < 3:
        continue
    n_early = sum(1 for r in subset if r['early'])
    delays = sorted(r['diff_hours'] for r in subset)
    med_d = delays[n // 2]
    stuck = sum(1 for d in delays if d > 72)
    print(f"{name:<25} | {n:>6} | {n_early:>6} | {n_early/n*100:>6.1f}% | {med_d:>8.1f}h | {stuck:>4} ({stuck/n*100:.0f}%)")

# ============================================================
# FINAL: Best rules for predicting early resolution
# ============================================================
print("\n" + "=" * 90)
print("PROPOSED RULES: markets likely to resolve early (safe to buy with end_date >1 day)")
print("=" * 90)

rules = [
    ("RULE 1: has_game_start + game before end_date",
     lambda r: r['has_game_start'] and r['game_before_end']),
    ("RULE 2: esports (any)",
     lambda r: r['category'] == 'esports'),
    ("RULE 3: sports_other + has_game_start",
     lambda r: r['category'] == 'sports_other' and r['has_game_start']),
    ("RULE 4: has_vs + is_sports",
     lambda r: r['has_vs'] and r['is_sports']),
    ("RULE 5: crypto + date in question",
     lambda r: r['category'] == 'crypto' and r['has_date_in_q']),
    ("COMBINED (any rule matches)",
     lambda r: (r['has_game_start'] and r['game_before_end']) or
               r['category'] == 'esports' or
               (r['has_vs'] and r['is_sports'])),
]

print(f"\n{'Rule':<45} | {'Total':>6} | {'Early':>6} | {'Early%':>7} | {'Late >24h':>10} | {'>72h stuck':>10}")
print("-" * 105)
for name, fn in rules:
    subset = [r for r in records if fn(r)]
    n = len(subset)
    if n < 3:
        continue
    n_early = sum(1 for r in subset if r['early'])
    late_24 = sum(1 for r in subset if r['diff_hours'] > 24)
    stuck = sum(1 for r in subset if r['diff_hours'] > 72)
    print(f"{name:<45} | {n:>6} | {n_early:>6} | {n_early/n*100:>6.1f}% | {late_24:>4} ({late_24/n*100:.0f}%) | {stuck:>4} ({stuck/n*100:.0f}%)")

# Show what we'd MISS (late markets that pass rules = false positives)
print("\n--- False positives: markets matching COMBINED rule but resolved LATE (>24h after end_date) ---")
combined_fn = lambda r: (r['has_game_start'] and r['game_before_end']) or r['category'] == 'esports' or (r['has_vs'] and r['is_sports'])
false_pos = [r for r in records if combined_fn(r) and r['diff_hours'] > 24]
false_pos.sort(key=lambda x: -x['diff_hours'])
print(f"\nTotal false positives (>24h late): {len(false_pos)}")
for r in false_pos[:20]:
    print(f"  {r['diff_hours']/24:>6.1f}d late | vol=${r['volume']:>8,.0f} | {r['category']:<15} | {r['question']}")
