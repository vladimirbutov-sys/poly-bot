import json, math
from datetime import datetime
from collections import defaultdict, Counter

with open('C:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot_v2/_analytics/data/denizz_full_history.json','r') as f:
    data = json.load(f)

trades = [r for r in data if r['type'] == 'TRADE']
print(f"Total trades: {len(trades)}")

positions = defaultdict(lambda: {'buys': [], 'sells': []})
for t in trades:
    key = (t['conditionId'], t.get('asset',''))
    side = t.get('side', '')
    if side == 'BUY':
        positions[key]['buys'].append(t)
    elif side == 'SELL':
        positions[key]['sells'].append(t)

print(f"Unique positions: {len(positions)}")

results = []
for (cid, asset), pos in positions.items():
    buys = pos['buys']
    sells = pos['sells']
    if not buys:
        continue

    total_buy_usd = sum(b['usdcSize'] for b in buys)
    total_buy_shares = sum(b['size'] for b in buys)
    total_sell_usd = sum(s['usdcSize'] for s in sells)
    total_sell_shares = sum(s['size'] for s in sells)

    first_buy_ts = min(b['timestamp'] for b in buys)
    sell_ratio = total_sell_shares / total_buy_shares if total_buy_shares > 0 else 0

    if sells and sell_ratio >= 0.5:
        last_sell_ts = max(s['timestamp'] for s in sells)
        hold_duration_hours = (last_sell_ts - first_buy_ts) / 3600
        early_sell_shares = sum(s['size'] for s in sells if s['timestamp'] - first_buy_ts < 3*3600)
        early_sell_ratio = early_sell_shares / total_buy_shares if total_buy_shares > 0 else 0

        pnl_usd = total_sell_usd - total_buy_usd
        pnl_pct = pnl_usd / total_buy_usd if total_buy_usd > 0 else 0

        if hold_duration_hours < 3 or early_sell_ratio > 0.8:
            trade_type = "scalp"
        elif hold_duration_hours < 24:
            trade_type = "medium"
        else:
            trade_type = "long"
        status = "closed"
    else:
        hold_duration_hours = None
        pnl_usd = None
        pnl_pct = None
        trade_type = "open"
        status = "open"

    title = buys[0].get('title', 'Unknown')
    results.append({
        'conditionId': cid, 'asset': asset, 'title': title,
        'total_buy_usd': total_buy_usd, 'total_sell_usd': total_sell_usd,
        'total_buy_shares': total_buy_shares, 'total_sell_shares': total_sell_shares,
        'sell_ratio': sell_ratio, 'first_buy_ts': first_buy_ts,
        'hold_duration_hours': hold_duration_hours,
        'pnl_usd': pnl_usd, 'pnl_pct': pnl_pct,
        'trade_type': trade_type, 'status': status,
        'n_buys': len(buys), 'n_sells': len(sells),
    })

type_counts = Counter(r['trade_type'] for r in results)
print(f"\nTrade type distribution:")
for t, c in type_counts.most_common():
    print(f"  {t}: {c}")

closed = [r for r in results if r['status'] == 'closed']
print(f"\nClosed positions: {len(closed)}")

all_buckets = [
    ("<$500", 0, 500),
    ("$500-$1000", 500, 1000),
    ("$1000-$2000", 1000, 2000),
    ("$2000-$3000", 2000, 3000),
    ("$3000-$5000", 3000, 5000),
    ("$5000-$10000", 5000, 10000),
    ("$10000+", 10000, 1e9),
]

print("\n" + "="*130)
hdr = f"{'Size':>15} | {'Total':>5} | {'Scalp':>5} | {'Med':>5} | {'Long':>5} | {'%Scalp':>6} | {'AvgPnL$ scalp':>14} | {'AvgPnL$ med':>12} | {'AvgPnL$ long':>13} | {'AvgPnL% scalp':>14}"
print(hdr)
print("-"*130)

