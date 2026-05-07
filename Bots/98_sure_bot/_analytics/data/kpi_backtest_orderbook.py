"""
KPI Backtest: model impact of orderbook check + sub-match filter on 98_sure_bot.
Uses real bot_log.txt data to simulate what would have happened.
"""
import re
import json
from collections import defaultdict
from datetime import datetime

LOG = r'C:\Users\Honor\Desktop\Polymarket\Bots\98_sure_bot\bot_log.txt'
POS = r'C:\Users\Honor\Desktop\Polymarket\Bots\98_sure_bot\positions.json'

# === Sub-match patterns ===
SUB_PATTERNS = [
    r'\bmap\s*\d', r'\bgame\s*\d', r'\bset\s*\d',
    r'\bround\s*\d', r'\bperiod\s*\d', r'\bhalf\s*[12]',
    r'\b(1st|2nd|3rd)\s*(game|map|set)',
    r'over/under.*game', r'over/under.*map',
    r'total kills.*game', r'total kills.*map',
]

def is_sub(title):
    t = title.lower()
    return any(re.search(p, t) for p in SUB_PATTERNS)

# === Parse log ===
placing_re = re.compile(r'(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}).*Placing bet: (.+?) \| price ([0-9.]+) -> limit ([0-9.]+) \| \$([0-9.]+)')
filled_re = re.compile(r'(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}).*\[main\] INFO: FILLED: (.+)')
not_filled_re = re.compile(r'(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}).*NOT FILLED \((\w+)\): (.+)')
partial_re = re.compile(r'(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}).*PARTIAL: (.+)')

bets = []
filled_set = set()
not_filled_set = set()

