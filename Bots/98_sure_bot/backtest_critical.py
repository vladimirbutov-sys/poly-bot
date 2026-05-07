"""Critical analysis of neg_risk recommendation.

Tests:
1. Survivorship bias -- does scanner only see winners?
2. Real resolve times from actual bot data vs scanner estimates
3. Day-by-day capital simulation with different bankrolls and neg_risk caps
4. Stress test: what if 1 neg_risk loss happens?
5. Fill rate impact -- scanner assumes 100% fill, real bot is ~60%
6. Gas costs for neg_risk redemption
"""
import json
import re
from datetime import datetime, timezone, timedelta
from collections import defaultdict

print("=" * 60)
print("  CRITICAL ANALYSIS OF NEG_RISK RECOMMENDATION")
print("=" * 60)

# ============================================================
# 1. SURVIVORSHIP BIAS CHECK
# ============================================================
print("\n\n### 1. SURVIVORSHIP BIAS ###")
print("Scanner records markets at price >= 97c.")
print("Question: does it only catch markets AFTER they've already won?")

with open("C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json") as f:
    scanner_raw = json.load(f)
    scanner = scanner_raw["markets"]

# Check: how many resolved markets lost (high_outcome_won=False)?
total_resolved = 0
total_won = 0
total_lost = 0
neg_resolved = 0
neg_won = 0
neg_lost = 0

for m in scanner.values():
    won = m.get("high_outcome_won")
    if won is None:
        continue
    total_resolved += 1
    is_neg = m.get("neg_risk", False)
    if is_neg:
        neg_resolved += 1
    if won:
        total_won += 1
        if is_neg:
            neg_won += 1
    else:
        total_lost += 1
        if is_neg:
            neg_lost += 1

print(f"All resolved: {total_resolved} (W:{total_won} L:{total_lost})")
print(f"  Loss rate: {total_lost/total_resolved*100:.2f}% ({total_lost} losses)")
print(f"Neg_risk resolved: {neg_resolved} (W:{neg_won} L:{neg_lost})")
print(f"  Neg_risk loss rate: {neg_lost/neg_resolved*100:.2f}%" if neg_resolved > 0 else "  N/A")

# Show ALL neg_risk losses
print(f"\nAll neg_risk losses ({neg_lost}):")
for m in scanner.values():
    won = m.get("high_outcome_won")
    if won is False and m.get("neg_risk", False):
        print(f"  [{m.get('category','')}] price={m.get('max_price_seen',0):.3f} "
              f"vol=${m.get('volume',0):.0f}: {m.get('question','')[:70]}")

# ============================================================
# 2. SAMPLE SIZE AND CONFIDENCE
# ============================================================
print("\n\n### 2. SAMPLE SIZE ANALYSIS ###")
print("Scanner ran 3.7 days. How confident can we be?")

# With 641 neg_risk markets passing filters, 0 losses:
# Using Wilson score interval for 0/641
import math

def wilson_upper(n, k, z=1.96):
    """Upper bound of Wilson confidence interval. k successes in n trials."""
    if n == 0:
        return 1.0
    p_hat = k / n
    denom = 1 + z**2 / n
    centre = p_hat + z**2 / (2 * n)
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n)
    return min(1.0, (centre + spread) / denom)

def wilson_lower(n, k, z=1.96):
    if n == 0:
        return 0.0
    p_hat = k / n
    denom = 1 + z**2 / n
    centre = p_hat + z**2 / (2 * n)
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z**2 / (4 * n)) / n)
    return max(0.0, (centre - spread) / denom)

# Current filters (124 markets, 0 losses)
wr_lower_124 = wilson_lower(124, 124) * 100
worst_loss_rate_124 = (1 - wilson_lower(124, 124)) * 100

# Neg_risk addition (641 markets, 0 losses)
wr_lower_641 = wilson_lower(641, 641) * 100
worst_loss_rate_641 = (1 - wilson_lower(641, 641)) * 100

# Combined (765 markets, 0 losses)
wr_lower_765 = wilson_lower(765, 765) * 100
worst_loss_rate_765 = (1 - wilson_lower(765, 765)) * 100

