"""
Backtest: Stop-Loss Rule (Change 4a) on Denizz's full trading history.

Stop-loss thresholds by entry tier:
  2-15c  → -60%
  15-50c → -50%
  50-82c → -45%
  82-99c → -40%

Usage: python _backtest_stoploss.py [--limit N]
  --limit N  = process only first N positions (default 50, 0 = all)
"""

import json
import time
import sys
import os
import requests
from collections import defaultdict
from datetime import datetime

# ── Settings ──────────────────────────────────────────────────────────
LIMIT = 50  # default; override with --limit
for i, arg in enumerate(sys.argv):
    if arg == "--limit" and i + 1 < len(sys.argv):
        LIMIT = int(sys.argv[i + 1])

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "_analytics", "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "_analytics")

TRADES_FILE = os.path.join(DATA_DIR, "denizz_trades_ALL.json")
POSITIONS_FILE = os.path.join(DATA_DIR, "denizz_positions_ALL.json")
RESOLUTIONS_FILE = os.path.join(DATA_DIR, "denizz_resolutions.json")

PRICE_API = "https://clob.polymarket.com/prices-history?market={token_id}&interval=max&fidelity=60"

# Stop-loss tiers: (min_price, max_price, stop_loss_pct)
TIERS = [
    (0.02, 0.15, 0.60, "2-15c"),
    (0.15, 0.70, 0.60, "15-70c"),
    (0.70, 0.82, 0.45, "70-82c"),
    (0.82, 0.99, 0.35, "82-99c"),
]


def get_tier(avg_price):
    """Return (stop_loss_pct, tier_name) for a given avg entry price."""
    for lo, hi, sl, name in TIERS:
        if lo <= avg_price < hi:
            return sl, name
    # Edge cases
    if avg_price < 0.02:
        return 0.60, "2-15c"  # lump with lowest
    if avg_price >= 0.99:
        return 0.40, "82-99c"  # lump with highest
    return None, None


def load_data():
    with open(TRADES_FILE, "r", encoding="utf-8") as f:
        trades = json.load(f)
    with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
        positions = json.load(f)
    with open(RESOLUTIONS_FILE, "r", encoding="utf-8") as f:
        resolutions = json.load(f)
    return trades, positions, resolutions


def reconstruct_positions(trades):
    """Group trades by (conditionId, asset) and compute avg buy price."""
    grouped = defaultdict(lambda: {
        "buys": [], "sells": [],
        "total_bought_usd": 0, "total_bought_shares": 0,
        "total_sold_usd": 0, "total_sold_shares": 0,
        "title": "", "asset": "", "conditionId": "",
        "outcome": "", "first_buy_ts": None,
    })

    for t in trades:
        key = (t["conditionId"], t["asset"])
        g = grouped[key]
        g["title"] = t.get("title", "")
        g["asset"] = t["asset"]
        g["conditionId"] = t["conditionId"]
        g["outcome"] = t.get("outcome", "")

        # Track last trade timestamp for sorting (recent = more likely to have API data)
        if "last_trade_ts" not in g or t["timestamp"] > g.get("last_trade_ts", 0):
            g["last_trade_ts"] = t["timestamp"]

        if t["side"] == "BUY":
            cost = t["size"] * t["price"]
            g["buys"].append(t)
            g["total_bought_usd"] += cost
            g["total_bought_shares"] += t["size"]
            if g["first_buy_ts"] is None or t["timestamp"] < g["first_buy_ts"]:
                g["first_buy_ts"] = t["timestamp"]
        else:
            revenue = t["size"] * t["price"]
            g["sells"].append(t)
            g["total_sold_usd"] += revenue
            g["total_sold_shares"] += t["size"]

    # Build position list
    positions = []
    for key, g in grouped.items():
        if g["total_bought_shares"] == 0:
            continue
        avg_buy = g["total_bought_usd"] / g["total_bought_shares"]
        net_shares = g["total_bought_shares"] - g["total_sold_shares"]
        positions.append({
            "conditionId": g["conditionId"],
            "asset": g["asset"],
            "title": g["title"],
            "outcome": g["outcome"],
            "avg_buy_price": avg_buy,
            "total_bought_usd": g["total_bought_usd"],
            "total_bought_shares": g["total_bought_shares"],
            "total_sold_usd": g["total_sold_usd"],
            "total_sold_shares": g["total_sold_shares"],
            "net_shares": net_shares,
            "first_buy_ts": g["first_buy_ts"],
            "last_trade_ts": g.get("last_trade_ts", 0),
        })

    return positions


