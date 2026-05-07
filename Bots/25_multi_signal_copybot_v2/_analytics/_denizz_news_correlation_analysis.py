"""
Analyze correlation between denizz's large entries (BUY >= $1000) on Iran-US
markets and significant news events (tier-1 timeline + Trump Truth Social posts).

Methodology:
1. Collect denizz BUYs >= $1000 on 3 Iran markets
2. Collect news events: tier-1 (hour-precision only) + Trump Iran-posts (with UTC)
3. For each BUY, compute:
   - hours_since_last_news (t < 0 means no news before)
   - hours_until_next_news (t = +inf means no news after in window)
4. Classify:
   - 'reactive_2h'      — within 2h AFTER a news event
   - 'reactive_6h'      — within 6h AFTER (broader)
   - 'anticipatory_2h'  — within 2h BEFORE a news event
   - 'isolated'         — no news within 6h in either direction
5. Compute baseline (null hypothesis): if BUYs were uniform in time over the
   analysis window, what fraction would land in a news +/- 2h band?
6. Chi-square vs binomial test to check significance.
"""
import json
from datetime import datetime, timezone, timedelta
from collections import Counter
import math

DATA_DIR = r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data'

# ---------- Load ----------
with open(fr'{DATA_DIR}\denizz_iran_trades.json', encoding='utf-8') as f:
    denizz = json.load(f)

with open(fr'{DATA_DIR}\iran_news_timeline_apr13_20.json', encoding='utf-8') as f:
    news_raw = json.load(f)

with open(fr'{DATA_DIR}\trump_truth_iran_apr13_20.json', encoding='utf-8') as f:
    trump_raw = json.load(f)


def parse_utc(s):
    if s.endswith('Z'):
        s = s[:-1] + '+00:00'
    return datetime.fromisoformat(s).astimezone(timezone.utc)


# ---------- News ----------
news_hour = []  # hour-precision only
news_day = []   # day-precision (excluded from hourly analysis)
for n in news_raw:
    ts = parse_utc(n['timestamp_utc'])
    item = {
        'ts': ts, 'event': n.get('event', ''),
        'tier': n.get('tier'), 'category': n.get('category'),
        'source': 'timeline', 'precision': n.get('timestamp_precision', 'hour')
    }
    if item['precision'] == 'day':
        news_day.append(item)
    else:
        news_hour.append(item)

# Trump posts — assume hour+minute precision; filter Iran-relevant already done upstream
trump_posts = []
for p in trump_raw:
    tsu = p.get('timestamp_utc')
    if not tsu:
        continue
    ts = parse_utc(tsu)
    trump_posts.append({
        'ts': ts, 'event': p.get('content', '')[:120],
        'tier': 1, 'category': 'trump_post', 'source': 'trump', 'precision': 'minute',
        'id': p.get('id'),
    })

# Combined news corpus (hourly+)
all_news = sorted(news_hour + trump_posts, key=lambda x: x['ts'])

# Filter to analysis window: 2026-04-12 00:00 UTC .. 2026-04-20 12:00 UTC
win_start = datetime(2026, 4, 12, 0, 0, tzinfo=timezone.utc)
win_end   = datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc)
all_news = [n for n in all_news if win_start <= n['ts'] <= win_end]

print(f"News within analysis window ({win_start.date()}..{win_end.date()}):")
print(f"  tier-1 hour-precision : {sum(1 for n in all_news if n['source']=='timeline')}")
print(f"  Trump posts           : {sum(1 for n in all_news if n['source']=='trump')}")
print(f"  total                 : {len(all_news)}")
print(f"  (excluded day-precision: {len(news_day)})")


# ---------- Denizz BUYs ----------
buys = []
for mkt_key, mkt in denizz['markets'].items():
    for t in mkt.get('trades', []):
        if t.get('side') != 'BUY':
            continue
        ts = parse_utc(t['datetime'])
        if not (win_start <= ts <= win_end):
            continue
        buys.append({
            'ts': ts, 'market': mkt_key,
            'outcome': t.get('outcome'), 'price': t['price'],
            'size': t['size'], 'usd': t['usd_value'],
        })

buys.sort(key=lambda b: b['ts'])

