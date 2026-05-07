"""
Backtest for denizz (0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73)
Analyzes closed positions by price range, simulates 4 sizing strategies.

IMPORTANT NOTE ON DATA:
  The Polymarket closed-positions API returns ALL closed positions,
  but in denizz's case ALL 100 returned records have positive realizedPnl.
  This could mean:
  a) denizz is an elite trader who actively sells losing positions early
     (curPrice=0 YES positions with positive PnL = sold before resolution)
  b) The API might filter out certain position types

  Conclusion: We CANNOT determine true win rate from this endpoint.
  We CAN determine: WHERE he trades, HOW LARGE his positions are, and
  HOW PROFITABLE his closed positions are.

Fields from API:
  avgPrice     - average entry price (0..1)
  totalBought  - total shares purchased
  realizedPnl  - actual profit/loss in USDC (net of fees, early sells)
  curPrice     - last market price (1.0=resolved YES, 0.0=resolved NO)
  outcome      - 'Yes' or 'No' (which side denizz held)

Cost = avgPrice * totalBought (total USD spent on position)
"""

import json
import statistics

# --- Load data ---
with open("denizz_closed_positions_raw.json", "r") as f:
    raw = json.load(f)

print(f"Total raw records: {len(raw)}")

# --- Build positions list (all) ---
all_positions = []
for p in raw:
    avg_price = float(p.get("avgPrice", 0))
    total_bought = float(p.get("totalBought", 0))
    realized_pnl = float(p.get("realizedPnl", 0))
    cur_price = float(p.get("curPrice", 0))
    cost = avg_price * total_bought  # USD spent
    roi = realized_pnl / cost if cost > 0 else 0

    all_positions.append({
        "avgPrice": avg_price,
        "totalBought": total_bought,
        "realizedPnl": realized_pnl,
        "curPrice": cur_price,
        "cost": cost,
        "roi": roi,
        "outcome": p.get("outcome", ""),
        "win": realized_pnl > 0,  # all are positive in this dataset
        "title": p.get("title", ""),
    })

# --- Filter: cost >= $500 ---
positions = [p for p in all_positions if p["cost"] >= 500]
print(f"After filter (cost >= $500): {len(positions)} positions")
print(f"NOTE: ALL {len(raw)} records have positive realizedPnl (sold early or won)")
print()

# --- Price ranges ---
ranges = [
    (0.00, 0.15),
    (0.15, 0.30),
    (0.30, 0.50),
    (0.50, 0.70),
    (0.70, 0.85),
    (0.85, 1.00),
]

def range_label(lo, hi):
    return f"{lo:.2f}-{hi:.2f}"

# --- 2a. WR/ROI by range (filtered positions) ---
range_positions = {range_label(lo, hi): [] for lo, hi in ranges}

for p in positions:
    price = p["avgPrice"]
    for lo, hi in ranges:
        if lo <= price < hi:
            range_positions[range_label(lo, hi)].append(p)
            break

print("=== 2a. WR/ROI by Price Range (cost >= $500) ===")
print("NOTE: WR% is 100% for all because API only returns profitable closed positions")
print(f"{'Range':<12} {'N':>4} {'WR%':>7} {'ROI%':>7} {'Avg PnL$':>9} {'Total PnL':>11} {'Avg Cost$':>10}")
print("-" * 70)

