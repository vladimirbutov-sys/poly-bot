"""
Backtest by price ranges for player Car
Wallet: 0x7c3db723f1d4d8cb9c550095203b686cb11e5c6b
Fields: avgPrice, totalBought (shares), realizedPnl (P&L)
"""

import json
from collections import defaultdict

# Load data
with open("car_closed_positions_raw.json", "r") as f:
    data = json.load(f)

print(f"Total positions loaded: {len(data)}")

# ----- FILTER: cost >= 500 USD -----
# cost = avgPrice * totalBought (what Car spent)
filtered = []
for pos in data:
    avg_price = float(pos.get("avgPrice", 0) or 0)
    total_bought = float(pos.get("totalBought", 0) or 0)
    realized_pnl = float(pos.get("realizedPnl", 0) or 0)
    cost = avg_price * total_bought
    if cost >= 500:
        filtered.append({
            "avgPrice": avg_price,
            "size": total_bought,
            "cashPnl": realized_pnl,
            "cost": cost,
            "won": realized_pnl > 0,
            "title": pos.get("title", ""),
        })

print(f"Filtered (cost >= $500): {len(filtered)} positions")

# Check a few
print("\nTop 5 by PnL:")
for p in sorted(filtered, key=lambda x: x["cashPnl"], reverse=True)[:5]:
    print(f"  price={p['avgPrice']:.4f}, cost=${p['cost']:.0f}, pnl=${p['cashPnl']:.0f}")

# ----- 2a. WR/ROI by price ranges -----
ranges = [
    (0.00, 0.15, "0.00–0.15"),
    (0.15, 0.30, "0.15–0.30"),
    (0.30, 0.50, "0.30–0.50"),
    (0.50, 0.70, "0.50–0.70"),
    (0.70, 0.85, "0.70–0.85"),
    (0.85, 1.00, "0.85–1.00"),
]

range_stats = {}
for lo, hi, label in ranges:
    bucket = [p for p in filtered if lo <= p["avgPrice"] < hi]
    if not bucket:
        range_stats[label] = {"n": 0, "wr": 0, "roi": 0, "avg_win": 0, "avg_loss": 0, "total_pnl": 0, "total_cost": 0}
        continue

    wins = [p for p in bucket if p["won"]]
    losses = [p for p in bucket if not p["won"]]
    total_cost = sum(p["cost"] for p in bucket)
    total_pnl = sum(p["cashPnl"] for p in bucket)
    wr = len(wins) / len(bucket) * 100
    roi = total_pnl / total_cost * 100 if total_cost > 0 else 0
    avg_win = sum(p["cashPnl"] for p in wins) / len(wins) if wins else 0
    avg_loss = sum(p["cashPnl"] for p in losses) / len(losses) if losses else 0

    range_stats[label] = {
        "n": len(bucket),
        "wr": round(wr, 1),
        "roi": round(roi, 1),
        "avg_win": round(avg_win, 1),
        "avg_loss": round(avg_loss, 1),
        "total_pnl": round(total_pnl, 1),
        "total_cost": round(total_cost, 1)
    }

print("\n===== 2a. WR/ROI BY PRICE RANGE =====")
print(f"{'Range':<12} {'N':>5} {'WR%':>7} {'ROI%':>8} {'AvgWin':>10} {'AvgLoss':>10} {'TotalPnL':>12} {'TotalCost':>12}")
print("-" * 80)
for label, s in range_stats.items():
    print(f"{label:<12} {s['n']:>5} {s['wr']:>7.1f} {s['roi']:>8.1f} {s['avg_win']:>10.0f} {s['avg_loss']:>10.0f} {s['total_pnl']:>12.0f} {s['total_cost']:>12.0f}")

# ----- SIZING STRATEGIES -----
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
    if price < 0.15: return 20
    if price < 0.30: return 35
    if price < 0.50: return 50
    if price < 0.70: return 60
    if price < 0.85: return 45
    return 25

strategies = {
    "A_fixed_50": strategy_A,
    "B_prop_price": strategy_B,
    "C_target35": strategy_C,
    "D_tiers": strategy_D,
}

