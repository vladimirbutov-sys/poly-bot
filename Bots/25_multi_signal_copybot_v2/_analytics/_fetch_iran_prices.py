"""Fetch minute-level price history for top Iran markets over Feb18-Apr18 2026 window."""
import urllib.request, sys, io, json, time
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

catalog = json.load(open(
    r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\_iran_markets_catalog.json',
    'r', encoding='utf-8'))

# Pick the politically reactive ones (skip FIFA)
blacklist_slugs = {'will-iran-win-the-2026-fifa-world-cup-788'}
chosen = [m for m in catalog if m['slug'] not in blacklist_slugs]
print('chosen markets:', len(chosen))

start_ts = int(datetime(2026, 2, 18, tzinfo=timezone.utc).timestamp())
end_ts = int(datetime(2026, 4, 18, 23, 59, tzinfo=timezone.utc).timestamp())
print('window:', start_ts, end_ts, '->', (end_ts - start_ts) / 86400, 'days')


def fetch_range(token, t0, t1):
    """CLOB returns <=1440 points per 1m request; split into ~24h chunks."""
    all_points = []
    cur = t0
    step = 24 * 3600
    while cur < t1:
        nxt = min(cur + step, t1)
        url = f'https://clob.polymarket.com/prices-history?market={token}&startTs={cur}&endTs={nxt}&fidelity=1'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            d = json.loads(resp.read())
            hist = d.get('history', d if isinstance(d, list) else [])
            all_points.extend(hist)
        except Exception as e:
            print(f'  chunk err {cur}-{nxt}: {e}')
        cur = nxt
        time.sleep(0.15)
    return all_points


result = {}
for m in chosen:
    tids = m.get('clobTokenIds')
    if isinstance(tids, str):
        tids = json.loads(tids)
    if not tids or len(tids) < 2:
        continue
    yes_token = tids[0]
    slug = m['slug']
    print(f'\n--- fetching {slug} YES ---')
    pts = fetch_range(yes_token, start_ts, end_ts)
    # Dedupe by timestamp
    by_t = {}
    for p in pts:
        by_t[int(p['t'])] = float(p['p'])
    series = sorted(by_t.items())
    print(f'  points: {len(series)} ({len(series)/1440:.1f} days of min-data)')
    if series:
        print(f'  range: {datetime.utcfromtimestamp(series[0][0])} -> {datetime.utcfromtimestamp(series[-1][0])}')
        print(f'  price range: {min(p for _, p in series):.3f} - {max(p for _, p in series):.3f}')
    result[slug] = {
        'question': m.get('question'),
        'yes_token': yes_token,
        'volume': m.get('volume'),
        'series': series,  # list of [ts, price]
    }

out = r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data\iran_prices_60d.json'
with open(out, 'w', encoding='utf-8') as f:
    json.dump(result, f)
print('\nsaved:', out)
print('markets:', list(result.keys()))
