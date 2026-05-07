"""
Бэктест трёх вариантов exit-стратегии на реальных данных бота.
Вариант A: Не продавать в убыток при частичных продажах денизза (<50%)
Вариант B: Продавать только выше входа (break-even)
Вариант C: Пропорциональный PnL-фильтр (три уровня)
"""

import json
import re
import os
import sys
from datetime import datetime

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8')

BOT_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Load data ---
with open(os.path.join(BOT_DIR, "positions.json"), encoding="utf-8") as f:
    positions = json.load(f)["positions"]

with open(os.path.join(BOT_DIR, "_analytics", "data", "denizz_resolutions.json"), encoding="utf-8") as f:
    resolutions = json.load(f)

# --- Helpers ---

def is_follow_sell(reason: str) -> bool:
    """Определяет, является ли продажа follow-продажей за денизом.
    Включает: denizz_follow_*, denizz_loss_follow_*, denizz_mirror_*,
    denizz_partial_*, denizz_big_dump_*, follow_denizz_*, manual_*_follow_denizz,
    denizz_full_exit, denizz_sell_detected.
    Исключает: stop_loss, price_target_99c, manual_sell_all, onchain_sync*"""
    r = reason.lower()
    # Явные исключения — не follow sell
    if any(x in r for x in ["stop_loss", "price_target", "onchain", "cascade", "drift_fix",
                              "resting_order", "consolidation", "car_"]):
        return False
    if r == "manual_sell_all":
        return False
    # Follow patterns
    if any(x in r for x in ["follow", "denizz_mirror", "denizz_partial",
                              "denizz_big_dump", "denizz_full_exit", "denizz_sell_detected"]):
        return True
    return False


def extract_denizz_sold_pct(reason: str) -> float | None:
    """Извлекает процент продажи денизза из reason string.
    Для denizz_follow_XX%_sellYY% — берём XX (denizz sold XX%).
    Для denizz_loss_follow_XX% — берём XX.
    Для denizz_mirror_*_XX% — берём XX.
    Для denizz_partial_XX% — берём XX.
    Для denizz_big_dump_XX% — берём XX.
    """
    r = reason.lower()
    # denizz_follow_XX%_sellYY% — first number is denizz's sold pct
    m = re.search(r'(\d+)%', r)
    if m:
        return float(m.group(1))
    # Special cases
    if "100%" in r or "full_exit" in r or "sell_detected" in r:
        return 100.0
    if "manual_50pct_follow" in r:
        return 50.0
    return None


def position_won(pos: dict, res_data: dict) -> bool | None:
    """Определяет, выиграла ли наша позиция.
    True = рынок resolved в нашу сторону (наш outcome = winning outcome)
    False = рынок resolved против нас
    None = не resolved"""
    cid = pos.get("condition_id")
    if not cid or cid not in res_data:
        return None
    res = res_data[cid]
    if not res.get("resolved"):
        return None
    winning = res.get("winning_outcome", "")
    our_outcome = pos.get("outcome", "")
    return our_outcome == winning


def hypothetical_pnl_for_blocked_sell(sell: dict, avg_entry: float, won: bool) -> float:
    """Считает разницу PnL если бы мы НЕ продали эти shares.
    won=True: получили бы $1/share вместо sell.price
    won=False: получили бы $0/share вместо sell.price
    Возвращает ДЕЛЬТУ к реальному PnL (положительная = лучше)"""
    shares = sell["shares"]
    actual_revenue = sell["revenue"]
    if won:
        hypothetical_revenue = shares * 1.0
    else:
        hypothetical_revenue = 0.0
    return hypothetical_revenue - actual_revenue


# --- Build extended resolution map ---
# 1. From resolutions file (by condition_id)
# 2. From won/lost positions (cross-reference by condition_id)

# Cross-reference: collect known outcomes from won/lost positions
known_from_status = {}
for pid, pos in positions.items():
    cid = pos.get("condition_id", "")
    if pos["status"] == "won":
        known_from_status[cid] = pos.get("outcome", "")  # winning outcome
    elif pos["status"] == "lost":
        # If our position lost, the winning outcome is the OTHER one
        our_out = pos.get("outcome", "")
        if our_out == "Yes":
            known_from_status[cid] = "No"
        elif our_out == "No":
            known_from_status[cid] = "Yes"
        # For non-binary outcomes, skip