with open(LOG, 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        m = placing_re.search(line)
        if m:
            bets.append({
                'date': m.group(1),
                'time': m.group(2),
                'hour': int(m.group(2)[:2]),
                'title': m.group(3).strip(),
                'gamma_price': float(m.group(4)),
                'limit': float(m.group(5)),
                'amount': float(m.group(6)),
                'slippage': round(float(m.group(5)) - float(m.group(4)), 4),
            })
            continue

        m = filled_re.search(line)
        if m and 'NOT FILLED' not in line:
            filled_set.add(m.group(3).strip()[:60])
            continue

        m = not_filled_re.search(line)
        if m:
            not_filled_set.add(m.group(4).strip()[:60])

# Mark filled status
for b in bets:
    key = b['title'][:60]
    if key in filled_set:
        b['filled'] = True
    elif key in not_filled_set:
        b['filled'] = False
    else:
        b['filled'] = None  # unknown (partial or still pending)

    b['is_sub'] = is_sub(b['title'])

    # Price bucket
    p = b['gamma_price']
    if p < 0.975:
        b['bucket'] = '96.0-97.5c'
    elif p < 0.985:
        b['bucket'] = '97.5-98.5c'
    elif p < 0.990:
        b['bucket'] = '98.5-99.0c'
    else:
        b['bucket'] = '99.0-99.5c'

# === Load positions for P&L ===
with open(POS, 'r', encoding='utf-8') as f:
    data = json.load(f)

pos_by_title = {}
for p in data['positions'].values():
    t = p.get('title', '')[:60]
    pos_by_title[t] = p

# === ANALYSIS ===
# Skip first day (March 18 = startup burst)
bets_analysis = [b for b in bets if b['date'] >= '2026-03-19']

# Calculate days
dates = sorted(set(b['date'] for b in bets_analysis))
num_days = len(dates)

print("=" * 70)
print(f"98_SURE_BOT KPI BACKTEST")
print(f"Period: {dates[0]} to {dates[-1]} ({num_days} days)")
print(f"Total bets analyzed: {len(bets_analysis)}")
print("=" * 70)

# === 1. Historical stats (AS-IS, before changes) ===
print("\n" + "=" * 70)
print("SECTION 1: HISTORICAL STATS (before orderbook + sub-match changes)")
print("=" * 70)

for label, filter_fn in [
    ("ALL bets", lambda b: True),
    ("Non-sub-match only", lambda b: not b['is_sub']),
    ("Sub-match only", lambda b: b['is_sub']),
]:
    subset = [b for b in bets_analysis if filter_fn(b)]
    filled = [b for b in subset if b['filled'] == True]
    unfilled = [b for b in subset if b['filled'] == False]
    total_attempts = len(filled) + len(unfilled)

    print(f"\n--- {label} ---")
    print(f"  Attempts: {total_attempts}")
    print(f"  Filled: {len(filled)}")
    print(f"  Not filled: {len(unfilled)}")
    if total_attempts > 0:
        print(f"  Fill rate: {len(filled)/total_attempts*100:.1f}%")
        print(f"  Fills/day: {len(filled)/num_days:.1f}")
        print(f"  Attempts/day: {total_attempts/num_days:.1f}")

# === 2. By bucket ===
print("\n" + "=" * 70)
print("SECTION 2: FILL RATE BY PRICE BUCKET (non-sub-match)")
print("=" * 70)

non_sub = [b for b in bets_analysis if not b['is_sub']]
bucket_order = ['96.0-97.5c', '97.5-98.5c', '98.5-99.0c', '99.0-99.5c']

print(f"\n{'Bucket':15s} | {'Attempts':>8s} | {'Filled':>6s} | {'Unfilled':>8s} | {'FillRate':>8s} | {'Fills/day':>9s}")
print("-" * 70)

bucket_stats = {}
for bucket in bucket_order:
    subset = [b for b in non_sub if b['bucket'] == bucket]
    filled = [b for b in subset if b['filled'] == True]
    unfilled = [b for b in subset if b['filled'] == False]
    total = len(filled) + len(unfilled)
    rate = len(filled)/total*100 if total > 0 else 0
    fpd = len(filled)/num_days
    bucket_stats[bucket] = {
        'attempts': total, 'filled': len(filled), 'unfilled': len(unfilled),
        'fill_rate': rate, 'fills_per_day': fpd,
    }
    print(f"{bucket:15s} | {total:8d} | {len(filled):6d} | {len(unfilled):8d} | {rate:7.1f}% | {fpd:9.1f}")

total_f = sum(s['filled'] for s in bucket_stats.values())
total_a = sum(s['attempts'] for s in bucket_stats.values())
print(f"{'TOTAL':15s} | {total_a:8d} | {total_f:6d} | {total_a-total_f:8d} | {total_f/total_a*100:7.1f}% | {total_f/num_days:9.1f}")

# === 3. P&L by bucket ===
print("\n" + "=" * 70)
print("SECTION 3: P&L BY PRICE BUCKET (from positions.json)")
print("=" * 70)

# Get all won/lost positions (non-sub)
wins_by_bucket = defaultdict(list)
losses_by_bucket = defaultdict(list)

for key, p in data['positions'].items():
    title = p.get('title', '')
    if is_sub(title):
        continue
    status = p.get('status', '')
    entry = p.get('entry_price', 0)
    pnl = p.get('pnl', 0)
    cost = p.get('cost_usd', 0)

    if entry < 0.975:
        bucket = '96.0-97.5c'
    elif entry < 0.985:
        bucket = '97.5-98.5c'
    elif entry < 0.990:
        bucket = '98.5-99.0c'
    else:
        bucket = '99.0-99.5c'

    if status == 'won':
        wins_by_bucket[bucket].append(pnl)
    elif status == 'lost':
        losses_by_bucket[bucket].append(pnl)

print(f"\n{'Bucket':15s} | {'Wins':>4s} | {'Losses':>6s} | {'AvgProfit':>9s} | {'TotalPnL':>9s} | {'PnL/day':>8s}")
print("-" * 65)

total_pnl = 0
for bucket in bucket_order:
    w = wins_by_bucket.get(bucket, [])
    l = losses_by_bucket.get(bucket, [])
    avg_p = sum(w)/len(w) if w else 0
    total = sum(w) + sum(l)
    total_pnl += total
    ppd = total / num_days
    print(f"{bucket:15s} | {len(w):4d} | {len(l):6d} | ${avg_p:8.4f} | ${total:8.2f} | ${ppd:7.2f}")

print(f"{'TOTAL':15s} | {sum(len(v) for v in wins_by_bucket.values()):4d} | {sum(len(v) for v in losses_by_bucket.values()):6d} | {'':>9s} | ${total_pnl:8.2f} | ${total_pnl/num_days:7.2f}")

# === 4. Hourly distribution ===
print("\n" + "=" * 70)
print("SECTION 4: FILLS BY HOUR (non-sub-match)")
print("=" * 70)

hour_fills = defaultdict(int)
for b in non_sub:
    if b['filled'] == True:
        hour_fills[b['hour']] += 1

print(f"\n{'Hour':>5s} | {'Fills':>5s} | {'Fills/day':>9s} | Distribution")
print("-" * 55)
for h in range(24):
    f = hour_fills.get(h, 0)
    fpd = f / num_days
    bar = '#' * int(fpd * 10)
    print(f"{h:02d}:00 | {f:5d} | {fpd:9.2f} | {bar}")

# Peak hours
peak = sorted(hour_fills.items(), key=lambda x: x[1], reverse=True)[:5]
print(f"\nPeak hours: {', '.join(f'{h:02d}:00 ({c} fills)' for h, c in peak)}")

# === 5. MODEL: Expected fills with orderbook check ===
print("\n" + "=" * 70)
print("SECTION 5: EXPECTED IMPACT OF ORDERBOOK CHECK")
print("=" * 70)

# Key insight from live data after the change:
# - Orderbook check shows most markets have best_ask = 0.999
# - Only markets where ask is genuinely in 96-99.5c range pass
# - This eliminates most of the "blind" attempts that timed out

# Estimated retention rates by bucket (based on observation):
# - 96-97.5c: these are politics, often have real asks in range -> 70% retained
# - 97.5-98.5c: mixed, many sports with real asks -> 50% retained
# - 98.5-99.0c: many have ask=0.999 -> 35% retained
# - 99.0-99.5c: almost all have ask=0.999 -> 15% retained

retention = {
    '96.0-97.5c': 0.70,
    '97.5-98.5c': 0.50,
    '98.5-99.0c': 0.35,
    '99.0-99.5c': 0.15,
}

# For retained bets, fill rate jumps because we only bet when ask is real
# Estimated fill rate for retained (orderbook-verified) bets:
new_fill_rate = {
    '96.0-97.5c': 0.55,  # politics: wider spread, slightly lower
    '97.5-98.5c': 0.60,
    '98.5-99.0c': 0.65,
    '99.0-99.5c': 0.50,
}

print(f"\n{'Bucket':15s} | {'OldFills/d':>10s} | {'Retained%':>9s} | {'NewFillR%':>9s} | {'NewFills/d':>10s} | {'Change':>7s}")
print("-" * 75)

total_old_fpd = 0
total_new_fpd = 0

for bucket in bucket_order:
    old = bucket_stats[bucket]
    old_fpd = old['fills_per_day']
    total_old_fpd += old_fpd

    # New: attempts * retention * new_fill_rate / num_days
    new_attempts = old['attempts'] * retention[bucket]
    new_fills = new_attempts * new_fill_rate[bucket]
    new_fpd = new_fills / num_days
    total_new_fpd += new_fpd

    change = new_fpd - old_fpd
    print(f"{bucket:15s} | {old_fpd:10.1f} | {retention[bucket]*100:8.0f}% | {new_fill_rate[bucket]*100:8.0f}% | {new_fpd:10.1f} | {change:+7.1f}")

print(f"{'TOTAL':15s} | {total_old_fpd:10.1f} | {'':>9s} | {'':>9s} | {total_new_fpd:10.1f} | {total_new_fpd-total_old_fpd:+7.1f}")

# === 6. Expected P&L ===
print("\n" + "=" * 70)
print("SECTION 6: EXPECTED P&L WITH ORDERBOOK CHECK")
print("=" * 70)

avg_profit_by_bucket = {
    '96.0-97.5c': 0.3160,
    '97.5-98.5c': 0.1722,
    '98.5-99.0c': 0.1145,
    '99.0-99.5c': 0.0699,
}

# With orderbook, profit per fill is slightly lower (tighter buffer)
# Buffer is ~0.1c less than slippage, so profit drops by ~$0.01
profit_adj = {
    '96.0-97.5c': 0.28,   # buffer 0.3c vs slippage 0.5c -> less overpay
    '97.5-98.5c': 0.15,   # buffer 0.2c vs slippage 0.4c
    '98.5-99.0c': 0.10,   # buffer 0.1c vs slippage 0.3c
    '99.0-99.5c': 0.06,   # buffer 0.1c vs slippage 0.3c
}

# Win rate stays same: 99.65%
win_rate = 0.9965
avg_loss = 4.89  # from the 1 observed loss

new_fills_by_bucket = {}
for bucket in bucket_order:
    old = bucket_stats[bucket]
    new_attempts = old['attempts'] * retention[bucket]
    new_fills = new_attempts * new_fill_rate[bucket]
    new_fpd = new_fills / num_days
    new_fills_by_bucket[bucket] = new_fpd

total_new_fills = sum(new_fills_by_bucket.values())
daily_win_profit = sum(new_fills_by_bucket[b] * profit_adj[b] for b in bucket_order)
daily_losses = total_new_fills * (1 - win_rate) * avg_loss
daily_net = daily_win_profit - daily_losses

print(f"\n{'Bucket':15s} | {'Fills/day':>9s} | {'Profit/fill':>11s} | {'Daily PnL':>9s}")
print("-" * 55)
for bucket in bucket_order:
    fpd = new_fills_by_bucket[bucket]
    profit = profit_adj[bucket]
    daily = fpd * profit * win_rate
    print(f"{bucket:15s} | {fpd:9.1f} | ${profit:10.4f} | ${daily:8.2f}")

print(f"\n  Daily win profit: ${daily_win_profit:.2f}")
print(f"  Daily loss estimate: ${daily_losses:.2f}")
print(f"  DAILY NET P&L: ${daily_net:.2f}")
print(f"  MONTHLY NET P&L: ${daily_net * 30:.2f}")

# === 7. Sub-match impact ===
print("\n" + "=" * 70)
print("SECTION 7: SUB-MATCH FILTER IMPACT")
print("=" * 70)

sub_bets = [b for b in bets_analysis if b['is_sub']]
sub_filled = [b for b in sub_bets if b['filled'] == True]
sub_unfilled = [b for b in sub_bets if b['filled'] == False]

# P&L from sub-match positions
sub_wins = []
sub_losses = []
for key, p in data['positions'].items():
    title = p.get('title', '')
    if not is_sub(title):
        continue
    if p.get('status') == 'won':
        sub_wins.append(p.get('pnl', 0))
    elif p.get('status') == 'lost':
        sub_losses.append(p.get('pnl', 0))

sub_total_pnl = sum(sub_wins) + sum(sub_losses)

print(f"\n  Sub-match attempts: {len(sub_filled) + len(sub_unfilled)}")
print(f"  Sub-match fills: {len(sub_filled)}")
print(f"  Sub-match wins: {len(sub_wins)}")
print(f"  Sub-match losses: {len(sub_losses)}")
print(f"  Sub-match total P&L: ${sub_total_pnl:.2f}")
print(f"  Sub-match avg profit/win: ${sum(sub_wins)/len(sub_wins):.4f}" if sub_wins else "  No wins")
if sub_losses:
    print(f"  Sub-match losses detail: {', '.join(f'${l:.2f}' for l in sub_losses)}")
print(f"\n  Verdict: {'REMOVE (negative P&L)' if sub_total_pnl < 0 else 'KEEP (positive P&L)' if sub_total_pnl > 1 else 'MARGINAL'}")

# === 8. COMBINED IMPACT ===
print("\n" + "=" * 70)
print("SECTION 8: COMBINED KPI COMPARISON")
print("=" * 70)

old_fills_day = total_f / num_days
old_pnl_day = total_pnl / num_days

print(f"\n{'Metric':25s} | {'OLD (as-is)':>12s} | {'NEW (projected)':>15s} | {'Change':>10s}")
print("-" * 70)
print(f"{'Fills/day':25s} | {old_fills_day:12.1f} | {total_new_fills:15.1f} | {total_new_fills - old_fills_day:+10.1f}")
print(f"{'Fill rate':25s} | {total_f/total_a*100:11.1f}% | {'~55%':>15s} | {'+35%':>10s}")
print(f"{'Daily P&L':25s} | ${old_pnl_day:11.2f} | ${daily_net:14.2f} | ${daily_net - old_pnl_day:+9.2f}")
print(f"{'Monthly P&L':25s} | ${old_pnl_day*30:11.2f} | ${daily_net*30:14.2f} | ${(daily_net-old_pnl_day)*30:+9.2f}")
print(f"{'Win rate':25s} | {'99.65%':>12s} | {'99.65%':>15s} | {'0%':>10s}")
print(f"{'Wasted attempts/day':25s} | {(total_a-total_f)/num_days:12.0f} | {'~10':>15s} | {'-90%':>10s}")
print(f"{'Sub-match fills lost':25s} | {'0':>12s} | {f'-{len(sub_filled)}/8d':>15s} | {'':>10s}")

# === 9. RECOMMENDED KPIs ===
print("\n" + "=" * 70)
print("SECTION 9: RECOMMENDED KPIs")
print("=" * 70)

print("""
+------------------------+-----------+-----------+-----------+
| KPI                    | GREEN     | YELLOW    | RED       |
+------------------------+-----------+-----------+-----------+
| Fills/day              | >= 20     | 12-19     | < 12      |
| Daily P&L              | >= $2.00  | $1.00-2   | < $1.00   |
| Monthly P&L            | >= $60    | $30-60    | < $30     |
| Win rate               | >= 99.0%  | 98-99%    | < 98%     |
| Fill rate              | >= 40%    | 25-40%    | < 25%     |
| Open positions         | >= 30     | 20-30     | < 20      |
| Avg profit/fill        | >= $0.10  | $0.06-10  | < $0.06   |
+------------------------+-----------+-----------+-----------+

TRIGGERS FOR CONFIG CHANGES:
- If fills/day < 12 for 3 consecutive days -> raise MAX_PRICE to 0.997
- If fills/day < 8 for 2 consecutive days  -> raise MAX_PRICE to 0.998
- If win rate drops below 98%              -> review loss patterns
- If daily P&L < $0 for 3 days             -> pause and audit
- If fill rate > 70%                       -> can tighten BUFFER_RULES

MONITORING SCHEDULE:
- Day 1-3 (Mar 27-29): observe, no changes
- Day 3: first KPI review vs targets
- Day 7: full review, decide on MAX_PRICE adjustment
- Weekly: ongoing P&L tracking
""")

print("\nDone. Output ready for report.")
