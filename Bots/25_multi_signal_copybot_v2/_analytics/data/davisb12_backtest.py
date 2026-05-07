"""
davisb12 backtest — price range analysis
Fields: avgPrice, totalBought, realizedPnl
cost = avgPrice * totalBought
"""
import json
import sys
import requests
import time
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')

RAW_FILE = "c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/_analytics/data/davisb12_closed_positions_raw.json"
OUT_FILE = "c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/_analytics/data/davisb12_backtest_results.json"
WALLET = "0xdf17f4a8dd01a4cfa6fc3da323a2baee5f8697d1"

# ─── Load data ───
with open(RAW_FILE, "r") as f:
    data = json.load(f)

print(f"Raw records: {len(data)}")

# ─── Parse positions ───
positions = []
for item in data:
    try:
        avg_price = float(item.get("avgPrice", 0) or 0)
        total_bought = float(item.get("totalBought", 0) or 0)
        realized_pnl = float(item.get("realizedPnl", 0) or 0)
        if avg_price <= 0 or avg_price >= 1.0:
            continue
        cost = avg_price * total_bought
        positions.append({
            "avgPrice": avg_price,
            "totalBought": total_bought,
            "realizedPnl": realized_pnl,
            "cost": cost,
            "win": realized_pnl > 0,
            "title": item.get("title", "")
        })
    except Exception as e:
        continue

print(f"Valid positions: {len(positions)}")
print(f"Cost distribution:")
cost_buckets = [0, 0, 0, 0, 0]
for p in positions:
    if p["cost"] < 500: cost_buckets[0] += 1
    elif p["cost"] < 1000: cost_buckets[1] += 1
    elif p["cost"] < 5000: cost_buckets[2] += 1
    elif p["cost"] < 10000: cost_buckets[3] += 1
    else: cost_buckets[4] += 1
print(f"  <$500: {cost_buckets[0]} | $500-1K: {cost_buckets[1]} | $1K-5K: {cost_buckets[2]} | $5K-10K: {cost_buckets[3]} | $10K+: {cost_buckets[4]}")

# ─── Ranges ───
RANGES = [
    (0.00, 0.15, "0.00-0.15"),
    (0.15, 0.30, "0.15-0.30"),
    (0.30, 0.50, "0.30-0.50"),
    (0.50, 0.70, "0.50-0.70"),
    (0.70, 0.85, "0.70-0.85"),
    (0.85, 1.00, "0.85-1.00"),
]

def get_range_label(price):
    for lo, hi, label in RANGES:
        if lo <= price < hi:
            return label
    return "0.85-1.00"

def calc_stats(pos_list):
    if not pos_list:
        return {
            "count": 0, "wr": 0, "roi": 0,
            "total_pnl": 0, "total_cost": 0,
            "avg_win": 0, "avg_loss": 0
        }
    wins = [p for p in pos_list if p["win"]]
    losses = [p for p in pos_list if not p["win"]]
    total_pnl = sum(p["realizedPnl"] for p in pos_list)
    total_cost = sum(p["cost"] for p in pos_list)
    wr = len(wins) / len(pos_list) * 100
    roi = total_pnl / total_cost * 100 if total_cost > 0 else 0
    avg_win = sum(p["realizedPnl"] for p in wins) / len(wins) if wins else 0
    avg_loss = sum(p["realizedPnl"] for p in losses) / len(losses) if losses else 0
    return {
        "count": len(pos_list),
        "wins": len(wins),
        "losses": len(losses),
        "wr": round(wr, 1),
        "roi": round(roi, 1),
        "total_pnl": round(total_pnl, 2),
        "total_cost": round(total_cost, 2),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2)
    }

# ═══════════════════════════════════════════
# 2a: Filter $500+
# ═══════════════════════════════════════════
pos_500 = [p for p in positions if p["cost"] >= 500]
print(f"\n=== 2a: cost >= $500 ({len(pos_500)} positions) ===")

by_range_500 = defaultdict(list)
for p in pos_500:
    by_range_500[get_range_label(p["avgPrice"])].append(p)

results_2a = {}
for _, _, label in RANGES:
    s = calc_stats(by_range_500[label])
    results_2a[label] = s
    print(f"  {label}: {s['count']:3d} pos | WR {s['wr']:5.1f}% | ROI {s['roi']:+7.1f}% | PnL ${s['total_pnl']:>12,.0f} | Cost ${s['total_cost']:>12,.0f}")

total_500 = calc_stats(pos_500)
results_2a["TOTAL"] = total_500
print(f"  TOTAL:    {total_500['count']:3d} pos | WR {total_500['wr']:5.1f}% | ROI {total_500['roi']:+7.1f}% | PnL ${total_500['total_pnl']:>12,.0f} | Cost ${total_500['total_cost']:>12,.0f}")

# ═══════════════════════════════════════════
# 2b: Filter $5000+
# ═══════════════════════════════════════════
pos_5k = [p for p in positions if p["cost"] >= 5000]
print(f"\n=== 2b: cost >= $5000 ({len(pos_5k)} positions) ===")

by_range_5k = defaultdict(list)
for p in pos_5k:
    by_range_5k[get_range_label(p["avgPrice"])].append(p)

results_2b = {}
for _, _, label in RANGES:
    s = calc_stats(by_range_5k[label])
    results_2b[label] = s
    print(f"  {label}: {s['count']:3d} pos | WR {s['wr']:5.1f}% | ROI {s['roi']:+7.1f}% | PnL ${s['total_pnl']:>12,.0f} | Cost ${s['total_cost']:>12,.0f}")

