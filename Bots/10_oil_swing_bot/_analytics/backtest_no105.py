"""
Backtest: NO $105 theta decay strategy.
Hypothesis: Buy NO on "WTI $105 by end of March" market.
As time runs out and WTI stays below $105, NO price rises.

Tests:
1. Correlation WTI <-> YES $105 / NO $105
2. Theta decay: does NO $105 trend upward as deadline approaches?
3. Simulated strategy: buy NO, sell at profit target or hold to expiry
"""
import json
import os
import math
from datetime import datetime, timezone, timedelta

BOT_DIR = os.path.join(os.path.dirname(__file__), "..")
CALIB_FILE = os.path.join(BOT_DIR, "theta_calibration.json")
DEADLINE = datetime(2026, 3, 31, 23, 59, tzinfo=timezone.utc)


def load_data():
    """Load chart data from theta_calibration.json."""
    with open(CALIB_FILE, "r") as f:
        data = json.load(f)
    return data["chart"]


def align_data(chart):
    """Align WTI + YES $105 into common time series."""
    last_wti = None
    last_yes105 = None
    aligned = []

    for pt in chart:
        if pt["wti"] is not None:
            last_wti = pt["wti"]
        if pt.get("yes105") is not None:
            last_yes105 = pt["yes105"]

        if last_wti is not None and last_yes105 is not None:
            dt = datetime.fromtimestamp(pt["t"], tz=timezone.utc)
            no105 = round(1.0 - last_yes105, 4)
            aligned.append({
                "t": pt["t"],
                "dt": dt,
                "wti": last_wti,
                "yes105": last_yes105,
                "no105": no105,
                "days_left": max(0, (DEADLINE - dt).total_seconds() / 86400),
            })
    return aligned


def pearson(xs, ys):
    n = len(xs)
    if n < 5:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n)
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n)
    if sx == 0 or sy == 0:
        return None
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / n
    return round(cov / (sx * sy), 4)


def linear_regression(xs, ys):
    """Simple linear regression. Returns slope, intercept, r_squared."""
    n = len(xs)
    if n < 3:
        return None, None, None
    mx = sum(xs) / n
    my = sum(ys) / n
    ss_xx = sum((x - mx) ** 2 for x in xs)
    ss_xy = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    if ss_xx == 0:
        return None, None, None
    slope = ss_xy / ss_xx
    intercept = my - slope * mx
    ss_yy = sum((y - my) ** 2 for y in ys)
    r_sq = (ss_xy ** 2) / (ss_xx * ss_yy) if ss_yy > 0 else 0
    return round(slope, 6), round(intercept, 4), round(r_sq, 4)


# =========================================================
#  ANALYSIS 1: Correlation WTI <-> YES/NO $105
# =========================================================

