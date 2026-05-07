# Hedge-detector блокирует directional top-ups (override fix)

**Дата:** 2026-04-21
**Модуль:** `filters.detect_timeseries_hedge`
**Серьёзность:** средняя (пропускаем крупные bullish сигналы денизза)
**Статус:** исправлено

---

## 1. Инцидент

Вечером 21.04 денизz сделал серию крупных покупок:

| Рынок | Сторона | Сумма buy | Бот |
|---|---|---:|---|
| Trump end mil ops **Apr 30** | YES | **$2 050** | SKIP hedge |
| Trump end mil ops Apr 30 | YES | **$3 979** | SKIP hedge |
| Trump end mil ops Apr 30 | YES | $122 | SKIP hedge |
| Iran uranium surrender Apr 30 | YES | **$1 457** | SKIP hedge |

Итого **~$7.6K denizz signal упущен**. Лог:
```
[MAIN:denizz] SKIP hedge: hedge detected but we have no primary position to hedge
```

## 2. Root cause

`detect_timeseries_hedge`:
1. Находит sibling-рынки в том же event_slug (Apr 21, May 31, ...)
2. Проверяет: держит ли денизz OPPOSITE outcome на siblings
3. Если да → classified as hedge
4. Если у нас нет OPPOSITE на siblings → SKIP «нечего хеджить»

Для Trump Apr 30 конкретно:
- Денизz держит **46 185 sh NO на Trump Apr 21** (= $45 493)
- Денизz покупает YES на Apr 30 на $2-6K
- `denizz_primary_usd = $46K` — **классифицируется как hedge**
- У нас нет NO на siblings → **SKIP**

**Экономически это действительно hedge**: его YES Apr 30 покрывает tail-вероятность «end-of-ops в узком окне Apr 21 – Apr 30». Но для копибота это **directional signal**: денизz явно bullish на скорое завершение военных операций.

## 3. Фикс

Файл: [filters.py:634-660](../filters.py#L634)

Добавлены **две override**-проверки ДО классификации hedge:

```python
# Override 1: denizz already holds substantial SAME-SIDE SAME-CID position
SAME_SIDE_DIRECTIONAL_MIN_USD = 500.0
denizz_same_side_usd = get_player_usd_on_outcome(
    condition_id, wallet, outcome_cap
)
if denizz_same_side_usd >= SAME_SIDE_DIRECTIONAL_MIN_USD:
    return {**NOT_HEDGE,
            "reason": f"same-cid same-side ${denizz_same_side_usd:.0f} — directional top-up"}

# Override 2: single buy event is LARGE (conviction signal)
HEDGE_OVERRIDE_BUY_USD = 1500.0
if float(player_invested) >= HEDGE_OVERRIDE_BUY_USD:
    return {**NOT_HEDGE,
            "reason": f"large buy ${float(player_invested):.0f} — conviction override"}
```

### Что это пропустило бы в инциденте

| Denizz buy | Override | Результат |
|---|---|---|
| Trump Apr 30 $2 050 | 2 ($2050 ≥ $1500) | **ENTRY** ✓ |
| Trump Apr 30 $3 979 | 2 | **ENTRY** ✓ |
| Trump Apr 30 $122 | neither | still SKIP (правильно — дозаправка) |
| Uranium $1 457 | neither (just below $1500) | still SKIP |

Основные упущенные сигналы ($6K из $7.6K) — исправлены.

### Trade-off

Пороги ($500 same-side / $1500 event) откалиброваны так:
- НЕ пропускаем мелкий legitimate hedge-dust
- НО пропускаем large directional top-ups

Можно опустить `HEDGE_OVERRIDE_BUY_USD` до $1000 для ловли Uranium-типа сигналов — но это увеличит risk копирования настоящих крупных хеджей.

## 4. Тесты

Файл: `tests/test_hedge_directional_override.py` — **8/8 passed**:
- 2 unit: override 1 (same-side threshold)
- 1 non-regression: same-side ниже порога → still hedge
- 2 unit: override 2 (event threshold)
- 1 non-regression: event ниже порога → still hedge
- 1 non-regression: классический hedge по-прежнему ловится
- 1 non-regression: нет siblings → NOT hedge

## 5. Связь с другими фиксами сегодня

Четвёртый за сутки баг по логике exit/entry фильтров. Шаблон:
- Старое правило: жёсткий SKIP в граничном случае
- Исправление: override когда есть явный сильный сигнал (размер, cumulative, конкретный тип)

Список:
1. Cumulative >100% → теперь clamp до 100%
2. YES open не блокирует NO entry → token-level check
3. `signal_player="unknown"` → теперь разрешает follow-sell
4. **Hedge directional top-ups → теперь override** (этот)

## 6. Deliverables

| Файл | Что |
|---|---|
| `filters.py:634-660` | 2 override'а перед hedge-классификацией |
| `tests/test_hedge_directional_override.py` | 8 тестов |
| Этот документ | Анализ и обоснование |