def fetch_price_history(token_id):
    """Fetch price history from Polymarket API. Returns list of {t, p}."""
    url = PRICE_API.format(token_id=token_id)
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if not data or not isinstance(data, dict):
            return None
        history = data.get("history", [])
        if not history:
            return None
        return history
    except Exception as e:
        print(f"  API error for {token_id[:20]}...: {e}")
        return None


def find_min_price_after(history, first_buy_ts):
    """Find minimum price after first buy timestamp."""
    min_price = None
    for point in history:
        t = point.get("t", 0)
        p = float(point.get("p", 1))
        if t >= first_buy_ts:
            if min_price is None or p < min_price:
                min_price = p
    return min_price


def determine_outcome(pos, resolutions):
    """Determine if position won, lost, or is still open. Returns (status, final_value_per_share)."""
    cid = pos["conditionId"]
    res = resolutions.get(cid)

    if res and res.get("resolved"):
        # Find which token won
        winning_outcome = res.get("winning_outcome", "")
        for tok in res.get("tokens", []):
            if tok.get("token_id") == pos["asset"]:
                if tok.get("winner"):
                    return "won", 1.0
                else:
                    return "lost", 0.0
        # If token not found in resolution tokens, infer from outcome name
        if pos["outcome"] == winning_outcome:
            return "won", 1.0
        else:
            return "lost", 0.0
    else:
        # Open position — we don't know final value, skip or use current price
        return "open", None


def calculate_pnl(pos, final_value_per_share):
    """Calculate actual PnL for a position."""
    # Money spent buying
    total_cost = pos["total_bought_usd"]
    # Money received from sells
    sell_revenue = pos["total_sold_usd"]
    # Value of remaining shares
    remaining_value = pos["net_shares"] * final_value_per_share if pos["net_shares"] > 0 else 0
    pnl = sell_revenue + remaining_value - total_cost
    return pnl


def calculate_stoploss_pnl(pos, sl_pct):
    """Calculate PnL if stop-loss had triggered.

    Stop-loss sells ALL remaining shares at (avg_buy * (1 - sl_pct)).
    But we need to account for any sells that happened BEFORE the stop would trigger.
    For simplicity: assume stop triggers early, so we sell all net_shares at stop price.
    Actually — stop would sell at the stop price level.
    PnL with stop = total_sold_usd (sells before stop) + net_shares * stop_price - total_bought_usd
    """
    stop_price = pos["avg_buy_price"] * (1 - sl_pct)
    # All remaining shares sold at stop price
    sl_revenue = pos["net_shares"] * stop_price if pos["net_shares"] > 0 else 0
    sl_pnl = pos["total_sold_usd"] + sl_revenue - pos["total_bought_usd"]
    return sl_pnl


