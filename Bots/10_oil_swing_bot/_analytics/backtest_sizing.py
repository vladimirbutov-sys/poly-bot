"""
Backtest: are current NO bet sizes too small?
Compare 4 NO sizing configs with same YES ($5/$5/$15).
Uses historical data from theta_calibration.json.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _analytics.backtest import load_chart, align_data, run_backtest, analyze, DEADLINE

# Base config (all share same structure except NO bet sizes)
BASE = {
    "yes_entry": [(92.0, 5), (90.0, 5), (88.0, 15)],
    "yes_exit": [(97.0, 0.3), (99.0, 0.5), (100.0, 1.0)],
    "yes_profit_target": 0.21,
    "max_yes_price": 0.59,
    "max_no_price": 0.26,
    "wti_sell_no_below": 91.0,
    "stop_ceasefire": 87.0,
    "theta_scaling": [(10, 1.0), (7, 0.80), (5, 0.60), (3, 0.30), (0, 0.0)],
}

# 4 NO sizing configs to compare
CONFIGS = [
    {
        **BASE,
        "name": "CURRENT ($5/$5/$10)",
        "no_entry": [(97.0, 5, 0.35), (98.0, 5, 0.69), (99.0, 10, 1.04)],
    },
    {
        **BASE,
        "name": "MEDIUM ($10/$10/$20)",
        "no_entry": [(97.0, 10, 0.35), (98.0, 10, 0.69), (99.0, 20, 1.04)],
    },
    {
        **BASE,
        "name": "LARGE ($15/$15/$30)",
        "no_entry": [(97.0, 15, 0.35), (98.0, 15, 0.69), (99.0, 30, 1.04)],
    },
    {
        **BASE,
        "name": "AGGRESSIVE ($20/$20/$40)",
        "no_entry": [(97.0, 20, 0.35), (98.0, 20, 0.69), (99.0, 40, 1.04)],
    },
]

# Also test: what if YES is $0 (no YES at all, only NO)?
CONFIGS.append({
    **BASE,
    "name": "NO-ONLY ($10/$10/$20, no YES)",
    "yes_entry": [],  # no YES trades at all
    "no_entry": [(97.0, 10, 0.35), (98.0, 10, 0.69), (99.0, 20, 1.04)],
})

# Also test bankroll-relative sizing: 3%/3%/7% of $341
bal = 341
CONFIGS.append({
    **BASE,
    "name": f"BANKROLL-REL (3%/3%/7% of ${bal})",
    "no_entry": [
        (97.0, round(bal * 0.03), 0.35),
        (98.0, round(bal * 0.03), 0.69),
        (99.0, round(bal * 0.07), 1.04),
    ],
})

if __name__ == "__main__":
    print("Loading data...")
    chart = load_chart()
    data = align_data(chart)
    print(f"  {len(data)} aligned points")
    print(f"  WTI: ${min(d['wti'] for d in data):.2f} - ${max(d['wti'] for d in data):.2f}")
    print()

    results = {}
    for cfg in CONFIGS:
        h, cash, dd = run_backtest(data, cfg)
        results[cfg["name"]] = analyze(cfg["name"], h, cash, dd)

    # Comparison
    print(f"\n{'='*90}")
    print(f"  BET SIZING COMPARISON")
    print(f"{'='*90}")

    header = f"  {'Metric':<22}"
    for cfg in CONFIGS:
        label = cfg["name"].split("(")[0].strip()
        header += f" {label:>12}"
    print(header)
    print(f"  {'-'*80}")

    for key, label in [
        ("trades", "Trades"),
        ("wins", "Wins"),
        ("yes_pnl", "YES P&L"),
        ("no_pnl", "NO P&L"),
        ("pnl", "Total P&L"),
        ("cash", "Final cash"),
        ("dd", "Max drawdown"),
    ]:
        row = f"  {label:<22}"
        for cfg in CONFIGS:
            v = results[cfg["name"]][key]
            if key in ("pnl", "yes_pnl", "no_pnl"):
                row += f" ${v:>+10.2f}"
            elif key == "cash":
                row += f" ${v:>10.2f}"
            elif key == "dd":
                row += f" {v:>11.1%}"
            else:
                row += f" {v:>12}"
        print(row)

    # ROI comparison
    print(f"\n  {'ROI':<22}", end="")
    for cfg in CONFIGS:
        v = results[cfg["name"]]["pnl"]
        roi = v / 300 * 100
        print(f" {roi:>+11.1f}%", end="")
    print()

    # Risk-adjusted return (P&L / max_dd)
    print(f"  {'P&L / MaxDD':<22}", end="")
    for cfg in CONFIGS:
        pnl = results[cfg["name"]]["pnl"]
        dd = results[cfg["name"]]["dd"]
        ratio = pnl / (dd * 300) if dd > 0 else 0
        print(f" {ratio:>12.2f}", end="")
    print()

    # NO exposure as % of bankroll
    print(f"\n  {'NO max exposure':<22}", end="")
    for cfg in CONFIGS:
        total = sum(s for _, s, _ in cfg["no_entry"])
        pct = total / 300 * 100
        print(f" ${total:>5} ({pct:.0f}%)", end="")
    print()
