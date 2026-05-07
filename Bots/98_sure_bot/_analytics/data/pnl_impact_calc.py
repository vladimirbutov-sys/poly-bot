"""
P&L Impact Calculator: Slippage change 0.002 -> 0.003 for bucket 99-99.5c
Based on REAL data from positions.json (371 positions, 7.84 days)
and bot_log.txt backtest (1,807 bets)
"""
import json
import os
from datetime import datetime

BOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
POSITIONS_FILE = os.path.join(BOT_DIR, "positions.json")

with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

positions = data["positions"]

# -- Parse dates and calculate bot running period --
timestamps = []
for p in positions.values():
    ts = p.get("timestamp", "")
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            timestamps.append(dt)
        except:
            pass

first_date = min(timestamps)
last_date = max(timestamps)
days_running = (last_date - first_date).total_seconds() / 86400
print(f"Bot running: {days_running:.1f} days ({first_date.date()} -> {last_date.date()})")
print()

# -- Current metrics by bucket --
buckets = [
    (0.960, 0.975, "96-97.5c", 0.005),
    (0.975, 0.985, "97.5-98.5c", 0.004),
    (0.985, 0.990, "98.5-99c", 0.003),
    (0.990, 0.996, "99-99.5c", 0.002),  # current
]

print("=" * 90)
print("  CURRENT STATE — Real P&L by bucket")
print("=" * 90)

total_pnl = 0
total_cost = 0
total_count = 0

for lo, hi, label, slip in buckets:
    in_bucket = [p for p in positions.values()
                 if lo <= p.get("entry_price", 0) < hi
                 and p.get("status") in ("won", "lost")]
    count = len(in_bucket)
    cost = sum(p["cost_usd"] for p in in_bucket)
    pnl = sum(p.get("pnl", 0) for p in in_bucket)
    won = sum(1 for p in in_bucket if p["status"] == "won")
    lost = sum(1 for p in in_bucket if p["status"] == "lost")
    avg_entry = sum(p["entry_price"] for p in in_bucket) / count if count else 0

    monthly_pnl = pnl / days_running * 30 if days_running > 0 else 0

    print(f"\n{label} (slippage={slip}):")
    print(f"  Positions: {count} (W:{won} L:{lost})")
    print(f"  Invested: ${cost:.2f}")
    print(f"  P&L: ${pnl:.2f} (${monthly_pnl:.2f}/month)")
    print(f"  Avg entry: {avg_entry:.4f}")
    if cost > 0:
        print(f"  ROI: {pnl/cost*100:.3f}%")

    total_pnl += pnl
    total_cost += cost
    total_count += count

monthly_total = total_pnl / days_running * 30
print(f"\n{'-'*60}")
print(f"TOTAL resolved: {total_count} positions")
print(f"TOTAL P&L: ${total_pnl:.2f}")
print(f"TOTAL monthly P&L: ${monthly_total:.2f}/month")
print(f"TOTAL invested: ${total_cost:.2f}")
print(f"ROI: {total_pnl/total_cost*100:.3f}%")

# -- IMPACT CALCULATION --
print()
print("=" * 90)
print("  IMPACT: Changing bucket 99-99.5c slippage 0.002 -> 0.003")
print("=" * 90)

# Bucket 99-99.5c stats
bucket_99 = [p for p in positions.values()
             if 0.990 <= p.get("entry_price", 0) < 0.996
             and p.get("status") in ("won", "lost")]
n99 = len(bucket_99)
cost99 = sum(p["cost_usd"] for p in bucket_99)
pnl99 = sum(p.get("pnl", 0) for p in bucket_99)
avg_entry99 = sum(p["entry_price"] for p in bucket_99) / n99 if n99 else 0
won99 = sum(1 for p in bucket_99 if p["status"] == "won")
lost99 = sum(1 for p in bucket_99 if p["status"] == "lost")
win_rate99 = won99 / n99 * 100 if n99 else 0

# From backtest: 1,011 attempts, 101 filled = 10% fill rate
# With 0.003: fill rate likely ~15% (conservative) to ~20% (optimistic)
BACKTEST_ATTEMPTS_99 = 1011
BACKTEST_FILLED_99 = 101
BACKTEST_UNFILLED_99 = 910
CURRENT_FILL_RATE = BACKTEST_FILLED_99 / BACKTEST_ATTEMPTS_99 * 100

