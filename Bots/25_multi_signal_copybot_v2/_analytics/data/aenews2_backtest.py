"""
Бэктест aenews2 с анализом по ценовым диапазонам
Дата: 2026-03-31
"""

import json
import datetime
from collections import defaultdict

# ─── Загрузка и объединение данных ───────────────────────────────────────────

def load_data():
    sources = [
        "c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/_analytics/data/aenews2_closed_positions_raw.json",
        "c:/Users/Honor/Desktop/Polymarket/Players_DB/aenews2/closed_positions.json",
    ]
    all_records = {}
    for path in sources:
        try:
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            for r in data:
                key = (r['conditionId'], r['outcome'])
                all_records[key] = r
            print(f"Loaded {len(data)} from {path}")
        except Exception as e:
            print(f"Error loading {path}: {e}")

    records = list(all_records.values())
    print(f"\nTotal unique records after dedup: {len(records)}")
    return records


# ─── Вспомогательные функции ─────────────────────────────────────────────────

def price_bucket(price):
    if price < 0.15:   return "0.00–0.15"
    if price < 0.30:   return "0.15–0.30"
    if price < 0.50:   return "0.30–0.50"
    if price < 0.70:   return "0.50–0.70"
    if price < 0.85:   return "0.70–0.85"
    return "0.85–1.00"

BUCKET_ORDER = ["0.00–0.15", "0.15–0.30", "0.30–0.50", "0.50–0.70", "0.70–0.85", "0.85–1.00"]


def bet_size_A(price, base=50):
    """Фиксированная ставка"""
    return base

def bet_size_B(price, base=50):
    """Обратная цене (пропорциональная)"""
    multiplier = price / 0.50
    return base * multiplier

def bet_size_C(price, target_profit=35):
    """По целевой прибыли $35"""
    if price >= 0.99:
        return 0
    stake = target_profit / (1 / price - 1)
    return max(5, min(stake, 150))

def bet_size_D(price, base=50):
    """Тиры по цене"""
    if price < 0.15:   return base * 0.4
    if price < 0.30:   return base * 0.7
    if price < 0.50:   return base * 1.0
    if price < 0.70:   return base * 1.2
    if price < 0.85:   return base * 0.9
    return base * 0.5


STRATEGIES = {
    "A (фиксированная $50)": bet_size_A,
    "B (пропорц. цене)":     bet_size_B,
    "C (целевая прибыль $35)": bet_size_C,
    "D (тиры по цене)":      bet_size_D,
}


def simulate_position(record, bet_fn, slippage=0.0):
    """
    Симулирует нашу позицию, следуя за aenews2.
    Возвращает (our_pnl, our_cost) или None если позиция не проходит фильтр.
    """
    avg_price = record['avgPrice']
    total_bought = record['totalBought']   # кол-во акций
    realized_pnl = record['realizedPnl']  # реализованный PnL aenews2

    # Стоимость позиции aenews2 в USD
    cost_aenews2 = avg_price * total_bought

    # Фильтр: только позиции $500+
    if cost_aenews2 < 500:
        return None

    # Применяем slippage к нашей цене входа
    entry_price = min(avg_price + slippage, 0.99)

    our_cost = bet_fn(entry_price)
    if our_cost <= 0:
        return None

    # Определяем win/loss по aenews2
    if realized_pnl > 0:
        # aenews2 выиграл → позиция закрылась за $1/акцию
        our_shares = our_cost / entry_price
        our_revenue = our_shares * 1.0
        our_pnl = our_revenue - our_cost
    else:
        # aenews2 проиграл → акции обнулились
        our_pnl = -our_cost

    return our_pnl, our_cost


# ─── Основной анализ ─────────────────────────────────────────────────────────

