# Rule C (whipsaw) блокирует крупную accumulation (override fix)

**Дата:** 2026-04-21
**Модуль:** `main.py` Rule C (post-exit whipsaw)
**Серьёзность:** средняя (пропускаем крупные reverse-signals после involuntary exit)
**Статус:** исправлено

---

## 1. Инцидент

21.04 22:39 на рынке «Strait of Hormuz traffic returns to normal by end of April» денизz сделал **5 покупок за 45 секунд** на общую сумму **$10 556**:

| Время | Buy USD |
|---|---:|
| 22:39:00 | $195 |
| 22:39:30 | $633 |
| 22:39:43 | **$7 638** |
| 22:39:44 | $1 900 |
| 22:39:46 | $190 |

Бот каждую из 5 покупок заблокировал:
```
[MAIN:denizz] RULE C SKIP: recent exit 2.0h ago @ 0.190, new entry @ 0.190
              (0.0% change < 5%), PnL $-209.71 <= 0 — whipsaw
```

## 2. Root cause

Rule C блокирует вход если:
1. Мы exited тот же (cid, token) в пределах POST_EXIT_WINDOW_HOURS = 12ч
2. Новая entry price отличается от exit price < 5%
3. PnL предыдущего exit'а ≤ 0 (loss)

Все 3 условия выполнены: мы вышли 2ч назад по $0.19 с −$209 loss, денизz покупает по $0.19 → whipsaw.

**Правило правильное для шумного retest'а** (денизz тестирует цену мелкими buys). Но не учитывает **conviction signal**: денизz агрессивно накапливает $10K за 45 сек — это явно новый сигнал, не шум.

## 3. Фикс

Файл: [main.py:758-781](../main.py#L758)

Добавлены **два override'а** в ветке «PnL ≤ 0, цена не изменилась»:

```python
RULE_C_OVERRIDE_SINGLE_BUY_USD = 1500.0    # override 1
RULE_C_OVERRIDE_BUFFER_USD = 3000.0        # override 2

_event_usd = float(cost_usd or 0)
_buffer_total = float(total_spent or 0)

if _event_usd >= RULE_C_OVERRIDE_SINGLE_BUY_USD:
    # conviction signal — ignore whipsaw
    pass  # fall through to normal entry logic
elif _buffer_total >= RULE_C_OVERRIDE_BUFFER_USD:
    # heavy 24h accumulation — ignore whipsaw
    pass
else:
    return  # classic SKIP
```

### Что это пропустило бы в инциденте

| Denizz buy | Buffer до | Override | Результат |
|---|---:|---|---|
| $195 | $0 | neither | SKIP (классика) |
| $633 | $195 | neither | SKIP |
| $7 638 | $828 | **1** ($7638 ≥ $1500) | **ENTRY** ✓ |
| $1 900 | $8 466 | **1** ($1900 ≥ $1500) | **ENTRY** (уже зашли, tier-upgrade) |
| $190 | $10 366 | **2** ($10366 ≥ $3000) | **ENTRY** (уже зашли) |

Бот зашёл бы на третьей покупке ($7 638) — крупнейшей и самой сильной. Мы бы захватили $10K сигнал.

### Trade-off

- Пороги ($1 500 single / $3 000 buffer) консервативные — не захватывают шумовые retest'ы
- Если денизz действительно делает whipsaw мелкими buys — ничего не меняется

## 4. Тесты

Файл: `tests/test_rule_c_override.py` — **6/6 passed**:
1. Classic whipsaw $600 buy → still SKIP (non-regression)
2. Large buy $7 638 → OVERRIDE → ENTRY (incident reproducer)
3. Threshold exact $1 500 → OVERRIDE
4. Just below $1 499 → still SKIP
5. Buffer pre-seeded $3K + small new buy → OVERRIDE (buffer path)
6. Profitable exit → Rule C ALLOW (non-regression)

## 5. Как это соотносится с hedge-фиксом

Оба фикса (#3 hedge + #4 Rule C) построены на **одной философии**:
- Жёсткий SKIP оправдан для ШУМА
- Большие convicted buys (absolute size >= threshold) обходят фильтр

Пороги несколько отличаются:
- Hedge: same-side $500 OR event $1 500
- Rule C: event $1 500 OR buffer $3 000

Можно в будущем унифицировать константы в config.py (CONVICTION_OVERRIDE_USD) — отложено.

## 6. Deliverables

| Файл | Что |
|---|---|
| `main.py:758-781` | 2 override'а в Rule C branch |
| `tests/test_rule_c_override.py` | 6 тестов |
| Этот документ | Анализ и обоснование |
