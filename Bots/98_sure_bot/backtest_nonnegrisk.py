"""
Backtest: non-neg_risk strategy on real historical Polymarket data.

Uses 97_scanner's 20,000+ resolved markets to answer the key question:
"Of all markets where price reached our entry threshold, how often did
the high-priced outcome win?"

METHODOLOGY NOTE:
- Scanner records max_price_seen (highest price observed), not entry price.
- Most markets pass through 97.5% on their way to 99%+, so filtering by
  MAX_PRICE would exclude them (they'd show max_price=0.998, not 0.985).
- For WIN RATE: we count all markets that reached the threshold (no upper cap).
- For PnL: we use the bot's actual average entry price from positions.json.

Data source: 97_scanner/scanner_data.json (20,371 markets)
"""
import json
import sys
from datetime import datetime, timezone
from collections import defaultdict, Counter

sys.stdout.reconfigure(encoding="utf-8")

SCANNER_DATA = "C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json"
POSITIONS_FILE = "C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json"
OUTPUT_FILE = "C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/backtest_results.json"

BET_SIZE = 10.0
CAPITAL = 574.0

# =====================================================
# Load data
# =====================================================
print("Loading scanner data...")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc = json.load(f)

print("Loading positions data...")
with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
    pos_data = json.load(f)

markets = sc.get("markets", {})
print(f"Total markets in scanner: {len(markets)}")

# Get actual average entry price from bot positions
won_positions = [p for p in pos_data["positions"].values() if p["status"] == "won"]
if won_positions:
    actual_avg_entry = sum(p["entry_price"] for p in won_positions) / len(won_positions)
else:
    actual_avg_entry = 0.985
print(f"Bot's actual avg entry price (from {len(won_positions)} wins): {actual_avg_entry:.4f}")

# =====================================================
# Build resolved dataset
# =====================================================
resolved = []

for mid, m in markets.items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue

    max_price = m.get("max_price_seen", 0)
    high_outcome = m.get("high_outcome", "")
    winner = res.get("winner", "")
    if not high_outcome or not winner:
        continue

    won = (high_outcome == winner)
    is_neg_risk = m.get("neg_risk", False)
    category = m.get("category", "other") or "other"
    closed_time = res.get("closed_time", "")

    resolved.append({
        "id": mid,
        "max_price": max_price,
        "won": won,
        "neg_risk": is_neg_risk,
        "category": category,
        "question": m.get("question", ""),
        "closed_time": closed_time,
    })

print(f"Total resolved markets: {len(resolved)}")

# =====================================================
# Win rate analysis (the core question)
# =====================================================
def analyze_win_rate(markets_list, label, min_price, skip_neg_risk=False, neg_risk_only=False):
    """Count wins/losses for markets that reached min_price threshold."""
    wins = 0
    losses = 0
    loss_details = []

    for m in markets_list:
        if m["max_price"] < min_price:
            continue
        if skip_neg_risk and m["neg_risk"]:
            continue
        if neg_risk_only and not m["neg_risk"]:
            continue

        if m["won"]:
            wins += 1
        else:
            losses += 1
            loss_details.append({
                "question": m["question"][:80],
                "max_price": m["max_price"],
                "category": m["category"],
                "neg_risk": m["neg_risk"],
            })

    total = wins + losses
    wr = wins / total * 100 if total > 0 else 0
    lr = losses / total if total > 0 else 0

    return {
        "label": label,
        "min_price": min_price,
        "wins": wins,
        "losses": losses,
        "total": total,
        "win_rate": round(wr, 4),
        "loss_rate_1_in_n": int(1 / lr) if lr > 0 else 0,
        "loss_details": loss_details,
    }


print(f"\n{'='*90}")
print("WIN RATE ANALYSIS (all resolved markets that reached price threshold)")
print(f"{'='*90}")
print(f"\n{'Scenario':45s} {'Total':>7s} {'W':>7s} {'L':>4s} {'WR':>8s} {'1 loss per':>10s}")
print("-" * 85)

analyses = [
    # All markets
    analyze_win_rate(resolved, "ALL, price reached 96%+", 0.96),
    analyze_win_rate(resolved, "ALL, price reached 97%+", 0.97),
    analyze_win_rate(resolved, "ALL, price reached 97.5%+", 0.975),
    analyze_win_rate(resolved, "ALL, price reached 98%+", 0.98),
    # Non-neg_risk only
    analyze_win_rate(resolved, "NON-NEG_RISK, price reached 96%+", 0.96, skip_neg_risk=True),
    analyze_win_rate(resolved, "NON-NEG_RISK, price reached 97%+", 0.97, skip_neg_risk=True),
    analyze_win_rate(resolved, "NON-NEG_RISK, price reached 97.5%+", 0.975, skip_neg_risk=True),
    analyze_win_rate(resolved, "NON-NEG_RISK, price reached 98%+", 0.98, skip_neg_risk=True),
    # Neg_risk only
    analyze_win_rate(resolved, "NEG_RISK only, price reached 97.5%+", 0.975, neg_risk_only=True),
]