for bname, bmin, bmax in all_buckets:
    in_bucket = [r for r in closed if bmin <= r['total_buy_usd'] < bmax]
    scalps = [r for r in in_bucket if r['trade_type'] == 'scalp']
    mediums = [r for r in in_bucket if r['trade_type'] == 'medium']
    longs = [r for r in in_bucket if r['trade_type'] == 'long']

    avg_pnl_scalp = sum(r['pnl_usd'] for r in scalps)/len(scalps) if scalps else 0
    avg_pnl_med = sum(r['pnl_usd'] for r in mediums)/len(mediums) if mediums else 0
    avg_pnl_long = sum(r['pnl_usd'] for r in longs)/len(longs) if longs else 0
    avg_pct_scalp = sum(r['pnl_pct'] for r in scalps)/len(scalps)*100 if scalps else 0

    pct_scalp = len(scalps)/len(in_bucket)*100 if in_bucket else 0

    print(f"{bname:>15} | {len(in_bucket):>5} | {len(scalps):>5} | {len(mediums):>5} | {len(longs):>5} | {pct_scalp:>5.1f}% | ${avg_pnl_scalp:>12.2f} | ${avg_pnl_med:>10.2f} | ${avg_pnl_long:>11.2f} | {avg_pct_scalp:>12.1f}%")

# FORMULAS
def formula_a(invested):
    bet = 46.41 * math.log(invested) - 278.39
    return max(10, min(200, bet))

X1 = 27 / (math.log(3000) - math.log(500))
Y1 = 10 - X1 * math.log(500)
X2 = 163 / (math.log(30000) - math.log(3000))
Y2 = 37 - X2 * math.log(3000)

def formula_b(invested):
    if invested < 3000:
        bet = X1 * math.log(invested) + Y1
    else:
        bet = X2 * math.log(invested) + Y2
    return max(10, min(200, bet))

print(f"\nFormula B coefficients:")
print(f"  Piece 1 (< $3000): X1={X1:.4f}, Y1={Y1:.4f}")
print(f"  Piece 2 (>= $3000): X2={X2:.4f}, Y2={Y2:.4f}")
print(f"  Check: B($500)=${formula_b(500):.2f}, B($1500)=${formula_b(1500):.2f}, B($3000)=${formula_b(3000):.2f}, B($10000)=${formula_b(10000):.2f}, B($30000)=${formula_b(30000):.2f}")
print(f"  Compare A: A($500)=${formula_a(500):.2f}, A($1500)=${formula_a(1500):.2f}, A($3000)=${formula_a(3000):.2f}, A($10000)=${formula_a(10000):.2f}, A($30000)=${formula_a(30000):.2f}")

# BACKTEST
backtest_pos = [r for r in closed if r['total_buy_usd'] >= 500]
print(f"\nBacktest positions (>=$500): {len(backtest_pos)}")

total_profit_a = 0
total_profit_b = 0
total_bet_a = 0
total_bet_b = 0
n_win = 0
n_lose = 0

bucket_results = {}
for bname, _, _ in all_buckets:
    bucket_results[bname] = {'a_profit': 0, 'b_profit': 0, 'a_bets': 0, 'b_bets': 0, 'count': 0, 'wins': 0, 'losses': 0}

for r in backtest_pos:
    invested = r['total_buy_usd']
    pnl_pct = r['pnl_pct']

    bet_a = formula_a(invested)
    bet_b = formula_b(invested)

    profit_a = bet_a * pnl_pct
    profit_b = bet_b * pnl_pct

    total_profit_a += profit_a
    total_profit_b += profit_b
    total_bet_a += bet_a
    total_bet_b += bet_b

    if pnl_pct > 0:
        n_win += 1
    else:
        n_lose += 1

    for bname, bmin, bmax in all_buckets:
        if bmin <= invested < bmax:
            br = bucket_results[bname]
            br['a_profit'] += profit_a
            br['b_profit'] += profit_b
            br['a_bets'] += bet_a
            br['b_bets'] += bet_b
            br['count'] += 1
            if pnl_pct > 0:
                br['wins'] += 1
            else:
                br['losses'] += 1
            break

print(f"\nWin/Loss: {n_win}/{n_lose}, WR: {n_win/(n_win+n_lose)*100:.1f}%")
print(f"\nFormula A: profit=${total_profit_a:.2f}, bets=${total_bet_a:.2f}, ROI={total_profit_a/total_bet_a*100:.2f}%")
print(f"Formula B: profit=${total_profit_b:.2f}, bets=${total_bet_b:.2f}, ROI={total_profit_b/total_bet_b*100:.2f}%")
print(f"Diff (B-A): ${total_profit_b - total_profit_a:.2f}")

