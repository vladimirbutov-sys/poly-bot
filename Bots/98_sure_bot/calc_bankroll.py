"""Calculate bankroll needs for expanded strategy."""
import sys, io, json, re
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, '.')

from filters import COIN_FLIP_PATTERNS, THRESHOLD_PATTERNS, WEATHER_PATTERNS, SLOW_KEYWORDS, FINANCIAL_ASSETS

with open('../97_scanner/scanner_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

resolved = [m for m in data['markets'].values() if m.get('resolved') and m.get('resolution')]
new_range = [m for m in resolved if 0.970 <= m.get('first_price', 0) < 0.993]

def apply_filters(m, min_liq=200):
    question = m.get('question', '')
    q_lower = question.lower()
    for p in FINANCIAL_ASSETS:
        if re.search(p, q_lower): return False
    for p in COIN_FLIP_PATTERNS:
        if re.search(p, q_lower): return False
    for p in THRESHOLD_PATTERNS:
        if re.search(p, q_lower): return False
    for p in WEATHER_PATTERNS:
        if re.search(p, question, re.IGNORECASE): return False
    for p in SLOW_KEYWORDS:
        if re.search(p, q_lower): return False
    snapshots = m.get('snapshots', [])
    liq = 0
    for s in snapshots[:2]:
        l = s.get('liquidity', 0) or 0
        if l > 0:
            liq = l
            break
    if 0 < liq < min_liq:
        return False
    return True

passed = [m for m in new_range if apply_filters(m)]

SLIPPAGE = [(0.970, 0.985, 0.003), (0.985, 0.990, 0.002), (0.990, 0.993, 0.001)]
buckets = [
    ('97.0-97.5', 0.970, 0.975),
    ('97.5-98.0', 0.975, 0.980),
    ('98.0-98.5', 0.980, 0.985),
    ('98.5-99.0', 0.985, 0.990),
    ('99.0-99.3', 0.990, 0.993),
]

print('=== EXPANDED STRATEGY: 97.0 - 99.3 ===')
print()

total_profit = 0
total_cost = 0
total_bets = 0
neg_risk_count = 0
normal_count = 0

for bname, lo, hi in buckets:
    b = [m for m in passed if lo <= m.get('first_price', 0) < hi]
    won = sum(1 for m in b if m.get('high_outcome_won') == True)
    lost = sum(1 for m in b if m.get('high_outcome_won') == False)
    shares = 10 if hi <= 0.985 else 5

    bucket_profit = 0
    bucket_cost = 0
    for m in b:
        price = m['first_price']
        lp = price
        for slo, shi, slip in SLIPPAGE:
            if slo <= price < shi:
                lp = min(price + slip, 0.993)
                break
        cost = shares * lp
        payout = shares * 1.0 if m.get('high_outcome_won') else 0
        pnl = payout - cost
        bucket_profit += pnl
        bucket_cost += cost
        if m.get('neg_risk'): neg_risk_count += 1
        else: normal_count += 1

    total_profit += bucket_profit
    total_cost += bucket_cost
    total_bets += len(b)
    avg_pnl = bucket_profit / len(b) if b else 0
    print(f'{bname}: {len(b)} bets ({won}W/{lost}L) | {shares} shares | avg +${avg_pnl:.4f}/bet | total +${bucket_profit:.2f}')

print(f'\nTotal: {total_bets} bets | Profit: ${total_profit:.2f} | Avg/bet: ${total_profit/total_bets:.4f}')

# Daily
by_date = defaultdict(int)
by_date_cost = defaultdict(float)
for m in passed:
    d = m.get('first_seen', '')[:10]
    if not d: continue
    by_date[d] += 1
    price = m['first_price']
    shares = 10 if price < 0.985 else 5
    lp = price
    for slo, shi, slip in SLIPPAGE:
        if slo <= price < shi:
            lp = min(price + slip, 0.993)
            break
    by_date_cost[d] += shares * lp

print(f'\n=== BY DAY ===')
for d in sorted(by_date.keys()):
    print(f'  {d}: {by_date[d]} bets, ${by_date_cost[d]:.0f} invested')

avg_bets_day = total_bets / len(by_date)
avg_cost_day = sum(by_date_cost.values()) / len(by_date)
avg_resolve = (normal_count * 2 + neg_risk_count * 9) / total_bets
avg_bet_cost = avg_cost_day / avg_bets_day

print(f'\n=== CAPITAL ===')
print(f'Avg bets/day: {avg_bets_day:.0f}')
print(f'Avg daily spend: ${avg_cost_day:.0f}')
print(f'neg_risk: {neg_risk_count}/{total_bets} ({neg_risk_count/total_bets*100:.0f}%)')
print(f'Avg resolve time: {avg_resolve:.1f}h')
print(f'Avg cost/bet: ${avg_bet_cost:.2f}')

peak_bets_per_hour = avg_bets_day * 0.7 / 12
max_locked = peak_bets_per_hour * avg_resolve * avg_bet_cost
avg_locked = avg_bets_day / 24 * avg_resolve * avg_bet_cost

print(f'Avg capital locked: ${avg_locked:.0f}')
print(f'Peak capital locked (70pct in 12h): ${max_locked:.0f}')
print(f'Recommended bankroll (peak x 1.5): ${max_locked * 1.5:.0f}')

# Monthly projection
print(f'\n=== MONTHLY PROJECTION (WR 99.8%) ===')
bets_month = avg_bets_day * 30
avg_profit_bet = total_profit / total_bets
losses_month = bets_month / 500
wins_month = bets_month - losses_month
profit_month = wins_month * avg_profit_bet - losses_month * avg_bet_cost
bankroll = max_locked * 1.5
print(f'Bets/month: {bets_month:.0f}')
print(f'Losses/month: {losses_month:.1f}')
print(f'Avg profit/win: ${avg_profit_bet:.4f}')
print(f'Avg loss: ${avg_bet_cost:.2f}')
print(f'Monthly profit: ${profit_month:.2f}')
print(f'Bankroll: ${bankroll:.0f}')
print(f'ROI: {profit_month/bankroll*100:.1f}%')

# Break-even WR
be_wr = avg_bet_cost / (avg_bet_cost + avg_profit_bet) * 100
print(f'Break-even WR: {be_wr:.2f}%')