LARGE_THRESHOLD = 1000.0
large_buys = [b for b in buys if b['usd'] >= LARGE_THRESHOLD]
print(f"\nDenizz BUYs in window:")
print(f"  total : {len(buys)}")
print(f"  >=$1000 (LARGE) : {len(large_buys)}")
print(f"  >=$5000        : {sum(1 for b in buys if b['usd']>=5000)}")


# ---------- Correlation ----------
def nearest_news(ts, news_list):
    """Return (delta_hours_before_trade, nearest_news_item_before,
               delta_hours_after_trade,  nearest_news_item_after)."""
    before, after = None, None
    for n in news_list:
        if n['ts'] <= ts:
            before = n  # latest before
        elif after is None and n['ts'] > ts:
            after = n  # first after
            break
    dt_before = (ts - before['ts']).total_seconds() / 3600 if before else None
    dt_after = (after['ts'] - ts).total_seconds() / 3600 if after else None
    return dt_before, before, dt_after, after


classification = []
for b in large_buys:
    dtb, nb, dta, na = nearest_news(b['ts'], all_news)
    # 'reactive' = news happened BEFORE the trade within N hours
    # 'anticipatory' = news happened AFTER the trade within N hours
    min_gap = min(dtb if dtb is not None else 1e9, dta if dta is not None else 1e9)
    if dtb is not None and dtb <= 2:
        cls = 'reactive_2h'
    elif dta is not None and dta <= 2:
        cls = 'anticipatory_2h'
    elif dtb is not None and dtb <= 6:
        cls = 'reactive_6h'
    elif dta is not None and dta <= 6:
        cls = 'anticipatory_6h'
    else:
        cls = 'isolated'
    classification.append({**b, 'cls': cls, 'dt_before_h': dtb, 'nb': nb, 'dt_after_h': dta, 'na': na})

print(f"\nClassification of {len(large_buys)} LARGE BUYs:")
cls_counts = Counter([c['cls'] for c in classification])
for cls, n in cls_counts.most_common():
    pct = 100 * n / len(large_buys)
    print(f"  {cls:20s} : {n:2d} ({pct:.1f}%)")


# ---------- Baseline ----------
# Null hypothesis: BUYs are uniformly distributed across the window.
# Compute fraction of time covered by ±2h bands around each news event.
win_hours = (win_end - win_start).total_seconds() / 3600
# Build union of [news_ts - 2h, news_ts + 2h] intervals
bands = sorted([(n['ts'] - timedelta(hours=2), n['ts'] + timedelta(hours=2)) for n in all_news])
merged = []
for b in bands:
    if merged and b[0] <= merged[-1][1]:
        merged[-1] = (merged[-1][0], max(merged[-1][1], b[1]))
    else:
        merged.append(list(b))
band_cov = sum((b[1]-b[0]).total_seconds()/3600 for b in merged)
# Also ±2h "before-news" (anticipatory band) and ±2h "after-news" (reactive band)
after_bands = sorted([(n['ts'], n['ts'] + timedelta(hours=2)) for n in all_news])
before_bands = sorted([(n['ts'] - timedelta(hours=2), n['ts']) for n in all_news])

def merged_coverage(intervals):
    m = []
    for b in sorted(intervals):
        if m and b[0] <= m[-1][1]:
            m[-1] = (m[-1][0], max(m[-1][1], b[1]))
        else:
            m.append(list(b))
    return sum((x[1]-x[0]).total_seconds()/3600 for x in m)

after_cov = merged_coverage(after_bands)
before_cov = merged_coverage(before_bands)
print(f"\nTime window     : {win_hours:.1f} h")
print(f"Union ±2h bands : {band_cov:.1f} h ({100*band_cov/win_hours:.1f}% of window)")
print(f"'Reactive' (0..+2h after news)    coverage: {after_cov:.1f} h ({100*after_cov/win_hours:.1f}%)")
print(f"'Anticipatory' (-2h..0 before news) coverage: {before_cov:.1f} h ({100*before_cov/win_hours:.1f}%)")

# Binomial test: observed reactive_2h vs expected
n_trades = len(large_buys)
observed_reactive = cls_counts.get('reactive_2h', 0)
expected_reactive_rate = after_cov / win_hours
expected_reactive_n = n_trades * expected_reactive_rate

