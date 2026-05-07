"""Bankroll calculation: nr off + ed 7d + dynamic bet sizing by liquidity."""
import json
import sys
import os
import random
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

random.seed(42)

# === Load data ===
with open('positions.json', 'r', encoding='utf-8') as f:
    bot_data = json.load(f)

SCANNER_DATA = os.path.join(os.path.dirname(__file__), "..", "97_scanner", "scanner_data.json")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc_data = json.load(f)

# === Constants from our data ===
AVG_ENTRY = 0.9867
LOSS_RATE = 7 / 6717  # 0.00104
MEDIAN_RESOLVE_H = 9.2

# === Current scan: get real liquidity distribution ===
import scanner
import filters
import tracker

candidates = scanner.scan()
tdata = tracker.load()

# Get candidates that pass with nr off + ed 7d
orig_nr = filters.MAX_NEG_RISK_FROZEN
orig_ed = filters.MAX_END_DATE_DAYS
filters.MAX_NEG_RISK_FROZEN = 999999
filters.MAX_END_DATE_DAYS = 7

passed = []
for c in candidates:
    p, r = filters.run_all_filters(c, set(), tdata)
    if p:
        passed.append(c)

filters.MAX_NEG_RISK_FROZEN = orig_nr
filters.MAX_END_DATE_DAYS = orig_ed

print("=" * 75)
print("BANKROLL: nr off + ed 7d + dynamic bet")
print("=" * 75)
print(f"Candidates passing filters: {len(passed)}")

# === Dynamic bet sizing rules ===
def get_bet_size(liquidity):
    if liquidity >= 10000:
        return 15
    elif liquidity >= 2000:
        return 10
    else:
        return 5

# Liquidity distribution of passed candidates
print(f"\nLiquidity -> bet size distribution:")
buckets = [
    ("$500-$2K -> $5", 500, 2000, 5),
    ("$2K-$10K -> $10", 2000, 10000, 10),
    ("$10K+ -> $15", 10000, 99999999, 15),
]

total_bet_value = 0
for label, lo, hi, bet in buckets:
    subset = [c for c in passed if lo <= c.get('liquidity', 0) < hi]
    value = len(subset) * bet
    total_bet_value += value
    print(f"  {label:25s}: {len(subset):3d} markets | ${value:>5d} total")

avg_bet = total_bet_value / len(passed) if passed else 10
print(f"\nAvg bet size: ${avg_bet:.1f}")

# === Simulation: what's the max simultaneous capital needed? ===
print(f"\n{'=' * 75}")
print("SIMULATION: peak capital usage over 30 days")
print("=" * 75)

DAYS = 30
RUNS = 500
REFRESH_RATE = 0.40

# Build candidate pool with real liquidity
pool_with_liq = [(c.get('liquidity', 1000), get_bet_size(c.get('liquidity', 1000))) for c in passed]
pool_size = len(passed)
daily_flow = pool_size * REFRESH_RATE

# Track peak open capital across many runs
all_peaks = []
all_profits = []
all_bets_count = []
all_losses_count = []

for run in range(RUNS):
    # Track open positions: list of (resolve_time_remaining, bet_size)
    open_positions = []
    total_invested = 0
    peak_invested = 0
    total_profit = 0
    total_bets = 0
    total_losses = 0

    for day in range(DAYS):
        # Resolve positions that are done
        new_open = []
        for remaining_h, bet_sz in open_positions:
            remaining_h -= 24  # advance one day
            if remaining_h <= 0:
                # Position resolved
                if random.random() < LOSS_RATE:
                    total_profit -= bet_sz
                    total_invested -= bet_sz
                    total_losses += 1
                else:
                    win = (1.0 - AVG_ENTRY) / AVG_ENTRY * bet_sz
                    total_profit += win
                    total_invested -= bet_sz
            else:
                new_open.append((remaining_h, bet_sz))
        open_positions = new_open

        # Place new bets
        if day == 0:
            new_bets = pool_size  # initial burst
        else:
            new_bets = int(daily_flow)

        for i in range(new_bets):
            # Pick random candidate from pool
            liq, bet_sz = random.choice(pool_with_liq)
            # Random resolve time (exponential around median)
            resolve_h = random.expovariate(1.0 / MEDIAN_RESOLVE_H)
            resolve_h = max(1, min(resolve_h, 168))  # 1h to 7 days

            open_positions.append((resolve_h, bet_sz))
            total_invested += bet_sz
            total_bets += 1

            if total_invested > peak_invested:
                peak_invested = total_invested

    all_peaks.append(peak_invested)
    all_profits.append(total_profit)
    all_bets_count.append(total_bets)
    all_losses_count.append(total_losses)