# Also: what if scanner missed 1 loss due to timing?
print(f"Win rate confidence (95% Wilson lower bound):")
print(f"  Current (124 bets, 0L): >= {wr_lower_124:.2f}% (worst-case loss rate: 1 in {1/(1-wr_lower_124/100):.0f})")
print(f"  Neg_risk only (641 bets, 0L): >= {wr_lower_641:.2f}% (worst-case loss rate: 1 in {1/(1-wr_lower_641/100):.0f})")
print(f"  Combined (765 bets, 0L): >= {wr_lower_765:.2f}% (worst-case loss rate: 1 in {1/(1-wr_lower_765/100):.0f})")

# What if true loss rate is 1 in 200 (0.5%)?
print(f"\nStress test: if true loss rate = 0.5% (1 in 200):")
print(f"  Probability of seeing 0 losses in 641 trials: {(1-0.005)**641:.4f} = {(1-0.005)**641*100:.1f}%")
print(f"  Probability of seeing 0 losses in 124 trials: {(1-0.005)**124:.4f} = {(1-0.005)**124*100:.1f}%")
print(f"  => With 0.5% loss rate, seeing 0/641 has only 4% chance - unlikely but possible")

print(f"\nStress test: if true loss rate = 0.2% (1 in 500):")
print(f"  Probability of seeing 0 losses in 641 trials: {(1-0.002)**641:.4f} = {(1-0.002)**641*100:.1f}%")
print(f"  Probability of seeing 0 losses in 765 trials: {(1-0.002)**765:.4f} = {(1-0.002)**765*100:.1f}%")

# ============================================================
# 3. REAL BOT DATA -- RESOLVE TIMES AND COSTS
# ============================================================
print("\n\n### 3. REAL BOT DATA ###")

with open("positions.json") as f:
    positions = json.load(f)

neg_positions = []
reg_positions = []
for pos in positions["positions"].values():
    if pos.get("status") not in ("won", "lost", "open"):
        continue
    if pos.get("neg_risk"):
        neg_positions.append(pos)
    else:
        reg_positions.append(pos)

print(f"Neg_risk positions: {len(neg_positions)} (won:{sum(1 for p in neg_positions if p['status']=='won')}, "
      f"open:{sum(1 for p in neg_positions if p['status']=='open')})")
print(f"Regular positions: {len(reg_positions)} (won:{sum(1 for p in reg_positions if p['status']=='won')}, "
      f"lost:{sum(1 for p in reg_positions if p['status']=='lost')}, "
      f"open:{sum(1 for p in reg_positions if p['status']=='open')})")

# Actual resolve times
neg_resolve_h = []
reg_resolve_h = []
for pos in positions["positions"].values():
    ts = pos.get("timestamp", "")
    resolved_at = pos.get("resolved_at", "")
    if not (ts and resolved_at and pos.get("status") == "won"):
        continue
    try:
        t0 = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(resolved_at.replace("Z", "+00:00"))
        hours = (t1 - t0).total_seconds() / 3600
        if pos.get("neg_risk"):
            neg_resolve_h.append(hours)
        else:
            reg_resolve_h.append(hours)
    except Exception:
        pass