def run_backtest():
    print("Loading cached data...")
    trades, cached_positions, resolutions = load_data()

    print(f"Trades: {len(trades)}, Cached positions: {len(cached_positions)}, Resolutions: {len(resolutions)}")

    print("Reconstructing positions from trades...")
    positions = reconstruct_positions(trades)
    print(f"Reconstructed {len(positions)} unique positions")

    # Sort by most recent trade first (recent markets more likely to have API data)
    positions.sort(key=lambda p: p["last_trade_ts"], reverse=True)

    # Determine tier for each
    valid_positions = []
    for pos in positions:
        sl_pct, tier = get_tier(pos["avg_buy_price"])
        if tier is None:
            continue
        pos["tier"] = tier
        pos["sl_pct"] = sl_pct
        valid_positions.append(pos)

    print(f"Positions with valid tier: {len(valid_positions)}")

    # Determine outcomes
    for pos in valid_positions:
        status, final_val = determine_outcome(pos, resolutions)
        pos["status"] = status
        pos["final_value_per_share"] = final_val

    # Filter: only resolved positions (we know the outcome)
    resolved = [p for p in valid_positions if p["status"] in ("won", "lost")]
    print(f"Resolved positions: {len(resolved)}")

    # Process all resolved positions, but stop after LIMIT positions WITH price data
    print(f"Processing up to {LIMIT if LIMIT > 0 else 'ALL'} positions with price data (out of {len(resolved)} resolved)")

    # Fetch price history and check stop-loss
    results = []
    positions_with_data = 0
    api_calls = 0
    for i, pos in enumerate(resolved):
        if LIMIT > 0 and positions_with_data >= LIMIT:
            break

        safe_title = pos['title'][:55].encode('ascii', 'replace').decode('ascii')
        print(f"  [{i+1}] {safe_title}... ", end="", flush=True)

        history = fetch_price_history(pos["asset"])
        api_calls += 1
        time.sleep(0.5)

        if not history:
            print("no price data")
            pos["has_price_data"] = False
            continue

        pos["has_price_data"] = True
        positions_with_data += 1
        min_price = find_min_price_after(history, pos["first_buy_ts"])

        if min_price is None:
            print("no prices after entry")
            pos["has_price_data"] = False
            continue

        pos["min_price_after_entry"] = min_price
        drawdown = (pos["avg_buy_price"] - min_price) / pos["avg_buy_price"] if pos["avg_buy_price"] > 0 else 0
        pos["max_drawdown"] = drawdown
        pos["sl_triggered"] = drawdown >= pos["sl_pct"]

        # Calculate PnL
        pos["actual_pnl"] = calculate_pnl(pos, pos["final_value_per_share"])

        if pos["sl_triggered"]:
            pos["sl_pnl"] = calculate_stoploss_pnl(pos, pos["sl_pct"])
            if pos["actual_pnl"] > 0:
                pos["stop_type"] = "false_stop"  # Was profitable, stop would have cut it
                pos["lost_profit"] = pos["actual_pnl"] - pos["sl_pnl"]
            else:
                pos["stop_type"] = "true_stop"  # Was a loss, stop would save money
                pos["saved"] = abs(pos["actual_pnl"]) - abs(pos["sl_pnl"]) if abs(pos["sl_pnl"]) < abs(pos["actual_pnl"]) else 0
                # Actually: saved = actual_loss - sl_loss (both negative, so saved = sl_pnl - actual_pnl)
                pos["saved"] = pos["sl_pnl"] - pos["actual_pnl"]  # sl_pnl is less negative

        results.append(pos)
        print(f"dd={drawdown:.1%} {'STOP' if pos['sl_triggered'] else 'ok'}")

    # ── Analysis ──────────────────────────────────────────────────────
    with_data = [r for r in results if r.get("has_price_data")]
    triggered = [r for r in with_data if r.get("sl_triggered")]
    false_stops = [r for r in triggered if r.get("stop_type") == "false_stop"]
    true_stops = [r for r in triggered if r.get("stop_type") == "true_stop"]

    # ── Table 1: Summary by tier ─────────────────────────────────────
    tier_stats = {}
    for tier_name in ["2-15c", "15-70c", "70-82c", "82-99c"]:
        tier_pos = [r for r in with_data if r["tier"] == tier_name]
        tier_triggered = [r for r in tier_pos if r.get("sl_triggered")]
        tier_false = [r for r in tier_triggered if r.get("stop_type") == "false_stop"]
        tier_true = [r for r in tier_triggered if r.get("stop_type") == "true_stop"]
        pct_false = len(tier_false) / len(tier_triggered) * 100 if tier_triggered else 0
        tier_stats[tier_name] = {
            "total": len(tier_pos),
            "triggered": len(tier_triggered),
            "false_stops": len(tier_false),
            "true_stops": len(tier_true),
            "pct_false": pct_false,
        }

    # ── Generate report ──────────────────────────────────────────────
    report = []
    report.append("# Backtest: Stop-Loss Rule (Change 4a)")
    report.append(f"**Дата:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report.append(f"**Трейдер:** Denizz")
    report.append(f"**Обработано позиций:** {len(with_data)} из {len(resolved)} resolved")
    report.append("")
    report.append("## Правило стоп-лосса")
    report.append("")
    report.append("| Тир входа | Стоп-лосс % |")
    report.append("|---|---|")
    report.append("| 2-15c | -60% |")
    report.append("| 15-70c | -60% |")
    report.append("| 70-82c | -45% |")
    report.append("| 82-99c | -35% |")
    report.append("")

    # Table 1
    report.append("## Таблица 1: Сводка по тирам")
    report.append("")
    report.append("| Тир | Всего позиций | Стоп сработал бы | Из них прибыльные (ложный стоп) | Из них убыточные (верный стоп) | % ложных |")
    report.append("|---|---|---|---|---|---|")
    totals = {"total": 0, "triggered": 0, "false": 0, "true": 0}
    for tier_name in ["2-15c", "15-70c", "70-82c", "82-99c"]:
        s = tier_stats[tier_name]
        report.append(f"| {tier_name} | {s['total']} | {s['triggered']} | {s['false_stops']} | {s['true_stops']} | {s['pct_false']:.0f}% |")
        totals["total"] += s["total"]
        totals["triggered"] += s["triggered"]
        totals["false"] += s["false_stops"]
        totals["true"] += s["true_stops"]
    pct_f = totals["false"] / totals["triggered"] * 100 if totals["triggered"] else 0
    report.append(f"| **ИТОГО** | **{totals['total']}** | **{totals['triggered']}** | **{totals['false']}** | **{totals['true']}** | **{pct_f:.0f}%** |")
    report.append("")

    # Table 2: False stops
    report.append("## Таблица 2: Ложные стопы (прибыльные позиции, которые бы вырезал стоп)")
    report.append("")
    report.append("| Название | Тир | Вход | Мин. цена | Просадка | Итог PnL | Упущенная прибыль |")
    report.append("|---|---|---|---|---|---|---|")
    false_stops_sorted = sorted(false_stops, key=lambda r: r.get("lost_profit", 0), reverse=True)
    for r in false_stops_sorted:
        report.append(f"| {r['title'][:50]} | {r['tier']} | {r['avg_buy_price']:.3f} | {r['min_price_after_entry']:.3f} | {r['max_drawdown']:.1%} | ${r['actual_pnl']:.0f} | ${r.get('lost_profit', 0):.0f} |")
    report.append("")

    # Table 3: True stops
    report.append("## Таблица 3: Верные стопы (убыточные позиции, где стоп спас бы деньги)")
    report.append("")
    report.append("| Название | Тир | Вход | Мин. цена | Итог убыток | Стоп сэкономил бы |")
    report.append("|---|---|---|---|---|---|")
    true_stops_sorted = sorted(true_stops, key=lambda r: r.get("saved", 0), reverse=True)
    for r in true_stops_sorted:
        report.append(f"| {r['title'][:50]} | {r['tier']} | {r['avg_buy_price']:.3f} | {r['min_price_after_entry']:.3f} | ${r['actual_pnl']:.0f} | ${r.get('saved', 0):.0f} |")
    report.append("")

    # Table 4: Net impact
    total_saved = sum(r.get("saved", 0) for r in true_stops)
    total_lost = sum(r.get("lost_profit", 0) for r in false_stops)
    net = total_saved - total_lost

    report.append("## Таблица 4: Чистый эффект")
    report.append("")
    report.append("| Метрика | Значение |")
    report.append("|---|---|")
    report.append(f"| Сэкономлено верными стопами | ${total_saved:,.0f} |")
    report.append(f"| Потеряно из-за ложных стопов | ${total_lost:,.0f} |")
    report.append(f"| **Чистый эффект** | **${net:+,.0f}** |")
    report.append("")

    # Verdict
    report.append("## Вердикт")
    report.append("")
    if net > 0:
        report.append(f"Stop-loss правило 4a **чистый плюс**: экономит ${net:,.0f} больше, чем теряет.")
    elif net < 0:
        report.append(f"Stop-loss правило 4a **чистый минус**: теряет ${abs(net):,.0f} больше, чем экономит.")
    else:
        report.append("Stop-loss правило 4a выходит примерно в ноль.")
    report.append("")

    report.append(f"Ложные стопы: {len(false_stops)} ({pct_f:.0f}% от сработавших)")
    report.append(f"Верные стопы: {len(true_stops)}")
    report.append("")

    if LIMIT > 0:
        report.append(f"> **Примечание:** обработано {len(with_data)} позиций с данными о ценах из {len(resolved)} resolved (API вызовов: {api_calls}). Для полного бэктеста запустите с `--limit 0`.")

    # ── Save report ──────────────────────────────────────────────────
    report_text = "\n".join(report)
    output_path = os.path.join(OUTPUT_DIR, "2026-04-16_stoploss-backtest-full.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nReport saved to: {output_path}")
    print(report_text)


if __name__ == "__main__":
    run_backtest()
