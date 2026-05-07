"""Final trader-mathematician analysis: what single change maximizes monthly profit?"""
import json
import sys
import os
import random
from datetime import datetime, timezone
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

random.seed(42)

# === Load all data ===
with open('positions.json', 'r', encoding='utf-8') as f:
    bot_data = json.load(f)

SCANNER_DATA = os.path.join(os.path.dirname(__file__), "..", "97_scanner", "scanner_data.json")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc_data = json.load(f)

# === Constants ===
positions = bot_data['positions']
stats = bot_data['stats']
open_p = [p for p in positions.values() if p.get('status') == 'open']
balance = stats['current_balance']
invested = sum(p.get('cost_usd', 0) for p in open_p)
CAPITAL = balance + invested

# Win/loss from scanner: 6710W / 7L = 99.896%
TOTAL_RESOLVED = 6717
TOTAL_LOSSES = 7
LOSS_RATE = TOTAL_LOSSES / TOTAL_RESOLVED  # 0.00104

# Resolve times from our actual bets
our_resolved = [p for p in positions.values() if p.get('status') in ('won', 'lost')]
our_resolve_hours = []
for p in our_resolved:
    ts, ra = p.get('timestamp', ''), p.get('resolved_at', '')
    if ts and ra:
        try:
            t1 = datetime.fromisoformat(ts)
            t2 = datetime.fromisoformat(ra)
            if t1.tzinfo is None: t1 = t1.replace(tzinfo=timezone.utc)
            if t2.tzinfo is None: t2 = t2.replace(tzinfo=timezone.utc)
            h = (t2 - t1).total_seconds() / 3600
            if h > 0: our_resolve_hours.append(h)
        except: pass

