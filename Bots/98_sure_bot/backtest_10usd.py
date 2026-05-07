"""Quick bankroll calc for $10 fixed bet + nr off + ed 7d."""
import sys
import os
import random

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

random.seed(42)

BET = 10.0
LOSS_RATE = 7 / 6717
AVG_ENTRY = 0.9867
WIN_PROFIT = (1.0 - AVG_ENTRY) / AVG_ENTRY * BET
MEDIAN_RESOLVE_H = 9.2
POOL_SIZE = 1000
REFRESH_RATE = 0.40
DAYS = 30
RUNS = 10000

print("=" * 80)
print(f"MONTE CARLO: $10 FIXED BET + NR OFF + ED 7D ({RUNS} runs x {DAYS} days)")
print("=" * 80)
print(f"  Win profit: ${WIN_PROFIT:.3f} | Loss cost: ${BET:.0f} | Loss rate: {LOSS_RATE*100:.3f}%")

for BANKROLL in [300, 400, 500, 600, 750, 1000]:
    all_peaks = []
    all_profits = []
    all_drawdowns = []
    all_bets = []
    all_losses = []

    for run in range(RUNS):
        open_positions = []
        invested = 0.0
        peak_invested = 0.0
        profit = 0.0
        peak_profit = 0.0
        max_dd = 0.0
        n_bets = 0
        n_losses = 0

        for day in range(DAYS):
            new_open = []
            for rem_h, bsz in open_positions:
                rem_h -= 24
                if rem_h <= 0:
                    invested -= bsz
                    if random.random() < LOSS_RATE:
                        profit -= bsz
                        n_losses += 1
                    else:
                        profit += WIN_PROFIT
                else:
                    new_open.append((rem_h, bsz))
            open_positions = new_open

            available_capital = BANKROLL + profit - invested
            slots = max(0, int(available_capital / BET))
            daily_flow = int(POOL_SIZE * REFRESH_RATE)
            new_bets = min(slots, POOL_SIZE) if day == 0 else min(slots, daily_flow)

            for _ in range(new_bets):
                rh = max(1, min(random.expovariate(1.0 / MEDIAN_RESOLVE_H), 168))
                open_positions.append((rh, BET))
                invested += BET
                n_bets += 1
                if invested > peak_invested:
                    peak_invested = invested

            if profit > peak_profit:
                peak_profit = profit
            dd = peak_profit - profit
            if dd > max_dd:
                max_dd = dd

        all_peaks.append(peak_invested)
        all_profits.append(profit)
        all_drawdowns.append(max_dd)
        all_bets.append(n_bets)
        all_losses.append(n_losses)

    profits = sorted(all_profits)
    peaks = sorted(all_peaks)
    drawdowns = sorted(all_drawdowns)
    bets_sorted = sorted(all_bets)

    median_profit = profits[RUNS // 2]
    p5_profit = profits[int(RUNS * 0.05)]
    median_bets = bets_sorted[RUNS // 2]
    peak_95 = peaks[int(RUNS * 0.95)]
    dd_99 = drawdowns[int(RUNS * 0.99)]
    loss_months = sum(1 for p in profits if p < 0)
    roi = median_profit / BANKROLL * 100

    print(f"\n  Bankroll ${BANKROLL}:")
    print(f"    Bets/month: {median_bets} | Peak invested: ${peak_95:.0f}")
    print(f"    Profit: median ${median_profit:+.2f} | 5th% ${p5_profit:+.2f}")
    print(f"    Max drawdown (99th%): ${dd_99:.2f}")
    print(f"    ROI: {roi:.1f}%/month")
    print(f"    Losing months: {loss_months}/{RUNS} ({loss_months/RUNS*100:.2f}%)")