def simulate(positions, strategy_fn, slippage=0.0):
    total_pnl = 0
    total_cost = 0
    wins = 0
    n = 0
    for p in positions:
        entry_price = p["avgPrice"]
        price_for_sizing = min(entry_price + slippage, 0.99)
        our_cost = strategy_fn(price_for_sizing)
        if our_cost <= 0:
            continue
        # If Car won: our profit = cost * (1/avgPrice - 1)
        # If Car lost: we lose our_cost
        if p["won"]:
            our_pnl = our_cost * (1 / entry_price - 1)
        else:
            our_pnl = -our_cost
        total_pnl += our_pnl
        total_cost += our_cost
        if our_pnl > 0:
            wins += 1
        n += 1
    wr = wins / n * 100 if n > 0 else 0
    roi = total_pnl / total_cost * 100 if total_cost > 0 else 0
    return {
        "n": n,
        "total_pnl": round(total_pnl, 1),
        "total_cost": round(total_cost, 1),
        "wr": round(wr, 1),
        "roi": round(roi, 1)
    }

print("\n===== 2b. STRATEGY SIMULATION (no slippage) =====")
print(f"{'Strategy':<18} {'N':>5} {'WR%':>7} {'ROI%':>7} {'TotalPnL':>10} {'TotalCost':>10}")
print("-" * 60)
strategy_results = {}
for name, fn in strategies.items():
    r = simulate(filtered, fn, slippage=0.0)
    strategy_results[f"{name}_no_slip"] = r
    print(f"{name:<18} {r['n']:>5} {r['wr']:>7.1f} {r['roi']:>7.1f} {r['total_pnl']:>10.1f} {r['total_cost']:>10.1f}")

print("\n===== 2b. STRATEGY SIMULATION (slippage +0.03) =====")
print(f"{'Strategy':<18} {'N':>5} {'WR%':>7} {'ROI%':>7} {'TotalPnL':>10} {'TotalCost':>10}")
print("-" * 60)
for name, fn in strategies.items():
    r = simulate(filtered, fn, slippage=0.03)
    strategy_results[f"{name}_slip003"] = r
    print(f"{name:<18} {r['n']:>5} {r['wr']:>7.1f} {r['roi']:>7.1f} {r['total_pnl']:>10.1f} {r['total_cost']:>10.1f}")

# ----- 2b per range with slippage -----
print("\n===== 2b. STRATEGY ROI% PER RANGE (slippage +0.03) =====")
print(f"{'Range':<12}", end="")
for name in strategies:
    print(f" {name[:12]:>13}", end="")
print()
print("-" * (12 + 13 * len(strategies)))

strategy_by_range = {}
for lo, hi, label in ranges:
    bucket = [p for p in filtered if lo <= p["avgPrice"] < hi]
    print(f"{label:<12}", end="")
    strategy_by_range[label] = {}
    for name, fn in strategies.items():
        if len(bucket) < 2:
            print(f" {'N/A':>13}", end="")
            continue
        r = simulate(bucket, fn, slippage=0.03)
        roi_str = f"{r['roi']:.1f}%"
        print(f" {roi_str:>13}", end="")
        strategy_by_range[label][name] = r
    print()

# ----- 2c. Dead zone analysis: Car invests $2000-$5000 -----
dead_zone = [p for p in filtered if 2000 <= p["cost"] <= 5000]
print(f"\n===== 2c. DEAD ZONE ANALYSIS ($2000–$5000 per position) =====")
print(f"Total positions in dead zone: {len(dead_zone)}")