def position_won_extended(pos: dict) -> bool | None:
    """Расширенное определение — сначала по статусу, потом resolutions, потом cross-ref."""
    if pos["status"] == "won":
        return True
    if pos["status"] == "lost":
        return False

    cid = pos.get("condition_id", "")
    our_outcome = pos.get("outcome", "")

    # Check resolutions file
    if cid in resolutions and resolutions[cid].get("resolved"):
        return our_outcome == resolutions[cid].get("winning_outcome", "")

    # Cross-reference with won/lost positions
    if cid in known_from_status:
        return our_outcome == known_from_status[cid]

    return None


# --- Main backtest ---

results = {
    "total_positions": 0,
    "closed_positions": 0,
    "resolved_positions": 0,
    "bad_data": 0,
    "unresolved_skipped": 0,
    "real_pnl": 0.0,
}

variants = {}
for v in ["A", "B", "C"]:
    variants[v] = {
        "blocked_sells": 0,
        "blocked_won": 0,
        "blocked_lost": 0,
        "blocked_unresolved": 0,
        "saved_usd": 0.0,    # Сэкономлено (blocked + won)
        "lost_usd": 0.0,     # Потеряно (blocked + lost)
        "delta_pnl": 0.0,    # Чистый эффект
        "details": [],        # Детализация каждой заблокированной продажи
    }