range_results = {}
for lo, hi in ranges:
    lbl = range_label(lo, hi)
    ps = range_positions[lbl]
    n = len(ps)
    if n == 0:
        range_results[lbl] = {"n": 0}
        print(f"{lbl:<12} {0:>4} {'—':>7} {'—':>7} {'—':>9} {'—':>11} {'—':>10}")
        continue

    wins = [p for p in ps if p["win"]]
    losses = [p for p in ps if not p["win"]]
    wr = len(wins) / n * 100
    total_pnl = sum(p["realizedPnl"] for p in ps)
    total_cost = sum(p["cost"] for p in ps)
    roi = total_pnl / total_cost * 100 if total_cost > 0 else 0
    avg_pnl = total_pnl / n
    avg_cost = total_cost / n

    range_results[lbl] = {
        "n": n,
        "wins": len(wins),
        "losses": len(losses),
        "wr_pct": round(wr, 1),
        "roi_pct": round(roi, 1),
        "avg_pnl": round(avg_pnl, 2),
        "total_pnl": round(total_pnl, 2),
        "total_cost": round(total_cost, 2),
        "avg_cost": round(avg_cost, 2),
    }
    print(f"{lbl:<12} {n:>4} {wr:>7.1f} {roi:>7.1f} {avg_pnl:>9.0f} {total_pnl:>11.0f} {avg_cost:>10.0f}")

# Summary
total_pnl_all = sum(p["realizedPnl"] for p in positions)
total_cost_all = sum(p["cost"] for p in positions)
total_wins = sum(1 for p in positions if p["win"])
print("-" * 70)
print(f"{'TOTAL':<12} {len(positions):>4} {total_wins/len(positions)*100:>7.1f} {total_pnl_all/total_cost_all*100:>7.1f} {total_pnl_all/len(positions):>9.0f} {total_pnl_all:>11.0f} {total_cost_all/len(positions):>10.0f}")

# --- Strategies ---
def strategy_A(price):
    return 50

def strategy_B(price):
    return 50 * (price / 0.50)

def strategy_C(price, target_profit=35):
    if price >= 0.99:
        return 0
    stake = target_profit / (1 / price - 1)
    return max(5, min(stake, 150))

def strategy_D(price):
    if price < 0.15:  return 20
    if price < 0.30:  return 35
    if price < 0.50:  return 50
    if price < 0.70:  return 60
    if price < 0.85:  return 45
    return 25

STRATEGIES = {
    "A_flat_$50": strategy_A,
    "B_linear": strategy_B,
    "C_fixed_profit": strategy_C,
    "D_tiered": strategy_D,
}

def simulate(positions, strategy_fn, slippage=0.0):
    total_pnl = 0
    total_cost = 0
    wins = 0
    losses = 0
    for p in positions:
        price = p["avgPrice"] + slippage
        if price <= 0 or price >= 1:
            continue
        our_cost = strategy_fn(price)
        if our_cost <= 0:
            continue
        if p["win"]:
            # Win: profit = our_cost * (1/entry_price - 1)
            our_pnl = our_cost * (1 / p["avgPrice"] - 1)
            wins += 1
        else:
            our_pnl = -our_cost
            losses += 1
        total_pnl += our_pnl
        total_cost += our_cost
    n = wins + losses
    roi = total_pnl / total_cost * 100 if total_cost > 0 else 0
    wr = wins / n * 100 if n > 0 else 0
    return {
        "n": n,
        "wins": wins,
        "losses": losses,
        "wr_pct": round(wr, 1),
        "total_pnl": round(total_pnl, 2),
        "total_cost": round(total_cost, 2),
        "roi_pct": round(roi, 1),
    }

# --- 2b. Simulate strategies ---
print("\n=== 2b. Strategy Simulation (no slippage, assuming all wins) ===")
print(f"{'Strategy':<18} {'N':>4} {'WR%':>6} {'Total PnL':>11} {'Total Cost':>11} {'ROI%':>7}")
print("-" * 62)

strategy_results = {}
for name, fn in STRATEGIES.items():
    res = simulate(positions, fn, slippage=0.0)
    strategy_results[name] = res
    print(f"{name:<18} {res['n']:>4} {res['wr_pct']:>6.1f} {res['total_pnl']:>11.1f} {res['total_cost']:>11.1f} {res['roi_pct']:>7.1f}")

print("\n=== 2b. Strategy Simulation (slippage +0.03) ===")
print(f"{'Strategy':<18} {'N':>4} {'WR%':>6} {'Total PnL':>11} {'Total Cost':>11} {'ROI%':>7}")
print("-" * 62)

