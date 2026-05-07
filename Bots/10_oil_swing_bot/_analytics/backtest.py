"""
Backtest Oil Swing Bot on historical data from theta_calibration.json.
Compares: original config, current (post-Smart-Tuner), and recommended.
"""
import json
import os
from datetime import datetime, timezone

BOT_DIR = os.path.join(os.path.dirname(__file__), "..")
CALIB_FILE = os.path.join(BOT_DIR, "theta_calibration.json")
DEADLINE = datetime(2026, 3, 26, tzinfo=timezone.utc)


def load_chart():
    with open(CALIB_FILE, "r") as f:
        data = json.load(f)
    return data["chart"]


def align_data(chart):
    last_wti = None
    last_yes = None
    aligned = []
    for pt in chart:
        if pt["wti"] is not None:
            last_wti = pt["wti"]
        if pt["yes100"] is not None:
            last_yes = pt["yes100"]
        if last_wti is not None and last_yes is not None:
            aligned.append({
                "t": pt["t"],
                "dt": datetime.fromtimestamp(pt["t"], tz=timezone.utc),
                "wti": last_wti,
                "yes": last_yes,
                "no": round(1.0 - last_yes, 4),
            })
    return aligned


# === CONFIGS ===

ORIGINAL = {
    "name": "ORIGINAL (pre-SmartTuner)",
    "yes_entry": [(92.0, 5), (90.0, 5), (88.0, 15)],
    "yes_exit": [(97.0, 0.3), (99.0, 0.5), (100.0, 1.0)],
    "no_entry": [(97.0, 5, 0.35), (98.0, 5, 0.69), (99.0, 10, 1.04)],
    "yes_profit_target": 0.21,
    "max_yes_price": 0.59,
    "max_no_price": 0.26,
    "wti_sell_no_below": 91.0,
    "stop_ceasefire": 87.0,
    "theta_scaling": [(10, 1.0), (7, 0.80), (5, 0.60), (3, 0.30), (0, 0.0)],
}

CURRENT = {
    "name": "CURRENT (post-SmartTuner)",
    "yes_entry": [(92.0, 5), (90.0, 10), (88.0, 30)],
    "yes_exit": [(97.0, 0.3), (98.0, 0.5), (100.0, 1.0)],
    "no_entry": [(97.0, 10, 0.24), (98.0, 10, 0.48), (98.0, 15, 0.71)],
    "yes_profit_target": 0.19,
    "max_yes_price": 0.56,
    "max_no_price": 0.26,
    "wti_sell_no_below": 91.0,
    "stop_ceasefire": 87.0,
    "theta_scaling": [(10, 1.0), (7, 0.80), (5, 0.60), (3, 0.30), (0, 0.0)],
}

RECOMMENDED = {
    "name": "RECOMMENDED (quant audit)",
    "yes_entry": [(94.0, 5), (93.0, 10), (92.0, 20)],
    "yes_exit": [(97.0, 0.3), (98.0, 0.5), (100.0, 1.0)],
    "no_entry": [(97.0, 10, 0.24), (98.0, 10, 0.48), (99.0, 15, 0.71)],
    "yes_profit_target": 0.13,
    "max_yes_price": 0.62,
    "max_no_price": 0.26,
    "wti_sell_no_below": 91.0,
    "stop_ceasefire": 87.0,
    "theta_scaling": [(10, 1.0), (7, 0.60), (5, 0.40), (3, 0.15), (0, 0.0)],
}


# === BACKTEST ENGINE ===