def main():
    records = load_data()

    # ── Шаг 1: Статистика aenews2 по ценовым диапазонам ──────────────────────
    print("\n" + "="*80)
    print("АНАЛИЗ aenews2 ПО ЦЕНОВЫМ ДИАПАЗОНАМ")
    print("="*80)

    bucket_stats = defaultdict(lambda: {
        'total': 0, 'wins': 0, 'losses': 0,
        'total_pnl': 0, 'total_cost': 0,
        'win_pnls': [], 'loss_pnls': []
    })

    valid_records = []
    skipped = 0

    for r in records:
        avg_price = r['avgPrice']
        total_bought = r['totalBought']
        realized_pnl = r['realizedPnl']

        cost = avg_price * total_bought

        # Фильтр $500+
        if cost < 500:
            skipped += 1
            continue

        valid_records.append(r)
        bucket = price_bucket(avg_price)
        s = bucket_stats[bucket]
        s['total'] += 1
        s['total_pnl'] += realized_pnl
        s['total_cost'] += cost

        if realized_pnl > 0:
            s['wins'] += 1
            s['win_pnls'].append(realized_pnl)
        else:
            s['losses'] += 1
            s['loss_pnls'].append(abs(realized_pnl))

    print(f"\nВсего записей: {len(records)}")
    print(f"Прошло фильтр $500+: {len(valid_records)}")
    print(f"Отфильтровано (< $500): {skipped}")

    print(f"\n{'Диапазон':<14} {'Позиций':>8} {'WR%':>8} {'ROI%':>8} {'Avg Win':>10} {'Avg Loss':>10} {'Total PnL':>12} {'Total Cost':>12}")
    print("-"*90)

    bucket_table = []
    for bucket in BUCKET_ORDER:
        s = bucket_stats[bucket]
        if s['total'] == 0:
            continue
        wr = s['wins'] / s['total'] * 100
        roi = s['total_pnl'] / s['total_cost'] * 100 if s['total_cost'] > 0 else 0
        avg_win = sum(s['win_pnls']) / len(s['win_pnls']) if s['win_pnls'] else 0
        avg_loss = sum(s['loss_pnls']) / len(s['loss_pnls']) if s['loss_pnls'] else 0
        print(f"{bucket:<14} {s['total']:>8} {wr:>8.1f} {roi:>8.1f} {avg_win:>10.0f} {avg_loss:>10.0f} {s['total_pnl']:>12.0f} {s['total_cost']:>12.0f}")
        bucket_table.append((bucket, s['total'], wr, roi, avg_win, avg_loss, s['total_pnl'], s['total_cost']))

    # Итого
    all_cost = sum(bucket_stats[b]['total_cost'] for b in BUCKET_ORDER)
    all_pnl = sum(bucket_stats[b]['total_pnl'] for b in BUCKET_ORDER)
    all_wins = sum(bucket_stats[b]['wins'] for b in BUCKET_ORDER)
    all_total = sum(bucket_stats[b]['total'] for b in BUCKET_ORDER)
    all_wr = all_wins / all_total * 100 if all_total > 0 else 0
    all_roi = all_pnl / all_cost * 100 if all_cost > 0 else 0
    print(f"{'ИТОГО':<14} {all_total:>8} {all_wr:>8.1f} {all_roi:>8.1f} {'—':>10} {'—':>10} {all_pnl:>12.0f} {all_cost:>12.0f}")

    # ── Шаг 2: Симуляция стратегий ────────────────────────────────────────────
    print("\n" + "="*80)
    print("СИМУЛЯЦИЯ СТРАТЕГИЙ НАШЕГО БОТА (фильтр $500+, без slippage)")
    print("="*80)

    # Собираем результаты по стратегиям и диапазонам
    strategy_results = {}

    for strat_name, bet_fn in STRATEGIES.items():
        results_by_bucket = defaultdict(lambda: {'pnl': 0, 'cost': 0, 'trades': 0})
        total_pnl = 0
        total_cost = 0
        total_trades = 0

        for r in valid_records:
            res = simulate_position(r, bet_fn, slippage=0.0)
            if res is None:
                continue
            our_pnl, our_cost = res
            bucket = price_bucket(r['avgPrice'])
            results_by_bucket[bucket]['pnl'] += our_pnl
            results_by_bucket[bucket]['cost'] += our_cost
            results_by_bucket[bucket]['trades'] += 1
            total_pnl += our_pnl
            total_cost += our_cost
            total_trades += 1

        strategy_results[strat_name] = {
            'by_bucket': results_by_bucket,
            'total_pnl': total_pnl,
            'total_cost': total_cost,
            'total_trades': total_trades,
        }

    # Итоговая таблица по стратегиям
    print(f"\n{'Стратегия':<28} {'Сделок':>8} {'Total PnL':>12} {'Total Cost':>12} {'ROI%':>8}")
    print("-"*70)
    for strat_name, res in strategy_results.items():
        roi = res['total_pnl'] / res['total_cost'] * 100 if res['total_cost'] > 0 else 0
        print(f"{strat_name:<28} {res['total_trades']:>8} {res['total_pnl']:>12.0f} {res['total_cost']:>12.0f} {roi:>8.1f}")

    # Детальная таблица по стратегиям и диапазонам
    print("\n" + "="*80)
    print("P&L НАШЕГО БОТА ПО ДИАПАЗОНАМ (4 стратегии)")
    print("="*80)

    strat_names = list(STRATEGIES.keys())
    header = f"{'Диапазон':<14}"
    for sn in strat_names:
        short = sn.split(' ')[0]
        header += f"  {short+' PnL':>10} {short+' ROI%':>8}"
    print(header)
    print("-"*100)

    for bucket in BUCKET_ORDER:
        line = f"{bucket:<14}"
        for sn in strat_names:
            rb = strategy_results[sn]['by_bucket'][bucket]
            pnl = rb['pnl']
            cost = rb['cost']
            roi = pnl / cost * 100 if cost > 0 else 0
            short = sn.split(' ')[0]
            line += f"  {pnl:>10.0f} {roi:>8.1f}"
        print(line)

    # ── Шаг 3: Анализ диапазона 15-30¢ со slippage ───────────────────────────
    print("\n" + "="*80)
    print("АНАЛИЗ ДИАПАЗОНА 0.15–0.30 (со slippage)")
    print("="*80)

    # Текущая ситуация: фильтр не пропускает 15-30¢ (предположим что бот имеет фильтр price>0.30)
    # Анализируем что было бы при включении

    target_records = [r for r in valid_records if 0.15 <= r['avgPrice'] < 0.30]
    print(f"\nПозиций в диапазоне 0.15–0.30: {len(target_records)}")

    if target_records:
        wins_15_30 = sum(1 for r in target_records if r['realizedPnl'] > 0)
        total_pnl_15_30 = sum(r['realizedPnl'] for r in target_records)
        total_cost_15_30 = sum(r['avgPrice'] * r['totalBought'] for r in target_records)
        wr_15_30 = wins_15_30 / len(target_records) * 100
        roi_15_30 = total_pnl_15_30 / total_cost_15_30 * 100 if total_cost_15_30 > 0 else 0
        print(f"WR aenews2: {wr_15_30:.1f}%")
        print(f"ROI aenews2: {roi_15_30:.1f}%")
        print(f"Total PnL aenews2: ${total_pnl_15_30:,.0f}")

        # Симуляция с разными slippage
        print(f"\n{'Slippage':>12} {'Стратегия':<28} {'PnL':>10} {'Cost':>10} {'ROI%':>8} {'Сделок':>8}")
        print("-"*80)
        for slip in [0.00, 0.02, 0.03, 0.05]:
            for sn, bet_fn in STRATEGIES.items():
                pnl_s = 0
                cost_s = 0
                trades_s = 0
                for r in target_records:
                    res = simulate_position(r, bet_fn, slippage=slip)
                    if res is None:
                        continue
                    our_pnl, our_cost = res
                    pnl_s += our_pnl
                    cost_s += our_cost
                    trades_s += 1
                roi_s = pnl_s / cost_s * 100 if cost_s > 0 else 0
                slip_str = f"+{slip:.2f}"
                print(f"{slip_str:>12} {sn:<28} {pnl_s:>10.0f} {cost_s:>10.0f} {roi_s:>8.1f} {trades_s:>8}")

    # ── Шаг 4: Что если убрать ценовой фильтр (включить 15-30¢) ─────────────
    print("\n" + "="*80)
    print("СРАВНЕНИЕ: С ФИЛЬТРОМ price>0.30 vs БЕЗ ФИЛЬТРА (все >= 0.15)")
    print("="*80)

    for sn, bet_fn in STRATEGIES.items():
        # С фильтром: только >= 0.30
        filtered_records = [r for r in valid_records if r['avgPrice'] >= 0.30]
        # Без фильтра: >= 0.15
        unfiltered_records = [r for r in valid_records if r['avgPrice'] >= 0.15]

        for label, recs in [("price>=0.30 (текущий)", filtered_records),
                             ("price>=0.15 (без фильтра)", unfiltered_records)]:
            pnl_total = 0
            cost_total = 0
            trades_total = 0
            for r in recs:
                res = simulate_position(r, bet_fn, slippage=0.0)
                if res is None:
                    continue
                our_pnl, our_cost = res
                pnl_total += our_pnl
                cost_total += our_cost
                trades_total += 1
            roi_total = pnl_total / cost_total * 100 if cost_total > 0 else 0
            print(f"{sn:<28} | {label:<26} | PnL: {pnl_total:>10.0f} | ROI: {roi_total:>6.1f}% | Сделок: {trades_total:>5}")

    # ── Итоговые метрики для отчёта ───────────────────────────────────────────
    print("\n" + "="*80)
    print("ИТОГОВЫЕ ДАННЫЕ ДЛЯ ОТЧЁТА")
    print("="*80)
    print(f"\nВсего закрытых позиций (уникальных): {len(records)}")
    print(f"Позиций с размером $500+: {len(valid_records)}")
    print(f"Дата первой позиции: {datetime.datetime.fromtimestamp(min(r['timestamp'] for r in records)).date()}")
    print(f"Дата последней позиции: {datetime.datetime.fromtimestamp(max(r['timestamp'] for r in records)).date()}")

    # Возвращаем данные для отчёта
    return bucket_table, strategy_results, target_records, valid_records, records


if __name__ == "__main__":
    result = main()
