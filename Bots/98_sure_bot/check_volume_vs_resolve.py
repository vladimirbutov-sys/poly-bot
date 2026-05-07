import sys, io, json
from datetime import datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('../97_scanner/scanner_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

resolved = [m for m in data['markets'].values() if m.get('resolved') and m.get('resolution')]

results = []
for m in resolved:
    end_str = m.get('end_date', '')
    closed_str = m.get('resolution', {}).get('closed_time', '')
    vol = m.get('volume', 0) or 0
    if not end_str or not closed_str:
        continue
    try:
        end = datetime.strptime(end_str, '%Y-%m-%d')
        closed = datetime.strptime(closed_str[:19], '%Y-%m-%d %H:%M:%S')
        hours = (closed - end).total_seconds() / 3600
        if hours < -48:
            continue
        results.append({'vol': vol, 'hours': hours, 'q': m.get('question','')[:50]})
    except:
        continue

vol_buckets = [
    ('0-500', 0, 500),
    ('500-1k', 500, 1000),
    ('1k-5k', 1000, 5000),
    ('5k-10k', 5000, 10000),
    ('10k-50k', 10000, 50000),
    ('50k+', 50000, 1e12),
]

print(f'Total resolved: {len(results)}')
print()
hdr = f'{"Volume":12s} | {"Count":>6s} | {"Avg hrs":>8s} | {"Med hrs":>8s} | {"Max hrs":>8s} | {"Slow>24h":>10s}'
print(hdr)
print('-' * len(hdr))

for name, lo, hi in vol_buckets:
    b = [r for r in results if lo <= r['vol'] < hi]
    if not b:
        print(f'{name:12s} | {0:6d} |')
        continue
    hours = sorted([r['hours'] for r in b])
    avg_h = sum(hours) / len(hours)
    median_h = hours[len(hours)//2]
    max_h = max(hours)
    slow = sum(1 for h in hours if h > 24)
    pct = slow / len(b) * 100
    print(f'{name:12s} | {len(b):6d} | {avg_h:8.1f} | {median_h:8.1f} | {max_h:8.1f} | {slow:4d} ({pct:.0f}%)')

print()
print('=== SLOWEST MARKETS (>48h after end_date) ===')
slow_markets = sorted([r for r in results if r['hours'] > 48], key=lambda x: -x['hours'])[:10]
for r in slow_markets:
    print(f'  {r["hours"]:.0f}h | vol=${r["vol"]:.0f} | {r["q"]}')