def analyze_correlation(data):
    print("\n" + "=" * 70)
    print("  ANALYSIS 1: Correlation WTI <-> YES/NO $105")
    print("=" * 70)

    # Price level correlation
    wti_prices = [d["wti"] for d in data]
    yes105_prices = [d["yes105"] for d in data]
    no105_prices = [d["no105"] for d in data]

    r_wti_yes = pearson(wti_prices, yes105_prices)
    r_wti_no = pearson(wti_prices, no105_prices)

    print(f"\n  Level correlation (full period, {len(data)} points):")
    print(f"    WTI <-> YES $105: r = {r_wti_yes}")
    print(f"    WTI <-> NO  $105: r = {r_wti_no}")

    # Change correlation (hourly changes)
    wti_changes = [data[i]["wti"] - data[i-1]["wti"] for i in range(1, len(data))
                   if data[i]["t"] - data[i-1]["t"] <= 7200]
    yes_changes = [data[i]["yes105"] - data[i-1]["yes105"] for i in range(1, len(data))
                   if data[i]["t"] - data[i-1]["t"] <= 7200]
    no_changes = [data[i]["no105"] - data[i-1]["no105"] for i in range(1, len(data))
                  if data[i]["t"] - data[i-1]["t"] <= 7200]

    r_chg_yes = pearson(wti_changes, yes_changes[:len(wti_changes)])
    r_chg_no = pearson(wti_changes, no_changes[:len(wti_changes)])

    print(f"\n  Change correlation (hourly delta, {len(wti_changes)} changes):")
    print(f"    dWTI <-> dYES $105: r = {r_chg_yes}")
    print(f"    dWTI <-> dNO  $105: r = {r_chg_no}")

    # Sensitivity: how much does YES $105 move per $1 WTI?
    if wti_changes and yes_changes:
        n = min(len(wti_changes), len(yes_changes))
        slope, intercept, r2 = linear_regression(wti_changes[:n], yes_changes[:n])
        if slope is not None:
            print(f"\n  Sensitivity: dYES $105 = {slope:.4f} * dWTI + {intercept:.4f}")
            print(f"    -> $1 WTI move = {slope * 100:.2f} pp YES $105 change")
            print(f"    -> R2 = {r2}")

    # By WTI zone
    print(f"\n  YES $105 by WTI zone:")
    zones = [(85, 90), (90, 93), (93, 96), (96, 99), (99, 102), (102, 110)]
    for lo, hi in zones:
        pts = [d for d in data if lo <= d["wti"] < hi]
        if pts:
            avg_yes = sum(d["yes105"] for d in pts) / len(pts)
            avg_no = sum(d["no105"] for d in pts) / len(pts)
            min_yes = min(d["yes105"] for d in pts)
            max_yes = max(d["yes105"] for d in pts)
            print(f"    WTI ${lo}-${hi}: YES avg={avg_yes:.3f} [{min_yes:.3f}-{max_yes:.3f}] | "
                  f"NO avg={avg_no:.3f} | {len(pts)} pts")

    return r_wti_yes, r_wti_no, r_chg_yes


# =========================================================
#  ANALYSIS 2: Theta decay — does NO $105 trend up over time?
# =========================================================

def analyze_theta_decay(data):
    print("\n" + "=" * 70)
    print("  ANALYSIS 2: Theta Decay — NO $105 trend over time")
    print("=" * 70)

    # Group by days_left buckets
    buckets = {}
    for d in data:
        bucket = int(d["days_left"])
        if bucket not in buckets:
            buckets[bucket] = {"no105": [], "yes105": [], "wti": []}
        buckets[bucket]["no105"].append(d["no105"])
        buckets[bucket]["yes105"].append(d["yes105"])
        buckets[bucket]["wti"].append(d["wti"])

    print(f"\n  {'Days left':>10} | {'Avg NO $105':>11} | {'Min-Max NO':>14} | "
          f"{'Avg YES $105':>12} | {'Avg WTI':>8} | {'Points':>6}")
    print(f"  {'-' * 75}")

    sorted_days = sorted(buckets.keys(), reverse=True)
    prev_no = None
    daily_changes = []

    for day in sorted_days:
        b = buckets[day]
        avg_no = sum(b["no105"]) / len(b["no105"])
        min_no = min(b["no105"])
        max_no = max(b["no105"])
        avg_yes = sum(b["yes105"]) / len(b["yes105"])
        avg_wti = sum(b["wti"]) / len(b["wti"])

        delta_str = ""
        if prev_no is not None:
            delta = avg_no - prev_no
            daily_changes.append(delta)
            delta_str = f" ({delta:+.3f})"

        print(f"  {day:>10} | {avg_no:>11.4f}{delta_str:>0} | "
              f"{min_no:.3f}-{max_no:.3f} | {avg_yes:>12.4f} | ${avg_wti:>7.2f} | {len(b['no105']):>6}")
        prev_no = avg_no

    # Overall trend
    days_left_list = [d["days_left"] for d in data]
    no105_list = [d["no105"] for d in data]
    slope, intercept, r2 = linear_regression(days_left_list, no105_list)

    print(f"\n  Trend regression: NO $105 = {slope:.6f} * days_left + {intercept:.4f}")
    print(f"  R2 = {r2}")
    if slope:
        print(f"  -> Each day closer to deadline: NO $105 changes by {-slope * 100:.2f} pp")
        print(f"  -> {'CONFIRMS' if slope < 0 else 'CONTRADICTS'} hypothesis "
              f"(NO should increase = negative slope on days_left)")

    # But need to control for WTI!
    # Partial analysis: within same WTI zone, does time help NO?
    print(f"\n  Time effect WITHIN WTI $93-$97 zone (controlling for WTI):")
    zone_data = [d for d in data if 93 <= d["wti"] <= 97]
    if len(zone_data) >= 10:
        z_days = [d["days_left"] for d in zone_data]
        z_no = [d["no105"] for d in zone_data]
        z_slope, z_int, z_r2 = linear_regression(z_days, z_no)
        print(f"    Regression: NO = {z_slope:.6f} * days_left + {z_int:.4f} (R2={z_r2})")
        if z_slope:
            print(f"    -> Each day closer: NO changes by {-z_slope * 100:.2f} pp")
            print(f"    -> {'CONFIRMS' if z_slope < 0 else 'CONTRADICTS'} theta decay hypothesis")
    else:
        print(f"    Not enough data in zone ({len(zone_data)} pts)")

    return slope, r2, daily_changes