MEDIAN_RESOLVE_H = sorted(our_resolve_hours)[len(our_resolve_hours)//2] if our_resolve_hours else 9.2

# Average entry price from our bets
entries = [p.get('entry_price', 0) for p in positions.values() if p.get('entry_price', 0) > 0]
AVG_ENTRY = sum(entries) / len(entries)

# === Current market scan ===
import scanner
import filters
import tracker

candidates = scanner.scan()
tdata = tracker.load()

print("=" * 75)
print("АНАЛИЗ ТРЕЙДЕРА-МАТЕМАТИКА: максимизация прибыли")
print("=" * 75)
print(f"Капитал: ${CAPITAL:.0f} | Средний вход: {AVG_ENTRY:.4f}")
print(f"Scanner история: {TOTAL_RESOLVED} resolved, {TOTAL_LOSSES} losses ({LOSS_RATE*100:.3f}%)")
print(f"Медиана разрешения: {MEDIAN_RESOLVE_H:.1f}ч")
print(f"Текущих кандидатов: {len(candidates)}")

# === FORMULA ===
# Monthly profit = bets_per_month * expected_value_per_bet
# EV per bet = WR * profit_per_win - LR * loss_per_bet
# bets_per_month = min(candidate_flow, capital_throughput) * 30
# capital_throughput = slots * turnovers_per_day
# slots = capital / bet_size
# turnovers_per_day = 24 / median_resolve_hours

print(f"\n{'=' * 75}")
print("ФОРМУЛА ПРИБЫЛИ")
print("=" * 75)
print(f"""
  Прибыль/мес = Ставок/мес x EV/ставку

  EV/ставку = WR x Выигрыш - LR x Проигрыш
  Ставок/мес = min(поток кандидатов, пропускная способность капитала) x 30
  Пропускная = (Капитал / Размер ставки) x (24ч / Время разрешения)
""")

# === Estimate candidate flow ===
# With different filter configs
def count_candidates(ed_days, nr_cap, bet_size=5):
    orig_ed = filters.MAX_END_DATE_DAYS
    orig_nr = filters.MAX_NEG_RISK_FROZEN
    filters.MAX_END_DATE_DAYS = ed_days
    filters.MAX_NEG_RISK_FROZEN = nr_cap
    passed = sum(1 for c in candidates if filters.run_all_filters(c, set(), tdata)[0])
    filters.MAX_END_DATE_DAYS = orig_ed
    filters.MAX_NEG_RISK_FROZEN = orig_nr
    return passed

pool_current = count_candidates(1, 300)
pool_no_nr = count_candidates(1, 999999)
pool_no_nr_3d = count_candidates(3, 999999)
pool_no_nr_7d = count_candidates(7, 999999)

# Daily flow = pool * refresh_rate
# From scanner: ~1679 markets resolve/day out of ~6700 tracked = 25% daily refresh
# But our filtered pool is smaller and refreshes faster (sports = 2h median)
REFRESH_RATE = 0.40  # conservative: 40% of pool refreshes daily

print(f"{'=' * 75}")
print("ПУЛЫ КАНДИДАТОВ (текущий снимок, без already-bought)")
print("=" * 75)
print(f"  Текущие (nr $300, ed 1д):     {pool_current:4d}")
print(f"  Без neg_risk cap, ed 1д:      {pool_no_nr:4d}")
print(f"  Без neg_risk cap, ed 3д:      {pool_no_nr_3d:4d}")
print(f"  Без neg_risk cap, ed 7д:      {pool_no_nr_7d:4d}")

# === SIMULATE ALL SCENARIOS ===
print(f"\n{'=' * 75}")
print("СИМУЛЯЦИЯ: 30 ДНЕЙ, 1000 ПРОГОНОВ (Монте-Карло)")
print("=" * 75)

DAYS = 30
RUNS = 1000

scenarios = [
    # (name, bet_size, pool_size, ed_days, nr_cap, notes)
    ("Текущие ($5, nr $300, ed 1д)",          5,  pool_current, "базовый"),
    ("Вариант 1: bet $10 (остальное как есть)",10, pool_current, "только увеличить ставку"),
    ("Вариант 2: убрать neg_risk cap",         5,  pool_no_nr,   "только убрать neg_risk"),
    ("Вариант 3: nr off + ed 3д",              5,  pool_no_nr_3d,"убрать nr + расширить ed"),
    ("Вариант 4: bet $10 + nr off + ed 3д",   10,  pool_no_nr_3d,"всё вместе $10"),
    ("Вариант 5: bet $10 + nr off + ed 7д",   10,  pool_no_nr_7d,"максимальный"),
    ("Вариант 6: bet $7 + nr off + ed 3д",     7,  pool_no_nr_3d,"компромисс"),
]

print(f"\n{'Сценарий':52s} | {'Ставок':>7s} | {'Прибыль':>10s} | {'Проигр':>6s} | {'Макс просадка':>13s} | {'ROI':>6s}")
print("-" * 105)

for name, bet_size, pool, notes in scenarios:
    all_profits = []
    all_bets = []
    all_losses_count = []
    all_max_drawdowns = []

    for run in range(RUNS):
        capital = CAPITAL
        peak_capital = CAPITAL
        max_drawdown = 0
        total_bets = 0
        total_profit = 0
        total_losses_run = 0

        slots = int(capital / bet_size)
        daily_throughput = slots * (24 / MEDIAN_RESOLVE_H)
        daily_flow = pool * REFRESH_RATE

        win_profit = (1.0 - AVG_ENTRY) / AVG_ENTRY * bet_size

        for day in range(DAYS):
            # Day 1: initial burst
            if day == 0:
                daily_bets = min(slots, pool)
            else:
                daily_bets = int(min(daily_throughput, daily_flow))

            if daily_bets <= 0:
                continue

            # Each bet: win or lose
            for _ in range(daily_bets):
                if random.random() < LOSS_RATE:
                    capital -= bet_size
                    total_profit -= bet_size
                    total_losses_run += 1
                else:
                    capital += win_profit
                    total_profit += win_profit

                total_bets += 1

                # Track drawdown
                if capital > peak_capital:
                    peak_capital = capital
                dd = peak_capital - capital
                if dd > max_drawdown:
                    max_drawdown = dd

            # Update slots based on new capital
            slots = int(capital / bet_size)
            daily_throughput = slots * (24 / MEDIAN_RESOLVE_H)

        all_profits.append(total_profit)
        all_bets.append(total_bets)
        all_losses_count.append(total_losses_run)
        all_max_drawdowns.append(max_drawdown)

    # Statistics
    avg_profit = sum(all_profits) / RUNS
    avg_bets = sum(all_bets) / RUNS
    avg_losses = sum(all_losses_count) / RUNS
    avg_drawdown = sum(all_max_drawdowns) / RUNS
    p5_profit = sorted(all_profits)[int(RUNS * 0.05)]  # 5th percentile (worst case)
    p95_profit = sorted(all_profits)[int(RUNS * 0.95)]

    roi = avg_profit / CAPITAL * 100

    print(f"  {name:50s} | {avg_bets:>7.0f} | ${avg_profit:>+8.2f} | {avg_losses:>5.1f} | ${avg_drawdown:>11.2f} | {roi:>5.1f}%")

# === DEEP DIVE: best scenario ===
print(f"\n{'=' * 75}")
print("ДЕТАЛЬНЫЙ РАЗБОР ЛУЧШИХ ВАРИАНТОВ")
print("=" * 75)

for name, bet_size, pool, notes in scenarios:
    slots = int(CAPITAL / bet_size)
    daily_throughput = slots * (24 / MEDIAN_RESOLVE_H)
    daily_flow = pool * REFRESH_RATE
    bottleneck = "капитал" if daily_throughput < daily_flow else "кандидаты"
    daily_bets = min(daily_throughput, daily_flow)
    win_profit = (1.0 - AVG_ENTRY) / AVG_ENTRY * bet_size
    ev_per_bet = (1 - LOSS_RATE) * win_profit - LOSS_RATE * bet_size

    print(f"\n  {name}:")
    print(f"    Слотов: {slots} | Оборот: {24/MEDIAN_RESOLVE_H:.1f}x/день")
    print(f"    Пропускная: {daily_throughput:.0f}/день | Поток кандидатов: {daily_flow:.0f}/день")
    print(f"    Узкое место: {bottleneck}")
    print(f"    Ставок/день: ~{daily_bets:.0f}")
    print(f"    Выигрыш: ${win_profit:.3f} | EV/ставку: ${ev_per_bet:.4f}")
    print(f"    Ожид. прибыль/день: ${daily_bets * ev_per_bet:.2f}")

# === RISK ANALYSIS ===
print(f"\n{'=' * 75}")
print("АНАЛИЗ РИСКОВ")
print("=" * 75)

# At $10/bet, one loss = $10. How often?
# 1 loss per ~1000 bets. At 15 bets/day = ~67 days between losses
# At 500 bets/month: ~2 losses expected

for bet_size in [5, 7, 10]:
    win_profit = (1.0 - AVG_ENTRY) / AVG_ENTRY * bet_size
    bets_to_recover = bet_size / win_profit
    print(f"\n  Ставка ${bet_size}:")
    print(f"    Выигрыш: ${win_profit:.3f}")
    print(f"    Проигрыш: ${bet_size:.2f}")
    print(f"    Ставок чтобы отбить 1 проигрыш: {bets_to_recover:.0f}")
    print(f"    При {LOSS_RATE*100:.3f}% loss rate: 1 проигрыш на {1/LOSS_RATE:.0f} ставок")
    print(f"    Соотношение: каждые {1/LOSS_RATE:.0f} ставок = +${(1/LOSS_RATE - 1) * win_profit - bet_size:.2f}")

# === VERDICT ===
print(f"\n{'=' * 75}")
print("ВЕРДИКТ")
print("=" * 75)