def get_theta(days_left, table):
    for min_d, mult in table:
        if days_left >= min_d:
            return mult
    return 0.0


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

    for pt in data:
        wti, yes_p, no_p, dt = pt["wti"], pt["yes"], pt["no"], pt["dt"]
        hour_et = (dt.hour - 4) % 24
        days_left = max(0, (DEADLINE - dt).days)
        theta = get_theta(days_left, cfg["theta_scaling"])

        # --- Equity tracking ---
        invested = sum(p["cost"] for p in positions)
        # Mark-to-market: approximate value of open positions
        mtm = sum(p["shares"] * (yes_p if p["side"] == "YES" else no_p) for p in positions)
        equity = cash + mtm
        if equity > peak_equity:
            peak_equity = equity
        dd = (peak_equity - equity) / peak_equity if peak_equity > 0 else 0
        if dd > max_dd:
            max_dd = dd

        # --- Deadline ---
        if days_left <= 0:
            for pos in list(positions):
                price = yes_p if pos["side"] == "YES" else no_p
                rev, _ = close_pos(pos, price, "deadline", dt)
                cash += rev
                history.append(pos)
            positions.clear()
            continue

        # --- Stop: ceasefire ---
        if wti < cfg["stop_ceasefire"]:
            for pos in [p for p in positions if p["side"] == "YES"]:
                rev, _ = close_pos(pos, yes_p, "ceasefire_stop", dt)
                cash += rev
                history.append(pos)
            positions = [p for p in positions if p["status"] == "open"]

        # --- Stop: NO WTI > 110 ---
        if wti > 110.0:
            for pos in [p for p in positions if p["side"] == "NO"]:
                rev, _ = close_pos(pos, no_p, "no_wti_stop", dt)
                cash += rev
                history.append(pos)
            positions = [p for p in positions if p["status"] == "open"]

        # --- Sell NO when WTI drops ---
        if wti <= cfg["wti_sell_no_below"]:
            for pos in [p for p in positions if p["side"] == "NO"]:
                rev, _ = close_pos(pos, no_p, "wti_below_91", dt)
                cash += rev
                history.append(pos)
            positions = [p for p in positions if p["status"] == "open"]

        # --- Sell YES by profit target ---
        for pos in [p for p in positions if p["side"] == "YES"]:
            gain = (yes_p - pos["entry_price"]) / pos["entry_price"]
            target = cfg["yes_profit_target"]
            if gain >= target:
                rev, _ = close_pos(pos, yes_p, f"yes_profit_{gain:.0%}", dt)
                cash += rev
                history.append(pos)
        positions = [p for p in positions if p["status"] == "open"]

        # --- Sell NO by profit targets ---
        for pos in [p for p in positions if p["side"] == "NO"]:
            gain = (no_p - pos["entry_price"]) / pos["entry_price"]
            adj_target = pos.get("profit_target", 0.35)
            if gain >= adj_target:
                rev, _ = close_pos(pos, no_p, f"no_profit_{gain:.0%}", dt)
                cash += rev
                history.append(pos)
        positions = [p for p in positions if p["status"] == "open"]

        # --- Dead zone: no buys ---
        if 12 <= hour_et < 16:
            continue

        # --- No entries at theta=0 ---
        if theta <= 0:
            continue

        invested = sum(p["cost"] for p in positions)
        free = cash - 0  # cash is actual free money

        # --- Buy YES ---
        for si, (trigger, bet_usd) in enumerate(cfg["yes_entry"]):
            if si in yes_steps:
                continue
            if wti <= trigger and yes_p <= cfg["max_yes_price"] and free >= 5:
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

        # --- Buy NO ---
        for si, (trigger, bet_usd, pt_target) in enumerate(cfg["no_entry"]):
            if si in no_steps:
                continue
            if wti >= trigger and no_p <= cfg["max_no_price"] and free >= 5:
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

        # --- Reset steps on WTI reversal ---
        if wti <= 93.0:
            no_steps.clear()
        if wti >= 97.0:
            yes_steps.clear()

    # Close remaining at last price
    if data:
        last = data[-1]
        for pos in list(positions):
            price = last["yes"] if pos["side"] == "YES" else last["no"]
            rev, _ = close_pos(pos, price, "end_of_data", last["dt"])
            cash += rev
            history.append(pos)

    return history, cash, max_dd