# =========================================================
#  ANALYSIS 3: Backtest — buy NO $105, sell at profit or expiry
# =========================================================

def run_strategy_backtest(data):
    print("\n" + "=" * 70)
    print("  ANALYSIS 3: Strategy Backtest — Buy NO $105")
    print("=" * 70)

    strategies = [
        {
            "name": "SIMPLE: Buy NO once, hold to expiry",
            "entry_rule": "first_available",
            "exit_rule": "hold_to_end",
            "bet_usd": 20,
        },
        {
            "name": "THETA PLAY: Buy NO when YES > 60%, sell when YES < 45%",
            "entry_rule": "yes_above_60",
            "exit_rule": "yes_below_45",
            "bet_usd": 20,
        },
        {
            "name": "DIP BUY: Buy NO when WTI >= $97, sell when WTI <= $93",
            "entry_rule": "wti_above_97",
            "exit_rule": "wti_below_93",
            "bet_usd": 10,
        },
        {
            "name": "TIME DECAY: Buy NO at days_left <= 20, target +15%",
            "entry_rule": "days_lte_20",
            "exit_rule": "profit_15pct",
            "bet_usd": 15,
        },
        {
            "name": "AGGRESSIVE: Buy NO at any dip (YES > 55%), sell +10%",
            "entry_rule": "yes_above_55",
            "exit_rule": "profit_10pct",
            "bet_usd": 10,
        },
    ]

    all_results = []

    for strat in strategies:
        cash = 300.0
        positions = []
        closed = []
        max_positions = 3  # max concurrent

        for i, pt in enumerate(data):
            wti = pt["wti"]
            no_p = pt["no105"]
            yes_p = pt["yes105"]
            days = pt["days_left"]
            dt = pt["dt"]

            # --- Check exits ---
            for pos in list(positions):
                should_exit = False
                reason = ""
                gain = (no_p - pos["entry"]) / pos["entry"] if pos["entry"] > 0 else 0

                if strat["exit_rule"] == "hold_to_end":
                    if i == len(data) - 1 or days <= 0:
                        should_exit = True
                        reason = "expiry"
                elif strat["exit_rule"] == "yes_below_45":
                    if yes_p < 0.45:
                        should_exit = True
                        reason = f"yes={yes_p:.2f}<0.45"
                    elif i == len(data) - 1:
                        should_exit = True
                        reason = "end_data"
                elif strat["exit_rule"] == "wti_below_93":
                    if wti <= 93:
                        should_exit = True
                        reason = f"wti=${wti:.0f}<=93"
                    elif i == len(data) - 1:
                        should_exit = True
                        reason = "end_data"
                elif strat["exit_rule"] == "profit_15pct":
                    if gain >= 0.15:
                        should_exit = True
                        reason = f"profit_{gain:.0%}"
                    elif i == len(data) - 1:
                        should_exit = True
                        reason = "end_data"
                elif strat["exit_rule"] == "profit_10pct":
                    if gain >= 0.10:
                        should_exit = True
                        reason = f"profit_{gain:.0%}"
                    elif i == len(data) - 1:
                        should_exit = True
                        reason = "end_data"

                # Stop-loss: WTI > $105 = total loss risk
                if wti >= 105:
                    should_exit = True
                    reason = "stop_wti_105"

                if should_exit:
                    revenue = pos["shares"] * no_p
                    pnl = revenue - pos["cost"]
                    pos.update({
                        "exit": no_p, "revenue": revenue, "pnl": pnl,
                        "reason": reason, "exit_dt": dt,
                        "exit_wti": wti, "exit_days": days,
                    })
                    cash += revenue
                    closed.append(pos)
                    positions.remove(pos)

            # --- Check entry ---
            if len(positions) < max_positions and no_p > 0.01:
                should_enter = False

                if strat["entry_rule"] == "first_available":
                    if not positions and not closed:
                        should_enter = True
                elif strat["entry_rule"] == "yes_above_60":
                    if yes_p > 0.60 and not positions:
                        should_enter = True
                elif strat["entry_rule"] == "wti_above_97":
                    if wti >= 97 and not positions:
                        should_enter = True
                elif strat["entry_rule"] == "days_lte_20":
                    if days <= 20 and not positions:
                        should_enter = True
                elif strat["entry_rule"] == "yes_above_55":
                    if yes_p > 0.55 and not positions:
                        should_enter = True

                if should_enter:
                    bet = min(strat["bet_usd"], cash * 0.25)
                    if bet >= 5:
                        shares = bet / no_p
                        cash -= bet
                        positions.append({
                            "entry": no_p, "shares": shares, "cost": bet,
                            "entry_dt": dt, "entry_wti": wti, "entry_days": days,
                            "status": "open",
                        })

        # Close remaining
        if positions and data:
            last = data[-1]
            for pos in positions:
                revenue = pos["shares"] * last["no105"]
                pnl = revenue - pos["cost"]
                pos.update({
                    "exit": last["no105"], "revenue": revenue, "pnl": pnl,
                    "reason": "end_of_data", "exit_dt": last["dt"],
                })
                cash += revenue
                closed.append(pos)

        # --- Report ---
        total_pnl = sum(t["pnl"] for t in closed)
        wins = [t for t in closed if t["pnl"] > 0]
        losses = [t for t in closed if t["pnl"] <= 0]

        print(f"\n  Strategy: {strat['name']}")
        print(f"  Trades: {len(closed)} | Wins: {len(wins)} | Losses: {len(losses)} | "
              f"Win rate: {len(wins)/max(len(closed),1)*100:.0f}%")
        print(f"  Total P&L: ${total_pnl:+.2f} | Final cash: ${cash:.2f}")

        if closed:
            avg_gain = sum((t["exit"] - t["entry"]) / t["entry"] for t in closed) / len(closed)
            avg_hold_hours = sum(
                (t["exit_dt"] - t["entry_dt"]).total_seconds() / 3600
                for t in closed if "entry_dt" in t and "exit_dt" in t
            ) / len(closed)
            print(f"  Avg gain: {avg_gain:+.1%} | Avg hold: {avg_hold_hours:.0f}h")

            print(f"\n  {'#':>3} {'Entry':>6} {'Exit':>6} {'Cost':>7} {'P&L':>8} {'%':>7} "
                  f"{'WTI in':>7} {'WTI out':>7} {'Days':>5} {'Reason'}")
            for i, t in enumerate(closed, 1):
                gain = (t["exit"] - t["entry"]) / t["entry"] * 100 if t["entry"] > 0 else 0
                e_wti = t.get("entry_wti", 0)
                x_wti = t.get("exit_wti", 0)
                days_e = t.get("entry_days", 0)
                print(f"  {i:3d} {t['entry']:6.3f} {t['exit']:6.3f} ${t['cost']:6.2f} "
                      f"${t['pnl']:+7.2f} {gain:+6.1f}% ${e_wti:6.1f} ${x_wti:6.1f} "
                      f"{days_e:5.0f} {t['reason']}")

        all_results.append({
            "name": strat["name"],
            "trades": len(closed),
            "wins": len(wins),
            "pnl": total_pnl,
            "cash": cash,
        })

    # --- Summary table ---
    print(f"\n{'=' * 70}")
    print(f"  STRATEGY COMPARISON")
    print(f"{'=' * 70}")
    print(f"  {'Strategy':<55} {'Trades':>6} {'Wins':>5} {'P&L':>8}")
    print(f"  {'-' * 78}")
    for r in all_results:
        print(f"  {r['name']:<55} {r['trades']:>6} {r['wins']:>5} ${r['pnl']:>+7.2f}")

    return all_results