print(f"\nPer-bucket backtest:")
hdr2 = f"{'Bucket':>15} | {'N':>4} | {'WR':>5} | {'ProfitA':>10} | {'ProfitB':>10} | {'BetsA':>8} | {'BetsB':>8} | {'ROI_A':>7} | {'ROI_B':>7} | {'B-A':>8}"
print(hdr2)
print("-"*100)
for bname, _, _ in all_buckets:
    br = bucket_results[bname]
    if br['count'] == 0:
        continue
    roi_a = br['a_profit']/br['a_bets']*100 if br['a_bets'] else 0
    roi_b = br['b_profit']/br['b_bets']*100 if br['b_bets'] else 0
    wr = br['wins']/(br['wins']+br['losses'])*100 if (br['wins']+br['losses']) else 0
    diff = br['b_profit'] - br['a_profit']
    print(f"{bname:>15} | {br['count']:>4} | {wr:>4.0f}% | ${br['a_profit']:>8.2f} | ${br['b_profit']:>8.2f} | ${br['a_bets']:>6.0f} | ${br['b_bets']:>6.0f} | {roi_a:>6.1f}% | {roi_b:>6.1f}% | ${diff:>7.2f}")

# SCALP detailed analysis
print("\n\nSCALP P&L IMPACT BY SIZE:")
hdr3 = f"{'Bucket':>15} | {'Scalps':>6} | {'NonScalp':>8} | {'ScalpTotPnL':>12} | {'NonScalpTotPnL':>15} | {'ScalpAvg%':>10} | {'NonScalpAvg%':>12}"
print(hdr3)
print("-"*95)
for bname, bmin, bmax in all_buckets:
    in_b = [r for r in closed if bmin <= r['total_buy_usd'] < bmax]
    sc = [r for r in in_b if r['trade_type'] == 'scalp']
    nsc = [r for r in in_b if r['trade_type'] != 'scalp']
    if not in_b:
        continue
    sc_pnl = sum(r['pnl_usd'] for r in sc)
    nsc_pnl = sum(r['pnl_usd'] for r in nsc)
    sc_avg = sum(r['pnl_pct'] for r in sc)/len(sc)*100 if sc else 0
    nsc_avg = sum(r['pnl_pct'] for r in nsc)/len(nsc)*100 if nsc else 0
    print(f"{bname:>15} | {len(sc):>6} | {len(nsc):>8} | ${sc_pnl:>10.2f} | ${nsc_pnl:>13.2f} | {sc_avg:>8.1f}% | {nsc_avg:>10.1f}%")

# Top losing scalps
print("\n\nTOP 10 LOSING SCALPS (by $ loss):")
scalps_all = [r for r in closed if r['trade_type'] == 'scalp']
scalps_all.sort(key=lambda x: x['pnl_usd'])
for r in scalps_all[:10]:
    print(f"  ${r['total_buy_usd']:>8.0f} inv, PnL=${r['pnl_usd']:>8.2f} ({r['pnl_pct']*100:>5.1f}%), hold={r['hold_duration_hours']:.1f}h, {r['title'][:50]}")

# TOP WINNING non-scalps
print("\n\nTOP 10 WINNING NON-SCALPS (by $ profit):")
non_scalps_all = [r for r in closed if r['trade_type'] != 'scalp']
non_scalps_all.sort(key=lambda x: x['pnl_usd'], reverse=True)
for r in non_scalps_all[:10]:
    print(f"  ${r['total_buy_usd']:>8.0f} inv, PnL=${r['pnl_usd']:>8.2f} ({r['pnl_pct']*100:>5.1f}%), hold={r['hold_duration_hours']:.1f}h, type={r['trade_type']}, {r['title'][:50]}")

# Save report data
report = {
    'X1': X1, 'Y1': Y1, 'X2': X2, 'Y2': Y2,
    'total_profit_a': total_profit_a, 'total_profit_b': total_profit_b,
    'roi_a': total_profit_a/total_bet_a*100, 'roi_b': total_profit_b/total_bet_b*100,
}
with open('C:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot_v2/_analytics/data/scalp_backtest_results.json', 'w') as f:
    json.dump(report, f, indent=2, default=str)
print("\nResults saved.")