dead_by_range = {}
if dead_zone:
    print(f"\n{'Range':<12} {'N':>5} {'WR%':>7} {'ROI%':>7} {'AvgPrice':>10} {'TotalPnL':>10}")
    print("-" * 55)
    for lo, hi, label in ranges:
        bucket = [p for p in dead_zone if lo <= p["avgPrice"] < hi]
        if not bucket:
            continue
        pnl = sum(p["cashPnl"] for p in bucket)
        cost = sum(p["cost"] for p in bucket)
        wins = sum(1 for p in bucket if p["won"])
        wr = wins / len(bucket) * 100
        roi = pnl / cost * 100 if cost > 0 else 0
        avg_price = sum(p["avgPrice"] for p in bucket) / len(bucket)
        dead_by_range[label] = {
            "n": len(bucket),
            "wr": round(wr, 1),
            "roi": round(roi, 1),
            "total_pnl": round(pnl, 1),
            "total_cost": round(cost, 1),
            "avg_price": round(avg_price, 4)
        }
        print(f"{label:<12} {len(bucket):>5} {wr:>7.1f} {roi:>7.1f} {avg_price:>10.4f} {pnl:>10.0f}")

    # Overall dead zone stats
    dz_pnl = sum(p["cashPnl"] for p in dead_zone)
    dz_cost = sum(p["cost"] for p in dead_zone)
    dz_wr = sum(1 for p in dead_zone if p["won"]) / len(dead_zone) * 100
    dz_roi = dz_pnl / dz_cost * 100
    print(f"\nDead zone overall: N={len(dead_zone)}, WR={dz_wr:.1f}%, ROI={dz_roi:.2f}%, PnL=${dz_pnl:.0f}")

    # Price concentration in dead zone
    print("\nTop price concentrations in dead zone:")
    price_buckets = defaultdict(list)
    for p in dead_zone:
        pr = round(p["avgPrice"], 1)
        price_buckets[pr].append(p)
    for pr, bucket in sorted(price_buckets.items(), key=lambda x: -len(x[1]))[:8]:
        pnl = sum(p["cashPnl"] for p in bucket)
        wr = sum(1 for p in bucket if p["won"]) / len(bucket) * 100
        print(f"  price~{pr:.1f}: {len(bucket)} positions, WR={wr:.0f}%, PnL=${pnl:.0f}")

# ----- BEST STRATEGY PER RANGE -----
print("\n===== BEST STRATEGY PER RANGE (slippage +0.03) =====")
best_per_range = {}
for lo, hi, label in ranges:
    bucket = [p for p in filtered if lo <= p["avgPrice"] < hi]
    if len(bucket) < 3:
        continue
    best = None
    best_roi = -999
    for name, fn in strategies.items():
        r = simulate(bucket, fn, slippage=0.03)
        if r["roi"] > best_roi and r["n"] > 0:
            best_roi = r["roi"]
            best = (name, r)
    if best:
        best_per_range[label] = {"strategy": best[0], **best[1]}
        print(f"{label}: best={best[0]}, ROI={best[1]['roi']}%, PnL=${best[1]['total_pnl']}, N={best[1]['n']}, WR={best[1]['wr']}%")

# ----- OVERALL BEST STRATEGY -----
print("\n===== OVERALL BEST (slippage +0.03) =====")
best_overall = max(
    [(name, simulate(filtered, fn, slippage=0.03)) for name, fn in strategies.items()],
    key=lambda x: x[1]["roi"]
)
print(f"Best strategy: {best_overall[0]}, ROI={best_overall[1]['roi']}%, PnL=${best_overall[1]['total_pnl']}")

# ----- PRICE FILTER TEST: what if we only copy in certain ranges? -----
print("\n===== PRICE FILTER ANALYSIS: PnL with D_tiers, slippage 0.03 =====")
print("(Which ranges to INCLUDE for best result)")
# Best filter = only non-negative ROI ranges
include_ranges = [(lo, hi, label) for lo, hi, label in ranges
                  if range_stats[label].get("roi", 0) > 0]
bucket_best_filter = [p for p in filtered
                      if any(lo <= p["avgPrice"] < hi for lo, hi, label in include_ranges)]
r_filtered = simulate(bucket_best_filter, strategy_D, slippage=0.03)
print(f"Only positive-ROI ranges: N={r_filtered['n']}, ROI={r_filtered['roi']}%, PnL=${r_filtered['total_pnl']}")

# ----- SAVE RESULTS -----
results = {
    "total_all": len(data),
    "total_filtered_500": len(filtered),
    "range_stats": range_stats,
    "strategy_results": strategy_results,
    "dead_zone_by_range": dead_by_range,
    "best_per_range": best_per_range,
    "strategy_by_range": {
        label: {
            name: r for name, r in sr.items()
        } for label, sr in strategy_by_range.items()
    }
}

with open("car_backtest_results.json", "w") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)
print("\nResults saved to car_backtest_results.json")