# =========================================================
#  ANALYSIS 4: Mathematical model — NO $105 fair value
# =========================================================

def analyze_fair_value(data):
    print("\n" + "=" * 70)
    print("  ANALYSIS 4: Mathematical Fair Value of NO $105")
    print("=" * 70)

    # Current conditions (last data point)
    last = data[-1]
    wti = last["wti"]
    days = last["days_left"]
    no_price = last["no105"]
    yes_price = last["yes105"]

    print(f"\n  Current state:")
    print(f"    WTI: ${wti:.2f}")
    print(f"    Days to deadline: {days:.1f}")
    print(f"    YES $105: {yes_price:.3f} ({yes_price*100:.1f}%)")
    print(f"    NO  $105: {no_price:.3f} ({no_price*100:.1f}%)")

    # How far is WTI from $105?
    gap = 105 - wti
    print(f"\n  Gap to $105: ${gap:.2f}")

    # Historical WTI volatility (from our data)
    wti_prices = [d["wti"] for d in data]
    hourly_returns = [(wti_prices[i] - wti_prices[i-1]) / wti_prices[i-1]
                      for i in range(1, len(wti_prices))
                      if data[i]["t"] - data[i-1]["t"] <= 7200]

    if hourly_returns:
        hourly_vol = math.sqrt(sum(r ** 2 for r in hourly_returns) / len(hourly_returns))
        daily_vol = hourly_vol * math.sqrt(24)
        annual_vol = daily_vol * math.sqrt(252)

        print(f"\n  Measured volatility:")
        print(f"    Hourly: {hourly_vol*100:.3f}%")
        print(f"    Daily:  {daily_vol*100:.2f}%")
        print(f"    Annual: {annual_vol*100:.1f}%")

        # Probability WTI >= $105 by deadline (simple random walk model)
        sigma_remaining = daily_vol * wti * math.sqrt(days)
        z = gap / sigma_remaining if sigma_remaining > 0 else 999

        # Normal CDF approximation
        def norm_cdf(x):
            return 0.5 * (1 + math.erf(x / math.sqrt(2)))

        p_above_105 = 1 - norm_cdf(z)

        print(f"\n  Random walk model:")
        print(f"    sigma remaining = ${sigma_remaining:.2f}")
        print(f"    z-score to $105 = {z:.2f}")
        print(f"    P(WTI >= $105 by deadline) = {p_above_105:.1%}")
        print(f"    Fair NO $105 = {1 - p_above_105:.3f} ({(1-p_above_105)*100:.1f}%)")
        print(f"    Market NO $105 = {no_price:.3f} ({no_price*100:.1f}%)")

        edge = (1 - p_above_105) - no_price
        print(f"\n    EDGE (fair - market) = {edge:+.3f} ({edge*100:+.1f} pp)")
        if edge > 0.02:
            print(f"    -> NO is UNDERPRICED by ~{edge*100:.0f}pp — BUY signal")
        elif edge < -0.02:
            print(f"    -> NO is OVERPRICED by ~{abs(edge)*100:.0f}pp — no edge")
        else:
            print(f"    -> NO is fairly priced (edge < 2pp)")

        # Theta projection: how will NO behave as days decrease?
        print(f"\n  Theta projection (NO $105 if WTI stays at ${wti:.0f}):")
        for d in [11, 9, 7, 5, 3, 1, 0]:
            sigma_d = daily_vol * wti * math.sqrt(d) if d > 0 else 0
            z_d = gap / sigma_d if sigma_d > 0 else 999
            p_d = 1 - norm_cdf(z_d)
            fair_no = 1 - p_d
            print(f"    {d:>2} days left: P($105) = {p_d:.1%} | Fair NO = {fair_no:.3f} "
                  f"({fair_no*100:.1f}%) | Gain from today: {(fair_no-no_price)/no_price*100:+.1f}%")


