"""Monthly profit simulation: no neg_risk cap, 1 loss per 1000 bets."""
import json
import sys
import os
from datetime import datetime, timezone

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# === Load current state ===
with open('positions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

stats = data['stats']
open_p = [p for p in data['positions'].values() if p.get('status') == 'open']
balance = stats['current_balance']
invested = sum(p.get('cost_usd', 0) for p in open_p)
total_capital = balance + invested

# === Load scanner for resolve time data ===
SCANNER_DATA = os.path.join(os.path.dirname(__file__), "..", "97_scanner", "scanner_data.json")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc_data = json.load(f)

# Get actual resolve times from scanner
resolve_hours = []
for mid, m in sc_data["markets"].items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue
    fs = m.get("first_seen", "")
    ct = res.get("closed_time", "")
    if not fs or not ct:
        continue
    try:
        t1 = datetime.fromisoformat(fs)
        t2 = datetime.fromisoformat(ct)
        if t1.tzinfo is None:
            t1 = t1.replace(tzinfo=timezone.utc)
        if t2.tzinfo is None:
            t2 = t2.replace(tzinfo=timezone.utc)
        h = (t2 - t1).total_seconds() / 3600
        if 0 < h < 200:
            resolve_hours.append(h)
    except Exception:
        pass

resolve_hours.sort()
median_resolve = resolve_hours[len(resolve_hours) // 2]
avg_resolve = sum(resolve_hours) / len(resolve_hours)

# Neg_risk finalization adds ~36-57h extra after resolution
# From our data: our 24 resolved bets had median 9.2h
# But neg_risk bets take longer to get money back
# Let's use our actual data for non-neg and estimate neg separately

our_resolved = [p for p in data['positions'].values() if p.get('status') in ('won', 'lost')]
our_times = []
for p in our_resolved:
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
            h = (t2 - t1).total_seconds() / 3600
            if h > 0:
                our_times.append(h)
        except Exception:
            pass

our_median = sorted(our_times)[len(our_times) // 2] if our_times else 9.2

# === Current scan: how many candidates with no neg_risk cap? ===
import scanner
import filters
import tracker

candidates = scanner.scan()
tdata = tracker.load()
open_cids = tracker.get_open_condition_ids(tdata)

# Count with different configs
configs = [
    ("ТЕКУЩИЕ (neg_risk $300, end_date 1д)", 1, True),
    ("Без neg_risk cap, end_date 1д", 1, False),
    ("Без neg_risk cap, end_date 3д", 3, False),
    ("Без neg_risk cap, end_date 7д", 7, False),
]

print("=" * 70)
print("ТЕКУЩИЙ СНИМОК: кандидаты при разных настройках")
print("=" * 70)

for label, ed_days, use_nr_cap in configs:
    orig_ed = filters.MAX_END_DATE_DAYS
    orig_nr = filters.MAX_NEG_RISK_FROZEN
    filters.MAX_END_DATE_DAYS = ed_days
    if not use_nr_cap:
        filters.MAX_NEG_RISK_FROZEN = 999999  # effectively no cap

    passed = 0
    for c in candidates:
        p, r = filters.run_all_filters(c, set(), tdata)  # ignore already-bought
        if p:
            passed += 1

    filters.MAX_END_DATE_DAYS = orig_ed
    filters.MAX_NEG_RISK_FROZEN = orig_nr
    print(f"  {label:50s}: {passed:5d} candidates")

# === SIMULATION ===
print(f"\n{'=' * 70}")
print("МЕСЯЧНАЯ СИМУЛЯЦИЯ")
print("=" * 70)

BET = 5.0
LOSS_RATE = 1 / 1000  # 1 loss per 1000 bets
WIN_RATE = 1 - LOSS_RATE
DAYS = 30

# Entry price distribution from our actual bets
entry_prices = [p.get('entry_price', 0.985) for p in data['positions'].values()]
avg_entry = sum(entry_prices) / len(entry_prices) if entry_prices else 0.985

# Profit per winning bet
win_profit = (1.0 - avg_entry) / avg_entry * BET  # shares worth $1 each, bought at avg_entry
# Loss per losing bet
loss_amount = BET  # lose entire bet

print(f"\nПараметры:")
print(f"  Стартовый капитал: ${total_capital:.0f}")
print(f"  Ставка: ${BET:.0f}")
print(f"  Средняя цена входа: {avg_entry:.4f}")
print(f"  Прибыль/выигрыш: ${win_profit:.3f}")
print(f"  Убыток/проигрыш: ${loss_amount:.2f}")
print(f"  Win rate: {WIN_RATE*100:.1f}%")
print(f"  Медиана разрешения (наши данные): {our_median:.1f}ч")

# For each scenario: estimate daily bets and monthly profit
scenarios = [
    ("ТЕКУЩИЕ настройки", {
        "ed_days": 1, "nr_cap": 300,
        "note": "neg_risk cap $300, end_date 1д",
    }),
    ("Убрать neg_risk cap + end_date 3д", {
        "ed_days": 3, "nr_cap": 999999,
        "note": "без ограничения neg_risk, end_date 3д",
    }),
    ("Убрать neg_risk cap + end_date 3д + politics 96%", {
        "ed_days": 3, "nr_cap": 999999,
        "note": "все изменения вместе",
    }),
]

# Need to estimate: how many UNIQUE NEW candidates appear per day?
# Day 1: initial pool (all current candidates that pass)
# Day 2+: as positions resolve, new markets appear
# From scanner: ~1679 markets resolve per day at 97%+
# Not all pass our filters. Rough estimate: 10-30% pass = 170-500/day

# More precise: use turnover model
# Slots = capital / bet_size
# Each slot turns over every median_resolve hours
# Daily throughput = slots * (24 / median_resolve)

# But also limited by candidate FLOW (new markets appearing)
# From scan data: ~3700 candidates exist right now
# Markets resolve/appear at ~1679/day
# So ~45% of pool refreshes daily

REFRESH_RATE = 0.45  # fraction of candidate pool that refreshes daily

print(f"\n{'=' * 70}")

for scenario_name, cfg in scenarios:
    print(f"\n--- {scenario_name} ---")
    print(f"    ({cfg['note']})")

    # Estimate candidate pool size
    orig_ed = filters.MAX_END_DATE_DAYS
    orig_nr = filters.MAX_NEG_RISK_FROZEN
    filters.MAX_END_DATE_DAYS = cfg["ed_days"]
    filters.MAX_NEG_RISK_FROZEN = cfg["nr_cap"]

    pool_size = 0
    for c in candidates:
        p, r = filters.run_all_filters(c, set(), tdata)
        if p:
            pool_size += 1

    filters.MAX_END_DATE_DAYS = orig_ed
    filters.MAX_NEG_RISK_FROZEN = orig_nr

    # Simulate day by day
    capital = total_capital
    total_bets = 0
    total_wins = 0
    total_losses = 0
    total_profit = 0
    daily_log = []

    for day in range(1, DAYS + 1):
        slots = int(capital / BET)

        if day == 1:
            # Initial burst: fill all slots from pool
            daily_bets = min(slots, pool_size)
        else:
            # Steady state: limited by slot turnover AND new candidates
            slot_turnover = slots * (24 / our_median)  # slots freed per day
            new_candidates = pool_size * REFRESH_RATE  # new markets appearing
            daily_bets = min(slot_turnover, new_candidates, slots)

        daily_bets = int(daily_bets)
        if daily_bets <= 0:
            daily_log.append((day, 0, capital, 0))
            continue

        # Apply win/loss rate
        daily_losses = max(1, int(daily_bets * LOSS_RATE)) if daily_bets >= 1000 else (1 if daily_bets > 500 else 0)
        # More precise: for small numbers, probabilistic
        import random
        random.seed(42 + day)  # reproducible
        daily_losses = sum(1 for _ in range(daily_bets) if random.random() < LOSS_RATE)
        daily_wins = daily_bets - daily_losses

        day_profit = daily_wins * win_profit - daily_losses * loss_amount
        capital += day_profit
        total_bets += daily_bets
        total_wins += daily_wins
        total_losses += daily_losses
        total_profit += day_profit

        daily_log.append((day, daily_bets, capital, day_profit))

    # Print summary
    print(f"    Пул кандидатов: {pool_size}")
    print(f"    Слотов: {int(total_capital / BET)}")

    # Show first 5 days and last 5 days
    print(f"\n    {'День':>6s} | {'Ставок':>7s} | {'Капитал':>10s} | {'Прибыль':>10s}")
    print(f"    {'-'*45}")
    for day, bets, cap, prof in daily_log[:5]:
        print(f"    {day:>6d} | {bets:>7d} | ${cap:>9.2f} | ${prof:>+9.2f}")
    if len(daily_log) > 10:
        print(f"    {'...':>6s}")
    for day, bets, cap, prof in daily_log[-3:]:
        print(f"    {day:>6d} | {bets:>7d} | ${cap:>9.2f} | ${prof:>+9.2f}")

    print(f"\n    ИТОГ ЗА 30 ДНЕЙ:")
    print(f"    Всего ставок: {total_bets}")
    print(f"    Выигрышей: {total_wins}, Проигрышей: {total_losses}")
    print(f"    Прибыль: ${total_profit:+.2f}")
    print(f"    Капитал: ${total_capital:.0f} -> ${capital:.0f} ({(capital/total_capital - 1)*100:+.1f}%)")
    print(f"    ROI: {total_profit/total_capital*100:.1f}%")