for a in analyses:
    loss_str = f"1 in {a['loss_rate_1_in_n']}" if a["loss_rate_1_in_n"] > 0 else "0 losses"
    print(f"{a['label']:45s} {a['total']:7d} {a['wins']:7d} {a['losses']:4d} {a['win_rate']:7.3f}% {loss_str:>10s}")

# =====================================================
# Category breakdown (non-neg_risk, 97.5%+)
# =====================================================
print(f"\n{'='*90}")
print("CATEGORY BREAKDOWN (non-neg_risk, price reached 97.5%+)")
print(f"{'='*90}")

cat_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "loss_q": []})
for m in resolved:
    if m["neg_risk"] or m["max_price"] < 0.975:
        continue
    cat = m["category"]
    if m["won"]:
        cat_stats[cat]["wins"] += 1
    else:
        cat_stats[cat]["losses"] += 1
        cat_stats[cat]["loss_q"].append(m["question"][:70])

print(f"\n{'Category':18s} {'W':>6s} {'L':>4s} {'WR':>8s} {'1 loss per':>12s}")
print("-" * 55)
for cat in sorted(cat_stats, key=lambda c: -(cat_stats[c]["wins"] + cat_stats[c]["losses"])):
    d = cat_stats[cat]
    total = d["wins"] + d["losses"]
    wr = d["wins"] / total * 100 if total > 0 else 0
    lr_n = total // d["losses"] if d["losses"] > 0 else 0
    loss_str = f"1 in {lr_n}" if lr_n > 0 else "0 losses"
    print(f"{cat:18s} {d['wins']:6d} {d['losses']:4d} {wr:7.3f}% {loss_str:>12s}")
    for q in d["loss_q"]:
        print(f"  LOSS: {q}")

# =====================================================
# All losses detail
# =====================================================
print(f"\n{'='*90}")
print("ALL LOSSES DETAIL (non-neg_risk, price reached 97.5%+)")
print(f"{'='*90}")

a_nnr_975 = next(a for a in analyses if a["label"] == "NON-NEG_RISK, price reached 97.5%+")
for ld in a_nnr_975["loss_details"]:
    print(f"  max_price={ld['max_price']:.4f} | {ld['category']:12s} | nr={ld['neg_risk']} | {ld['question']}")

# =====================================================
# P&L projection
# =====================================================
print(f"\n{'='*90}")
print("MONTHLY P&L PROJECTIONS")
print(f"{'='*90}")

scenarios = [
    # (name, win_rate_source, avg_entry, avg_redeem_h, capital, bet_size)
    ("Current (neg_risk ON, 45h redeem)", "ALL, price reached 97.5%+", actual_avg_entry, 45, CAPITAL, BET_SIZE),
    ("Skip neg_risk (12h redeem)", "NON-NEG_RISK, price reached 97.5%+", actual_avg_entry, 12, CAPITAL, BET_SIZE),
    ("Skip neg_risk, $15 bet", "NON-NEG_RISK, price reached 97.5%+", actual_avg_entry, 12, CAPITAL, 15),
    ("Skip neg_risk, $1000 capital", "NON-NEG_RISK, price reached 97.5%+", actual_avg_entry, 12, 1000, BET_SIZE),
]

print(f"\n{'Scenario':45s} {'Bets/mo':>8s} {'Gross':>8s} {'Loss':>8s} {'Net':>8s} {'ROI':>6s}")
print("-" * 85)

projection_results = []

for name, wr_label, avg_entry, redeem_h, capital, bet in scenarios:
    wr_data = next(a for a in analyses if a["label"] == wr_label)
    win_rate = wr_data["win_rate"] / 100
    loss_rate = 1 - win_rate

    profit_per_win = bet / avg_entry - bet  # shares * $1 - cost
    slots = int(capital / bet)
    turns_per_day = 24 / redeem_h
    bets_per_month = slots * turns_per_day * 30

    gross = bets_per_month * win_rate * profit_per_win
    loss = bets_per_month * loss_rate * bet
    net = gross - loss
    roi = net / capital * 100

    print(f"{name:45s} {bets_per_month:8.0f} ${gross:7.1f} ${loss:7.1f} ${net:7.1f} {roi:5.1f}%")

    projection_results.append({
        "name": name,
        "bets_per_month": round(bets_per_month),
        "gross": round(gross, 2),
        "loss": round(loss, 2),
        "net": round(net, 2),
        "roi_pct": round(roi, 2),
        "win_rate_used": round(win_rate * 100, 4),
        "loss_rate_1_in_n": wr_data["loss_rate_1_in_n"],
    })