for pid, pos in positions.items():
    results["total_positions"] += 1

    # Только закрытые позиции
    if pos["status"] == "open" or pos["status"] == "merged_into_primary":
        continue

    results["closed_positions"] += 1

    avg_entry = pos.get("avg_entry", 0)
    if avg_entry > 1.0:
        results["bad_data"] += 1
        continue

    # Check resolution (extended: resolutions file + cross-reference + status)
    won = position_won_extended(pos)

    sells = pos.get("sells", [])

    # Real PnL — используем final_pnl как есть (уже посчитан ботом)
    real_pnl = pos.get("final_pnl", 0) or 0
    results["real_pnl"] += real_pnl

    if won is None:
        results["unresolved_skipped"] += 1
    else:
        results["resolved_positions"] += 1

    for sell in sells:
        reason = sell.get("reason", "")
        sell_price = sell.get("price", 0)
        shares = sell.get("shares", 0)
        sell_pnl = sell.get("pnl", 0)
        is_follow = is_follow_sell(reason)
        in_loss = sell_price < avg_entry
        denizz_pct = extract_denizz_sold_pct(reason)
        our_pnl_pct = (sell_price - avg_entry) / avg_entry if avg_entry > 0 else 0

        detail_base = {
            "market": pos.get("title", ""),
            "condition_id": pos.get("condition_id", ""),
            "outcome": pos.get("outcome", ""),
            "avg_entry": avg_entry,
            "sell_price": sell_price,
            "shares": shares,
            "reason": reason,
            "denizz_pct": denizz_pct,
            "our_pnl_pct": round(our_pnl_pct * 100, 1),
            "won": won,
            "actual_sell_pnl": sell_pnl,
        }

        # === Вариант A: Не продавать в убыток при частичных follow (<50%) ===
        block_a = False
        if is_follow and in_loss and denizz_pct is not None and denizz_pct < 50:
            block_a = True
        elif is_follow and in_loss and denizz_pct is None:
            # Неизвестный процент — не блокируем (оставляем как есть)
            pass

        if block_a:
            variants["A"]["blocked_sells"] += 1
            if won is None:
                variants["A"]["blocked_unresolved"] += 1
            elif won:
                variants["A"]["blocked_won"] += 1
                delta = hypothetical_pnl_for_blocked_sell(sell, avg_entry, True)
                variants["A"]["saved_usd"] += delta
                variants["A"]["delta_pnl"] += delta
            else:
                variants["A"]["blocked_lost"] += 1
                delta = hypothetical_pnl_for_blocked_sell(sell, avg_entry, False)
                variants["A"]["lost_usd"] += abs(delta) if delta < 0 else 0
                variants["A"]["saved_usd"] += delta if delta > 0 else 0
                variants["A"]["delta_pnl"] += delta
            d = detail_base.copy()
            d["variant"] = "A"
            d["delta"] = hypothetical_pnl_for_blocked_sell(sell, avg_entry, won) if won is not None else None
            d["effect"] = "won" if won else ("lost" if won is False else "unresolved")
            variants["A"]["details"].append(d)

        # === Вариант B: Продавать только выше входа ===
        block_b = False
        if in_loss:
            block_b = True

        if block_b:
            variants["B"]["blocked_sells"] += 1
            if won is None:
                variants["B"]["blocked_unresolved"] += 1
            elif won:
                variants["B"]["blocked_won"] += 1
                delta = hypothetical_pnl_for_blocked_sell(sell, avg_entry, True)
                variants["B"]["saved_usd"] += delta
                variants["B"]["delta_pnl"] += delta
            else:
                variants["B"]["blocked_lost"] += 1
                delta = hypothetical_pnl_for_blocked_sell(sell, avg_entry, False)
                variants["B"]["lost_usd"] += abs(delta) if delta < 0 else 0
                variants["B"]["saved_usd"] += delta if delta > 0 else 0
                variants["B"]["delta_pnl"] += delta
            d = detail_base.copy()
            d["variant"] = "B"
            d["delta"] = hypothetical_pnl_for_blocked_sell(sell, avg_entry, won) if won is not None else None
            d["effect"] = "won" if won else ("lost" if won is False else "unresolved")
            variants["B"]["details"].append(d)

        # === Вариант C: Пропорциональный PnL-фильтр ===
        block_c = False
        if is_follow:
            if our_pnl_pct >= -0.10:
                # PnL > -10% — продаём как обычно, не блокируем
                pass
            elif our_pnl_pct >= -0.30:
                # PnL от -10% до -30% — блокируем если denizz sold < 40%
                if denizz_pct is not None and denizz_pct < 40:
                    block_c = True
            else:
                # PnL хуже -30% — блокируем если denizz sold < 70%
                if denizz_pct is not None and denizz_pct < 70:
                    block_c = True

        if block_c:
            variants["C"]["blocked_sells"] += 1
            if won is None:
                variants["C"]["blocked_unresolved"] += 1
            elif won:
                variants["C"]["blocked_won"] += 1
                delta = hypothetical_pnl_for_blocked_sell(sell, avg_entry, True)
                variants["C"]["saved_usd"] += delta
                variants["C"]["delta_pnl"] += delta
            else:
                variants["C"]["blocked_lost"] += 1
                delta = hypothetical_pnl_for_blocked_sell(sell, avg_entry, False)
                variants["C"]["lost_usd"] += abs(delta) if delta < 0 else 0
                variants["C"]["saved_usd"] += delta if delta > 0 else 0
                variants["C"]["delta_pnl"] += delta
            d = detail_base.copy()
            d["variant"] = "C"
            d["delta"] = hypothetical_pnl_for_blocked_sell(sell, avg_entry, won) if won is not None else None
            d["effect"] = "won" if won else ("lost" if won is False else "unresolved")
            variants["C"]["details"].append(d)


# --- Calculate hypothetical PnLs ---
hypo_pnl = {}
for v in ["A", "B", "C"]:
    hypo_pnl[v] = results["real_pnl"] + variants[v]["delta_pnl"]


# --- Output ---

def fmt(x):
    sign = "+" if x > 0 else ""
    return f"{sign}${x:.2f}" if x != 0 else "$0.00"

def fmt_abs(x):
    return f"${x:.2f}"

separator = "=" * 80

output_lines = []
def p(line=""):
    print(line)
    output_lines.append(line)