# =========================================================
#  ANALYSIS 5: WTI max touched & probability path
# =========================================================

def analyze_wti_extremes(data):
    print("\n" + "=" * 70)
    print("  ANALYSIS 5: WTI extremes & path to $105")
    print("=" * 70)

    wti_prices = [d["wti"] for d in data]
    wti_max = max(wti_prices)
    wti_min = min(wti_prices)
    wti_last = wti_prices[-1]

    print(f"\n  WTI range: ${wti_min:.2f} — ${wti_max:.2f}")
    print(f"  WTI current: ${wti_last:.2f}")
    print(f"  WTI max ever touched: ${wti_max:.2f}")
    print(f"  Gap from max to $105: ${105 - wti_max:.2f}")

    # How many hours was WTI above various thresholds?
    thresholds = [95, 97, 99, 100, 102, 105, 110]
    total_pts = len(data)
    print(f"\n  Time above thresholds ({total_pts} hours total):")
    for thr in thresholds:
        above = sum(1 for d in data if d["wti"] >= thr)
        pct = above / total_pts * 100
        print(f"    WTI >= ${thr}: {above} hours ({pct:.1f}%)")

    # Did WTI ever touch $105?
    touched_105 = any(d["wti"] >= 105 for d in data)
    print(f"\n  WTI touched $105: {'YES' if touched_105 else 'NO'}")
    if touched_105:
        first_touch = next(d for d in data if d["wti"] >= 105)
        print(f"  First touch: {first_touch['dt'].strftime('%Y-%m-%d %H:%M')} at ${first_touch['wti']:.2f}")
        print(f"  YES $105 at that moment: {first_touch['yes105']:.3f}")
        print(f"  NO $105 at that moment: {first_touch['no105']:.3f}")