# Two-sided binomial p-value (exact)
def binom_pmf(n, k, p):
    from math import comb
    return comb(n, k) * (p**k) * ((1-p)**(n-k))

def binom_p_at_least(n, k, p):
    s = 0
    for i in range(k, n+1):
        s += binom_pmf(n, i, p)
    return s

p_gt = binom_p_at_least(n_trades, observed_reactive, expected_reactive_rate)
print(f"\n--- Statistical test (binomial) ---")
print(f"H0 : P(BUY lands in a 0..+2h post-news band) = {expected_reactive_rate:.3f}")
print(f"Observed reactive_2h : {observed_reactive}/{n_trades}  ({100*observed_reactive/n_trades:.1f}%)")
print(f"Expected reactive_2h : {expected_reactive_n:.1f}")
print(f"P(X >= observed | H0): {p_gt:.4f}")
if p_gt < 0.05:
    print(">>> Statistically significant (p<0.05): denizz buys MORE often after news than chance")
elif p_gt > 0.95:
    print(">>> Statistically significant (p>0.95): denizz buys LESS often after news than chance")
else:
    print(">>> Not statistically significant")

# Also test anticipatory
observed_anti = cls_counts.get('anticipatory_2h', 0)
exp_anti_rate = before_cov / win_hours
p_anti = binom_p_at_least(n_trades, observed_anti, exp_anti_rate)
print(f"\nObserved anticipatory_2h : {observed_anti}/{n_trades}")
print(f"Expected anticipatory_2h : {n_trades*exp_anti_rate:.1f}")
print(f"P(X >= observed | H0)    : {p_anti:.4f}")


# ---------- Event-level table ----------
print(f"\n=== LARGE BUYs with nearest news ===")
for c in classification:
    dtb = c.get('dt_before_h')
    nb = c.get('nb')
    dta = c.get('dt_after_h')
    na = c.get('na')
    print(f"\n{c['ts'].isoformat()[:16]}  [{c['cls']}]")
    print(f"  {c['market'][:50]}  {c['outcome']} @ ${c['price']:.3f}  ${c['usd']:,.0f}")
    if nb and dtb is not None:
        print(f"  -{dtb:5.1f}h ago: [{nb['source']}] {nb['event'][:110]}")
    if na and dta is not None:
        print(f"  +{dta:5.1f}h next: [{na['source']}] {na['event'][:110]}")


# ---------- Save results as JSON for md file ----------
out = {
    'analysis_timestamp_utc': datetime.now(timezone.utc).isoformat(),
    'window_start': win_start.isoformat(),
    'window_end': win_end.isoformat(),
    'window_hours': win_hours,
    'news_count_hour_precision': sum(1 for n in all_news if n['source']=='timeline'),
    'trump_post_count': sum(1 for n in all_news if n['source']=='trump'),
    'total_news_events': len(all_news),
    'excluded_day_precision': len(news_day),
    'total_denizz_buys': len(buys),
    'large_buys_count': len(large_buys),
    'large_threshold_usd': LARGE_THRESHOLD,
    'classification': dict(cls_counts),
    'expected_reactive_rate': expected_reactive_rate,
    'expected_anticipatory_rate': exp_anti_rate,
    'observed_reactive_2h': observed_reactive,
    'observed_anticipatory_2h': observed_anti,
    'binom_p_reactive_ge': p_gt,
    'binom_p_anticipatory_ge': p_anti,
    'large_buys_detail': [{
        'ts': c['ts'].isoformat(),
        'market': c['market'],
        'outcome': c['outcome'],
        'price': c['price'],
        'usd': c['usd'],
        'cls': c['cls'],
        'dt_before_h': c['dt_before_h'],
        'nearest_before_event': c['nb']['event'] if c.get('nb') else None,
        'nearest_before_source': c['nb']['source'] if c.get('nb') else None,
        'dt_after_h': c['dt_after_h'],
        'nearest_after_event': c['na']['event'] if c.get('na') else None,
        'nearest_after_source': c['na']['source'] if c.get('na') else None,
    } for c in classification],
}
out_path = fr'{DATA_DIR}\denizz_news_correlation_results.json'
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print(f"\nResults saved to {out_path}")
