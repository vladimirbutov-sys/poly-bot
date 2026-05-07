#!/usr/bin/env python3
"""
Бэктест: оптимальные параметры лимитных ордеров.
Анализируем поминутную ценовую историю после каждого входа/выхода,
чтобы определить оптимальный offset и timeout для лимитных ордеров.
"""

import json
import time
import os
import sys
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "positions.json")
ANALYTICS_DIR = os.path.join(os.path.dirname(__file__), "_analytics")
OUTPUT_FILE = os.path.join(ANALYTICS_DIR, "2026-04-16_limit_order_params.md")

SKIP_SELL_REASONS = [
    "onchain_sync", "reconcile", "disappeared", "manual",
    "drift_fix", "cascade", "consolidation", "audit",
    "resting_order", "exit_skip",
]

OFFSETS = [0.01, 0.02, 0.03, 0.05, 0.07, 0.10]
WINDOWS = [5, 10, 15, 30, 60]
FINE_WINDOWS = [1, 2, 5, 10, 15, 20, 30, 45, 60]

price_cache = {}


def iso_to_unix(iso_str):
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def fetch_price_history(token_id):
    if token_id in price_cache:
        return price_cache[token_id]

    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval=max&fidelity=1"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        history = data.get("history", [])
        points = [(int(h["t"]), float(h["p"])) for h in history]
        points.sort(key=lambda x: x[0])
        price_cache[token_id] = points
        return points
    except (HTTPError, URLError, json.JSONDecodeError, KeyError) as e:
        print(f"  API error for token {token_id[:20]}...: {e}")
        price_cache[token_id] = None
        return None


def get_prices_in_window(prices, start_ts, window_minutes):
    """Get all prices within [start_ts, start_ts + window*60]."""
    end_ts = start_ts + window_minutes * 60
    return [p for t, p in prices if start_ts <= t <= end_ts]


def find_min_by_minute(prices, start_ts, max_minutes):
    """
    For each minute 1..max_minutes, find running minimum price.
    Returns dict: minute -> min_price_so_far
    """
    result = {}
    running_min = None
    for m in range(1, max_minutes + 1):
        end_ts = start_ts + m * 60
        # Get prices in this 1-minute slice
        new_prices = [p for t, p in prices if start_ts + (m-1)*60 < t <= end_ts]
        if m == 1:
            # Also include prices at start_ts for first minute
            new_prices += [p for t, p in prices if start_ts <= t <= start_ts + 60]

        if new_prices:
            slice_min = min(new_prices)
            if running_min is None:
                running_min = slice_min
            else:
                running_min = min(running_min, slice_min)

        result[m] = running_min
    return result


def find_max_by_minute(prices, start_ts, max_minutes):
    """Same but for max."""
    result = {}
    running_max = None
    for m in range(1, max_minutes + 1):
        end_ts = start_ts + m * 60
        new_prices = [p for t, p in prices if start_ts + (m-1)*60 < t <= end_ts]
        if m == 1:
            new_prices += [p for t, p in prices if start_ts <= t <= start_ts + 60]

        if new_prices:
            slice_max = max(new_prices)
            if running_max is None:
                running_max = slice_max
            else:
                running_max = max(running_max, slice_max)

        result[m] = running_max
    return result


def should_skip_sell(reason):
    reason_lower = reason.lower()
    for skip in SKIP_SELL_REASONS:
        if skip in reason_lower:
            return True
    return False


