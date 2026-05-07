# Sub-market duplicate-entry guard блокирует противоположную сторону

**Дата:** 2026-04-21
**Модуль:** `main.py` (handle_buy path), `tracker.py` (`has_position_on_condition`)
**Серьёзность:** средняя (пропускаем валидные сигналы на противоположной стороне)
**Статус:** исправлено

---

## 1. Наблюдаемый инцидент

Рынок: [Will Trump visit Pakistan by May 31?](https://polymarket.com/event/will-trump-visit-pakistan-by-april-30/will-trump-visit-pakistan-by-may-31)
- CID: `0x2017a6a234f761d6a44be17094ecf247d7d1e706024edbef59d6391a3c19e1b2`
- token_id YES: `99330795757571363234851451205536017161332408986406953147002333922936546715260`
- token_id NO:  `1192802665638980616216788590237061395276410589743162170306107523355745552362`

### Что делал denizz
- 17.04: купил NO на ~$1 137
- 18.04: **полностью вышел из NO** за $1 244 (profit)
- 21.04 06:59 UTC: **re-entry NO $1 621** @ $0.685

### Что делал бот
- 17.04: корректно скопировал NO BUY (Part 1 $33.42 + докупки → cost $108)
- 18.04: скопировал SELL 100% (PARTIAL fill, остальное дошло через sync → выход в микро-плюсе +$1.19)
- **21.04 09:59:47 (UTC+3)**: на re-entry denizz'а `SKIP: Already have position on this sub-market`

### Почему SKIP был ошибкой
На момент re-entry наш tracker содержал:
```
NO side: status=sold    (старая денизz-позиция, закрыта)
YES side: status=open   (ручная $40 через _manual_buy_usiran_diplomatic_meeting_apr22_50usd.py)
```

Ручная YES-позиция не связана с сигналом denizz на NO — это разные направления, разные решения. Но бот посчитал «на рынке уже есть open позиция → значит мы уже вошли → новый сигнал дубликат».

---

## 2. Root cause

`main.py:783`:
```python
if condition_id and tracker.has_position_on_condition(data, condition_id):
    print(f"[MAIN:{player_name}] SKIP: Already have position on this sub-market {title[:40]}")
    return
```

`tracker.py:238-243`:
```python
def has_position_on_condition(data, condition_id: str) -> bool:
    """Check if we already have an open position on this specific condition_id (sub-market)."""
    for pos in data["positions"].values():
        if pos.get("status") == "open" and pos.get("condition_id") == condition_id:
            return True
    return False
```

Функция корректно фильтрует по `status==open`, но **игнорирует `outcome`/`token_id`**. Т.е. для бинарных рынков YES+NO открытая позиция на одной стороне блокирует сигнал на **другой** стороне, хотя это экономически независимые ставки.

### Когда триггерится

| У нас | Сигнал | Было | Должно быть |
|---|---|---|---|
| open denizz NO | denizz BUY NO | tier-upgrade (OK, не через этот SKIP) | tier-upgrade |
| open manual YES | denizz BUY NO | **SKIP (баг)** | **ENTRY** на NO |
| open manual NO | denizz BUY YES | **SKIP (баг)** | **ENTRY** на YES |
| open denizz NO | denizz BUY YES (хедж) | SKIP (спорно, но hedge-detector в filters.check_signal должен решить) | пусть решает filters.detect_hedge_signal |
| нет open | denizz BUY YES | ENTRY (OK) | ENTRY |

### Почему `_signaled_keys`-путь не спасает

Up-stream от SKIP-check есть `_signaled_keys` branch (tier-upgrade путь, main.py:544). Он сработал бы, если бы key был в `_signaled_keys`. Но после нашего полного exit 18.04 `_rehydrate_from_tracker` **корректно очистил** этот ключ (Direction 2, main.py:240-247). Поэтому re-entry denizz'а уходит по «new signal» path и упирается в SKIP.

Это как раз то, для чего rehydrate и нужен — дать возможность заново войти. Но следующая же проверка (has_position_on_condition) блокирует вход из-за независимой **manual-YES** на противоположной стороне.

---

## 3. Фикс

### Идея

Проверять дубликат только на **той же стороне** (same token_id), а не на всём рынке.

### Код

[tracker.py](../tracker.py) — новая функция:
```python
def has_open_position_on_token(data, token_id: str) -> bool:
    """Check if we have an OPEN position on this specific token
    (same outcome / same side of a binary market)."""
    for pos in data["positions"].values():
        if pos.get("status") == "open" and str(pos.get("token_id", "")) == str(token_id):
            return True
    return False
```

[main.py:783](../main.py#L783) — замена условия:
```python
# Fix 2026-04-21: check same-token (same outcome), not entire condition.
# Binary markets have YES and NO as independent outcomes. An open position
# on one side must not block a fresh signal on the OTHER side.
if token_id and tracker.has_open_position_on_token(data, token_id):
    print(f"[MAIN:{player_name}] SKIP: Already have open position on this token {title[:40]}")
    return
```

### Что НЕ трогаем

- Сохраняем `has_position_on_condition` как-есть — она может быть полезна в других местах (тесты, future callers).
- Не трогаем hedge-detection в filters.py — это отдельный слой и он сам решит, копировать hedge или нет.
- Не трогаем `_signaled_keys` логику — она работает корректно.

### Альтернативы, которые я рассмотрел

| Вариант | Почему отверг |
|---|---|
| Изменить `has_position_on_condition` добавив outcome-фильтр | Ломает все существующие места использования (тесты) |
| Исключать manual-позиции при проверке | Слишком специфично; упадёт если в будущем добавится sync-adopted позиция на противоположной стороне |
| Передать hedge-check первым | hedge detector сам запрашивает has_position и может решить иначе; лучше починить сам check |

---

## 4. Тесты

Файл: `tests/test_reentry_opposite_side.py`

Сценарии:
1. **Manual YES открыта → denizz BUY NO → ENTRY** (наш инцидент).
2. **denizz NO sold → manual YES open → denizz BUY NO (re-entry) → ENTRY** (полная воспроизводимость Pakistan-кейса).
3. **denizz NO open → denizz BUY NO** → tier-upgrade path (наш fix не должен это ломать).
4. **denizz NO open → new signal на NO (не в _signaled_keys)** → SKIP (same token, справедливо блокируем).

---

## 5. Воздействие на прошлые события

Поиск по bot.log за 10 дней по строке `Already have position on this sub-market` показывает, как часто SKIP срабатывал. Часть из них, возможно, была ложной (как Pakistan). Отдельная задача — прогнать диагностику и ретроспективно оценить, сколько денег/сделок мы пропустили из-за этого.

---

## 6. Что с Pakistan-позицией сейчас

- Мы **не скопировали** re-entry denizz'а на $1 621 NO
- На момент этого фикса цена NO ≈ $0.765 (было $0.685 при покупке denizz)
- **Возможность упущена**, но можно войти вручную если thesis остаётся актуальной

---

## 7. Deliverables

| Файл | Что |
|---|---|
| `tracker.py` | +`has_open_position_on_token` |
| `main.py:783-785` | Замена check на token-level |
| `tests/test_reentry_opposite_side.py` | 4 регрессионных теста |
| Этот документ | Анализ и обоснование |