# =====================================================
# Risk analysis: worst-case streaks
# =====================================================
print(f"\n{'='*90}")
print("RISK ANALYSIS")
print(f"{'='*90}")

wr_nnr = next(a for a in analyses if a["label"] == "NON-NEG_RISK, price reached 97.5%+")
loss_rate = wr_nnr["losses"] / wr_nnr["total"] if wr_nnr["total"] > 0 else 0

print(f"\n  Loss rate (non-NR, 97.5%+): {wr_nnr['losses']}/{wr_nnr['total']} = 1 in {wr_nnr['loss_rate_1_in_n']}")
print(f"  At $10/bet, each loss costs: $10.00")
print(f"  Avg profit per win: ${BET_SIZE / actual_avg_entry - BET_SIZE:.4f}")
print(f"  Wins needed to cover 1 loss: {int(BET_SIZE / (BET_SIZE / actual_avg_entry - BET_SIZE))}")

# Monte Carlo survival
import random
random.seed(42)

def monte_carlo(capital, bet, win_rate, profit_per_win, n_bets, n_sims=10000):
    """Run Monte Carlo simulation, return survival rate and P&L distribution."""
    survived = 0
    final_pnls = []
    min_pnl = float("inf")

    for _ in range(n_sims):
        bal = capital
        for _ in range(n_bets):
            if bal < bet:
                break
            if random.random() < win_rate:
                bal += profit_per_win
            else:
                bal -= bet
        else:
            survived += 1
        final_pnls.append(bal - capital)
        min_pnl = min(min_pnl, bal - capital)

    final_pnls.sort()
    n = len(final_pnls)
    return {
        "survival_rate": survived / n_sims * 100,
        "median_pnl": final_pnls[n // 2],
        "p5_pnl": final_pnls[int(n * 0.05)],
        "p95_pnl": final_pnls[int(n * 0.95)],
        "worst_pnl": final_pnls[0],
        "best_pnl": final_pnls[-1],
    }

profit_per_win = BET_SIZE / actual_avg_entry - BET_SIZE
wr = wr_nnr["win_rate"] / 100

mc_30d = monte_carlo(CAPITAL, BET_SIZE, wr, profit_per_win, 3420)  # ~3420 bets/month
mc_90d = monte_carlo(CAPITAL, BET_SIZE, wr, profit_per_win, 10260)

print(f"\n  Monte Carlo (10,000 sims, non-NR, $10/bet, 12h redeem):")
print(f"  --- 30 days ({3420} bets) ---")
print(f"    Survival: {mc_30d['survival_rate']:.2f}%")
print(f"    Median PnL: ${mc_30d['median_pnl']:.2f}")
print(f"    5th percentile: ${mc_30d['p5_pnl']:.2f}")
print(f"    95th percentile: ${mc_30d['p95_pnl']:.2f}")
print(f"    Worst case: ${mc_30d['worst_pnl']:.2f}")

print(f"  --- 90 days ({10260} bets) ---")
print(f"    Survival: {mc_90d['survival_rate']:.2f}%")
print(f"    Median PnL: ${mc_90d['median_pnl']:.2f}")
print(f"    5th percentile: ${mc_90d['p5_pnl']:.2f}")
print(f"    95th percentile: ${mc_90d['p95_pnl']:.2f}")
print(f"    Worst case: ${mc_90d['worst_pnl']:.2f}")

# =====================================================
# Save results
# =====================================================
output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "methodology": (
        "Win rate calculated from 97_scanner resolved markets. "
        "max_price_seen used as threshold (did market ever reach X%?), "
        "not as entry price. PnL uses bot's actual avg entry price. "
        "No upper price cap applied — bot enters during price journey, "
        "not at max_price_seen."
    ),
    "data_source": {
        "scanner_markets": len(markets),
        "resolved_markets": len(resolved),
        "bot_avg_entry_price": actual_avg_entry,
    },
    "win_rate_analysis": [
        {k: v for k, v in a.items() if k != "loss_details"}
        for a in analyses
    ],
    "all_losses_nonnr_975": a_nnr_975["loss_details"],
    "category_breakdown_nonnr_975": {
        cat: {
            "wins": d["wins"],
            "losses": d["losses"],
            "win_rate": round(d["wins"] / (d["wins"] + d["losses"]) * 100, 4) if (d["wins"] + d["losses"]) > 0 else 0,
            "loss_questions": d["loss_q"],
        }
        for cat, d in cat_stats.items()
    },
    "monthly_projections": projection_results,
    "monte_carlo": {
        "params": {
            "capital": CAPITAL,
            "bet_size": BET_SIZE,
            "win_rate": round(wr * 100, 4),
            "profit_per_win": round(profit_per_win, 4),
            "simulations": 10000,
        },
        "30_days": mc_30d,
        "90_days": mc_90d,
    },
}

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\nResults saved to {OUTPUT_FILE}")
