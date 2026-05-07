"""
Backtest: graduated stop-loss based on hours to CME settlement (14:30 ET).
Key insight: intraday price != settlement price. The further from settlement,
the more noise. Stop should be LOOSER far from settlement, TIGHTER close to it.

Compares:
1. FLAT $110 (current)
2. GRADUATED: $108 far / $104 medium / $101 close / $115 panic
3. GRADUATED + no YES ceasefire far from settlement
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _analytics.backtest import load_chart, align_data, DEADLINE

SETTLEMENT_HOUR_ET = 14  # 14:30 ET


def hours_to_settlement(dt):
    """How many hours until next 14:30 ET from this UTC datetime."""
    et_hour = (dt.hour - 5) % 24  # UTC to ET (EST, approx)
    if et_hour < SETTLEMENT_HOUR_ET:
        return SETTLEMENT_HOUR_ET - et_hour
    else:
        return (24 - et_hour) + SETTLEMENT_HOUR_ET


def get_no_stop_graduated(dt):
    """Graduated NO stop based on hours to settlement."""
    h = hours_to_settlement(dt)
    if h <= 1:
        return 101.0   # <1h: intraday ≈ settlement, tight
    elif h <= 4:
        return 103.0   # 1-4h: US session, reliable
    elif h <= 8:
        return 105.0   # 4-8h: Europe, stabilizing
    else:
        return 108.0   # >8h: far from settlement, loose


def get_ceasefire_stop_graduated(dt):
    """Graduated YES ceasefire stop based on hours to settlement."""
    h = hours_to_settlement(dt)
    if h <= 1:
        return 88.0    # <1h: tight, intraday ≈ settlement
    elif h <= 4:
        return 86.0    # 1-4h: medium
    elif h <= 8:
        return 84.0    # 4-8h: loose
    else:
        return 82.0    # >8h: very loose (night noise)


PANIC_NO_STOP = 115.0    # Absolute panic, always
PANIC_CEASEFIRE = 75.0    # Absolute ceasefire panic


def close_pos(pos, price, reason, dt):
    revenue = pos["shares"] * price
    pnl = revenue - pos["cost"]
    pos.update({"status": "closed", "exit_price": price, "pnl": pnl,
                "reason": reason, "closed_at": dt, "revenue": revenue})
    return revenue, pnl


def run_backtest(data, cfg):
    cash = 300.0
    positions = []
    history = []
    yes_steps = set()
    no_steps = set()
    peak_equity = 300.0
    max_dd = 0.0
    stop_mode = cfg["stop_mode"]  # "flat" or "graduated"

    for pt in data:
        wti, yes_p, no_p, dt = pt["wti"], pt["yes"], pt["no"], pt["dt"]
        hour_et = (dt.hour - 5) % 24
        days_left = max(0, (DEADLINE - dt).days)

        # Theta
        theta = 1.0
        for min_d, mult in cfg["theta_scaling"]:
            if days_left >= min_d:
                theta = mult
                break

        # Equity
        mtm = sum(p["shares"] * (yes_p if p["side"] == "YES" else no_p) for p in positions)
        equity = cash + mtm
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
        if dd > max_dd:
            max_dd = dd

        # Deadline
        if days_left <= 0:
            for pos in list(positions):
                price = yes_p if pos["side"] == "YES" else no_p
                rev, _ = close_pos(pos, price, "deadline", dt)
                cash += rev
                history.append(pos)
            positions.clear()
            continue

        # === STOP LOGIC ===
        if stop_mode == "flat":
            no_stop = cfg.get("stop_no", 110.0)
            ceasefire_stop = cfg.get("stop_ceasefire", 87.0)
        else:
            no_stop = get_no_stop_graduated(dt)
            ceasefire_stop = get_ceasefire_stop_graduated(dt)

        # Ceasefire stop (YES)
        if wti < ceasefire_stop or wti < PANIC_CEASEFIRE:
            for pos in [p for p in positions if p["side"] == "YES"]:
                rev, _ = close_pos(pos, yes_p, f"ceasefire_{ceasefire_stop:.0f}", dt)
                cash += rev
                history.append(pos)
            positions = [p for p in positions if p["status"] == "open"]

        # NO stop
        if wti > no_stop or wti > PANIC_NO_STOP:
            stop_used = min(no_stop, PANIC_NO_STOP) if wti > PANIC_NO_STOP else no_stop
            for pos in [p for p in positions if p["side"] == "NO"]:
                rev, _ = close_pos(pos, no_p, f"no_stop_{stop_used:.0f}", dt)
                cash += rev
                history.append(pos)
            positions = [p for p in positions if p["status"] == "open"]

        # Sell NO when WTI drops
        if wti <= 91.0:
            for pos in [p for p in positions if p["side"] == "NO"]:
                rev, _ = close_pos(pos, no_p, "wti_below_91", dt)
                cash += rev
                history.append(pos)
            positions = [p for p in positions if p["status"] == "open"]

        # YES profit target
        for pos in [p for p in positions if p["side"] == "YES"]:
            gain = (yes_p - pos["entry_price"]) / pos["entry_price"]
            if gain >= 0.21:
                rev, _ = close_pos(pos, yes_p, f"yes_profit_{gain:.0%}", dt)
                cash += rev
                history.append(pos)
        positions = [p for p in positions if p["status"] == "open"]

        # NO profit targets
        for pos in [p for p in positions if p["side"] == "NO"]:
            gain = (no_p - pos["entry_price"]) / pos["entry_price"]
            if gain >= pos.get("profit_target", 0.35):
                rev, _ = close_pos(pos, no_p, f"no_profit_{gain:.0%}", dt)
                cash += rev
                history.append(pos)
        positions = [p for p in positions if p["status"] == "open"]

        # Dead zone
        if 14 <= hour_et < 15:
            continue
        if theta <= 0:
            continue

        invested = sum(p["cost"] for p in positions)
        free = cash

        # Buy YES
        for si, (trigger, bet_usd) in enumerate(cfg["yes_entry"]):
            if si in yes_steps:
                continue
            if wti <= trigger and yes_p <= 0.59 and free >= 5:
                actual = min(bet_usd * theta, free * 0.25, free)
                if actual < 5:
                    continue
                shares = actual / yes_p
                if shares < 5:
                    continue
                cash -= actual
                positions.append({
                    "side": "YES", "entry_price": yes_p, "shares": shares,
                    "cost": actual, "entry_wti": wti, "step": si,
                    "opened_at": dt, "status": "open",
                })
                free -= actual
                yes_steps.add(si)

        # Buy NO
        for si, (trigger, bet_usd, pt_target) in enumerate(cfg["no_entry"]):
            if si in no_steps:
                continue
            if wti >= trigger and no_p <= 0.26 and free >= 5:
                actual = min(bet_usd * theta, free * 0.25, free)
                if actual < 5:
                    continue
                shares = actual / no_p
                if shares < 5:
                    continue
                cash -= actual
                positions.append({
                    "side": "NO", "entry_price": no_p, "shares": shares,
                    "cost": actual, "entry_wti": wti, "step": si,
                    "profit_target": pt_target,
                    "opened_at": dt, "status": "open",
                })
                free -= actual
                no_steps.add(si)

        # Reset steps
        if wti <= 93.0:
            no_steps.clear()
        if wti >= 97.0:
            yes_steps.clear()

    # Close remaining
    if data:
        last = data[-1]
        for pos in list(positions):
            price = last["yes"] if pos["side"] == "YES" else last["no"]
            rev, _ = close_pos(pos, price, "end_of_data", last["dt"])
            cash += rev
            history.append(pos)

    return history, cash, max_dd


def analyze(name, history, final_cash, max_dd):
    total_pnl = sum(t["pnl"] for t in history)
    yes_t = [t for t in history if t["side"] == "YES"]
    no_t = [t for t in history if t["side"] == "NO"]
    wins = [t for t in history if t["pnl"] > 0]
    stops = [t for t in history if "stop" in t.get("reason", "") or "ceasefire" in t.get("reason", "")]

    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")
    print(f"  Trades: {len(history)} | Wins: {len(wins)} ({len(wins)/max(len(history),1)*100:.0f}%)")
    print(f"  YES P&L: ${sum(t['pnl'] for t in yes_t):+.2f} | NO P&L: ${sum(t['pnl'] for t in no_t):+.2f}")
    print(f"  Total P&L: ${total_pnl:+.2f} | Final: ${final_cash:.2f} | Max DD: {max_dd:.1%}")

    if stops:
        print(f"\n  Stop-loss events:")
        for t in stops:
            d = t.get("opened_at", "")
            cd = t.get("closed_at", "")
            if hasattr(cd, "strftime"):
                cd = cd.strftime("%m-%d %H:%M UTC")
            print(f"    {t['side']:>3} | cost ${t['cost']:.2f} | pnl ${t['pnl']:+.2f} | {t['reason']} | closed {cd}")

    return {
        "pnl": total_pnl, "cash": final_cash, "dd": max_dd,
        "trades": len(history), "wins": len(wins),
        "yes_pnl": sum(t["pnl"] for t in yes_t),
        "no_pnl": sum(t["pnl"] for t in no_t),
        "stop_losses": len(stops),
        "stop_pnl": sum(t["pnl"] for t in stops),
    }


BASE = {
    "yes_entry": [(92.0, 5), (90.0, 5), (88.0, 15)],
    "no_entry": [(97.0, 10, 0.35), (98.0, 10, 0.69), (99.0, 20, 1.04)],
    "theta_scaling": [(10, 1.0), (7, 0.80), (5, 0.60), (3, 0.30), (0, 0.0)],
}

CONFIGS = [
    {**BASE, "name": "FLAT $110 (current)", "stop_mode": "flat", "stop_no": 110.0, "stop_ceasefire": 87.0},
    {**BASE, "name": "GRADUATED (settlement-aware)", "stop_mode": "graduated"},
    {**BASE, "name": "FLAT $105 (tighter)", "stop_mode": "flat", "stop_no": 105.0, "stop_ceasefire": 87.0},
    {**BASE, "name": "FLAT $115 (looser)", "stop_mode": "flat", "stop_no": 115.0, "stop_ceasefire": 87.0},
]

if __name__ == "__main__":
    print("Loading data...")
    chart = load_chart()
    data = align_data(chart)
    print(f"  {len(data)} points, WTI ${min(d['wti'] for d in data):.2f}-${max(d['wti'] for d in data):.2f}")

    # Show when WTI > 100 happened and hours to settlement
    print("\n  WTI > $100 events (intraday):")
    for pt in data:
        if pt["wti"] > 100:
            h = hours_to_settlement(pt["dt"])
            et_h = (pt["dt"].hour - 5) % 24
            print(f"    {pt['dt'].strftime('%m-%d %H:%M UTC')} | WTI ${pt['wti']:.2f} | {h}h to settlement | {et_h}:00 ET")

    results = {}
    for cfg in CONFIGS:
        h, cash, dd = run_backtest(data, cfg)
        results[cfg["name"]] = analyze(cfg["name"], h, cash, dd)

    # Comparison
    print(f"\n{'='*70}")
    print(f"  COMPARISON")
    print(f"{'='*70}")
    print(f"  {'':25} {'FLAT $110':>12} {'GRADUATED':>12} {'FLAT $105':>12} {'FLAT $115':>12}")
    print(f"  {'-'*65}")
    for key, label in [
        ("pnl", "Total P&L"),
        ("yes_pnl", "YES P&L"),
        ("no_pnl", "NO P&L"),
        ("dd", "Max DD"),
        ("stop_losses", "Stop events"),
        ("stop_pnl", "Stop P&L"),
    ]:
        row = f"  {label:25}"
        for cfg in CONFIGS:
            v = results[cfg["name"]][key]
            if key == "dd":
                row += f" {v:>11.1%}"
            elif key in ("stop_losses",):
                row += f" {v:>12}"
            else:
                row += f" ${v:>+10.2f}"
        print(row)
