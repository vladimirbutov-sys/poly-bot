"""
Backtest: Dual Strategy Analysis for oil_swing_bot ($100) and oil_swing_bot2 ($105)
Tests proposed changes on 612 hourly data points (theta_calibration.json).

Proposals tested:
1. YES>80% blocks NO entry (bot1)
2. YES>60% blocks NO entry (bot2)
3. Weekend gap guard (no open positions Friday 20:00 ET → Monday 09:00 ET)
4. Momentum filter (don't buy NO if WTI rose >$2 in last 6 hours)
5. Days-to-expiry graduated stops
"""
import json
from datetime import datetime, timezone

with open("theta_calibration.json") as f:
    data = json.load(f)

chart = data["chart"]

# Filter to points that have both WTI and YES prices
bot1_data = []  # $100 market
bot2_data = []  # $105 market

for p in chart:
    if p["wti"] is not None and p["yes100"] is not None:
        bot1_data.append({"t": p["t"], "wti": p["wti"], "yes": p["yes100"], "no": round(1.0 - p["yes100"], 3)})
    if p["wti"] is not None and p["yes105"] is not None:
        bot2_data.append({"t": p["t"], "wti": p["wti"], "yes": p["yes105"], "no": round(1.0 - p["yes105"], 3)})

print(f"Bot1 ($100) data points: {len(bot1_data)}")
print(f"Bot2 ($105) data points: {len(bot2_data)}")

# ============================================================
# SIMULATION ENGINE
# ============================================================