# Attempts per day (from backtest over same period)
attempts_per_day = BACKTEST_ATTEMPTS_99 / days_running
current_fills_per_day = BACKTEST_FILLED_99 / days_running

print(f"\nBucket 99-99.5c current stats:")
print(f"  Resolved positions: {n99} ({won99}W / {lost99}L, {win_rate99:.1f}% win rate)")
print(f"  Avg entry price: {avg_entry99:.4f}")
print(f"  Current P&L: ${pnl99:.2f}")
print(f"  Monthly P&L: ${pnl99/days_running*30:.2f}/month")
print(f"  Backtest: {BACKTEST_ATTEMPTS_99} attempts, {BACKTEST_FILLED_99} filled ({CURRENT_FILL_RATE:.1f}%)")
print(f"  Attempts/day: {attempts_per_day:.0f}, Fills/day: {current_fills_per_day:.1f}")

# -- Model: current vs proposed --
# Average bet size in this bucket
avg_bet = cost99 / n99 if n99 else 10.0

# Current: cost_per_share = entry_price + 0.002
current_limit = avg_entry99 + 0.002
current_profit_per_share = 1.0 - current_limit  # payout - cost
current_shares_per_bet = avg_bet / current_limit
current_profit_per_bet = current_shares_per_bet * current_profit_per_share

# Proposed: cost_per_share = entry_price + 0.003
proposed_limit = min(avg_entry99 + 0.003, 0.995)
proposed_profit_per_share = 1.0 - proposed_limit
proposed_shares_per_bet = avg_bet / proposed_limit
proposed_profit_per_bet = proposed_shares_per_bet * proposed_profit_per_share

print(f"\n-- Per-trade economics (avg bet ${avg_bet:.2f}) --")
print(f"  Current (slip=0.002): limit={current_limit:.4f}, profit/bet=${current_profit_per_bet:.4f}")
print(f"  Proposed (slip=0.003): limit={proposed_limit:.4f}, profit/bet=${proposed_profit_per_bet:.4f}")
print(f"  Loss per trade: ${current_profit_per_bet - proposed_profit_per_bet:.4f}")

# -- Scenarios --
scenarios = [
    ("Conservative (15% fill rate)", 0.15),
    ("Moderate (18% fill rate)", 0.18),
    ("Optimistic (22% fill rate)", 0.22),
]

print(f"\n{'-'*70}")
print(f"{'SCENARIO':35s} | {'Monthly P&L':>12s} | {'vs Current':>10s} | {'ROI':>6s}")
print(f"{'-'*70}")

# Current monthly P&L from this bucket
current_fills_per_month = current_fills_per_day * 30
current_monthly_pnl = current_fills_per_month * current_profit_per_bet * (win_rate99/100)
# Account for losses
loss_rate = (100 - win_rate99) / 100
avg_loss_per_bet = avg_bet  # on loss, we lose the entire bet
current_monthly_loss = current_fills_per_month * loss_rate * avg_loss_per_bet

net_current = current_monthly_pnl - current_monthly_loss

print(f"{'Current (10% fill rate)':35s} | ${net_current:11.2f} | {'baseline':>10s} | {net_current/cost99*100 if cost99 else 0:5.2f}%")

for name, new_fill_rate in scenarios:
    new_fills_per_day = attempts_per_day * new_fill_rate
    new_fills_per_month = new_fills_per_day * 30

    # Profit from wins
    monthly_pnl = new_fills_per_month * proposed_profit_per_bet * (win_rate99/100)
    # Losses
    monthly_loss = new_fills_per_month * loss_rate * avg_bet
    net_pnl = monthly_pnl - monthly_loss

    delta = net_pnl - net_current
    # Monthly invested
    monthly_invested = new_fills_per_month * avg_bet
    roi = net_pnl / monthly_invested * 100 if monthly_invested > 0 else 0

    print(f"{name:35s} | ${net_pnl:11.2f} | ${delta:+9.2f} | {roi:5.2f}%")

# -- FULL BOT P&L IMPACT --
print(f"\n{'='*70}")
print(f"  FULL BOT P&L (all buckets combined)")
print(f"{'='*70}")

other_buckets_pnl = total_pnl - pnl99  # P&L from other buckets stays the same
other_monthly = other_buckets_pnl / days_running * 30

