"""Analyze actual fill prices vs Gamma prices from real bot data."""
import re
import json

LOG_FILE = r'C:\Users\Honor\Desktop\Polymarket\Bots\98_sure_bot\bot_log.txt'
POS_FILE = r'C:\Users\Honor\Desktop\Polymarket\Bots\98_sure_bot\positions.json'

# Parse all 'Placing bet' lines
placing_re = re.compile(r'Placing bet: (.+?) \| price ([0-9.]+) -> limit ([0-9.]+) \| \$([0-9.]+)')

bets = []
with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        m = placing_re.search(line)
        if m:
            bets.append({
                'title': m.group(1).strip()[:60],
                'gamma_price': float(m.group(2)),
                'limit': float(m.group(3)),
                'amount': float(m.group(4)),
            })

# Parse NOT FILLED
not_filled_re = re.compile(r'NOT FILLED \(TIMEOUT\): (.+)')
not_filled_titles = set()
with open(LOG_FILE, 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        m = not_filled_re.search(line)
        if m:
            not_filled_titles.add(m.group(1).strip()[:60])

for b in bets:
    b['filled'] = b['title'] not in not_filled_titles

# Load positions.json for actual entry prices
with open(POS_FILE, 'r', encoding='utf-8') as f:
    data = json.load(f)

actual_prices = {}
for p in data['positions'].values():
    title = p.get('title', '')[:60]
    actual_prices[title] = p.get('entry_price', 0)

filled_bets = [b for b in bets if b['filled']]
unfilled_bets = [b for b in bets if not b['filled']]

# Match filled bets to actual entry prices
examples = []
for b in filled_bets:
    actual = actual_prices.get(b['title'], 0)
    if actual > 0:
        saved = b['limit'] - actual
        examples.append({
            'title': b['title'],
            'gamma': b['gamma_price'],
            'limit': b['limit'],
            'actual': actual,
            'saved': saved,
        })

examples.sort(key=lambda x: x['saved'], reverse=True)

print("=== TOP 20 FILLS: Gamma vs Limit vs Actual ===")
print()
hdr = f"{'Title':50s} | {'Gamma':>6s} | {'Limit':>6s} | {'Actual':>6s} | {'Saved':>6s} | Note"
print(hdr)
print("-" * len(hdr))

for e in examples[:20]:
    if e['saved'] > 0.001:
        note = 'BETTER than limit'
    elif e['saved'] < -0.001:
        note = 'WORSE than limit?!'
    else:
        note = '~at limit'
    print(f"{e['title']:50s} | {e['gamma']:.4f} | {e['limit']:.4f} | {e['actual']:.4f} | {e['saved']:+.4f} | {note}")

print(f"\n... showing top 20 of {len(examples)} matched fills")

# Statistics
if examples:
    savings = [e['saved'] for e in examples]
    better = [e for e in examples if e['saved'] > 0.001]
    at_limit = [e for e in examples if abs(e['saved']) <= 0.001]
    worse = [e for e in examples if e['saved'] < -0.001]

    print(f"\n=== FILL PRICE vs LIMIT ({len(examples)} fills) ===")
    print(f"Got BETTER price than limit: {len(better):4d} ({len(better)/len(examples)*100:.1f}%)")
    print(f"Filled at ~limit (+/-0.1c):  {len(at_limit):4d} ({len(at_limit)/len(examples)*100:.1f}%)")
    print(f"Paid MORE than limit:        {len(worse):4d} ({len(worse)/len(examples)*100:.1f}%)")
    print(f"Avg saving vs limit: {sum(savings)/len(savings)*100:.3f}c per fill")

    if better:
        avg_s = sum(e['saved'] for e in better) / len(better)
        print(f"Avg saving when better: {avg_s*100:.3f}c")

    print(f"\n=== PRICE IMPROVEMENT DISTRIBUTION ===")
    brackets = [
        ('Filled at limit (0c)',     -0.001, 0.001),
        ('0.1-0.2c better',          0.001, 0.003),
        ('0.2-0.5c better',          0.003, 0.006),
        ('0.5-1.0c better',          0.006, 0.011),
        ('1.0c+ better',             0.011, 1.0),
    ]
    for label, lo, hi in brackets:
        count = sum(1 for e in examples if lo <= e['saved'] < hi)
        pct = count / len(examples) * 100
        print(f"  {label:25s}: {count:4d} ({pct:.1f}%)")

    # KEY: actual fill vs gamma price
    print(f"\n=== ACTUAL FILL PRICE vs GAMMA PRICE ===")
    below_gamma = [e for e in examples if e['actual'] < e['gamma'] - 0.001]
    at_gamma = [e for e in examples if abs(e['actual'] - e['gamma']) <= 0.001]
    above_gamma = [e for e in examples if e['actual'] > e['gamma'] + 0.001]

    print(f"Filled BELOW Gamma:  {len(below_gamma):4d} ({len(below_gamma)/len(examples)*100:.1f}%) -- seller cheaper than Gamma showed")
    print(f"Filled AT Gamma:     {len(at_gamma):4d} ({len(at_gamma)/len(examples)*100:.1f}%) -- Gamma was accurate")
    print(f"Filled ABOVE Gamma:  {len(above_gamma):4d} ({len(above_gamma)/len(examples)*100:.1f}%) -- paid more than Gamma (slippage eaten)")

    if above_gamma:
        avg_overpay = sum(e['actual'] - e['gamma'] for e in above_gamma) / len(above_gamma)
        print(f"Avg overpay vs Gamma (when above): {avg_overpay*100:.3f}c")

    # For unfilled: what was the gap between limit and likely best_ask?
    print(f"\n=== UNFILLED ANALYSIS ===")
    print(f"Total unfilled: {len(unfilled_bets)}")
    uf_by_bucket = {}
    for b in unfilled_bets:
        if b['gamma_price'] < 0.975:
            bucket = '96-97.5c'
        elif b['gamma_price'] < 0.985:
            bucket = '97.5-98.5c'
        elif b['gamma_price'] < 0.990:
            bucket = '98.5-99c'
        else:
            bucket = '99-99.5c'
        if bucket not in uf_by_bucket:
            uf_by_bucket[bucket] = {'count': 0, 'avg_limit': 0, 'limits': []}
        uf_by_bucket[bucket]['count'] += 1
        uf_by_bucket[bucket]['limits'].append(b['limit'])

    print(f"\n{'Bucket':15s} | {'Unfilled':>8s} | {'Avg Limit':>9s} | {'Min Limit':>9s} | {'Max Limit':>9s}")
    print("-" * 60)
    for bucket in ['96-97.5c', '97.5-98.5c', '98.5-99c', '99-99.5c']:
        if bucket in uf_by_bucket:
            d = uf_by_bucket[bucket]
            avg_l = sum(d['limits']) / len(d['limits'])
            print(f"{bucket:15s} | {d['count']:8d} | {avg_l:9.4f} | {min(d['limits']):9.4f} | {max(d['limits']):9.4f}")

print(f"\n=== OVERALL ===")
print(f"Total bets attempted: {len(bets)}")
print(f"Filled: {len(filled_bets)} ({len(filled_bets)/len(bets)*100:.1f}%)")
print(f"Not filled: {len(unfilled_bets)} ({len(unfilled_bets)/len(bets)*100:.1f}%)")