total_5k = calc_stats(pos_5k)
results_2b["TOTAL"] = total_5k
print(f"  TOTAL:    {total_5k['count']:3d} pos | WR {total_5k['wr']:5.1f}% | ROI {total_5k['roi']:+7.1f}% | PnL ${total_5k['total_pnl']:>12,.0f} | Cost ${total_5k['total_cost']:>12,.0f}")

# ═══════════════════════════════════════════
# 2c: Strategy simulation (5K+ only)
# ═══════════════════════════════════════════
print(f"\n=== 2c: Strategy simulation ($5K+ filter, {len(pos_5k)} trades) ===")

def strategy_A(price): return 50

def strategy_B(price): return 50 * (price / 0.50)

def strategy_C(price, target_profit=35):
    if price >= 0.99: return 0
    stake = target_profit / (1/price - 1)
    return max(5, min(stake, 150))

def strategy_D(price):
    if price < 0.15:  return 20
    if price < 0.30:  return 35
    if price < 0.50:  return 50
    if price < 0.70:  return 60
    if price < 0.85:  return 45
    return 25

strategies = {
    "A (fixed $50)": strategy_A,
    "B (proportional)": strategy_B,
    "C (target $35 profit)": strategy_C,
    "D (stepped)": strategy_D,
}

results_2c = {}
for strat_name, strat_fn in strategies.items():
    total_pnl = 0
    total_cost = 0
    wins = 0
    trades = 0
    for p in pos_5k:
        our_cost = strat_fn(p["avgPrice"])
        if our_cost <= 0:
            continue
        trades += 1
        total_cost += our_cost
        if p["win"]:
            our_pnl = our_cost * (1.0 / p["avgPrice"] - 1)
            total_pnl += our_pnl
            wins += 1
        else:
            total_pnl -= our_cost
    wr = wins / trades * 100 if trades > 0 else 0
    roi = total_pnl / total_cost * 100 if total_cost > 0 else 0
    results_2c[strat_name] = {
        "trades": trades,
        "wins": wins,
        "wr": round(wr, 1),
        "total_pnl": round(total_pnl, 2),
        "total_cost": round(total_cost, 2),
        "roi": round(roi, 1)
    }
    print(f"  {strat_name:25s}: {trades} trades | WR {wr:.1f}% | PnL ${total_pnl:>9,.2f} | Invested ${total_cost:>7,.0f} | ROI {roi:+.1f}%")

# ═══════════════════════════════════════════
# 2d: Small vs large comparison + correlation
# ═══════════════════════════════════════════
print(f"\n=== 2d: Small vs Large stakes ===")

pos_mid = [p for p in positions if 500 <= p["cost"] < 5000]
stats_mid = calc_stats(pos_mid)
stats_5k_all = calc_stats(pos_5k)
stats_all = calc_stats(positions)

print(f"  All positions:  {stats_all['count']:3d} | WR {stats_all['wr']:.1f}% | ROI {stats_all['roi']:+.1f}% | PnL ${stats_all['total_pnl']:>10,.0f}")
print(f"  $500-5000:      {stats_mid['count']:3d} | WR {stats_mid['wr']:.1f}% | ROI {stats_mid['roi']:+.1f}% | PnL ${stats_mid['total_pnl']:>10,.0f}")
print(f"  $5000+:         {stats_5k_all['count']:3d} | WR {stats_5k_all['wr']:.1f}% | ROI {stats_5k_all['roi']:+.1f}% | PnL ${stats_5k_all['total_pnl']:>10,.0f}")

# Entry price correlation
wins_5k = [p for p in pos_5k if p["win"]]
losses_5k = [p for p in pos_5k if not p["win"]]
avg_price_win = sum(p["avgPrice"] for p in wins_5k)/len(wins_5k) if wins_5k else 0
avg_price_loss = sum(p["avgPrice"] for p in losses_5k)/len(losses_5k) if losses_5k else 0

print(f"\n  Avg entry price ($5K+):")
print(f"    Wins ({len(wins_5k)}):   {avg_price_win:.4f}")
print(f"    Losses ({len(losses_5k)}): {avg_price_loss:.4f}")

# Top 10 best and worst trades (5K+)
sorted_by_pnl = sorted(pos_5k, key=lambda p: p["realizedPnl"], reverse=True)
print(f"\n  Top 5 best trades ($5K+):")
for p in sorted_by_pnl[:5]:
    print(f"    price={p['avgPrice']:.3f} cost=${p['cost']:,.0f} pnl=${p['realizedPnl']:,.0f} | {p['title'][:60]}")
print(f"\n  Top 5 worst trades ($5K+):")
for p in sorted_by_pnl[-5:]:
    print(f"    price={p['avgPrice']:.3f} cost=${p['cost']:,.0f} pnl=${p['realizedPnl']:,.0f} | {p['title'][:60]}")

# ═══════════════════════════════════════════
# Save results
# ═══════════════════════════════════════════
results = {
    "meta": {
        "wallet": WALLET,
        "total_raw": len(data),
        "valid_positions": len(positions),
        "filter_500_count": len(pos_500),
        "filter_5k_count": len(pos_5k),
    },
    "2a_by_range_500plus": results_2a,
    "2b_by_range_5k_plus": results_2b,
    "2c_strategies_5k_plus": results_2c,
    "2d_comparison": {
        "all": stats_all,
        "500_to_5k": stats_mid,
        "5k_plus": stats_5k_all,
        "avg_entry_price_wins_5k": round(avg_price_win, 4),
        "avg_entry_price_losses_5k": round(avg_price_loss, 4),
    }
}

with open(OUT_FILE, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print(f"\n=== DONE. Results saved to {OUT_FILE} ===")
