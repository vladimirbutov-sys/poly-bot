# TIMEOUT retry logic не адаптивен к падению bid

**Дата:** 2026-04-22
**Модуль:** `exit_manager._execute_sell_impl`
**Серьёзность:** средняя (бросает позицию при резком обвале bid после TIMEOUT)
**Статус:** исправлено

---

## 1. Инцидент

Рынок: US x Iran permanent peace deal by April 30, 2026?
Событие: денизz продаёт 65 % своей позиции (85 % cumulative за час).

Наш бот:
- 22.04 01:19:04 — `[EXIT] Following denizz: 139.3 sh @ 0.220 | denizz_follow_85%_sell100%`
- 01:19:04 — `SELL order placed: 139.3 shares @ 0.220`
- 01:24:57 — `[EXIT] Sell not filled (TIMEOUT)`
- 01:30:05 — новый ордер 139.3 sh @ **$0.220** (retry на -2% от original)
- 01:35:12 — снова TIMEOUT

**Итог:** 139 sh зависли, bid опустился до $0.14 пока мы стояли с ордерами по $0.22.

## 2. Root cause

Старый код в `exit_manager.py:674-692` (до фикса):

```python
# Nothing filled — try again at lower price
print(f"[EXIT] Sell not filled ({status}): {title[:50]}")
new_price = round(price * 0.98, 2)    # <-- price = оригинал $0.22
if new_price > 0.01:                  # <-- 0.22 × 0.98 = 0.216, не 0.14!
    result2 = executor.place_limit_sell(token_id, new_price, shares)
    ...
```

Проблемы:
1. **Не читает актуальный bid** — использует stale price первого ордера
2. **Только одна** попытка retry
3. **Фиксированный −2 %** от stale цены → не приспосабливается к скорости падения рынка

В нашем инциденте bid упал с $0.23 → $0.14 (−39 %) пока мы retry'или. Нужно было идти минимум на $0.14 × 0.95 = $0.133, чтобы cross-d book.

## 3. Фикс

Файл: [exit_manager.py:674-720](../exit_manager.py#L674)

Заменён single-retry на **adaptive ladder**:

```python
print(f"[EXIT] Sell not filled ({status}): {title[:50]} — entering adaptive retry")
remaining = shares
retry_ladder = [0.98, 0.95, 0.90]  # fractions below FRESH bid
for attempt, factor in enumerate(retry_ladder, 1):
    if remaining < 0.5:
        break
    # Read FRESH bid each retry — adapt to market moves
    bid, _ask = filters.get_orderbook_prices(token_id)
    base = float(bid) if bid and bid > 0 else float(price)
    new_price = round(base * factor, 4)
    ...
    result2 = executor.place_limit_sell(token_id, new_price, remaining)
    fill2 = executor.wait_for_fill_with_details(result2["order_id"], timeout=180)
    s2 = fill2.get("status")
    m2 = float(fill2.get("size_matched", 0) or 0)
    if s2 == "MATCHED":
        ...record, return
    if s2 == "PARTIAL" and m2 > 0.5:
        ...record partial, subtract from remaining, continue
```

### Ключевые изменения

| Аспект | Было | Стало |
|---|---|---|
| Источник цены | stale original × 0.98 | **fresh bid × factor** каждую попытку |
| Кол-во попыток | 1 | **3** (ladder 0.98, 0.95, 0.90) |
| Partial fill handling | мог потеряться | **subtract matched, continue** с remaining |
| Fallback | n/a | если bid=0 → original × factor |

### Что это пропустило бы в инциденте

| Попытка | Bid в момент | Цена retry | Результат |
|---|---:|---:|---|
| Initial | $0.23 | $0.22 | TIMEOUT |
| **Retry 1 (FRESH bid × 0.98)** | $0.15 | **$0.147** | Скорее всего fill — cross the book |
| Retry 2 (bid × 0.95) | $0.14 | $0.133 | backup если 1-й не прошёл |
| Retry 3 (bid × 0.90) | $0.14 | $0.126 | final fallback |

Минимальный revenue был бы ~139 × $0.14 = **$19.46** вместо $0 (позиция зависла).

## 4. Тесты

Файл: `tests/test_adaptive_retry.py` — **5/5 passed**:

1. `test_retry_reads_fresh_bid` — **воспроизведение инцидента**: original $0.22, bid $0.14 → retry использует **свежий** bid, не stale
2. `test_retry_ladder_walks_deeper` — все 3 retry TIMEOUT → ladder 0.98/0.95/0.90 от fresh bid
3. `test_retry_first_attempt_succeeds` — retry 1 MATCHED → больше попыток нет
4. `test_fallback_to_original_price_when_no_bid` — bid=0 fallback на original × factor
5. `test_retry_partial_tracks_remaining` — partial 40/100 на retry 1 → retry 2 запрашивает остаток 60

## 5. Trade-off

- **Risk sell too low:** если bid temporarily пропал из стакана (сеть моргнула), retry может выставить слишком низкую цену. Mitigation: мы всё равно crossing через бид, fill происходит по **лучшему доступному bid** в стакане, не по нашей квоте.
- **Latency:** 3 × 180 sec = до 9 минут на полный цикл retries. Достаточно для нормализации стакана, не критично.

## 6. Связь с другими фиксами сегодня

6-й баг за 48 часов в exit/entry logic:

| # | Баг | Модуль |
|---|---|---|
| 1 | cumul >100% → dust | exit_manager tier loop |
| 2 | YES open blocks NO entry | main/tracker |
| 3 | unknown signal_player blocks follow-sell | exit_manager |
| 4 | hedge blocks directional top-up | filters |
| 5 | Rule C blocks large accumulation | main |
| **6** | **TIMEOUT retry stale-price** | **exit_manager** |

Общая тема: **жёсткие simple-правила vs адаптация к market state**. Фиксы читают live данные (bid, player positions, cumulative size) вместо slepo применять стартовую логику.

## 7. Deliverables

| Файл | Что |
|---|---|
| `exit_manager.py:674-720` | Adaptive retry ladder (3 попытки, fresh bid) |
| `tests/test_adaptive_retry.py` | 5 тестов |
| Этот документ | Анализ + обоснование |