def main():
    with open(POSITIONS_FILE) as f:
        data = json.load(f)

    positions = data["positions"]
    tokens_fetched = set()

    # ========== ENTRY ANALYSIS ==========
    print("=" * 70)
    print("ЗАГРУЗКА ЦЕНОВЫХ ДАННЫХ ДЛЯ ВХОДОВ")
    print("=" * 70)

    entry_data = []  # list of dicts with per-minute min prices
    entry_skipped = 0
    entry_api_fail = 0

    for pid, pos in positions.items():
        avg_entry = pos.get("avg_entry", 0)
        token_id = pos.get("token_id", "")
        timestamp = pos.get("timestamp", "")
        cost_usd = pos.get("cost_usd", 0)
        title = pos.get("title", "unknown")
        status = pos.get("status", "")

        if avg_entry > 1.0 or avg_entry <= 0:
            entry_skipped += 1
            continue
        if not token_id or not timestamp:
            entry_skipped += 1
            continue
        if status == "merged_into_primary":
            entry_skipped += 1
            continue

        our_shares = cost_usd / avg_entry if avg_entry > 0 else 0
        entry_ts = iso_to_unix(timestamp)

        if token_id not in tokens_fetched:
            tokens_fetched.add(token_id)
            if token_id not in price_cache:
                time.sleep(0.3)

        prices = fetch_price_history(token_id)
        if prices is None:
            entry_api_fail += 1
            continue

        # Get per-minute running min
        min_by_min = find_min_by_minute(prices, entry_ts, 60)

        if min_by_min.get(60) is None and min_by_min.get(30) is None:
            entry_api_fail += 1
            continue

        entry_data.append({
            "title": title[:50],
            "avg_entry": avg_entry,
            "our_shares": our_shares,
            "cost_usd": cost_usd,
            "min_by_min": min_by_min,
        })

        sys.stdout.write(f"\r  Обработано входов: {len(entry_data)}...")
        sys.stdout.flush()

    print(f"\n  Всего: {len(positions)}, пропущено: {entry_skipped}, API fail: {entry_api_fail}")
    print(f"  Успешно: {len(entry_data)}")

    # ========== SELL ANALYSIS ==========
    print("\n" + "=" * 70)
    print("ЗАГРУЗКА ЦЕНОВЫХ ДАННЫХ ДЛЯ ВЫХОДОВ")
    print("=" * 70)

    sell_data = []
    sell_skipped = 0
    sell_api_fail = 0

    for pid, pos in positions.items():
        token_id = pos.get("token_id", "")
        title = pos.get("title", "unknown")
        sells = pos.get("sells", [])
        status = pos.get("status", "")

        if status == "merged_into_primary":
            sell_skipped += len(sells)
            continue

        for sell in sells:
            reason = sell.get("reason", "")
            if should_skip_sell(reason):
                sell_skipped += 1
                continue

            sell_price = sell.get("price", 0)
            sell_ts_str = sell.get("timestamp", "")
            sell_shares = sell.get("shares", 0)

            if sell_price <= 0 or sell_price > 1.0 or not sell_ts_str:
                sell_skipped += 1
                continue

            sell_ts = iso_to_unix(sell_ts_str)

            if token_id not in tokens_fetched:
                tokens_fetched.add(token_id)
                if token_id not in price_cache:
                    time.sleep(0.3)

            prices = fetch_price_history(token_id)
            if prices is None:
                sell_api_fail += 1
                continue

            max_by_min = find_max_by_minute(prices, sell_ts, 60)

            if max_by_min.get(60) is None and max_by_min.get(30) is None:
                sell_api_fail += 1
                continue

            sell_data.append({
                "title": title[:50],
                "sell_price": sell_price,
                "shares": sell_shares,
                "reason": reason[:40],
                "max_by_min": max_by_min,
            })

        sys.stdout.write(f"\r  Обработано продаж: {len(sell_data)}...")
        sys.stdout.flush()

    print(f"\n  Пропущено: {sell_skipped}, API fail: {sell_api_fail}")
    print(f"  Успешно: {len(sell_data)}")

    # ========== COMPUTE TABLES ==========
    lines = []

    def out(text=""):
        print(text)
        lines.append(text)

    out("# Оптимальные параметры лимитных ордеров")
    out(f"\nДата анализа: 2026-04-16")
    out(f"Входов проанализировано: {len(entry_data)}")
    out(f"Выходов проанализировано: {len(sell_data)}")

    # ---- ENTRY TABLE ----
    out("\n## Анализ ВХОДОВ (Buy)")
    out("\nДля каждого offset: какой % лимитных ордеров заполнился бы за N минут.")
    out("Offset = на сколько % ниже рыночной цены ставим лимит.")
    out("")
    out("| Offset | Fill 5m | Fill 10m | Fill 15m | Fill 30m | Fill 60m | Avg savings | Суммарная экономия |")
    out("|--------|---------|----------|----------|----------|----------|-------------|-------------------|")

    entry_best_score = 0
    entry_best_combo = ""

    for offset in OFFSETS:
        fills = {w: 0 for w in WINDOWS}
        savings_list = []
        total_savings_usd = 0

        for ed in entry_data:
            limit_price = ed["avg_entry"] * (1 - offset)

            for w in WINDOWS:
                min_price = ed["min_by_min"].get(w)
                if min_price is not None and min_price <= limit_price:
                    fills[w] += 1

            # For 60-min window savings calculation
            min_60 = ed["min_by_min"].get(60)
            if min_60 is not None and min_60 <= limit_price:
                saving = ed["avg_entry"] - limit_price
                savings_list.append(saving)
                total_savings_usd += saving * ed["our_shares"]

        n = len(entry_data)
        avg_sav = (sum(savings_list) / len(savings_list) * 100) if savings_list else 0

        fill_strs = []
        for w in WINDOWS:
            pct = fills[w] / n * 100 if n > 0 else 0
            fill_strs.append(f"{pct:.0f}%")

        out(f"| {offset*100:.0f}%     | {fill_strs[0]:>7} | {fill_strs[1]:>8} | {fill_strs[2]:>8} | {fill_strs[3]:>8} | {fill_strs[4]:>8} | {avg_sav:.1f}c        | ${total_savings_usd:.2f}            |")

        # Score: fill_rate_15m * avg_savings
        fr15 = fills[15] / n if n > 0 else 0
        score = fr15 * avg_sav
        if score > entry_best_score:
            entry_best_score = score
            entry_best_combo = f"offset={offset*100:.0f}%, fill_15m={fr15*100:.0f}%, savings={avg_sav:.1f}c"

    out(f"\nЛучшая комбинация (вход): {entry_best_combo}")

    # ---- SELL TABLE ----
    out("\n## Анализ ВЫХОДОВ (Sell)")
    out("\nДля каждого offset: какой % лимитных ордеров заполнился бы за N минут.")
    out("Offset = на сколько % выше рыночной цены ставим лимит на продажу.")
    out("")
    out("| Offset | Fill 5m | Fill 10m | Fill 15m | Fill 30m | Fill 60m | Avg improvement | Суммарный выигрыш |")
    out("|--------|---------|----------|----------|----------|----------|-----------------|-------------------|")

    sell_best_score = 0
    sell_best_combo = ""

    for offset in OFFSETS:
        fills = {w: 0 for w in WINDOWS}
        improvement_list = []
        total_gain_usd = 0

        for sd in sell_data:
            limit_price = sd["sell_price"] * (1 + offset)

            for w in WINDOWS:
                max_price = sd["max_by_min"].get(w)
                if max_price is not None and max_price >= limit_price:
                    fills[w] += 1

            max_60 = sd["max_by_min"].get(60)
            if max_60 is not None and max_60 >= limit_price:
                improvement = limit_price - sd["sell_price"]
                improvement_list.append(improvement)
                total_gain_usd += improvement * sd["shares"]

        n = len(sell_data)
        avg_imp = (sum(improvement_list) / len(improvement_list) * 100) if improvement_list else 0

        fill_strs = []
        for w in WINDOWS:
            pct = fills[w] / n * 100 if n > 0 else 0
            fill_strs.append(f"{pct:.0f}%")

        out(f"| {offset*100:.0f}%     | {fill_strs[0]:>7} | {fill_strs[1]:>8} | {fill_strs[2]:>8} | {fill_strs[3]:>8} | {fill_strs[4]:>8} | {avg_imp:.1f}c             | ${total_gain_usd:.2f}            |")

        fr15 = fills[15] / n if n > 0 else 0
        score = fr15 * avg_imp
        if score > sell_best_score:
            sell_best_score = score
            sell_best_combo = f"offset={offset*100:.0f}%, fill_15m={fr15*100:.0f}%, improvement={avg_imp:.1f}c"

    out(f"\nЛучшая комбинация (выход): {sell_best_combo}")

    # ---- TIME WINDOW TABLE (fixed 3% offset) ----
    out("\n## Зависимость fill rate от времени ожидания (offset = 3%)")
    out("")
    out("| Время ожидания | Fill rate (вход) | Fill rate (выход) |")
    out("|----------------|------------------|-------------------|")

    for w in FINE_WINDOWS:
        # Entry
        entry_fills = 0
        for ed in entry_data:
            limit_price = ed["avg_entry"] * 0.97
            min_price = ed["min_by_min"].get(w)
            if min_price is not None and min_price <= limit_price:
                entry_fills += 1
        entry_fr = entry_fills / len(entry_data) * 100 if entry_data else 0

        # Sell
        sell_fills = 0
        for sd in sell_data:
            limit_price = sd["sell_price"] * 1.03
            max_price = sd["max_by_min"].get(w)
            if max_price is not None and max_price >= limit_price:
                sell_fills += 1
        sell_fr = sell_fills / len(sell_data) * 100 if sell_data else 0

        out(f"| {w:>3} мин         | {entry_fr:>5.0f}%           | {sell_fr:>5.0f}%            |")

    # ---- EXPECTED VALUE TABLE ----
    out("\n## Ожидаемая ценность (Expected Value) по комбинациям")
    out("\nEV = fill_rate * savings_per_trade (чем выше, тем лучше)")
    out("Для входа: средняя экономия на 1 сделку = offset * avg_entry * fill_rate")
    out("")
    out("### Входы: EV по комбинациям (offset x timeout)")
    out("")

    header = "| Offset  |"
    for w in FINE_WINDOWS:
        header += f" {w}m     |"
    out(header)
    out("|---------|" + "---------|" * len(FINE_WINDOWS))

    entry_best_ev = 0
    entry_best_ev_combo = ""

    for offset in OFFSETS:
        row = f"| {offset*100:.0f}%     |"
        for w in FINE_WINDOWS:
            fills = 0
            total_sav = 0
            for ed in entry_data:
                limit_price = ed["avg_entry"] * (1 - offset)
                min_price = ed["min_by_min"].get(w)
                if min_price is not None and min_price <= limit_price:
                    fills += 1
                    total_sav += (ed["avg_entry"] - limit_price) * ed["our_shares"]

            fr = fills / len(entry_data) if entry_data else 0
            # EV = total savings across all trades / N trades
            ev = total_sav / len(entry_data) if entry_data else 0
            row += f" ${ev:.2f}  |"

            if ev > entry_best_ev:
                entry_best_ev = ev
                entry_best_ev_combo = f"offset={offset*100:.0f}%, timeout={w}m, EV=${ev:.2f}/trade, fill={fr*100:.0f}%"

        out(row)

    out(f"\nЛучший EV (вход): {entry_best_ev_combo}")

    out("\n### Выходы: EV по комбинациям (offset x timeout)")
    out("")

    header = "| Offset  |"
    for w in FINE_WINDOWS:
        header += f" {w}m     |"
    out(header)
    out("|---------|" + "---------|" * len(FINE_WINDOWS))

    sell_best_ev = 0
    sell_best_ev_combo = ""

    for offset in OFFSETS:
        row = f"| {offset*100:.0f}%     |"
        for w in FINE_WINDOWS:
            fills = 0
            total_gain = 0
            for sd in sell_data:
                limit_price = sd["sell_price"] * (1 + offset)
                max_price = sd["max_by_min"].get(w)
                if max_price is not None and max_price >= limit_price:
                    fills += 1
                    total_gain += (limit_price - sd["sell_price"]) * sd["shares"]

            fr = fills / len(sell_data) if sell_data else 0
            ev = total_gain / len(sell_data) if sell_data else 0
            row += f" ${ev:.2f}  |"

            if ev > sell_best_ev:
                sell_best_ev = ev
                sell_best_ev_combo = f"offset={offset*100:.0f}%, timeout={w}m, EV=${ev:.2f}/trade, fill={fr*100:.0f}%"

        out(row)

    out(f"\nЛучший EV (выход): {sell_best_ev_combo}")

    # ---- RECOMMENDATION ----
    out("\n## РЕКОМЕНДАЦИЯ")
    out("")
    out("### Для ВХОДА (Buy):")
    out(f"  {entry_best_ev_combo}")
    out("  Стратегия: ставим лимит на offset% ниже текущей цены, ждём timeout минут.")
    out("  Если не заполнился — fallback на market order.")
    out("")
    out("### Для ВЫХОДА (Sell):")
    out(f"  {sell_best_ev_combo}")
    out("  Стратегия: ставим лимит на offset% выше текущей цены, ждём timeout минут.")
    out("  Если не заполнился — fallback на market order.")

    # ---- DETAILED RETRACEMENT STATS ----
    out("\n## Статистика откатов после входа")
    out("\nДля каждой минуты: средний и медианный откат от цены входа (%).")
    out("")
    out("| Минута | Средний откат | Медианный откат | Макс откат | % с откатом >1% | % с откатом >3% |")
    out("|--------|---------------|-----------------|------------|-----------------|-----------------|")

    for w in FINE_WINDOWS:
        retracements = []
        for ed in entry_data:
            min_price = ed["min_by_min"].get(w)
            if min_price is not None:
                retr = (ed["avg_entry"] - min_price) / ed["avg_entry"] * 100
                retracements.append(retr)

        if retracements:
            avg_r = sum(retracements) / len(retracements)
            sorted_r = sorted(retracements)
            median_r = sorted_r[len(sorted_r)//2]
            max_r = max(retracements)
            pct_gt1 = sum(1 for r in retracements if r > 1) / len(retracements) * 100
            pct_gt3 = sum(1 for r in retracements if r > 3) / len(retracements) * 100
            out(f"| {w:>3} мин | {avg_r:>12.1f}% | {median_r:>14.1f}% | {max_r:>9.1f}% | {pct_gt1:>14.0f}% | {pct_gt3:>14.0f}% |")

    out("\n## Статистика отскоков после выхода")
    out("")
    out("| Минута | Средний отскок | Медианный отскок | Макс отскок | % с отскоком >1% | % с отскоком >3% |")
    out("|--------|----------------|------------------|-------------|------------------|------------------|")

    for w in FINE_WINDOWS:
        bounces = []
        for sd in sell_data:
            max_price = sd["max_by_min"].get(w)
            if max_price is not None:
                bounce = (max_price - sd["sell_price"]) / sd["sell_price"] * 100
                bounces.append(bounce)

        if bounces:
            avg_b = sum(bounces) / len(bounces)
            sorted_b = sorted(bounces)
            median_b = sorted_b[len(sorted_b)//2]
            max_b = max(bounces)
            pct_gt1 = sum(1 for b in bounces if b > 1) / len(bounces) * 100
            pct_gt3 = sum(1 for b in bounces if b > 3) / len(bounces) * 100
            out(f"| {w:>3} мин | {avg_b:>13.1f}% | {median_b:>15.1f}% | {max_b:>10.1f}% | {pct_gt1:>15.0f}% | {pct_gt3:>15.0f}% |")

    # Save
    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n\nРезультат сохранён в: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