p(separator)
p("## Сводка бэктеста exit-стратегий")
p(separator)
p()
p(f"Всего позиций: {results['total_positions']}")
p(f"Закрытых позиций: {results['closed_positions']}")
p(f"  - Resolved (есть итог рынка): {results['resolved_positions']}")
p(f"  - Unresolved (нет данных): {results['unresolved_skipped']}")
p(f"  - Bad data (avg_entry > 1): {results['bad_data']}")
p()
p(f"| {'Метрика':<45} | {'Реальный':>12} | {'Вариант A':>12} | {'Вариант B':>12} | {'Вариант C':>12} |")
p(f"|{'-'*47}|{'-'*14}|{'-'*14}|{'-'*14}|{'-'*14}|")
p(f"| {'Суммарный PnL':<45} | {fmt_abs(results['real_pnl']):>12} | {fmt_abs(hypo_pnl['A']):>12} | {fmt_abs(hypo_pnl['B']):>12} | {fmt_abs(hypo_pnl['C']):>12} |")
p(f"| {'Продаж заблокировано':<45} | {'—':>12} | {variants['A']['blocked_sells']:>12} | {variants['B']['blocked_sells']:>12} | {variants['C']['blocked_sells']:>12} |")
p(f"| {'Из них рынок потом WON':<45} | {'—':>12} | {variants['A']['blocked_won']:>12} | {variants['B']['blocked_won']:>12} | {variants['C']['blocked_won']:>12} |")
p(f"| {'Из них рынок потом LOST':<45} | {'—':>12} | {variants['A']['blocked_lost']:>12} | {variants['B']['blocked_lost']:>12} | {variants['C']['blocked_lost']:>12} |")
p(f"| {'Из них unresolved':<45} | {'—':>12} | {variants['A']['blocked_unresolved']:>12} | {variants['B']['blocked_unresolved']:>12} | {variants['C']['blocked_unresolved']:>12} |")
p(f"| {'Сэкономлено (blocked -> рынок won)':<45} | {'---':>12} | {fmt(variants['A']['saved_usd']):>12} | {fmt(variants['B']['saved_usd']):>12} | {fmt(variants['C']['saved_usd']):>12} |")
p(f"| {'Потеряно (blocked -> рынок lost -> $0)':<45} | {'---':>12} | {fmt_abs(variants['A']['lost_usd']):>12} | {fmt_abs(variants['B']['lost_usd']):>12} | {fmt_abs(variants['C']['lost_usd']):>12} |")
p(f"| {'Чистый эффект vs реальный':<45} | {'—':>12} | {fmt(variants['A']['delta_pnl']):>12} | {fmt(variants['B']['delta_pnl']):>12} | {fmt(variants['C']['delta_pnl']):>12} |")
p()

# --- Detail tables ---
for v in ["A", "B", "C"]:
    details = variants[v]["details"]
    if not details:
        p(f"\n### Вариант {v}: нет заблокированных продаж")
        continue
    p(f"\n### Вариант {v}: детализация заблокированных продаж ({len(details)} шт.)")
    p()
    p(f"| {'#':>3} | {'Рынок':<40} | {'Outcome':>7} | {'Entry':>6} | {'Sell$':>6} | {'Shares':>7} | {'Denizz%':>7} | {'PnL%':>6} | {'WON?':>5} | {'Дельта$':>9} | {'Reason':<40} |")
    p(f"|{'-'*5}|{'-'*42}|{'-'*9}|{'-'*8}|{'-'*8}|{'-'*9}|{'-'*9}|{'-'*8}|{'-'*7}|{'-'*11}|{'-'*42}|")
    for i, d in enumerate(details, 1):
        title = d["market"][:38]
        delta_str = fmt(d["delta"]) if d["delta"] is not None else "N/A"
        won_str = "YES" if d["won"] else ("NO" if d["won"] is False else "???")
        dpct = f"{d['denizz_pct']:.0f}%" if d["denizz_pct"] is not None else "N/A"
        p(f"| {i:>3} | {title:<40} | {d['outcome']:>7} | {d['avg_entry']:>6.3f} | {d['sell_price']:>6.3f} | {d['shares']:>7.2f} | {dpct:>7} | {d['our_pnl_pct']:>5.1f}% | {won_str:>5} | {delta_str:>9} | {d['reason']:<40} |")
    p()

# --- Save to analytics ---
analytics_dir = os.path.join(BOT_DIR, "_analytics")
os.makedirs(analytics_dir, exist_ok=True)
md_path = os.path.join(analytics_dir, "2026-04-16_exit_variants_backtest.md")
with open(md_path, "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

p(f"\nРезультат сохранён: {md_path}")
