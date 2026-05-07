#!/usr/bin/env python3
"""
Бэктест: лимитные ордера vs рыночные.
Проверяем, были ли откаты цены после наших сделок,
и выгоднее ли было бы использовать лимитные ордера.
"""

import json
import time
import os
import sys
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

# Fix encoding for Windows console
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "positions.json")
ANALYTICS_DIR = os.path.join(os.path.dirname(__file__), "_analytics")
OUTPUT_FILE = os.path.join(ANALYTICS_DIR, "2026-04-16_limit_vs_market_backtest.md")

# Sell reasons to skip (not real trading decisions)
SKIP_SELL_REASONS = [
    "onchain_sync", "reconcile", "disappeared", "manual",
    "drift_fix", "cascade", "consolidation", "audit",
    "resting_order", "exit_skip",
]

# Cache for price history to avoid duplicate API calls
price_cache = {}


def iso_to_unix(iso_str):
    """Convert ISO timestamp string to unix timestamp (seconds)."""
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def fetch_price_history(token_id):
    """Fetch price history from Polymarket API with caching."""
    if token_id in price_cache:
        return price_cache[token_id]

    url = f"https://clob.polymarket.com/prices-history?market={token_id}&interval=max&fidelity=1"
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        history = data.get("history", [])
        # Convert to list of (timestamp, price) tuples
        points = [(int(h["t"]), float(h["p"])) for h in history]
        points.sort(key=lambda x: x[0])
        price_cache[token_id] = points
        return points
    except (HTTPError, URLError, json.JSONDecodeError, KeyError) as e:
        print(f"  API error for token {token_id[:20]}...: {e}")
        price_cache[token_id] = None
        return None


def find_min_price_in_window(prices, start_ts, window_minutes):
    """Find minimum price in [start_ts, start_ts + window_minutes*60]."""
    end_ts = start_ts + window_minutes * 60
    candidates = [p for t, p in prices if start_ts <= t <= end_ts]
    if not candidates:
        return None
    return min(candidates)


def find_max_price_in_window(prices, start_ts, window_minutes):
    """Find maximum price in [start_ts, start_ts + window_minutes*60]."""
    end_ts = start_ts + window_minutes * 60
    candidates = [p for t, p in prices if start_ts <= t <= end_ts]
    if not candidates:
        return None
    return max(candidates)


def should_skip_sell(reason):
    """Check if sell reason should be skipped."""
    reason_lower = reason.lower()
    for skip in SKIP_SELL_REASONS:
        if skip in reason_lower:
            return True
    return False


