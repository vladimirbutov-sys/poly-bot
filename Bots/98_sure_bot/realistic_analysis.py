"""Realistic profit analysis: capital constraints + end_date impact on freeze time."""
import json
import sys
import os
from datetime import datetime, timezone
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# === Current bot state ===
with open('positions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

positions = data['positions']
stats = data['stats']
open_p = [p for p in positions.values() if p.get('status') == 'open']
balance = stats['current_balance']
invested = sum(p.get('cost_usd', 0) for p in open_p)
total_capital = balance + invested
BET = 5.0
max_slots = int(total_capital / BET)

print("=" * 70)
print("РЕАЛИСТИЧНЫЙ АНАЛИЗ")
print("=" * 70)
print(f"Капитал: ${total_capital:.0f} (${balance:.0f} свободно + ${invested:.0f} в ставках)")
print(f"Слоты: {max_slots} макс, {len(open_p)} занято, {max_slots - len(open_p)} свободно")

# === Actual resolve time from our bets ===
resolved_p = [p for p in positions.values() if p.get('status') in ('won', 'lost')]
resolve_times = []
for p in resolved_p:
    ts = p.get('timestamp', '')
    ra = p.get('resolved_at', '')
    if ts and ra:
        try:
            t1 = datetime.fromisoformat(ts)
            t2 = datetime.fromisoformat(ra)
            if t1.tzinfo is None:
                t1 = t1.replace(tzinfo=timezone.utc)
            if t2.tzinfo is None:
                t2 = t2.replace(tzinfo=timezone.utc)
            hours = (t2 - t1).total_seconds() / 3600
            if hours > 0:
                resolve_times.append(hours)
        except Exception:
            pass

if resolve_times:
    rt = sorted(resolve_times)
    median_h = rt[len(rt) // 2]
    print(f"\nНаши {len(rt)} закрытых ставок — время разрешения:")
    print(f"  Медиана: {median_h:.1f}ч")
    print(f"  Среднее: {sum(rt)/len(rt):.1f}ч")
    print(f"  90-й перцентиль: {rt[int(len(rt)*0.9)]:.1f}ч")
else:
    median_h = 6.0

# === Actual bets per day ===
bets_by_day = defaultdict(int)
for p in positions.values():
    day = p.get('timestamp', '')[:10]
    if day:
        bets_by_day[day] += 1

print(f"\nСтавок по дням:")
for day in sorted(bets_by_day.keys()):
    print(f"  {day}: {bets_by_day[day]}")

# === KEY QUESTION: does distant end_date = longer freeze? ===
print(f"\n{'=' * 70}")
print("КЛЮЧЕВОЙ ВОПРОС: end_date далеко = деньги заморожены дольше?")
print("=" * 70)

SCANNER_DATA = os.path.join(os.path.dirname(__file__), "..", "97_scanner", "scanner_data.json")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc_data = json.load(f)

ed_vs_resolve = []
for mid, m in sc_data["markets"].items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue
    first_seen = m.get("first_seen", "")
    closed_time = res.get("closed_time", "")
    end_date = m.get("end_date", "")
    if not first_seen or not closed_time or not end_date:
        continue
    try:
        fs = datetime.fromisoformat(first_seen)
        ct = datetime.fromisoformat(closed_time)
        if "T" in end_date:
            ed = datetime.fromisoformat(end_date)
        else:
            ed = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if fs.tzinfo is None:
            fs = fs.replace(tzinfo=timezone.utc)
        if ct.tzinfo is None:
            ct = ct.replace(tzinfo=timezone.utc)
        if ed.tzinfo is None:
            ed = ed.replace(tzinfo=timezone.utc)

        days_to_end = (ed - fs).total_seconds() / 86400
        actual_hours = (ct - fs).total_seconds() / 3600
        if actual_hours > 0 and days_to_end > 0:
            ed_vs_resolve.append({
                "days_to_end": days_to_end,
                "actual_hours": actual_hours,
            })
    except Exception:
        pass

print(f"Выборка: {len(ed_vs_resolve)} рынков")
print(f"\n{'Расстояние до end_date':>22s} | {'N':>6s} | {'Медиана resolve':>15s} | {'90-й%':>10s} | {'Макс':>8s}")
print("-" * 70)

for label, lo, hi in [
    ("< 1 день", 0, 1),
    ("1-3 дня", 1, 3),
    ("3-7 дней", 3, 7),
    ("7-14 дней", 7, 14),
    ("14-30 дней", 14, 30),
    ("30+ дней", 30, 9999),
]:
    subset = [r for r in ed_vs_resolve if lo <= r["days_to_end"] < hi]
    if not subset:
        continue
    hours = sorted([r["actual_hours"] for r in subset])
    med = hours[len(hours) // 2]
    p90 = hours[int(len(hours) * 0.9)]
    mx = hours[-1]
    print(f"{label:>22s} | {len(subset):>6d} | {med:>12.1f}ч | {p90:>8.1f}ч | {mx:>6.1f}ч")

print("""
ВЫВОД: end_date далеко НЕ значит что деньги заморожены дольше!
Рынок с end_date через 7 дней резолвится за те же ~3ч (медиана).
end_date — крайний срок, не фактическое время заморозки.
""")

# === Simulate different configs ===
print("=" * 70)
print("СИМУЛЯЦИЯ: сколько кандидатов проходят при разных end_date")
print("=" * 70)

import scanner
import filters
import tracker

print("Сканируем рынок...")
candidates = scanner.scan()
tdata = tracker.load()
open_cids = tracker.get_open_condition_ids(tdata)

orig_default = filters.MAX_END_DATE_DAYS

for default_days in [1, 2, 3, 5, 7]:
    filters.MAX_END_DATE_DAYS = default_days
    passed = []
    for c in candidates:
        p, r = filters.run_all_filters(c, open_cids, tdata)
        if p:
            passed.append(c)

    # Unique condition_ids (one bet per market)
    unique_cids = set(c["condition_id"] for c in passed)

    # Category breakdown
    cats = defaultdict(int)
    for c in passed:
        cats[c.get("category", "other")] += 1

    cat_str = ", ".join(f"{c}:{n}" for c, n in sorted(cats.items(), key=lambda x: x[1], reverse=True)[:5])
    print(f"  end_date={default_days}д: {len(passed):4d} кандидатов ({len(unique_cids)} уник. рынков) | {cat_str}")

filters.MAX_END_DATE_DAYS = orig_default

# === Capital turnover model ===
print(f"\n{'=' * 70}")
print("МОДЕЛЬ ОБОРОТА КАПИТАЛА")
print("=" * 70)

free_slots = max_slots - len(open_p)
scans_per_day = 288  # every 5 min

# With current settings: ~18 candidates pass per scan, but most repeat
# New unique candidates appear as markets open/resolve
# Estimate: ~10-20% of passed candidates are new each scan

for label, passed_per_scan, new_pct in [
    ("Текущие (1д default)", 18, 0.05),
    ("2д default", 50, 0.05),
    ("3д default", 120, 0.05),
]:
    new_per_scan = passed_per_scan * new_pct
    new_per_day = new_per_scan * scans_per_day
    # Limited by free slots
    actual_bets = min(new_per_day, free_slots * (24 / median_h))

    avg_entry = 0.985
    profit_per_bet = (1.0 - avg_entry) * BET / avg_entry  # ~$0.076

    daily_profit = actual_bets * profit_per_bet
    monthly_profit = daily_profit * 30

    print(f"\n  {label}:")
    print(f"    Проходят фильтры/скан: ~{passed_per_scan}")
    print(f"    Новых уникальных/скан: ~{new_per_scan:.1f}")
    print(f"    Новых/день: ~{new_per_day:.0f}")
    print(f"    Лимит капитала: {free_slots} слотов × {24/median_h:.1f} оборотов = {free_slots * 24/median_h:.0f}/день")
    print(f"    Реальных ставок/день: ~{actual_bets:.0f}")
    print(f"    Прибыль: ~${daily_profit:.2f}/день → ${monthly_profit:.0f}/мес")

print(f"\n{'=' * 70}")
print("ИТОГ")
print("=" * 70)
print(f"""
Текущая проблема: НЕ капитал (53 свободных слота), а ПОТОК кандидатов.

end_date=3д НЕ замораживает деньги на 3 дня:
  - Медиана фактического разрешения одинакова (~3ч) независимо от end_date
  - end_date — это крайний срок, события разрешаются по факту

Рекомендация:
  1. end_date 3д для всех (кроме soccer 1д) — разблокирует ~100+ новых кандидатов/скан
  2. Уже сделано: categorize() + politics 96% + 7д
  3. Главный эффект: больше уникальных рынков → больше ставок → больше прибыль
     при той же скорости оборота капитала
""")
