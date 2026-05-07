"""
Генератор отчётов A/B теста лимитных ордеров.

Читает limit_ab_log.csv, считает KPI, генерирует markdown-отчёт.

Использование:
    python _report_limit_ab.py --day 0   # начальный (тестовый)
    python _report_limit_ab.py --day 5   # 5-й день
    python _report_limit_ab.py --day 10  # 10-й день
    python _report_limit_ab.py --day 15  # финальный
"""

import argparse
import csv
import os
import shutil
from datetime import datetime, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "limit_ab_log.csv")
ANALYTICS_DIR = os.path.join(SCRIPT_DIR, "_analytics")

START_DATE = datetime(2026, 4, 16)

# Пороги KPI: (метрика, порог_успеха, порог_провала)
THRESHOLDS = {
    "fill_rate_buy":       {"success": 50, "fail": 30, "unit": "%"},
    "fill_rate_sell":      {"success": 60, "fail": 40, "unit": "%"},
    "avg_savings_buy":     {"success": 0.015, "fail": 0.005, "unit": "$"},
    "avg_savings_sell":    {"success": 0.010, "fail": 0.003, "unit": "$"},
    "total_savings_usd":   {"success": 30, "fail": 10, "unit": "$"},
    "avg_delay_cost":      {"success": 0.01, "fail": 0.025, "unit": "$", "lower_is_better": True},
}


