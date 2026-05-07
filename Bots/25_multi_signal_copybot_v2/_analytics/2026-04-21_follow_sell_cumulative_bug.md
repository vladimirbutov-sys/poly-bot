# Баг follow-sell при cumulative > 100%

**Дата:** 2026-04-21
**Модуль:** `exit_manager.py`
**Серьёзность:** средняя (потеря exit-сигналов → зависшие позиции, искажённый PnL)
**Статус:** исправлено

---

## 1. Что наблюдалось в проде

Рынок [US x Iran diplomatic meeting by April 21, 2026?](https://polymarket.com/event/us-x-iran-diplomatic-meeting-by-329/will-us-x-iran-diplomatic-meeting-happen-by-april-21):
- CID: `0x6c31c73a5447ef744d271098ce51594afa5a521fe367c07f7138c868703d693f`
- Наша позиция: 74.97 sh NO @ avg $0.76, открыта 2026-04-20 17:54 (tier-upgrade за denizz).

Денизz в течение 2026-04-21 постепенно вышел из своей NO-позиции на 100 %.

Ключевые строки `bot.log`:

```
10:48:16 [EXIT] denizz 10520 → 4906 sh (delta 5614 = 53%)
10:48:17 [EXIT] tiered: player sold 53%, we LOSS, sell 55% of our 27 sh
10:48:19 [EXIT] SOLD: 14.8 sh | $11.11          <-- первый follow-sell OK

11:02:17 [EXIT] denizz 4906 → 0 sh (delta 4906 = 100%)
11:02:17 [EXIT] CUMULATIVE TRIGGER: denizz cumul 153% over 2 events in last 60min
11:02:19 [EXIT] SKIP denizz dust sell (153%): we in PROFIT, below tier threshold
```

Второе событие — финальный 100 %-выход denizz — было ошибочно классифицировано как «dust sell» и **пропущено**. В итоге у нас осталась зависшая позиция 12 sh NO (приблизительно $9 в cost basis).

---

## 2. Root cause

### 2.1 Поток в `exit_manager.handle_player_sell`

[exit_manager.py:785](../exit_manager.py#L785) — вычисление `sold_pct` этого события:
```python
sold_pct_player = delta_sold / cached_size
# 4906 / 4906 = 1.00  (100% this-event)
```

[exit_manager.py:801-822](../exit_manager.py#L801-L822) — cumulative tracking:
```python
history.append((cumul_now, float(sold_pct_player)))
...
cumulative_pct = sum(p for _, p in history)   # 0.53 + 1.00 = 1.53
...
if will_escalate:
    sold_pct_player = cumulative_pct           # sold_pct_player = 1.53
```

[exit_manager.py:914-918 (ДО фикса)](../exit_manager.py#L914) — tier loop:
```python
our_sell_fraction = 0.0
for lo, hi, frac in tiers:
    if lo <= sold_pct_player < hi:   # 1.53 не матчит ни один tier
        our_sell_fraction = frac
        break
```

[exit_manager.py:922](../exit_manager.py#L922) — падение в dust-ветку:
```python
if our_sell_fraction <= 0:
    print(f"[EXIT] SKIP {player_name} dust sell ({pct_s}): ...")
    return
```

### 2.2 Структура tier-таблицы

[config.py:328-339](../config.py#L328):
```python
FOLLOW_SELL_TIERS_PROFIT = [
    (0.00, 0.05, 0.00),
    (0.05, 0.10, 0.10),
    (0.10, 0.20, 0.15),
    ...
    (0.80, 1.01, 1.00),   # верхняя граница 1.01 — хак для захвата 1.0000…01
]
```

Верхняя граница `1.01` была рассчитана на защиту от накопленных floating-point артефактов (например, `0.999999` или `1.00000001`), но **не учитывала**, что `CUMULATIVE TRIGGER` может штатно выставлять `sold_pct_player` значительно выше 100 % (в данном случае 153 %, теоретически — сколько угодно при фрагментации продаж).

### 2.3 Почему метка «below tier threshold» вводила в заблуждение

Логика кода пишет одно и то же сообщение и для dust (0 %-5 %), и для over-ceiling (>101 %). Оба случая приводят к `our_sell_fraction = 0.0`, но семантически это разные ситуации: первый — «микрошум, игнорировать», второй — «полный выход, максимально срочно».

---

## 3. Применённый фикс

Файл: [exit_manager.py:914-928](../exit_manager.py#L914-L928)

```python
# Fix 2026-04-21: cumul > tier table ceiling must force 100%.
# CUMULATIVE TRIGGER can escalate sold_pct_player above 1.0 (e.g. 153%
# when two sells within the rolling window each report against a
# shrinking baseline). Tier tables end at (0.80, 1.01, 1.00) — any value
# >= 1.01 falls through the loop with our_sell_fraction=0 and mis-logs
# "dust sell" on what is actually a full/over-exit signal. Clamp to the
# top tier's representative point so full-exit is fired.
effective_pct = min(float(sold_pct_player), 0.9999)
our_sell_fraction = 0.0
for lo, hi, frac in tiers:
    if lo <= effective_pct < hi:
        our_sell_fraction = frac
        break
```

Минимальный скоуп — один `min()`-clamp и замена переменной в цикле. **Таблицу tiers и саму CUMULATIVE-логику не трогаем.**

### 3.1 Почему именно clamp, а не изменение таблицы

Альтернативные варианты, которые я рассмотрел и отверг:

| Вариант | Почему отверг |
|---|---|
| Изменить tier: `(0.80, inf, 1.00)` | Правка config — требует обновления всех backtest'ов, потенциально ломает другие потребители таблицы |
| Проверка `if sold_pct_player >= 1.0: force 100%` перед циклом | Дублирует семантику таблицы. Clamp чище. |
| Поменять `will_escalate` чтобы он не выставлял >1.0 | Ломает log-читаемость (мы хотим видеть cumul 153% в логе — это сигнал) |

---

## 4. Регрессионные тесты

Файл: [tests/test_follow_sell_cumulative.py](../tests/test_follow_sell_cumulative.py)

4 кейса:
1. `test_cumul_153pct_profit_fires_full_exit` — воспроизводит **именно** инцидент 2026-04-21.
2. `test_cumul_110pct_loss_fires_full_exit` — близко к потолку 100 %, LOSS-ветка.
3. `test_cumul_300pct_profit_fires_full_exit` — экстремальное overshoot (2 prior по 100 % + новое 100 %).
4. `test_normal_95pct_profit_still_fires_full_exit` — non-regression: обычный 95 % sell без cumul эскалации должен продолжать давать 100 %.

Запуск: `python -m pytest tests/test_follow_sell_cumulative.py -v` — **4 passed**.

Полный прогон: `python -m pytest tests/` — **156 passed, 7 failed**. Все 7 падений **pre-existing** и не связаны с данным фиксом (устаревшие ассерты после более раннего изменения `FOLLOW_SELL_TIERS`, тесты в `test_manual_follow.py` падают на `peak_size=0` в блоке до моего фикса).

---

## 5. Побочные сценарии, закрытые этим фиксом

Cumulative >100 % может возникать в штатном режиме при:

1. **Фрагментированном выходе** (inc 53 % → затем 100 % от остатка = cumul 153 %) — именно этот кейс.
2. **Массивном one-shot выходе** с уже заcached'енной историей — prior 30 % + новое 100 % = 130 %.
3. **Несинхронности cache и peak** — если `_peak_get` вернул старое значение, а cache обновлялся несколько раз.

До фикса все такие кейсы давали `our_sell_fraction = 0` → SKIP.

---

## 6. Упомянутый, но НЕ исправленный баг: tracker `cost_usd` drift

Позиция `0x6b99f375a8bcde2e59443f6f8758e79bceeef580ee9ffa963f3d9f8ad1ba0996`:
- `size_shares` в tracker: `12.116` (правильно — on-chain тоже 12.14)
- `cost_usd` в tracker: `$56.97` (**устаревшее** — соответствует первоначальной покупке 74.97 sh, не текущему остатку)

Промежуточные уменьшения `size_shares` через `sync_with_onchain` (forward scan `onchain_sync_down`) в [tracker.py](../tracker.py) **не декрементировали `cost_usd` пропорционально**. То же с `_execute_sell`: в некоторых ветках фиксировалась только `sells[]` запись, `cost_usd` оставался прежним.

Следствие: финальный PnL при закрытии позиции будет **занижен**. На самом деле мы больше в плюсе, чем показывает tracker.

Фикс отложен — отдельный скоуп, не блокирует текущую задачу. Рекомендация: при каждом уменьшении `size_shares` (sell или `onchain_sync_down`) декрементировать `cost_usd` пропорционально `delta_shares / pre_shares`.

---

## 7. Deliverables

| Файл | Что |
|---|---|
| `exit_manager.py:914-928` | Patch — clamp `effective_pct` |
| `tests/test_follow_sell_cumulative.py` | 4 регрессионных теста (all pass) |
| `_manual_sell_diplomatic_meeting_apr21_bug_cleanup.py` | Ручной закрытие зависших 12 sh |
| `_analytics/2026-04-21_follow_sell_cumulative_bug.md` | Этот документ |

---

## 8. Рекомендации на будущее

1. **Лог-сообщение** «below tier threshold» заменить на осмысленное: для `sold_pct_player >= 1.0` писать «CUMULATIVE saturated — forcing 100%». Делает post-mortem легче.
2. **Метрика**: считать счётчик `cumulative_saturation_count` — сколько раз cumul вышел за tier ceiling. Для мониторинга.
3. **Tracker cost-drift fix** как отдельная задача.