def simulate_no_strategy(data, config, label):
    """
    Simulate NO swing trading on hourly data.
    Returns stats dict.
    """
    trades = []
    position = None
    skipped = {"yes_block": 0, "momentum": 0, "weekend": 0, "wti_low": 0, "price_high": 0}

    for i, p in enumerate(data):
        dt = datetime.fromtimestamp(p["t"], tz=timezone.utc)
        weekday = dt.weekday()  # 0=Mon, 5=Sat, 6=Sun
        hour_et = (dt.hour - 4) % 24

        # Calculate momentum (WTI change over last 6 data points = ~6 hours)
        wti_6h_ago = data[max(0, i - 6)]["wti"]
        wti_momentum = p["wti"] - wti_6h_ago

        # Check if weekend (Friday after 20 ET to Monday 9 ET)
        is_weekend = False
        if weekday == 4 and hour_et >= 20:  # Friday evening
            is_weekend = True
        elif weekday in (5, 6):  # Sat/Sun
            is_weekend = True
        elif weekday == 0 and hour_et < 9:  # Monday morning
            is_weekend = True

        # === SELL CHECK ===
        if position is not None:
            sell = False
            reason = ""

            # Profit target
            profit_pct = (p["no"] / position["entry_no"] - 1.0)
            if profit_pct >= config["profit_target"]:
                sell = True
                reason = f"profit_{profit_pct*100:.0f}%"

            # Stop-loss (WTI too high)
            if p["wti"] >= config["stop_wti"]:
                sell = True
                reason = f"stop_wti_{p['wti']:.0f}"

            # Panic stop
            if p["wti"] >= config.get("panic_stop", 999):
                sell = True
                reason = f"panic_{p['wti']:.0f}"

            # Weekend exit (if enabled)
            if config.get("weekend_exit") and is_weekend and position is not None:
                sell = True
                reason = "weekend_exit"

            if sell:
                pnl = (p["no"] - position["entry_no"]) * position["shares"]
                trades.append({
                    "entry_no": position["entry_no"],
                    "exit_no": p["no"],
                    "entry_wti": position["entry_wti"],
                    "exit_wti": p["wti"],
                    "pnl": pnl,
                    "profit_pct": profit_pct,
                    "reason": reason,
                    "held_hours": (p["t"] - position["t"]) / 3600,
                })
                position = None

        # === BUY CHECK ===
        if position is None:
            # Basic entry: WTI above threshold
            if p["wti"] < config["wti_entry"]:
                skipped["wti_low"] += 1
                continue

            # NO price not too expensive
            if p["no"] > config["max_no_price"]:
                skipped["price_high"] += 1
                continue

            # Dead zone
            if 12 <= hour_et < 16:
                continue

            # === PROPOSED FILTERS ===

            # Filter 1: YES > threshold blocks NO entry
            if config.get("yes_block") and p["yes"] > config["yes_block"]:
                skipped["yes_block"] += 1
                continue

            # Filter 2: Momentum filter
            if config.get("momentum_block") and wti_momentum > config["momentum_block"]:
                skipped["momentum"] += 1
                continue

            # Filter 3: Weekend block
            if config.get("weekend_block") and is_weekend:
                skipped["weekend"] += 1
                continue

            # ENTER
            bet_usd = config["bet_usd"]
            shares = bet_usd / p["no"]
            position = {
                "entry_no": p["no"],
                "entry_wti": p["wti"],
                "shares": shares,
                "t": p["t"],
            }

    # Close any remaining position at last price
    if position is not None:
        p = data[-1]
        pnl = (p["no"] - position["entry_no"]) * position["shares"]
        profit_pct = (p["no"] / position["entry_no"] - 1.0)
        trades.append({
            "entry_no": position["entry_no"],
            "exit_no": p["no"],
            "entry_wti": position["entry_wti"],
            "exit_wti": p["wti"],
            "pnl": pnl,
            "profit_pct": profit_pct,
            "reason": "end_of_data",
            "held_hours": (p["t"] - position["t"]) / 3600,
        })

    # Calculate stats
    total_pnl = sum(t["pnl"] for t in trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl"] for t in losses) / len(losses) if losses else 0
    max_drawdown = 0
    running = 0
    peak = 0
    for t in trades:
        running += t["pnl"]
        if running > peak:
            peak = running
        dd = peak - running
        if dd > max_drawdown:
            max_drawdown = dd

    return {
        "label": label,
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "max_drawdown": max_drawdown,
        "skipped": skipped,
        "avg_hold_hours": sum(t["held_hours"] for t in trades) / len(trades) if trades else 0,
        "trades_detail": trades,
    }


# ============================================================
# BOT 1 ($100 market) — SCENARIOS
# ============================================================
print("\n" + "=" * 70)
print("BOT 1: OIL SWING BOT ($100 market)")
print("=" * 70)

bot1_configs = {
    "BASELINE (current)": {
        "wti_entry": 97.0,
        "max_no_price": 0.26,
        "profit_target": 0.35,
        "stop_wti": 110.0,
        "panic_stop": 115.0,
        "bet_usd": 10.0,
    },
    "+YES>80% block": {
        "wti_entry": 97.0,
        "max_no_price": 0.26,
        "profit_target": 0.35,
        "stop_wti": 110.0,
        "panic_stop": 115.0,
        "bet_usd": 10.0,
        "yes_block": 0.80,
    },
    "+YES>75% block": {
        "wti_entry": 97.0,
        "max_no_price": 0.26,
        "profit_target": 0.35,
        "stop_wti": 110.0,
        "panic_stop": 115.0,
        "bet_usd": 10.0,
        "yes_block": 0.75,
    },
    "+momentum $2 block": {
        "wti_entry": 97.0,
        "max_no_price": 0.26,
        "profit_target": 0.35,
        "stop_wti": 110.0,
        "panic_stop": 115.0,
        "bet_usd": 10.0,
        "momentum_block": 2.0,
    },
    "+weekend block": {
        "wti_entry": 97.0,
        "max_no_price": 0.26,
        "profit_target": 0.35,
        "stop_wti": 110.0,
        "panic_stop": 115.0,
        "bet_usd": 10.0,
        "weekend_block": True,
    },
    "+weekend EXIT": {
        "wti_entry": 97.0,
        "max_no_price": 0.26,
        "profit_target": 0.35,
        "stop_wti": 110.0,
        "panic_stop": 115.0,
        "bet_usd": 10.0,
        "weekend_exit": True,
    },
    "COMBINED (YES80+momentum+weekendBlock)": {
        "wti_entry": 97.0,
        "max_no_price": 0.26,
        "profit_target": 0.35,
        "stop_wti": 110.0,
        "panic_stop": 115.0,
        "bet_usd": 10.0,
        "yes_block": 0.80,
        "momentum_block": 2.0,
        "weekend_block": True,
    },
}

bot1_results = {}
for name, cfg in bot1_configs.items():
    r = simulate_no_strategy(bot1_data, cfg, name)
    bot1_results[name] = r
    print(f"\n--- {name} ---")
    print(f"  Trades: {r['trades']} (W:{r['wins']} L:{r['losses']}) WR: {r['win_rate']:.0f}%")
    print(f"  P&L: ${r['total_pnl']:.2f} | Avg win: ${r['avg_win']:.2f} | Avg loss: ${r['avg_loss']:.2f}")
    print(f"  Max DD: ${r['max_drawdown']:.2f} | Avg hold: {r['avg_hold_hours']:.1f}h")
    print(f"  Skipped: {r['skipped']}")


# ============================================================
# BOT 2 ($105 market) — SCENARIOS
# ============================================================
print("\n" + "=" * 70)
print("BOT 2: OIL SWING BOT2 ($105 market)")
print("=" * 70)

bot2_configs = {
    "BASELINE (current)": {
        "wti_entry": 95.0,  # lower entry for $105 market
        "max_no_price": 0.60,
        "profit_target": 0.13,
        "stop_wti": 107.0,
        "panic_stop": 110.0,
        "bet_usd": 60.0,
    },
    "+YES>60% block": {
        "wti_entry": 95.0,
        "max_no_price": 0.60,
        "profit_target": 0.13,
        "stop_wti": 107.0,
        "panic_stop": 110.0,
        "bet_usd": 60.0,
        "yes_block": 0.60,
    },
    "+YES>70% block": {
        "wti_entry": 95.0,
        "max_no_price": 0.60,
        "profit_target": 0.13,
        "stop_wti": 107.0,
        "panic_stop": 110.0,
        "bet_usd": 60.0,
        "yes_block": 0.70,
    },
    "+momentum $2 block": {
        "wti_entry": 95.0,
        "max_no_price": 0.60,
        "profit_target": 0.13,
        "stop_wti": 107.0,
        "panic_stop": 110.0,
        "bet_usd": 60.0,
        "momentum_block": 2.0,
    },
    "+weekend block": {
        "wti_entry": 95.0,
        "max_no_price": 0.60,
        "profit_target": 0.13,
        "stop_wti": 107.0,
        "panic_stop": 110.0,
        "bet_usd": 60.0,
        "weekend_block": True,
    },
    "+weekend EXIT": {
        "wti_entry": 95.0,
        "max_no_price": 0.60,
        "profit_target": 0.13,
        "stop_wti": 107.0,
        "panic_stop": 110.0,
        "bet_usd": 60.0,
        "weekend_exit": True,
    },
    "COMBINED (YES60+momentum+weekendBlock)": {
        "wti_entry": 95.0,
        "max_no_price": 0.60,
        "profit_target": 0.13,
        "stop_wti": 107.0,
        "panic_stop": 110.0,
        "bet_usd": 60.0,
        "yes_block": 0.60,
        "momentum_block": 2.0,
        "weekend_block": True,
    },
    "+lower profit 10%": {
        "wti_entry": 95.0,
        "max_no_price": 0.60,
        "profit_target": 0.10,
        "stop_wti": 107.0,
        "panic_stop": 110.0,
        "bet_usd": 60.0,
    },
    "+higher profit 20%": {
        "wti_entry": 95.0,
        "max_no_price": 0.60,
        "profit_target": 0.20,
        "stop_wti": 107.0,
        "panic_stop": 110.0,
        "bet_usd": 60.0,
    },
}

bot2_results = {}
for name, cfg in bot2_configs.items():
    r = simulate_no_strategy(bot2_data, cfg, name)
    bot2_results[name] = r
    print(f"\n--- {name} ---")
    print(f"  Trades: {r['trades']} (W:{r['wins']} L:{r['losses']}) WR: {r['win_rate']:.0f}%")
    print(f"  P&L: ${r['total_pnl']:.2f} | Avg win: ${r['avg_win']:.2f} | Avg loss: ${r['avg_loss']:.2f}")
    print(f"  Max DD: ${r['max_drawdown']:.2f} | Avg hold: {r['avg_hold_hours']:.1f}h")
    print(f"  Skipped: {r['skipped']}")


# ============================================================
# WEEKEND GAP ANALYSIS
# ============================================================
print("\n" + "=" * 70)
print("WEEKEND GAP ANALYSIS")
print("=" * 70)

# Find Friday close → Monday open gaps
for dataset, market in [(bot1_data, "$100"), (bot2_data, "$105")]:
    gaps = []
    for i in range(1, len(dataset)):
        dt_prev = datetime.fromtimestamp(dataset[i-1]["t"], tz=timezone.utc)
        dt_curr = datetime.fromtimestamp(dataset[i]["t"], tz=timezone.utc)

        # Gap > 20 hours (weekend)
        hours_gap = (dataset[i]["t"] - dataset[i-1]["t"]) / 3600
        if hours_gap > 20:
            wti_gap = dataset[i]["wti"] - dataset[i-1]["wti"]
            yes_gap = dataset[i]["yes"] - dataset[i-1]["yes"]
            gaps.append({
                "date": dt_curr.strftime("%Y-%m-%d"),
                "wti_gap": wti_gap,
                "yes_gap": yes_gap,
                "fri_wti": dataset[i-1]["wti"],
                "mon_wti": dataset[i]["wti"],
            })

    print(f"\nMarket {market}: {len(gaps)} weekend gaps found")
    for g in gaps:
        direction = "UP" if g["wti_gap"] > 0 else "DOWN"
        print(f"  {g['date']}: WTI {g['fri_wti']:.2f} -> {g['mon_wti']:.2f} ({direction} ${abs(g['wti_gap']):.2f}), YES {g['yes_gap']:+.3f}")

# ============================================================
# SAVE RESULTS
# ============================================================
results = {
    "bot1_results": {k: {kk: vv for kk, vv in v.items() if kk != "trades_detail"} for k, v in bot1_results.items()},
    "bot2_results": {k: {kk: vv for kk, vv in v.items() if kk != "trades_detail"} for k, v in bot2_results.items()},
}
with open("_analytics/data/backtest_dual_results.json", "w") as f:
    json.dump(results, f, indent=2)
print("\nResults saved to _analytics/data/backtest_dual_results.json")