def load_csv():
    """Загружает данные из limit_ab_log.csv. Возвращает список словарей."""
    if not os.path.exists(CSV_PATH):
        return []

    rows = []
    with open(CSV_PATH, "r", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Приводим типы
            try:
                row["our_price"] = float(row["our_price"])
                row["our_shares"] = float(row["our_shares"])
                row["our_usd"] = float(row["our_usd"])
                row["limit_price_2pct"] = float(row["limit_price_2pct"])
                row["best_price_in_window"] = float(row["best_price_in_window"])
                row["would_fill"] = row["would_fill"].strip().lower() == "true"
                row["fill_minute"] = float(row["fill_minute"])
                row["savings_per_share"] = float(row["savings_per_share"])
                row["savings_total_usd"] = float(row["savings_total_usd"])
                row["window_minutes"] = int(row["window_minutes"])
                row["checks_done"] = int(row["checks_done"])
                rows.append(row)
            except (ValueError, KeyError):
                continue
    return rows


def compute_kpi(rows):
    """Считает все KPI. Возвращает словарь метрик."""
    buys = [r for r in rows if r["direction"] == "BUY"]
    sells = [r for r in rows if r["direction"] == "SELL"]

    filled_buys = [r for r in buys if r["would_fill"]]
    filled_sells = [r for r in sells if r["would_fill"]]

    # Fill rates
    fill_rate_buy = (len(filled_buys) / len(buys) * 100) if buys else 0
    fill_rate_sell = (len(filled_sells) / len(sells) * 100) if sells else 0

    # Средняя экономия на share (только для заполнившихся)
    avg_savings_buy = 0
    if filled_buys:
        avg_savings_buy = sum(r["savings_per_share"] for r in filled_buys) / len(filled_buys)

    avg_savings_sell = 0
    if filled_sells:
        avg_savings_sell = sum(r["savings_per_share"] for r in filled_sells) / len(filled_sells)

    # Суммарная экономия USD (только заполнившиеся)
    total_savings = sum(r["savings_total_usd"] for r in filled_buys + filled_sells)

    # Delay cost: разница best_price - our_price для BUY (отрицательное = цена ушла вверх)
    # По сути savings_per_share уже содержит эту информацию для всех BUY
    avg_delay_cost = 0
    if buys:
        # Для BUY: our_price - best_price_in_window (если отрицательное — цена выросла)
        # delay cost = насколько цена ушла вверх за окно
        costs = []
        for r in buys:
            # best_price_in_window — минимальная ask за окно
            # Если best > our, значит цена ушла вверх (delay cost положительный)
            cost = r["best_price_in_window"] - r["our_price"]
            costs.append(cost)
        avg_delay_cost = sum(costs) / len(costs) if costs else 0

    return {
        "total_trades": len(rows),
        "total_buys": len(buys),
        "total_sells": len(sells),
        "filled_buys": len(filled_buys),
        "filled_sells": len(filled_sells),
        "fill_rate_buy": round(fill_rate_buy, 1),
        "fill_rate_sell": round(fill_rate_sell, 1),
        "avg_savings_buy": round(avg_savings_buy, 6),
        "avg_savings_sell": round(avg_savings_sell, 6),
        "total_savings_usd": round(total_savings, 2),
        "avg_delay_cost": round(avg_delay_cost, 6),
    }


def status_emoji(metric_name, value):
    """Возвращает статус KPI: зелёный, жёлтый или красный."""
    t = THRESHOLDS.get(metric_name)
    if t is None:
        return "—"

    lower_is_better = t.get("lower_is_better", False)

    if lower_is_better:
        if value <= t["success"]:
            return "OK"
        elif value >= t["fail"]:
            return "FAIL"
        else:
            return "??"
    else:
        if value >= t["success"]:
            return "OK"
        elif value <= t["fail"]:
            return "FAIL"
        else:
            return "??"


def format_value(value, unit, force_dollars=False):
    """Форматирует значение с единицей измерения."""
    if unit == "%":
        return f"{value:.1f}%"
    elif unit == "$":
        if force_dollars or abs(value) >= 1:
            return f"${value:.2f}"
        elif abs(value) < 0.0001:
            return "$0.00"
        else:
            return f"{value*100:.2f} центов"
    return str(value)


def generate_conclusion(kpi):
    """Автоматический вывод на основе KPI."""
    if kpi["total_trades"] == 0:
        return "Данных пока нет. Ожидаем первые сделки бота."

    if kpi["total_trades"] < 5:
        return "Слишком мало данных для выводов. Нужно минимум 5 сделок."

    ok_count = 0
    fail_count = 0
    metrics = {
        "fill_rate_buy": kpi["fill_rate_buy"],
        "fill_rate_sell": kpi["fill_rate_sell"],
        "avg_savings_buy": kpi["avg_savings_buy"],
        "avg_savings_sell": kpi["avg_savings_sell"],
        "total_savings_usd": kpi["total_savings_usd"],
        "avg_delay_cost": abs(kpi["avg_delay_cost"]),
    }

    for name, val in metrics.items():
        s = status_emoji(name, val)
        if s == "OK":
            ok_count += 1
        elif s == "FAIL":
            fail_count += 1

    if ok_count >= 4 and fail_count == 0:
        return "ВНЕДРЯЕМ ЛИМИТЫ. Большинство KPI в зелёной зоне, лимитные ордера дают заметную экономию."
    elif fail_count >= 3:
        return "НЕ ВНЕДРЯЕМ. Большинство KPI в красной зоне. Рыночные ордера лучше для нашей стратегии."
    else:
        return "ПОКА НЕДОСТАТОЧНО ДАННЫХ для однозначного решения. Продолжаем наблюдение."


def generate_report(day, kpi, rows):
    """Генерирует markdown-отчёт."""
    end_date = START_DATE + timedelta(days=day) if day > 0 else START_DATE

    lines = []
    lines.append(f"# A/B Тест: Лимитные vs Рыночные ордера — День {day}")
    lines.append("")
    lines.append(f"Период: {START_DATE.strftime('%Y-%m-%d')} — {end_date.strftime('%Y-%m-%d')}")
    lines.append(f"Сделок: {kpi['total_trades']} (BUY: {kpi['total_buys']}, SELL: {kpi['total_sells']})")
    lines.append("")

    # KPI таблица
    lines.append("## KPI")
    lines.append("")
    lines.append("| Метрика | Значение | Порог успеха | Статус |")
    lines.append("|---|---|---|---|")

    # (label, value, metric_name, threshold_text, force_dollars)
    kpi_rows = [
        ("Fill rate входов", kpi["fill_rate_buy"], "fill_rate_buy", ">50%", False),
        ("Fill rate выходов", kpi["fill_rate_sell"], "fill_rate_sell", ">60%", False),
        ("Ср. экономия/share (вход)", kpi["avg_savings_buy"], "avg_savings_buy", ">1.5 центов", False),
        ("Ср. экономия/share (выход)", kpi["avg_savings_sell"], "avg_savings_sell", ">1.0 центов", False),
        ("Суммарная экономия USD", kpi["total_savings_usd"], "total_savings_usd", ">$30", True),
        ("Средний delay cost", abs(kpi["avg_delay_cost"]), "avg_delay_cost", "<1 цент", False),
    ]

    for label, value, metric_name, threshold_text, force_usd in kpi_rows:
        t = THRESHOLDS[metric_name]
        formatted = format_value(value, t["unit"], force_dollars=force_usd)
        s = status_emoji(metric_name, value)
        lines.append(f"| {label} | {formatted} | {threshold_text} | {s} |")

    lines.append("")

    # Детализация по сделкам
    lines.append("## Детализация по сделкам")
    lines.append("")

    if rows:
        lines.append("| Дата | Рынок | Направление | Наша цена | Лимит 2% | Лучшая за окно | Заполнился бы? | Экономия |")
        lines.append("|---|---|---|---|---|---|---|---|")

        for r in rows:
            ts = r["timestamp"][:10] if len(r["timestamp"]) >= 10 else r["timestamp"]
            market = r["market"][:40]
            direction = r["direction"]
            our = f"{r['our_price']:.4f}"
            limit = f"{r['limit_price_2pct']:.4f}"
            best = f"{r['best_price_in_window']:.4f}"
            filled = "Да" if r["would_fill"] else "Нет"
            savings = f"${r['savings_total_usd']:.4f}"
            lines.append(f"| {ts} | {market} | {direction} | {our} | {limit} | {best} | {filled} | {savings} |")
    else:
        lines.append("*Сделок пока нет. Ожидаем данные.*")

    lines.append("")

    # Вывод
    lines.append("## Вывод")
    lines.append("")
    lines.append(generate_conclusion(kpi))
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Отчёт A/B теста лимитных ордеров")
    parser.add_argument("--day", type=int, required=True, help="День теста (0, 5, 10, 15)")
    args = parser.parse_args()

    os.makedirs(ANALYTICS_DIR, exist_ok=True)

    # Загружаем данные
    rows = load_csv()

    # Считаем KPI
    kpi = compute_kpi(rows)

    # Генерируем отчёт
    report = generate_report(args.day, kpi, rows)

    # Сохраняем отчёт
    report_path = os.path.join(ANALYTICS_DIR, f"limit_order_ab_report_DAY_{args.day}.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Отчёт сохранён: {report_path}")

    # Копируем исходный CSV
    if os.path.exists(CSV_PATH):
        raw_path = os.path.join(ANALYTICS_DIR, f"limit_ab_log_raw_DAY_{args.day}.csv")
        shutil.copy2(CSV_PATH, raw_path)
        print(f"Данные скопированы: {raw_path}")
    else:
        # CSV ещё нет — создаём пустой с заголовком
        raw_path = os.path.join(ANALYTICS_DIR, f"limit_ab_log_raw_DAY_{args.day}.csv")
        with open(raw_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "market", "direction", "our_price", "our_shares", "our_usd",
                "limit_price_2pct", "best_price_in_window", "would_fill", "fill_minute",
                "savings_per_share", "savings_total_usd", "window_minutes", "checks_done",
            ])
        print(f"CSV пока пуст, создана заглушка: {raw_path}")

    # Выводим краткую сводку
    print()
    print(f"=== День {args.day} ===")
    print(f"Всего сделок: {kpi['total_trades']} (BUY: {kpi['total_buys']}, SELL: {kpi['total_sells']})")
    if kpi["total_trades"] > 0:
        print(f"Fill rate BUY: {kpi['fill_rate_buy']:.1f}%")
        print(f"Fill rate SELL: {kpi['fill_rate_sell']:.1f}%")
        print(f"Суммарная экономия: ${kpi['total_savings_usd']:.2f}")
    else:
        print("Данных пока нет. Ожидаем первые сделки.")


if __name__ == "__main__":
    main()