def main():
    with open(POSITIONS_FILE) as f:
        data = json.load(f)

    positions = data["positions"]

    # === ENTRY ANALYSIS ===
    entry_results = []
    entry_skipped = 0
    entry_api_fail = 0
    tokens_fetched = set()

    print("=" * 70)
    print("АНАЛИЗ ПОКУПОК (Entry)")
    print("=" * 70)

    for pid, pos in positions.items():
        avg_entry = pos.get("avg_entry", 0)
        token_id = pos.get("token_id", "")
        timestamp = pos.get("timestamp", "")
        cost_usd = pos.get("cost_usd", 0)
        title = pos.get("title", "unknown")

        # Filters
        if avg_entry > 1.0 or avg_entry <= 0:
            entry_skipped += 1
            continue
        if not token_id or not timestamp:
            entry_skipped += 1
            continue

        # Calculate our shares from cost
        our_shares = cost_usd / avg_entry if avg_entry > 0 else 0

        entry_ts = iso_to_unix(timestamp)

        # Fetch price history (with rate limiting)
        if token_id not in tokens_fetched:
            tokens_fetched.add(token_id)
            if token_id not in price_cache:
                time.sleep(0.5)

        prices = fetch_price_history(token_id)
        if prices is None:
            entry_api_fail += 1
            continue

        min_30 = find_min_price_in_window(prices, entry_ts, 30)
        min_60 = find_min_price_in_window(prices, entry_ts, 60)

        if min_30 is None and min_60 is None:
            entry_api_fail += 1
            continue

        # Determine outcome for "missed entry" cost calculation
        status = pos.get("status", "")
        final_pnl = pos.get("final_pnl", 0)

        entry_results.append({
            "title": title[:50],
            "avg_entry": avg_entry,
            "min_30": min_30,
            "min_60": min_60,
            "savings_30": (avg_entry - min_30) if min_30 is not None else None,
            "savings_60": (avg_entry - min_60) if min_60 is not None else None,
            "our_shares": our_shares,
            "cost_usd": cost_usd,
            "status": status,
            "final_pnl": final_pnl,
        })

        sys.stdout.write(f"\r  Обработано позиций: {len(entry_results)}...")
        sys.stdout.flush()

    print(f"\n  Всего позиций: {len(positions)}, пропущено: {entry_skipped}, API ошибки: {entry_api_fail}")
    print(f"  Успешно проанализировано: {len(entry_results)}")

    # === SELL ANALYSIS ===
    sell_results = []
    sell_skipped = 0
    sell_api_fail = 0

    print("\n" + "=" * 70)
    print("АНАЛИЗ ПРОДАЖ (Exit)")
    print("=" * 70)

    for pid, pos in positions.items():
        token_id = pos.get("token_id", "")
        title = pos.get("title", "unknown")
        sells = pos.get("sells", [])

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

            # Fetch price history
            if token_id not in tokens_fetched:
                tokens_fetched.add(token_id)
                if token_id not in price_cache:
                    time.sleep(0.5)

            prices = fetch_price_history(token_id)
            if prices is None:
                sell_api_fail += 1
                continue

            max_30 = find_max_price_in_window(prices, sell_ts, 30)
            max_60 = find_max_price_in_window(prices, sell_ts, 60)

            if max_30 is None and max_60 is None:
                sell_api_fail += 1
                continue

            sell_results.append({
                "title": title[:50],
                "sell_price": sell_price,
                "max_30": max_30,
                "max_60": max_60,
                "improvement_30": (max_30 - sell_price) if max_30 is not None else None,
                "improvement_60": (max_60 - sell_price) if max_60 is not None else None,
                "shares": sell_shares,
                "reason": reason,
            })

        sys.stdout.write(f"\r  Обработано продаж: {len(sell_results)}...")
        sys.stdout.flush()

    print(f"\n  Всего продаж: {sum(len(p.get('sells', [])) for p in positions.values())}")
    print(f"  Пропущено (не торговые): {sell_skipped}, API ошибки: {sell_api_fail}")
    print(f"  Успешно проанализировано: {len(sell_results)}")

    # === CALCULATE STATS ===
    def calc_entry_stats(results, window):
        key_min = f"min_{window}"
        key_sav = f"savings_{window}"

        valid = [r for r in results if r[key_sav] is not None]
        if not valid:
            return None

        better_limit = [r for r in valid if r[key_sav] > 0.001]  # >0.1 cent
        better_market = [r for r in valid if r[key_sav] <= 0.001]

        avg_savings = (sum(r[key_sav] for r in better_limit) / len(better_limit)) if better_limit else 0
        avg_savings_pct = (sum(r[key_sav] / r["avg_entry"] * 100 for r in better_limit) / len(better_limit)) if better_limit else 0

        total_savings_usd = sum(r[key_sav] * r["our_shares"] for r in better_limit)

        # Loss from missed entries: positions where limit wouldn't fill and position was profitable
        total_missed_usd = 0
        for r in better_market:
            if r["status"] in ("won",):
                total_missed_usd += (1.0 - r["avg_entry"]) * r["our_shares"]
            elif r["status"] == "sold" and r.get("final_pnl", 0) > 0:
                total_missed_usd += r["final_pnl"]

        return {
            "total": len(valid),
            "better_limit": len(better_limit),
            "better_market": len(better_market),
            "avg_savings_cents": avg_savings * 100,
            "avg_savings_pct": avg_savings_pct,
            "total_savings_usd": total_savings_usd,
            "total_missed_usd": total_missed_usd,
        }

    def calc_sell_stats(results, window):
        key_max = f"max_{window}"
        key_imp = f"improvement_{window}"

        valid = [r for r in results if r[key_imp] is not None]
        if not valid:
            return None

        better_limit = [r for r in valid if r[key_imp] > 0.001]
        better_market = [r for r in valid if r[key_imp] <= 0.001]

        avg_improvement = (sum(r[key_imp] for r in better_limit) / len(better_limit)) if better_limit else 0

        total_gain_usd = sum(r[key_imp] * r["shares"] for r in better_limit)
        total_loss_usd = sum(abs(r[key_imp]) * r["shares"] for r in better_market if r[key_imp] < -0.001)

        return {
            "total": len(valid),
            "better_limit": len(better_limit),
            "better_market": len(better_market),
            "avg_improvement_cents": avg_improvement * 100,
            "total_gain_usd": total_gain_usd,
            "total_loss_usd": total_loss_usd,
        }

    e30 = calc_entry_stats(entry_results, 30)
    e60 = calc_entry_stats(entry_results, 60)
    s30 = calc_sell_stats(sell_results, 30)
    s60 = calc_sell_stats(sell_results, 60)

    # === OUTPUT ===
    lines = []

    def out(text=""):
        print(text)
        lines.append(text)

    out("\n" + "=" * 70)
    out("## Бэктест: Лимитные ордера vs Рыночные")
    out("=" * 70)

    out(f"\n### ПОКУПКИ (Entry)")
    out(f"Проанализировано: {len(entry_results)} позиций (из {len(positions)} — для {entry_api_fail} не удалось получить данные, {entry_skipped} пропущено по фильтрам)")
    out("")

    if e30 and e60:
        out(f"| Метрика | 30 мин окно | 60 мин окно |")
        out(f"|---------|-------------|-------------|")
        out(f"| Откат был (лимит лучше) | {e30['better_limit']} из {e30['total']} ({e30['better_limit']/e30['total']*100:.0f}%) | {e60['better_limit']} из {e60['total']} ({e60['better_limit']/e60['total']*100:.0f}%) |")
        out(f"| Откат не было (рынок лучше) | {e30['better_market']} из {e30['total']} ({e30['better_market']/e30['total']*100:.0f}%) | {e60['better_market']} из {e60['total']} ({e60['better_market']/e60['total']*100:.0f}%) |")
        out(f"| Средняя экономия (когда откат был) | {e30['avg_savings_cents']:.1f}¢ на share | {e60['avg_savings_cents']:.1f}¢ на share |")
        out(f"| Средняя экономия в % от цены входа | {e30['avg_savings_pct']:.1f}% | {e60['avg_savings_pct']:.1f}% |")
        out(f"| Суммарная экономия (USD на наших размерах) | ${e30['total_savings_usd']:.2f} | ${e60['total_savings_usd']:.2f} |")
        out(f"| Суммарная потеря (если лимит не заполнился) | ${e30['total_missed_usd']:.2f} | ${e60['total_missed_usd']:.2f} |")
    else:
        out("Недостаточно данных для анализа покупок.")

    out(f"\n### ПРОДАЖИ (Exit)")
    out(f"Проанализировано: {len(sell_results)} продаж (пропущено не-торговых: {sell_skipped}, API ошибки: {sell_api_fail})")
    out("")

    if s30 and s60:
        out(f"| Метрика | 30 мин окно | 60 мин окно |")
        out(f"|---------|-------------|-------------|")
        out(f"| Откат вверх был (лимит лучше) | {s30['better_limit']} из {s30['total']} ({s30['better_limit']/s30['total']*100:.0f}%) | {s60['better_limit']} из {s60['total']} ({s60['better_limit']/s60['total']*100:.0f}%) |")
        out(f"| Откат не было (рынок лучше) | {s30['better_market']} из {s30['total']} ({s30['better_market']/s30['total']*100:.0f}%) | {s60['better_market']} из {s60['total']} ({s60['better_market']/s60['total']*100:.0f}%) |")
        out(f"| Средний выигрыш (когда откат был) | {s30['avg_improvement_cents']:.1f}¢ на share | {s60['avg_improvement_cents']:.1f}¢ на share |")
        out(f"| Суммарный выигрыш | ${s30['total_gain_usd']:.2f} | ${s60['total_gain_usd']:.2f} |")
    else:
        out("Недостаточно данных для анализа продаж.")

    out(f"\n### Итог")
    out(f"| Сценарий | Суммарный эффект |")
    out(f"|----------|-----------------|")
    if e30:
        net_e30 = e30['total_savings_usd'] - e30['total_missed_usd']
        sign_e30 = "+" if net_e30 >= 0 else ""
        out(f"| Лимит на вход (30м) | {sign_e30}${net_e30:.2f} |")
    if e60:
        net_e60 = e60['total_savings_usd'] - e60['total_missed_usd']
        sign_e60 = "+" if net_e60 >= 0 else ""
        out(f"| Лимит на вход (60м) | {sign_e60}${net_e60:.2f} |")
    if s30:
        sign_s30 = "+" if s30['total_gain_usd'] >= 0 else ""
        out(f"| Лимит на выход (30м) | {sign_s30}${s30['total_gain_usd']:.2f} |")
    if s60:
        sign_s60 = "+" if s60['total_gain_usd'] >= 0 else ""
        out(f"| Лимит на выход (60м) | {sign_s60}${s60['total_gain_usd']:.2f} |")

    # === DETAIL TABLE: ENTRIES ===
    out(f"\n### Детализация по покупкам")
    out(f"| Market | Entry | Min 30m | Min 60m | Savings 30m | Savings 60m | Our Size USD |")
    out(f"|--------|-------|---------|---------|-------------|-------------|--------------|")
    for r in sorted(entry_results, key=lambda x: -(x.get("savings_60") or 0)):
        s30v = f"{r['savings_30']*100:.1f}¢" if r['savings_30'] is not None else "N/A"
        s60v = f"{r['savings_60']*100:.1f}¢" if r['savings_60'] is not None else "N/A"
        m30v = f"{r['min_30']:.3f}" if r['min_30'] is not None else "N/A"
        m60v = f"{r['min_60']:.3f}" if r['min_60'] is not None else "N/A"
        color30 = "+" if r.get('savings_30') and r['savings_30'] > 0.001 else "-" if r.get('savings_30') and r['savings_30'] < -0.001 else "="
        color60 = "+" if r.get('savings_60') and r['savings_60'] > 0.001 else "-" if r.get('savings_60') and r['savings_60'] < -0.001 else "="
        out(f"| {r['title'][:45]} | {r['avg_entry']:.3f} | {m30v} | {m60v} | {color30}{s30v} | {color60}{s60v} | ${r['cost_usd']:.2f} |")

    # === DETAIL TABLE: SELLS ===
    out(f"\n### Детализация по продажам")
    out(f"| Market | Sell Price | Max 30m | Max 60m | Improv 30m | Improv 60m | Shares | Reason |")
    out(f"|--------|-----------|---------|---------|------------|------------|--------|--------|")
    for r in sorted(sell_results, key=lambda x: -(x.get("improvement_60") or 0)):
        i30v = f"{r['improvement_30']*100:.1f}¢" if r['improvement_30'] is not None else "N/A"
        i60v = f"{r['improvement_60']*100:.1f}¢" if r['improvement_60'] is not None else "N/A"
        m30v = f"{r['max_30']:.3f}" if r['max_30'] is not None else "N/A"
        m60v = f"{r['max_60']:.3f}" if r['max_60'] is not None else "N/A"
        out(f"| {r['title'][:40]} | {r['sell_price']:.3f} | {m30v} | {m60v} | {i30v} | {i60v} | {r['shares']:.1f} | {r['reason'][:30]} |")

    # Save to file
    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"\n\nРезультат сохранён в: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
