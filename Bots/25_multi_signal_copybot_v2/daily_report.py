"""Daily reports for Multi-Signal Copy-Bot.

Sends three reports per day:
- 09:00 MSK (06:00 UTC): Full detailed report saved to data/ folder
- 13:00 MSK (10:00 UTC): Daily status — portfolio, trades, positions
- 19:00 MSK (16:00 UTC): Evening summary — day results + strategy suggestions

Also supports manual sending:
  python daily_report.py            # send daily report now
  python daily_report.py --evening  # send evening report now
  python daily_report.py --file     # save full report to data/
"""
import os
import sys
import json
import time
import threading
from datetime import datetime, timezone, timedelta

import config
import tracker
import telegram_notify as tg

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _msk_hour():
    """Get current hour in Moscow time (UTC+3)."""
    utc_now = datetime.now(timezone.utc)
    msk = utc_now + timedelta(hours=3)
    return msk.hour


def _msk_date_str():
    """Get current date string in Moscow time."""
    utc_now = datetime.now(timezone.utc)
    msk = utc_now + timedelta(hours=3)
    return msk.strftime("%d.%m.%Y")


def _get_trades_last_24h(data):
    """Get trades (entries + exits) from last 24 hours."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    recent_entries = []
    recent_exits = []

    for key, pos in data.get("positions", {}).items():
        # Check entry time
        ts = pos.get("timestamp", "")
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt >= cutoff:
                    recent_entries.append(pos)
            except Exception:
                pass

        # Check sell times
        for sell in pos.get("sells", []):
            ts = sell.get("timestamp", "")
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if dt >= cutoff:
                        recent_exits.append({**sell, "title": pos.get("title", "?"), "outcome": pos.get("outcome", "")})
                except Exception:
                    pass

    return recent_entries, recent_exits


def _calc_win_rate_last_n_days(data, days=7):
    """Calculate win rate for last N days."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    wins = 0
    total = 0

    for key, pos in data.get("positions", {}).items():
        if pos.get("status") not in ("won", "lost", "sold"):
            continue
        ts = pos.get("timestamp", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                total += 1
                if pos.get("status") == "won" or (pos.get("final_pnl", 0) > 0):
                    wins += 1
        except Exception:
            pass

    return wins / total if total > 0 else 0, total


def _calc_category_stats(data, days=30):
    """Calculate win rate per category for last N days."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days)
    cats = {}

    for key, pos in data.get("positions", {}).items():
        if pos.get("status") not in ("won", "lost", "sold"):
            continue
        cat = pos.get("category", "unknown")
        ts = pos.get("timestamp", "")
        if not ts:
            continue
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff:
                continue
        except Exception:
            continue

        if cat not in cats:
            cats[cat] = {"wins": 0, "total": 0}
        cats[cat]["total"] += 1
        if pos.get("status") == "won" or (pos.get("final_pnl", 0) > 0):
            cats[cat]["wins"] += 1

    result = {}
    for cat, s in cats.items():
        result[cat] = {
            "wr": s["wins"] / s["total"] if s["total"] > 0 else 0,
            "trades": s["total"],
        }
    return result


PLAYER_EMOJI = {"Car": "🚗", "aenews2": "📰", "denizz": "🔵"}


def _player_stats(data, player_name):
    """Count entries/exits/pnl per signal_player."""
    wins = losses = pnl = entries = 0
    for pos in data.get("positions", {}).values():
        if pos.get("signal_player") != player_name:
            continue
        entries += 1
        for sell in pos.get("sells", []):
            p = sell.get("pnl", 0)
            pnl += p
            if p > 0:
                wins += 1
            else:
                losses += 1
        if pos.get("status") == "won":
            wins += 1
            pnl += pos.get("final_pnl", 0)
        elif pos.get("status") == "lost":
            losses += 1
            pnl += pos.get("final_pnl", 0)
    return {"entries": entries, "wins": wins, "losses": losses, "pnl": pnl}


def build_daily_report():
    """Build daily status report (13:00 MSK)."""
    data = tracker.load()
    stats = data["stats"]
    open_positions = tracker.get_open_positions(data)
    open_count = len(open_positions)
    recent_entries, recent_exits = _get_trades_last_24h(data)

    pnl_pct = (stats["total_pnl"] / config.BANKROLL * 100) if config.BANKROLL > 0 else 0
    in_positions = sum(p.get("cost_usd", 0) for p in open_positions.values())

    report = f"📊 MULTI-SIGNAL BOT | ДНЕВНОЙ ОТЧЁТ | {_msk_date_str()}\n\n"

    # Portfolio
    report += "======= ПОРТФЕЛЬ =======\n"
    report += f"Банкролл: ${stats['current_balance'] + in_positions:.2f} ({pnl_pct:+.1f}% от старта)\n"
    report += f"В позициях: ${in_positions:.2f} ({open_count} открытых)\n"
    report += f"Свободно: ${stats['current_balance']:.2f}\n\n"

    # Last 24h
    day_pnl = sum(s.get("pnl", 0) for s in recent_exits)
    wins_24h = sum(1 for s in recent_exits if s.get("pnl", 0) > 0)
    losses_24h = len(recent_exits) - wins_24h

    report += "======= ЗА 24 ЧАСА =======\n"
    report += f"Новых входов: {len(recent_entries)}\n"
    report += f"Выходов: {len(recent_exits)} ({wins_24h} прибыль, {losses_24h} убыток)\n"
    for s in recent_exits[:5]:
        emoji = "✅" if s.get("pnl", 0) > 0 else "❌"
        report += f"  {emoji} {s.get('title', '?')[:38]} → ${s.get('pnl', 0):+.2f}\n"
    if len(recent_exits) > 5:
        report += f"  ... и ещё {len(recent_exits) - 5}\n"
    report += f"P&L за сутки: ${day_pnl:+.2f}\n\n"

    # Per-player stats
    report += "======= ПО ИГРОКАМ (всё время) =======\n"
    for player, emoji in PLAYER_EMOJI.items():
        ps = _player_stats(data, player)
        wr = ps["wins"] / (ps["wins"] + ps["losses"]) if (ps["wins"] + ps["losses"]) > 0 else 0
        report += f"{emoji} {player}: {ps['entries']} входов | W/L {ps['wins']}/{ps['losses']} ({wr:.0%}) | P&L ${ps['pnl']:+.2f}\n"
    report += "\n"

    # Open positions
    if open_positions:
        report += "======= ОТКРЫТЫЕ ПОЗИЦИИ =======\n"
        for i, (key, pos) in enumerate(list(open_positions.items())[:8], 1):
            player = pos.get("signal_player", "?")
            pemoji = PLAYER_EMOJI.get(player, "👤")
            outcome = pos.get("outcome", "?")
            entry = pos.get("avg_entry", 0)
            cost = pos.get("cost_usd", 0)
            ts = pos.get("timestamp", "")
            days_held = 0
            if ts:
                try:
                    dt = datetime.fromisoformat(ts)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    days_held = (datetime.now(timezone.utc) - dt).days
                except Exception:
                    pass
            report += f"  {i}. {pemoji} {outcome} {pos.get('title', '?')[:32]} @ {entry:.2f} | ${cost:.0f} | {days_held}д\n"
        if len(open_positions) > 8:
            report += f"  ... и ещё {len(open_positions) - 8}\n"
        report += "\n"

    # Overall stats
    wr_total = stats["wins"] / (stats["wins"] + stats["losses"]) if (stats["wins"] + stats["losses"]) > 0 else 0
    wr_7d, trades_7d = _calc_win_rate_last_n_days(data, 7)
    report += "======= СТАТИСТИКА =======\n"
    report += f"Всего сделок: {stats['total_bets']}\n"
    report += f"Win rate (всё время): {wr_total:.0%}\n"
    report += f"Win rate (7 дней): {wr_7d:.0%} ({trades_7d} сделок)\n"
    report += f"Общий P&L: ${stats['total_pnl']:+.2f}\n"

    return report


def generate_strategy_suggestions(data):
    """Generate strategy adjustment suggestions for evening report."""
    suggestions = []

    # 1. WR for last 7 days
    wr_7d, trades_7d = _calc_win_rate_last_n_days(data, 7)
    if trades_7d >= 3:
        if wr_7d < 0.70:
            suggestions.append(
                f"🔴 WR за 7 дней: {wr_7d:.0%} (КРИТИЧНО, {trades_7d} сделок)\n"
                "  → Рекомендация: уменьшить ставки вдвое на 2 недели.\n"
                "  → Отключить категории: Tech, Iran, Russia"
            )
        elif wr_7d < 0.80:
            suggestions.append(
                f"⚠️ WR за 7 дней: {wr_7d:.0%} ({trades_7d} сделок)\n"
                "  → Наблюдать. При падении ниже 70% — принять меры"
            )
        else:
            suggestions.append(f"✅ WR за 7 дней: {wr_7d:.0%} — в норме")

    # 2. Drawdown from peak
    stats = data["stats"]
    peak = stats.get("peak_balance", config.BANKROLL)
    current = stats.get("current_balance", config.BANKROLL)
    if peak > 0:
        drawdown = (peak - current) / peak
        if drawdown > 0.30:
            suggestions.append(
                f"🔴 Просадка: -{drawdown:.0%} от пика (${peak:.0f} → ${current:.0f})\n"
                "  → ПАУЗА! Уменьшить ставки вдвое"
            )
        elif drawdown > 0.15:
            suggestions.append(
                f"⚠️ Просадка: -{drawdown:.0%} от пика\n"
                "  → Наблюдать. Пауза при -30%"
            )

    # 3. Category WR for last 30 days
    cat_stats = _calc_category_stats(data, 30)
    for cat, cs in cat_stats.items():
        if cs["wr"] < 0.60 and cs["trades"] >= 5:
            suggestions.append(
                f"🔴 Категория {cat}: WR {cs['wr']:.0%} за месяц ({cs['trades']} сделок)\n"
                "  → Рекомендация: отключить категорию"
            )

    if not suggestions:
        suggestions.append("✅ Всё в норме. Стратегия работает по плану.")

    return suggestions


def build_evening_report():
    """Build evening report with strategy suggestions (19:00 MSK)."""
    data = tracker.load()
    stats = data["stats"]
    recent_entries, recent_exits = _get_trades_last_24h(data)

    day_pnl = sum(s.get("pnl", 0) for s in recent_exits)
    wins = sum(1 for s in recent_exits if s.get("pnl", 0) > 0)
    losses = len(recent_exits) - wins

    report = f"📊 MULTI-SIGNAL BOT | ВЕЧЕРНИЙ ОТЧЁТ | {_msk_date_str()}\n\n"

    report += "======= ИТОГИ ДНЯ =======\n"
    report += f"Новых входов: {len(recent_entries)}\n"
    report += f"Выходов: {len(recent_exits)} ({wins} прибыль, {losses} убыток)\n"
    report += f"P&L за день: ${day_pnl:+.2f}\n"
    report += f"Банкролл: ${stats['current_balance']:.2f}\n\n"

    # Per-player day stats
    recent_players = {}
    for pos in recent_entries:
        pl = pos.get("signal_player", "?")
        recent_players[pl] = recent_players.get(pl, 0) + 1
    if recent_players:
        report += "======= СИГНАЛЫ ЗА ДЕНЬ =======\n"
        for player, cnt in recent_players.items():
            pemoji = PLAYER_EMOJI.get(player, "👤")
            report += f"{pemoji} {player}: {cnt} входов\n"
        report += "\n"

    # Strategy suggestions
    suggestions = generate_strategy_suggestions(data)
    report += "======= ПРЕДЛОЖЕНИЯ ПО СТРАТЕГИИ =======\n"
    for s in suggestions:
        report += s + "\n\n"

    return report


def build_full_file_report():
    """Build full detailed report for saving to data/ folder."""
    data = tracker.load()
    stats = data["stats"]
    open_positions = tracker.get_open_positions(data)
    all_positions = data.get("positions", {})
    now = datetime.now(timezone.utc)
    msk = now + timedelta(hours=3)
    date_str = msk.strftime("%d.%m.%Y %H:%M MSK")

    lines = []
    lines.append(f"MULTI-SIGNAL COPY-BOT — ПОЛНЫЙ ОТЧЁТ {date_str}")
    lines.append("=" * 60)

    # Portfolio summary
    in_pos = sum(p.get("cost_usd", 0) for p in open_positions.values())
    pnl_pct = (stats["total_pnl"] / config.BANKROLL * 100) if config.BANKROLL > 0 else 0
    lines.append(f"\nПОРТФЕЛЬ")
    lines.append(f"  Банкролл старт:  ${config.BANKROLL:.2f}")
    lines.append(f"  Текущий баланс:  ${stats['current_balance']:.2f}")
    lines.append(f"  В позициях:      ${in_pos:.2f} ({len(open_positions)} шт.)")
    lines.append(f"  Итого стоимость: ${stats['current_balance'] + in_pos:.2f} ({pnl_pct:+.1f}%)")
    lines.append(f"  Общий P&L:       ${stats['total_pnl']:+.2f}")
    lines.append(f"  Пик баланса:     ${stats.get('peak_balance', config.BANKROLL):.2f}")
    lines.append(f"  Всего сделок:    {stats['total_bets']}")
    lines.append(f"  W / L:           {stats['wins']} / {stats['losses']}")

    # Per-player stats
    lines.append(f"\nПО ИГРОКАМ")
    lines.append(f"  {'Игрок':<12} {'Входов':>7} {'W':>5} {'L':>5} {'WR':>6} {'P&L':>10}")
    lines.append(f"  {'-'*50}")
    for player, emoji in PLAYER_EMOJI.items():
        ps = _player_stats(data, player)
        wr = ps["wins"] / (ps["wins"] + ps["losses"]) if (ps["wins"] + ps["losses"]) > 0 else 0
        lines.append(f"  {emoji} {player:<10} {ps['entries']:>7} {ps['wins']:>5} {ps['losses']:>5} {wr:>5.0%} {ps['pnl']:>+10.2f}")

    # Open positions
    lines.append(f"\nОТКРЫТЫЕ ПОЗИЦИИ ({len(open_positions)})")
    lines.append(f"  {'#':<3} {'Игрок':<10} {'Исход':<5} {'Цена':>6} {'Вложено':>8} {'Дней':>5}  Рынок")
    lines.append(f"  {'-'*80}")
    for i, (key, pos) in enumerate(open_positions.items(), 1):
        player = pos.get("signal_player", "?")
        outcome = pos.get("outcome", "?")[:3]
        entry = pos.get("avg_entry", 0)
        cost = pos.get("cost_usd", 0)
        title = pos.get("title", "?")[:45]
        ts = pos.get("timestamp", "")
        days_held = 0
        if ts:
            try:
                dt = datetime.fromisoformat(ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                days_held = (now - dt).days
            except Exception:
                pass
        lines.append(f"  {i:<3} {player:<10} {outcome:<5} {entry:>6.3f} {cost:>8.2f} {days_held:>5}д  {title}")

    # Closed positions (last 30 days)
    cutoff = now - timedelta(days=30)
    closed = [
        (k, p) for k, p in all_positions.items()
        if p.get("status") in ("won", "lost", "sold")
    ]
    # Sort by timestamp desc
    def _ts(item):
        try:
            dt = datetime.fromisoformat(item[1].get("timestamp", ""))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            return datetime.min.replace(tzinfo=timezone.utc)

    closed_recent = [(k, p) for k, p in closed if _ts((k, p)) >= cutoff]
    closed_recent.sort(key=_ts, reverse=True)

    lines.append(f"\nЗАКРЫТЫЕ ПОЗИЦИИ ЗА 30 ДНЕЙ ({len(closed_recent)})")
    lines.append(f"  {'#':<3} {'Игрок':<10} {'Статус':<6} {'Вход':>6} {'Вложено':>8} {'P&L':>9}  Рынок")
    lines.append(f"  {'-'*80}")
    for i, (key, pos) in enumerate(closed_recent[:50], 1):
        player = pos.get("signal_player", "?")
        status = pos.get("status", "?")[:4]
        entry = pos.get("avg_entry", pos.get("entry_price", 0))
        cost = pos.get("cost_usd", 0)
        pnl = pos.get("final_pnl", sum(s.get("pnl", 0) for s in pos.get("sells", [])))
        title = pos.get("title", "?")[:45]
        lines.append(f"  {i:<3} {player:<10} {status:<6} {entry:>6.3f} {cost:>8.2f} {pnl:>+9.2f}  {title}")
    if len(closed_recent) > 50:
        lines.append(f"  ... и ещё {len(closed_recent) - 50} позиций")

    # Strategy health
    wr_7d, trades_7d = _calc_win_rate_last_n_days(data, 7)
    wr_30d, trades_30d = _calc_win_rate_last_n_days(data, 30)
    peak = stats.get("peak_balance", config.BANKROLL)
    drawdown = (peak - stats["current_balance"]) / peak if peak > 0 else 0

    lines.append(f"\nЗДОРОВЬЕ СТРАТЕГИИ")
    lines.append(f"  Win rate 7 дней:  {wr_7d:.0%} ({trades_7d} сделок)")
    lines.append(f"  Win rate 30 дней: {wr_30d:.0%} ({trades_30d} сделок)")
    lines.append(f"  Просадка от пика: -{drawdown:.1%}")

    lines.append("\n" + "=" * 60)
    lines.append(f"Отчёт сгенерирован: {date_str}")

    return "\n".join(lines)


def save_full_report():
    """Save full detailed report to data/ folder."""
    os.makedirs(DATA_DIR, exist_ok=True)
    msk = datetime.now(timezone.utc) + timedelta(hours=3)
    filename = f"report_{msk.strftime('%Y-%m-%d')}.txt"
    filepath = os.path.join(DATA_DIR, filename)

    report = build_full_file_report()
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[REPORT] Full report saved: {filepath}")

    # Also save positions snapshot as JSON
    data = tracker.load()
    json_path = os.path.join(DATA_DIR, f"snapshot_{msk.strftime('%Y-%m-%d')}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[REPORT] Snapshot saved: {json_path}")

    return filepath


def send_daily():
    """Send daily report."""
    report = build_daily_report()
    tg.send(report)
    print(f"[REPORT] Daily report sent at {_msk_date_str()}")


def send_evening():
    """Send evening report."""
    report = build_evening_report()
    tg.send(report)
    print(f"[REPORT] Evening report sent at {_msk_date_str()}")


def _scheduler_loop():
    """Background scheduler. Checks time every 60 seconds."""
    last_sent = {}

    while True:
        try:
            now_msk_h = _msk_hour()
            today = _msk_date_str()

            # 09:00 MSK — save full report to data/ + generate trades report
            if now_msk_h == 9 and f"{today}_file" not in last_sent:
                last_sent[f"{today}_file"] = True
                save_full_report()
                # Generate all-trades-report markdown
                try:
                    import subprocess
                    bot_dir = os.path.dirname(os.path.abspath(__file__))
                    subprocess.run(
                        [sys.executable, os.path.join(bot_dir, "_gen_report.py")],
                        cwd=bot_dir, timeout=120,
                        capture_output=True,
                    )
                    print("[REPORT] All-trades report generated")
                except Exception as e:
                    print(f"[REPORT] All-trades report error: {e}")
                time.sleep(120)

            for schedule in config.REPORT_SCHEDULE:
                h = schedule["hour_msk"]
                rtype = schedule["type"]
                key = f"{today}_{rtype}"

                if now_msk_h == h and key not in last_sent:
                    last_sent[key] = True

                    if rtype == "daily":
                        send_daily()
                    elif rtype == "evening":
                        send_evening()

                    time.sleep(120)  # prevent double-send
        except Exception as e:
            print(f"[REPORT] Scheduler error: {e}")

        time.sleep(60)


def start_background():
    """Start the report scheduler in a background thread."""
    thread = threading.Thread(target=_scheduler_loop, daemon=True)
    thread.start()
    print("[REPORT] Scheduler started (13:00 + 19:00 MSK)")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--evening":
        send_evening()
    elif len(sys.argv) > 1 and sys.argv[1] == "--file":
        path = save_full_report()
        print(f"Saved to: {path}")
    else:
        send_daily()