peaks = sorted(all_peaks)
profits = sorted(all_profits)

print(f"Results across {RUNS} runs:")
print(f"\nPeak simultaneous capital:")
print(f"  Median:    ${peaks[len(peaks)//2]:>8.0f}")
print(f"  75th%:     ${peaks[int(len(peaks)*0.75)]:>8.0f}")
print(f"  90th%:     ${peaks[int(len(peaks)*0.90)]:>8.0f}")
print(f"  95th%:     ${peaks[int(len(peaks)*0.95)]:>8.0f}")
print(f"  Max:       ${peaks[-1]:>8.0f}")

print(f"\nMonthly profit:")
print(f"  5th% (worst): ${profits[int(len(profits)*0.05)]:>+8.2f}")
print(f"  Median:       ${profits[len(profits)//2]:>+8.2f}")
print(f"  95th% (best): ${profits[int(len(profits)*0.95)]:>+8.2f}")

avg_bets = sum(all_bets_count) / RUNS
avg_losses = sum(all_losses_count) / RUNS
print(f"\nAvg bets/month: {avg_bets:.0f}")
print(f"Avg losses/month: {avg_losses:.1f}")

# === Bankroll recommendation ===
print(f"\n{'=' * 75}")
print("BANKROLL RECOMMENDATION")
print("=" * 75)

p95_peak = peaks[int(len(peaks) * 0.95)]
p99_peak = peaks[int(len(peaks) * 0.99)] if len(peaks) > 100 else peaks[-1]
median_profit = profits[len(profits) // 2]
worst_profit = profits[int(len(profits) * 0.05)]

# Bankroll = peak capital + buffer for losses
# Buffer = max possible consecutive losses * max bet size
max_bet = 15
# At 0.1% loss rate, chance of 2 consecutive losses = 0.001^2 = 0.000001
# Practically impossible, but add 2-loss buffer anyway
loss_buffer = 2 * max_bet

print(f"\nPeak capital (95th percentile): ${p95_peak:.0f}")
print(f"Loss buffer (2 x ${max_bet}):         ${loss_buffer:.0f}")
print(f"")

for safety, label in [(1.0, "Minimum (risky)"), (1.3, "Comfortable"), (1.5, "Conservative"), (2.0, "Very safe")]:
    bankroll = p95_peak * safety + loss_buffer
    roi = median_profit / bankroll * 100
    print(f"  {label:25s}: ${bankroll:>6.0f} | ROI {roi:>5.1f}%/month | profit ${median_profit:>+.2f}/month")

# === Compare with fixed bet sizes ===
print(f"\n{'=' * 75}")
print("COMPARISON: dynamic vs fixed bet size")
print("=" * 75)

# Run same simulation with fixed $5, $10
for bet_label, get_bet_fn in [
    ("Fixed $5", lambda liq: 5),
    ("Fixed $10", lambda liq: 10),
    ("Dynamic $5/$10/$15", get_bet_size),
]:
    pool_bets = [(c.get('liquidity', 1000), get_bet_fn(c.get('liquidity', 1000))) for c in passed]
    run_peaks = []
    run_profits = []

    for run in range(200):
        open_pos = []
        invested = 0
        peak = 0
        profit = 0

        for day in range(DAYS):
            new_open = []
            for rem, bsz in open_pos:
                rem -= 24
                if rem <= 0:
                    invested -= bsz
                    if random.random() < LOSS_RATE:
                        profit -= bsz
                    else:
                        profit += (1.0 - AVG_ENTRY) / AVG_ENTRY * bsz
                else:
                    new_open.append((rem, bsz))
            open_pos = new_open

            n_bets = pool_size if day == 0 else int(daily_flow)
            for _ in range(n_bets):
                liq, bsz = random.choice(pool_bets)
                rh = max(1, min(random.expovariate(1.0 / MEDIAN_RESOLVE_H), 168))
                open_pos.append((rh, bsz))
                invested += bsz
                if invested > peak:
                    peak = invested

        run_peaks.append(peak)
        run_profits.append(profit)

    p95 = sorted(run_peaks)[int(len(run_peaks) * 0.95)]
    med_prof = sorted(run_profits)[len(run_profits) // 2]
    bankroll_comfy = p95 * 1.3 + 30
    roi = med_prof / bankroll_comfy * 100

    print(f"  {bet_label:25s}: peak ${p95:>6.0f} | bankroll ${bankroll_comfy:>6.0f} | profit ${med_prof:>+7.2f}/mo | ROI {roi:>5.1f}%")