# =========================================================
#  MAIN
# =========================================================

if __name__ == "__main__":
    print("Loading theta_calibration.json...")
    chart = load_data()
    data = align_data(chart)

    if not data:
        print("ERROR: No aligned data found (yes105 is null)")
        exit(1)

    print(f"  Total aligned points: {len(data)}")
    print(f"  Period: {data[0]['dt'].strftime('%Y-%m-%d %H:%M')} to "
          f"{data[-1]['dt'].strftime('%Y-%m-%d %H:%M')}")
    print(f"  WTI range: ${min(d['wti'] for d in data):.2f} - ${max(d['wti'] for d in data):.2f}")
    print(f"  YES $105 range: {min(d['yes105'] for d in data):.3f} - "
          f"{max(d['yes105'] for d in data):.3f}")
    print(f"  NO $105 range: {min(d['no105'] for d in data):.3f} - "
          f"{max(d['no105'] for d in data):.3f}")

    analyze_correlation(data)
    theta_slope, theta_r2, _ = analyze_theta_decay(data)
    results = run_strategy_backtest(data)
    analyze_fair_value(data)
    analyze_wti_extremes(data)

    # === FINAL VERDICT ===
    print("\n" + "=" * 70)
    print("  FINAL VERDICT: NO $105 Strategy")
    print("=" * 70)

    best = max(results, key=lambda r: r["pnl"])
    worst = min(results, key=lambda r: r["pnl"])

    print(f"\n  Best strategy:  {best['name']}")
    print(f"    P&L: ${best['pnl']:+.2f} | Trades: {best['trades']} | Wins: {best['wins']}")
    print(f"\n  Worst strategy: {worst['name']}")
    print(f"    P&L: ${worst['pnl']:+.2f} | Trades: {worst['trades']} | Wins: {worst['wins']}")

    if theta_slope and theta_slope < 0:
        print(f"\n  Theta decay CONFIRMED: NO gains {-theta_slope*100:.2f} pp per day closer to deadline")
    else:
        print(f"\n  Theta decay NOT confirmed in raw data (confounded by WTI moves)")

    print(f"\n  Recommendation based on backtest will be saved to report.")