if neg_resolve_h:
    neg_resolve_h.sort()
    print(f"\nNeg_risk resolve times ({len(neg_resolve_h)} samples):")
    for pct_name, idx in [("p10", int(len(neg_resolve_h)*0.1)), ("p25", int(len(neg_resolve_h)*0.25)),
                           ("p50", len(neg_resolve_h)//2), ("p75", int(len(neg_resolve_h)*0.75)),
                           ("p90", int(len(neg_resolve_h)*0.9))]:
        print(f"  {pct_name}: {neg_resolve_h[min(idx, len(neg_resolve_h)-1)]:.1f}h")

if reg_resolve_h:
    reg_resolve_h.sort()
    print(f"\nRegular resolve times ({len(reg_resolve_h)} samples):")
    for pct_name, idx in [("p10", int(len(reg_resolve_h)*0.1)), ("p25", int(len(reg_resolve_h)*0.25)),
                           ("p50", len(reg_resolve_h)//2), ("p75", int(len(reg_resolve_h)*0.75)),
                           ("p90", int(len(reg_resolve_h)*0.9))]:
        print(f"  {pct_name}: {reg_resolve_h[min(idx, len(reg_resolve_h)-1)]:.1f}h")

# ============================================================
# 4. GAS COSTS
# ============================================================
print("\n\n### 4. GAS COSTS ###")
print("Each neg_risk redeem = 1 on-chain transaction on Polygon")
print("Regular redeem = also 1 transaction")
print("Typical gas on Polygon: ~30 gwei, ~300K gas = ~0.009 MATIC = ~$0.003")
print("Even 100 redeems/month = $0.30 -- negligible")

# ============================================================
# 5. FILL RATE IMPACT
# ============================================================
print("\n\n### 5. FILL RATE ###")
print("Scanner backtest assumes 100% fill. Real bot fill rate = 59.6%")
print("This affects ALL bets equally (neg_risk and regular)")
print("So the RATIO of bets stays the same, but absolute numbers drop ~40%")

# Real fill adjustment
fill_rate = 0.596
scanner_days = 3.7

# From previous backtest: 124 regular, 641 neg_risk pass filters
reg_bets_scanner = 124
neg_bets_scanner = 641

# Adjusted for fill rate
reg_bets_real = reg_bets_scanner * fill_rate
neg_bets_real = neg_bets_scanner * fill_rate

print(f"\nAdjusted bets in {scanner_days}d:")
print(f"  Regular: {reg_bets_scanner} -> {reg_bets_real:.0f} (after fill rate)")
print(f"  Neg_risk: {neg_bets_scanner} -> {neg_bets_real:.0f}")

# ============================================================
# 6. DAY-BY-DAY CAPITAL SIMULATION
# ============================================================
print("\n\n### 6. CAPITAL SIMULATION ###")
print("Simulate 30 days with different bankrolls and neg_risk caps")

# Parameters from real data
reg_median_resolve_h = reg_resolve_h[len(reg_resolve_h)//2] if reg_resolve_h else 10
neg_median_resolve_h = neg_resolve_h[len(neg_resolve_h)//2] if neg_resolve_h else 53
reg_avg_price = 0.9854
neg_avg_price = 0.9828
bet_size = 10
loss_rate = 0.005  # conservative: 1 in 200

# Bets available per hour (from scanner data)
reg_per_hour = reg_bets_real / (scanner_days * 24)
neg_per_hour = neg_bets_real / (scanner_days * 24)

print(f"Parameters:")
print(f"  Reg resolve: {reg_median_resolve_h:.0f}h, Neg resolve: {neg_median_resolve_h:.0f}h")
print(f"  Reg opportunities/hour: {reg_per_hour:.2f}, Neg: {neg_per_hour:.2f}")
print(f"  Fill rate: {fill_rate*100:.0f}%, Loss rate: {loss_rate*100:.1f}%")
print(f"  Bet size: ${bet_size}")

import random
random.seed(42)

def simulate_month(bankroll, neg_risk_cap_pct, days=30, runs=100):
    """Simulate trading for N days, M times. Return avg monthly PnL."""
    results = []

    for run in range(runs):
        balance = bankroll
        total_pnl = 0
        neg_frozen = 0  # $ in neg_risk positions
        reg_frozen = 0  # $ in regular positions

        # Track active bets as (resolve_time_remaining, amount, is_neg, won)
        active_bets = []

        for hour in range(days * 24):
            # 1. Resolve completed bets
            new_active = []
            for remaining, amount, is_neg, won in active_bets:
                if remaining <= 1:
                    # Bet resolves
                    if is_neg:
                        neg_frozen -= amount
                    else:
                        reg_frozen -= amount
                    if won:
                        price = neg_avg_price if is_neg else reg_avg_price
                        payout = amount / price  # shares * $1
                        profit = payout - amount
                        balance += payout
                        total_pnl += profit
                    else:
                        total_pnl -= amount  # lost everything
                else:
                    new_active.append((remaining - 1, amount, is_neg, won))
            active_bets = new_active

            # 2. Place regular bets
            reg_available = random.random() < reg_per_hour  # ~Bernoulli per hour
            if reg_available and balance >= bet_size:
                won = random.random() > loss_rate
                active_bets.append((reg_median_resolve_h, bet_size, False, won))
                balance -= bet_size
                reg_frozen += bet_size

            # 3. Place neg_risk bets (with cap)
            neg_cap = bankroll * neg_risk_cap_pct
            # Multiple neg_risk opportunities per hour possible
            neg_count = 0
            while random.random() < neg_per_hour and neg_count < 3:
                neg_count += 1
                if balance >= bet_size and neg_frozen < neg_cap:
                    won = random.random() > loss_rate
                    active_bets.append((neg_median_resolve_h, bet_size, True, won))
                    balance -= bet_size
                    neg_frozen += bet_size

        results.append(total_pnl)

    avg_pnl = sum(results) / len(results)
    min_pnl = min(results)
    max_pnl = max(results)
    p10 = sorted(results)[int(len(results) * 0.1)]
    return avg_pnl, min_pnl, max_pnl, p10

# Test different bankrolls and caps
print(f"\n{'Bankroll':>10} {'Neg Cap':>10} {'Avg PnL':>10} {'p10 PnL':>10} {'Worst':>10} {'Best':>10}")
print("-" * 62)

scenarios = []
for bankroll in [200, 350, 500, 700, 1000, 1500]:
    for neg_cap in [0, 0.3, 0.5, 0.7, 1.0]:
        avg, worst, best, p10 = simulate_month(bankroll, neg_cap, days=30, runs=200)
        label = f"{int(neg_cap*100)}%"
        if neg_cap == 0:
            label = "OFF"
        print(f"${bankroll:>8} {label:>10} ${avg:>8.0f} ${p10:>8.0f} ${worst:>8.0f} ${best:>8.0f}")
        scenarios.append({
            "bankroll": bankroll, "neg_cap_pct": neg_cap,
            "avg_pnl": round(avg, 2), "p10_pnl": round(p10, 2),
            "worst_pnl": round(worst, 2), "best_pnl": round(best, 2),
        })

# ============================================================
# 7. CRITICAL WEAKNESSES SUMMARY
# ============================================================
print("\n\n### 7. CRITICAL WEAKNESSES IN PREVIOUS ANALYSIS ###")
print("""
1. SURVIVORSHIP BIAS: Scanner ran 3.7 days -- too short for rare events.
   0/641 losses doesn't prove safety. True loss rate could be 0.2-0.5%
   and we'd still see 0 losses in this sample.

2. RESOLVE TIME UNDERESTIMATE: Scanner shows 26.6h median, but actual
   bot data shows 52.7h. Previous PnL estimate used scanner times ->
   overestimated capital turnover by ~2x.

3. FILL RATE IGNORED: Previous analysis assumed 100% fill rate.
   Real fill rate is 59.6% -> actual bets are ~40% fewer.

4. MONTHLY PnL WAS OVERSTATED: Previous estimate of $220/month with
   50% cap was based on:
   - 100% fill rate (reality: 60%)
   - 26.6h resolve (reality: 53h for neg_risk)
   - No losses assumed (reality: ~0.2-0.5% possible)

5. SCANNER DATA ≠ BOT BEHAVIOR: Scanner captures markets at any
   snapshot; bot scans every 5 minutes. Different timing = different
   markets caught.
""")

# Save results
output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "analysis": "critical review of neg_risk recommendation",
    "survivorship": {
        "total_resolved": total_resolved,
        "total_lost": total_lost,
        "neg_resolved": neg_resolved,
        "neg_lost": neg_lost,
    },
    "confidence": {
        "current_124_lower_bound_wr": round(wr_lower_124, 2),
        "neg_641_lower_bound_wr": round(wr_lower_641, 2),
        "combined_765_lower_bound_wr": round(wr_lower_765, 2),
    },
    "resolve_times_actual": {
        "neg_risk_samples": len(neg_resolve_h),
        "neg_risk_percentiles": {
            "p10": round(neg_resolve_h[int(len(neg_resolve_h)*0.1)], 1) if neg_resolve_h else None,
            "p50": round(neg_resolve_h[len(neg_resolve_h)//2], 1) if neg_resolve_h else None,
            "p90": round(neg_resolve_h[int(len(neg_resolve_h)*0.9)], 1) if neg_resolve_h else None,
        },
        "regular_samples": len(reg_resolve_h),
        "regular_percentiles": {
            "p10": round(reg_resolve_h[int(len(reg_resolve_h)*0.1)], 1) if reg_resolve_h else None,
            "p50": round(reg_resolve_h[len(reg_resolve_h)//2], 1) if reg_resolve_h else None,
            "p90": round(reg_resolve_h[int(len(reg_resolve_h)*0.9)], 1) if reg_resolve_h else None,
        },
    },
    "simulation_scenarios": scenarios,
}

with open("_analytics/data/backtest_critical_analysis_2026-03-20.json", "w") as f:
    json.dump(output, f, indent=2)
print("\nSaved to _analytics/data/backtest_critical_analysis_2026-03-20.json")