strategy_results_slip = {}
for name, fn in STRATEGIES.items():
    res = simulate(positions, fn, slippage=0.03)
    key = name + "_slip0.03"
    strategy_results_slip[key] = res
    print(f"{name+'_s0.03':<18} {res['n']:>4} {res['wr_pct']:>6.1f} {res['total_pnl']:>11.1f} {res['total_cost']:>11.1f} {res['roi_pct']:>7.1f}")

# --- 2c. denizz trading patterns ---
print("\n=== 2c. denizz Trading Patterns (ALL 100 positions) ===")
all_range_data = {range_label(lo, hi): [] for lo, hi in ranges}
for p in all_positions:
    price = p["avgPrice"]
    for lo, hi in ranges:
        if lo <= price < hi:
            all_range_data[range_label(lo, hi)].append(p)
            break

print(f"{'Range':<12} {'N (all)':>8} {'N (>=500)':>10} {'Avg ROI%':>9} {'Avg Cost$':>10} {'Total PnL$':>12}")
print("-" * 65)
for lo, hi in ranges:
    lbl = range_label(lo, hi)
    all_ps = all_range_data[lbl]
    n_all = len(all_ps)
    if n_all == 0:
        print(f"{lbl:<12} {0:>8} {0:>10} {'—':>9} {'—':>10} {'—':>12}")
        continue
    big_ps = [p for p in all_ps if p["cost"] >= 500]
    n_big = len(big_ps)
    avg_roi = statistics.mean([p["roi"] for p in all_ps]) * 100
    avg_cost = statistics.mean([p["cost"] for p in all_ps])
    total_pnl = sum(p["realizedPnl"] for p in all_ps)
    print(f"{lbl:<12} {n_all:>8} {n_big:>10} {avg_roi:>9.1f} {avg_cost:>10.0f} {total_pnl:>12.0f}")

# Outcome analysis
print()
yes_pos = [p for p in all_positions]
no_ps = [p for p in all_positions if p["outcome"] == "No"]
yes_ps = [p for p in all_positions if p["outcome"] == "Yes"]
print(f"Trades Yes: {len(yes_ps)} | Trades No: {len(no_ps)}")
print(f"  Yes avg_cost: ${statistics.mean([p['cost'] for p in yes_ps]):,.0f}" if yes_ps else "")
print(f"  No  avg_cost: ${statistics.mean([p['cost'] for p in no_ps]):,.0f}" if no_ps else "")

# Top winners
print("\n--- Top 5 biggest wins ---")
top_wins = sorted(positions, key=lambda p: p["realizedPnl"], reverse=True)[:5]
for p in top_wins:
    print(f"  +${p['realizedPnl']:>10,.0f} | ROI={p['roi']*100:.0f}% | price={p['avgPrice']:.3f} | cost=${p['cost']:>8,.0f} | {p['title'][:45]}")

# --- Save results ---
output = {
    "wallet": "0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73",
    "total_raw": len(raw),
    "total_filtered_500": len(positions),
    "data_note": "ALL 100 records have positive realizedPnl - true WR cannot be determined from this endpoint",
    "range_stats_filtered": range_results,
    "strategy_results_no_slippage": strategy_results,
    "strategy_results_slip_0_03": strategy_results_slip,
    "all_positions_by_range": {
        k: {
            "count": len(v),
            "avg_roi_pct": round(statistics.mean([p["roi"] for p in v]) * 100, 1) if v else None,
            "avg_cost": round(statistics.mean([p["cost"] for p in v]), 0) if v else None,
            "total_pnl": round(sum(p["realizedPnl"] for p in v), 0) if v else None,
        }
        for k, v in all_range_data.items()
    },
    "yes_count": len(yes_ps),
    "no_count": len(no_ps),
}

with open("denizz_backtest_results.json", "w") as f:
    json.dump(output, f, indent=2)

print("\nResults saved to denizz_backtest_results.json")