for name, new_fill_rate in scenarios:
    new_fills_per_day = attempts_per_day * new_fill_rate
    new_fills_per_month = new_fills_per_day * 30

    monthly_pnl = new_fills_per_month * proposed_profit_per_bet * (win_rate99/100)
    monthly_loss = new_fills_per_month * loss_rate * avg_bet
    bucket99_net = monthly_pnl - monthly_loss

    full_monthly = other_monthly + bucket99_net
    delta_vs_current = full_monthly - monthly_total

    print(f"\n{name}:")
    print(f"  Other buckets: ${other_monthly:.2f}/month (no change)")
    print(f"  Bucket 99-99.5c: ${bucket99_net:.2f}/month")
    print(f"  TOTAL: ${full_monthly:.2f}/month (current: ${monthly_total:.2f}/month, delta: ${delta_vs_current:+.2f})")

# -- BANKROLL IMPACT --
print(f"\n{'='*70}")
print(f"  BANKROLL REQUIREMENT")
print(f"{'='*70}")

# How much capital is frozen at any given time?
# Open positions = capital tied up until resolution
open_positions = [p for p in positions.values() if p.get("status") in ("open", "selling")]
current_frozen = sum(p["cost_usd"] for p in open_positions)

# Average time to resolution (from filled resolved trades)
resolved = [p for p in positions.values() if p.get("status") in ("won", "lost")
            and p.get("timestamp") and p.get("resolved_at")]
resolution_times = []
for p in resolved:
    try:
        t1 = datetime.fromisoformat(p["timestamp"])
        t2 = datetime.fromisoformat(p["resolved_at"])
        resolution_times.append((t2 - t1).total_seconds() / 86400)
    except:
        pass

avg_resolution_days = sum(resolution_times) / len(resolution_times) if resolution_times else 2.0

print(f"\nCurrent frozen capital: ${current_frozen:.2f} ({len(open_positions)} positions)")
print(f"Avg resolution time: {avg_resolution_days:.1f} days")

for name, new_fill_rate in scenarios:
    new_fills_per_day = attempts_per_day * new_fill_rate
    additional_fills_per_day = new_fills_per_day - current_fills_per_day
    additional_frozen = additional_fills_per_day * avg_resolution_days * avg_bet
    new_total_frozen = current_frozen + additional_frozen

    print(f"\n{name}:")
    print(f"  Additional fills/day: {additional_fills_per_day:.1f}")
    print(f"  Additional capital frozen: ${additional_frozen:.0f}")
    print(f"  Total capital needed: ${new_total_frozen:.0f} (current ${current_frozen:.0f} + ${additional_frozen:.0f})")

# -- SUMMARY TABLE --
print(f"\n{'='*70}")
print(f"  SUMMARY: DECISION TABLE")
print(f"{'='*70}")
print()
print(f"{'Metric':40s} | {'Current':>12s} | {'Proposed':>12s}")
print(f"{'-'*70}")
print(f"{'Slippage (99-99.5c bucket)':40s} | {'0.002':>12s} | {'0.003':>12s}")
print(f"{'Fill rate':40s} | {'10%':>12s} | {'15-22%':>12s}")
print(f"{'Profit per winning trade':40s} | ${current_profit_per_bet:>11.4f} | ${proposed_profit_per_bet:>11.4f}")
print(f"{'Loss per trade':40s} | ${current_profit_per_bet - proposed_profit_per_bet:>11.4f} |")

# Use moderate scenario for summary
mod_fills_per_month = attempts_per_day * 0.18 * 30
mod_monthly_pnl = mod_fills_per_month * proposed_profit_per_bet * (win_rate99/100)
mod_monthly_loss = mod_fills_per_month * loss_rate * avg_bet
mod_bucket_net = mod_monthly_pnl - mod_monthly_loss
mod_full_monthly = other_monthly + mod_bucket_net
mod_additional_frozen = (attempts_per_day * 0.18 - current_fills_per_day) * avg_resolution_days * avg_bet

print(f"{'Monthly P&L (moderate scenario)':40s} | ${monthly_total:>11.2f} | ${mod_full_monthly:>11.2f}")
print(f"{'Delta P&L/month':40s} | {'—':>12s} | ${mod_full_monthly - monthly_total:>+11.2f}")
print(f"{'Additional frozen capital':40s} | {'—':>12s} | ${mod_additional_frozen:>11.0f}")
print(f"{'Win rate':40s} | {win_rate99:>11.1f}% | {win_rate99:>11.1f}%")