def analyze(name, history, final_cash, max_dd):
    wins = [t for t in history if t["pnl"] > 0]
    losses = [t for t in history if t["pnl"] <= 0]
    total_pnl = sum(t["pnl"] for t in history)
    yes_t = [t for t in history if t["side"] == "YES"]
    no_t = [t for t in history if t["side"] == "NO"]

    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"{'='*70}")
    print(f"  Trades: {len(history)} | Wins: {len(wins)} ({len(wins)/max(len(history),1)*100:.0f}%) | Losses: {len(losses)}")
    print(f"  YES: {len(yes_t)} trades | NO: {len(no_t)} trades")
    print(f"  Total P&L:  ${total_pnl:+.2f}")
    print(f"  Final cash:  ${final_cash:.2f}")
    print(f"  Return:      {(final_cash - 300) / 300 * 100:+.1f}%")
    print(f"  Max drawdown: {max_dd:.1%}")

    if wins:
        avg_w = sum(t["pnl"] for t in wins) / len(wins)
        print(f"  Avg win:  ${avg_w:.2f}")
    if losses:
        avg_l = sum(t["pnl"] for t in losses) / len(losses)
        print(f"  Avg loss: ${avg_l:.2f}")

    # By side
    for side, trades in [("YES", yes_t), ("NO", no_t)]:
        if not trades:
            continue
        s_pnl = sum(t["pnl"] for t in trades)
        s_w = len([t for t in trades if t["pnl"] > 0])
        print(f"\n  [{side}] {len(trades)} trades, {s_w} wins, P&L ${s_pnl:+.2f}")
        by_step = {}
        for t in trades:
            s = t.get("step", -1)
            by_step.setdefault(s, {"n": 0, "w": 0, "pnl": 0})
            by_step[s]["n"] += 1
            by_step[s]["pnl"] += t["pnl"]
            if t["pnl"] > 0:
                by_step[s]["w"] += 1
        for s in sorted(by_step):
            d = by_step[s]
            print(f"    Step {s}: {d['n']} trades, {d['w']} wins, ${d['pnl']:+.2f}")

    # Trade log
    print(f"\n  Trade log:")
    print(f"  {'#':>3} {'Side':>4} {'Entry':>6} {'Exit':>6} {'Cost':>7} {'P&L':>8} {'%':>7} {'Reason':<22} {'Date'}")
    sorted_h = sorted(history, key=lambda x: x.get("opened_at", x.get("closed_at")))
    for i, t in enumerate(sorted_h, 1):
        e = t.get("entry_price", 0)
        x = t.get("exit_price", 0)
        c = t.get("cost", 0)
        p = t.get("pnl", 0)
        g = ((x - e) / e * 100) if e > 0 else 0
        r = t.get("reason", "?")
        d = t.get("opened_at", "")
        if hasattr(d, "strftime"):
            d = d.strftime("%m-%d %H:%M")
        print(f"  {i:3d} {t['side']:>4} {e:6.3f} {x:6.3f} ${c:6.2f} ${p:+7.2f} {g:+6.1f}% {r:<22} {d}")

    return {
        "trades": len(history), "wins": len(wins), "losses": len(losses),
        "pnl": total_pnl, "cash": final_cash, "dd": max_dd,
        "yes": len(yes_t), "no": len(no_t),
        "yes_pnl": sum(t["pnl"] for t in yes_t),
        "no_pnl": sum(t["pnl"] for t in no_t),
    }


if __name__ == "__main__":
    print("Loading theta_calibration.json...")
    chart = load_chart()
    data = align_data(chart)
    print(f"  Chart points: {len(chart)}, aligned: {len(data)}")
    print(f"  Period: {data[0]['dt'].strftime('%Y-%m-%d %H:%M')} to {data[-1]['dt'].strftime('%Y-%m-%d %H:%M')}")
    print(f"  WTI range: ${min(d['wti'] for d in data):.2f} - ${max(d['wti'] for d in data):.2f}")
    print(f"  YES range: {min(d['yes'] for d in data):.3f} - {max(d['yes'] for d in data):.3f}")

    results = {}
    for cfg in [ORIGINAL, CURRENT, RECOMMENDED]:
        h, cash, dd = run_backtest(data, cfg)
        results[cfg["name"]] = analyze(cfg["name"], h, cash, dd)

    # Comparison table
    print(f"\n{'='*70}")
    print(f"  COMPARISON TABLE")
    print(f"{'='*70}")
    header = f"  {'Metric':<20}"
    for cfg in [ORIGINAL, CURRENT, RECOMMENDED]:
        label = cfg["name"].split("(")[0].strip()
        header += f" {label:>14}"
    print(header)
    print(f"  {'-'*62}")

    for key, label in [
        ("trades", "Trades"), ("wins", "Wins"), ("losses", "Losses"),
        ("yes", "YES trades"), ("no", "NO trades"),
        ("yes_pnl", "YES P&L"), ("no_pnl", "NO P&L"),
        ("pnl", "Total P&L"), ("cash", "Final cash"),
        ("dd", "Max drawdown"),
    ]:
        row = f"  {label:<20}"
        for cfg in [ORIGINAL, CURRENT, RECOMMENDED]:
            v = results[cfg["name"]][key]
            if key in ("pnl", "yes_pnl", "no_pnl"):
                row += f" ${v:>+12.2f}"
            elif key == "cash":
                row += f" ${v:>12.2f}"
            elif key == "dd":
                row += f" {v:>13.1%}"
            else:
                row += f" {v:>14}"
        print(row)
