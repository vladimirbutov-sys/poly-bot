"""
Backtest: YES $100 entry threshold comparison.
Question: WTI is $94 — should we buy YES at $94 instead of waiting for $92?

Compares YES entry steps:
1. Current: $92 / $90 / $88
2. Raised-1: $94 / $92 / $90
3. Raised-2: $95 / $93 / $91
4. Raised-3: $96 / $94 / $92
5. Aggressive: $96 / $94 / $92 with bigger bets
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from backtest import load_chart, align_data, run_backtest, analyze, DEADLINE

# Base config matching CURRENT bot settings (theta removed, graduated stops)
BASE = {
    "yes_exit": [(97.0, 0.3), (99.0, 0.5), (100.0, 1.0)],
    "no_entry": [(97.0, 10, 0.35), (98.0, 10, 0.69), (99.0, 20, 1.04)],
    "yes_profit_target": 0.21,
    "max_yes_price": 0.59,
    "max_no_price": 0.26,
    "wti_sell_no_below": 91.0,
    "stop_ceasefire": 87.0,
    "theta_scaling": [(2, 1.0), (0, 0.0)],  # current: no scaling, block at 0-2 days
}

CONFIGS = [
    {
        **BASE,
        "name": "CURRENT: $92/$90/$88",
        "yes_entry": [(92.0, 5), (90.0, 5), (88.0, 15)],
    },
    {
        **BASE,
        "name": "RAISED: $94/$92/$90",
        "yes_entry": [(94.0, 5), (92.0, 5), (90.0, 15)],
    },
    {
        **BASE,
        "name": "RAISED: $95/$93/$91",
        "yes_entry": [(95.0, 5), (93.0, 5), (91.0, 15)],
    },
    {
        **BASE,
        "name": "RAISED: $96/$94/$92",
        "yes_entry": [(96.0, 5), (94.0, 5), (92.0, 15)],
    },
    {
        **BASE,
        "name": "AGGRESSIVE: $96/$94/$92 big",
        "yes_entry": [(96.0, 10), (94.0, 10), (92.0, 20)],
    },
    {
        **BASE,
        "name": "MAX YES PRICE 0.75",
        "yes_entry": [(94.0, 5), (92.0, 5), (90.0, 15)],
        "max_yes_price": 0.75,
    },
]


if __name__ == "__main__":
    print("Loading data...")
    chart = load_chart()
    data = align_data(chart)
    print(f"  {len(data)} points, WTI ${min(d['wti'] for d in data):.2f}-${max(d['wti'] for d in data):.2f}")
    print(f"  YES $100: {min(d['yes'] for d in data):.3f}-{max(d['yes'] for d in data):.3f}")

    # Show WTI distribution
    wti_vals = [d["wti"] for d in data]
    for level in [96, 95, 94, 93, 92, 91, 90]:
        count = sum(1 for w in wti_vals if w <= level)
        pct = count / len(wti_vals) * 100
        print(f"  WTI <= ${level}: {count} points ({pct:.1f}%)")

    # Show YES price when WTI is at different levels
    print("\n  YES $100 price at different WTI levels:")
    for level in [96, 95, 94, 93, 92, 91, 90]:
        pts = [d for d in data if abs(d["wti"] - level) < 1.0]
        if pts:
            avg_yes = sum(p["yes"] for p in pts) / len(pts)
            print(f"    WTI ~${level}: YES avg = {avg_yes:.3f} ({avg_yes*100:.1f}%)")

    results = {}
    for cfg in CONFIGS:
        h, cash, dd = run_backtest(data, cfg)
        results[cfg["name"]] = analyze(cfg["name"], h, cash, dd)

    # Comparison
    print(f"\n{'='*90}")
    print(f"  YES ENTRY THRESHOLD COMPARISON")
    print(f"{'='*90}")
    print(f"  {'Config':<30} {'Trades':>7} {'YES':>5} {'NO':>4} {'Win%':>6} {'YES P&L':>10} {'NO P&L':>10} {'Total':>10} {'MaxDD':>7}")
    print(f"  {'-'*87}")
    for cfg in CONFIGS:
        r = results[cfg["name"]]
        wr = r["wins"] / max(r["trades"], 1) * 100
        print(f"  {cfg['name']:<30} {r['trades']:>7} {r['yes']:>5} {r['no']:>4} {wr:>5.0f}% ${r['yes_pnl']:>+8.2f} ${r['no_pnl']:>+8.2f} ${r['pnl']:>+8.2f} {r['dd']:>6.1%}")
