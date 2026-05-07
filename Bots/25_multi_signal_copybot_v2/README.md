# 25_multi_signal_copybot_v2 — бот, копирующий сделки denizz на Polymarket

**Актуально на**: 2026-04-15
**Режим**: live (DRY_RUN = False)
**Активные игроки**: только `denizz` (`0xbaa2bcb5...b4700027d1b92c73`)
**Точка входа**: `main.py` → `python -u -X utf8 main.py`
**Состояние**: `positions.json` в корне каталога

Этот README состоит из **двух частей**:

- **Часть 1** — логика входов и выходов простым языком, со всеми реализованными сценариями и реальными примерами из логов. Для владельца бота и для ревью правил.
- **Часть 2** — техническое описание архитектуры и устройства. Для разработчика, который будет менять код.

---

---

# Часть 1. Логика — простым языком

## 1. Что делает бот за одну минуту

Бот непрерывно смотрит публичный кошелёк trader'а `denizz` на Polymarket и **копирует его сделки**: когда denizz покупает — бот покупает (в пропорции к своему банку), когда denizz продаёт — бот продаёт. Плюс независимые механизмы защиты: stop-loss, target-sell, фильтры по цене/горизонту/размеру. Плюс пользователь (ты) может покупать и продавать **вручную** через `_manual_buy_*.py` / `_manual_sell_*.py` скрипты — такие позиции тоже попадают в tracker и обслуживаются ботом.

Активная стратегия:
- Банк `BANKROLL = $2700`
- Покрывает сигналы от denizz ≥ `$500` суммарных инвестиций на рынке
- Максимум одной позиции — `MAX_POSITION_USD = $300`
- Максимум одного bet — `MAX_BET_USD = $200`
- Максимум одновременных позиций — `MAX_CONCURRENT = 40`

---

## 2. Как бот ловит BUY сигнал

Сигнал проходит через **последовательность фильтров**. Если хотя бы один не пройден — бот не входит.

### Шаг A. Есть ли «живой» buy-event?

Источник — `monitor.py`, который периодически запрашивает Polymarket data-api и смотрит активность кошелька denizz. Когда обнаружен buy (`size > 0` на каком-то рынке), создаётся `event` dict с полями:

```
{
  "player": "denizz",
  "token_id": "...",
  "condition_id": "0x...",
  "price": 0.79,
  "size": 5854.8,
  "cost_usd": 4625.28,    # размер конкретной покупки
  "title": "US obtains Iranian enriched uranium by May 31?",
  "outcome": "No",
  "event_slug": "us-obtains-iranian-enriched-uranium-by-may-31",
}
```

Этот event передаётся в `main.handle_buy()` для принятия решения.

### Шаг B. Фильтр «микро-buy»: `MIN_BUY_EVENT_USD = $150`

**Первое**, что проверяется. Если `cost_usd` события меньше `$150` — сигнал полностью игнорируется, независимо от пути обработки (новый сигнал, re-entry, tier-upgrade).

> **Пример**: 2026-04-15 13:05, denizz купил всего $2 на «Iran agrees to surrender enriched uranium stockpile by April 30?» — микро-топап к его существующей $7K позиции. **До** этого фильтра бот через Rule C (re-entry, см. ниже) зашёл на $104. Теперь такой сигнал даёт в логе: `[MAIN:denizz] SKIP: buy event $2 below MIN_BUY_EVENT_USD ($150)` — и на этом всё.

### Шаг C. Буфер накопления и `MIN_PLAYER_INVESTED`

Если событие прошло фильтр $150 — оно добавляется в **24-часовой буфер** по этому (condition_id, token_id). Буфер копит суммарные buys denizz за последние 24 часа.

- Если суммарный `total_spent` в буфере **меньше** `MIN_PLAYER_INVESTED = $500` → ничего не делаем, просто ждём новых buys и копим дальше.
- Когда `total_spent ≥ $500` — шлём Telegram-уведомление «denizz buy crossed $500» и **впервые** переходим к проверкам сигнала (если этого рынка ещё нет в `_signaled_keys`).

### Шаг D. Если мы уже сигналили на этом рынке — tier-upgrade

Если рынок уже в `_signaled_keys[denizz]`, идёт путь **tier-upgrade**:

1. Получаем реальную общую инвестицию denizz в этот рынок (`filters.get_player_invested_on_token`).
2. Считаем `effective_invested = max(buffer_total, real_invested)`.
3. **Rule B (anti-chasing)**: если наша цена входа `entry_price > 1.5 × price denizz'а в этом конкретном buy-событии` → блокировка. Причина: не хотим гнаться за pumpом — если denizz покупает по $0.20, а нам надо по $0.40, это плохой трейд.
4. Считаем `new_bet` по [логарифмической формуле](#формула-размера-ставки) для `effective_invested`.
5. Считаем `increment = new_bet − already_bet` (сколько докинуть к уже имеющейся позиции).
6. Проверяем slippage — `current_ask − denizz_entry_price ≤ MAX_SLIPPAGE_TIERS` (по нашему входному цену).
7. Если `increment < MIN_UPGRADE_USD = $5` → лог `[MAIN:denizz] Already signaled (inc $X < $5 min @ $Y)`, выход.
8. Иначе — докупка на `increment`.

### Шаг E. Новый сигнал — Rule C (post-exit whipsaw)

Если рынка НЕТ в `_signaled_keys`, но у нас **была позиция на нём, которую мы закрыли недавно**, работает Rule C:

- Окно `POST_EXIT_WINDOW_HOURS` (в коде — 2 часа).
- Если с момента выхода прошло меньше окна И цена **не изменилась** существенно (`POST_EXIT_PRICE_CHANGE_MIN`) И **последний выход был в убыток** (`pnl ≤ 0`) → блокировка (`RULE C SKIP: whipsaw`).
- Если последний выход был **в прибыль** (`pnl > 0`) → **разрешено**, это не whipsaw. Лог: `Rule C ALLOW: previous exit was profitable (PnL $X)`.
- Если окно истекло — не применяется, обычный новый вход.

> **Пример**: 2026-04-15 13:05, Iran stockpile. denizz купил $2 (сейчас блокируется новым фильтром). Раньше — без фильтра — Rule C пропускал этот сигнал, потому что наш предыдущий выход на этом рынке был с прибылью $2.80. Бот входил на полный размер $104.45.

### Шаг F. Финальные фильтры `check_signal`

Даже если Rule C пропустил, вход всё ещё может быть отменён:

- **`EXCLUDED_KEYWORDS`** — рынки про крипту, инфляцию, FED исключены целиком (bitcoin, eth, inflation, rate и т.д.).
- **`PRICE_FILTER`** — цена входа должна быть в диапазоне игрока. Для denizz: `$0.05 – $0.99`.
- **`HORIZON_TIERS`** — дней до резолва рынка:
  - `0–30`: множитель 1.0
  - `30–60`: 0.8
  - `60–90`: 0.7
  - `90–120`: 0.4
  - `>120`: **0 → блок входа**
- **Opposition check** — не релевантно в текущем состоянии (только denizz активен).
- **Hedge detection** — если denizz одновременно держит противоположную сторону рынка больше нашего нового buy, это классифицируется как хедж, и применяется более строгий фильтр (`HEDGE_RATIO_MAX = 12%`, `HEDGE_MIN_GAIN_PCT = 12%`).

### Формула размера ставки

```
our_bet_base = 31.75 × ln(denizz_total_invested) − 177
```

Последовательно применяются множители:

| Множитель | Значения |
|---|---|
| `BET_SCALE` | 1.0 в live, 0.5 в test |
| `PRICE_BET_MULTIPLIERS` | 1.0 для 0–82c, 0.65 для 82–99c |
| `TOPUP_RATIO_TIERS` | `<3% → 0.0`, `3-10% → 0.5`, `10-30% → 0.75`, `30%+ → 1.0` |
| `HORIZON_TIERS` множитель | 1.0 / 0.8 / 0.7 / 0.4 / 0 |
| `calculate_entry_size_multiplier` (Rule A+) | late-gate, если текущий ask сильно выше avg denizz |

Ограничения после всех множителей:
- `MAX_BET_USD = $200`
- `MAX_POSITION_USD = $300` — потолок на общую сумму в одной позиции
- `MIN_BET_USD = $10`

> **Пример формулы**: denizz инвестировал $105,157 на рынок «US obtains Iranian uranium May 31». Формула: `31.75 × ln(105157) − 177 = 31.75 × 11.56 − 177 ≈ $190`. После multiplier'ов для 4.4% top-up × horizon 0.8 ≈ $8 — наш increment. Это выше `MIN_UPGRADE_USD = $5`, поэтому tier-upgrade бы сработал на $8. Но размер buy-события ($4625) > `MIN_BUY_EVENT_USD = $150`, значит ранний фильтр пропускает. Итог: upgrade $8 проходит.

### Шаг G. Исполнение входа — `execute_part1`

Если все фильтры пройдены:
1. Берём текущий best ask из orderbook.
2. Отправляем лимит-buy на эту цену через `executor.place_limit_buy`.
3. Ждём исполнения `wait_for_fill_with_details` (timeout `ORDER_TTL_SECONDS = 600s`).
4. При MATCHED — записываем в `positions.json` (`record_position`) и отправляем Telegram-уведомление.
5. При PARTIAL — сохраняем filled-порцию, refund'им unfilled cost.

**Важно**: в текущем конфиге `ENTRY_PART1_PCT = 1.00` — одна часть, 100% сразу. Пакетного входа (2/3 части) сейчас нет.

### Manual buys

Пользователь может купить напрямую через скрипт `_manual_buy_*.py`. Такая позиция записывается в tracker с полями:

```
"tier": "manual",
"signal_player": "manual",
"_adopted_from": "manual_buy_YYYY-MM-DD",
```

Что особенного: при продажах denizz бот **всё равно копирует** (из-за фикса manual-follow от 2026-04-15). Для follow-exit семантика: `signal_player == "manual"` разрешается для любого активного игрока из `PLAYERS`.

---

## 3. Как бот выходит — SELL

Есть **4 источника** решения о продаже:

### Источник A — Follow-player exit (когда denizz продал)

Самый частый триггер. Логика в `exit_manager.handle_player_sell()`:

1. **Dedup guard** — если такой же sell-event уже был обработан за последние `EXIT_DEDUP_WINDOW_SEC` (обычно 60s) → SKIP «duplicate».
2. **On-chain truth** — запрашиваем реальный balance denizz через Polygon CTF.balanceOf, сравниваем с нашим кэшем «какой размер был до этого». Вычисляем `actual_sold = cached − current_onchain`.
   - Если `actual_sold ≤ 0` → это phantom sell (на самом деле не продавал), SKIP.
   - Если RPC failed → fail-safe, не продаём.
3. **Cache baseline**: если кэша нет (первый раз видим) → записываем текущий balance как baseline, SKIP этого сигнала. Следующий sell уже обработается.
4. **Проверка `signal_player`**:
   - Позиция открыта denizz, сигнал от denizz → OK, идём в decision matrix.
   - Позиция `signal_player == "manual"` → ВСЕГДА разрешено (для любого игрока из `PLAYERS`).
   - Позиция открыта другим игроком, сигнал от другого → **SKIP** (cross-player protection).
5. **Decision matrix (FOLLOW_SELL_TIERS)**: считаем `sold_pct_player = actual_sold / cached`.
   - `< PLAYER_SELL_DUST_PCT` (обычно 3%) → dust, SKIP.
   - Иначе — смотрим таблицу:

     | denizz продал | Мы продаём |
     |---|---|
     | 0–10% | 0% (ничего) |
     | 10–30% | 25% |
     | 30–60% | 50% |
     | 60–90% | 75% |
     | 90–100% | 100% |

6. **Loss-threshold** (`FOLLOW_SELL_LOSS_THRESHOLD = 0.60`): если мы **в минусе** по позиции, бот выходит **только** когда суммарный denizz-sell ≥ 60%. До этого держим, несмотря на сигналы.

> **Пример**: 2026-04-15 11:35, denizz продал 29,842 sh Hezbollah April 15 (100% своей позиции) @ $0.935. Бот увидел: `100% ≥ 60%`, мы в убытке (entry $0.95, текущая $0.94), тир `90-100% → 100%`. Решение: продать наши 59.5 sh. Отправлен ордер $0.937. **Но упал на precision** (см. Источник D).

### Источник B — Stop-loss (цена упала)

В `exit_manager.check_exits()` периодически (каждые `POSITIONS_CHECK_INTERVAL = 60s`) проходит по всем open-позициям и считает процент падения:

```
drop_pct = (entry_price − current_best_bid) / entry_price
```

Если `drop_pct ≥ stop_loss_pct_from_tier` — продаём всё по best_bid.

Тиры `STOP_LOSS_TIERS`:

| Entry price | Stop |
|---|---|
| 2–15c | 60% |
| 15–70c | 60% |
| 70–82c | 45% |
| 82–99c | 35% |

> **Пример**: позиция куплена по $0.90 на Trump Iranian transit fees. Stop = 35%, значит стоп срабатывает при цене ≤ $0.585. Пока цена держится выше — держим.

### Источник C — Target exit (цена поднялась к 99¢)

`EXIT_SELL_AT_PRICE = $0.99`. Если `best_bid ≥ 0.99` — продаём всё, фиксируем почти-максимальный выигрыш.

### Источник D — Precision-safe sell + retry-on-fail (архитектурная защита)

Любой sell (из A/B/C) проходит через `executor.place_limit_sell`, который сам вызывает `safe_sell.compute_safe_sell_size`:

1. Запрашивает **реальный on-chain balance** нашего кошелька для этого токена.
2. Возвращает `min(requested_shares, onchain) − SAFETY_MARGIN_SHARES (0.001)`, округлено **вниз** до 2 знаков (точность CLOB).
3. Если получилось `< MIN_SHARES = 5` → возвращает спец-ошибку `SELL_SKIP_INSUFFICIENT_BALANCE`, и exit_manager помечает позицию как `sold` (on-chain реально пустой).

Если на бирже ордер упал с **любой другой ошибкой** (не-insufficient-balance):
- **Первый retry** сразу же с `safety_margin × 5` (больше запас на precision).
- Если и это не прошло → в позиции пишется `_pending_exit_retry`:

  ```json
  {
    "since": "2026-04-15T11:35:24+00:00",
    "last_attempt": "...",
    "attempts": 2,
    "last_price": 0.937,
    "last_reason": "follow_denizz",
    "last_error": "api_error"
  }
  ```

- На следующем цикле `check_exits` функция `process_pending_retries()` проходит по помеченным позициям:
  - `RETRY_WINDOW_MIN = 30 min` — общее окно попыток
  - `RETRY_MAX_ATTEMPTS = 6` — максимум попыток
  - `RETRY_MIN_SPACING_SEC = 60` — минимум между попытками
- При успешной продаже маркер стирается.

> **Пример**: 2026-04-15 11:35, Hezbollah. Бот запросил продать 59.51 sh, но on-chain было 59.509092 (на 908 микро-shares меньше). Raw-ордер упал `not enough balance`. **До фикса** это приводило к зацикленным `[EXIT] Sell order failed` каждые 2 минуты и спаму в Telegram. **После фикса** `safe_sell` перед отправкой ордера автоматически обрезал до `59.50` (floor к on-chain − margin), и продажа прошла бы сразу.

### Manual positions — следуют за denizz

Пример: 2026-04-15, ты вручную купил 44.78 sh «Litani River No» @ $0.67. Эта позиция в tracker с `signal_player = "manual"`. Когда denizz продаст по этому рынку, `handle_player_sell` увидит:
- позиция найдена
- `signal_player == "manual"` → путь разрешён (не блокируется cross-player)
- в лог: `[EXIT] manual position following denizz: Israeli forces cross the Litani River...`
- дальше — обычная follow-sell логика (dust-filter + tiers + loss-threshold).

---

## 4. Redeemer — сбор денег после резолва

`redeemer.py` запускается как отдельный поток, каждые `REDEEM_CHECK_INTERVAL = 300s`:
- Проверяет статус open-позиций через Gamma API.
- Если рынок `closed=True` → определяет, winning-outcome у нас или нет.
- Winning → делает `redeem()` транзакцию на Polygon, забирает $1 per share.
- Losing / zero-payout → молча закрывает позицию в tracker без транзакции.

> **Пример**: куплено 200 sh «Iran-Israel conflict ends by April 7» Yes. 7 апреля резолвится Yes → payout 200 × $1 = $200. Redeemer автоматически делает транзакцию и записывает `resolve_position(won=True)` в tracker.

---

## 5. On-chain sync — самолечение

Периодически (внутри `check_exits`) `tracker.sync_with_onchain` сверяет tracker с реальным on-chain state кошелька:

- **Forward scan**: для каждой open-позиции читает `CTF.balanceOf`, сравнивает с `size_shares` tracker:
  - on-chain ≈ tracker → noop
  - on-chain > tracker → `onchain_sync_up`, записывает дельту в `manual_additions`, увеличивает `size_shares` и `cost_usd`
  - on-chain < tracker → `onchain_sync_down`, записывает как псевдо-sell, уменьшает `size_shares`
  - on-chain = 0 → `onchain_sync_disappeared`, status → sold
- **Reverse scan**: если есть on-chain позиция, которой НЕТ в tracker ни с каким статусом (включая sold/lost) — адоптирует новую строку с ключом `0xsync_*`.
  - **Важный патч 2026-04-15**: reverse scan проверяет `existing_keys` по **всем статусам** (не только `open`). Это не даёт пере-адоптировать позиции, которые мы вручную закрыли. До фикса: пометил позицию `lost` → следующий sync видит on-chain баланс → адоптирует заново → бот снова пытается продать. Бесконечный цикл с Telegram-спамом.

> **Пример**: 2026-04-15, Iran-Iraq `No` 114.16 sh. Позиция была закрыта вручную (пометил `lost`). До фикса бот каждые 2 минуты адоптировал её заново, пытался продать, получал ошибки, спамил Telegram. После фикса — reverse scan видит что (cid, token) уже в existing_keys → пропускает → тишина.

---

## 6. Пять реальных историй сегодняшней сессии

### История 1 — Hezbollah precision bug (→ фикс safe_sell)

**Что было**: 11:35 denizz продал 100% Hezbollah April 15 No. Бот решил копировать. Отправил ордер 59.51 sh @ $0.937. Биржа: `not enough balance / allowance: balance: 59509092, order amount: 59510000`. Разница — 908 микро-shares (tracker хранит до 2 знаков, on-chain до 6 знаков). **Сигнал denizz мы упустили.** Следующие часы бот каждые 2 минуты пытался заново и каждый раз получал ту же ошибку → Telegram-спам.

**Фикс**: `safe_sell.compute_safe_sell_size` перед отправкой ордера.

### История 2 — Iran stockpile $2 → $104 (→ фикс MIN_BUY_EVENT_USD)

**Что было**: 13:05 denizz купил $2 на Iran stockpile (крошечный top-up к своей $7K позиции). У нас раньше была позиция на этом рынке, закрыли её с прибылью $2.80. Rule C пропустил re-entry. Полная формула сайзинга дала $104.45. Бот зашёл. Несоразмерно: $2 → $104.

**Фикс**: `MIN_BUY_EVENT_USD = $150` early-фильтр в `handle_buy`. Теперь buy-event $2 даже не доходит до Rule C.

### История 3 — Iran-Iraq re-adoption loop (→ фикс existing_keys)

**Что было**: Iran-Iraq позиция 114.16 sh No была уже losing. Вручную пометил `status=lost`. Но `tracker.sync` делал reverse-scan: видит on-chain `114.16 sh`, проверяет `existing_keys` (только `open` статусы) → нет совпадения → адоптирует заново как `0xsync_*`. Exit_manager видит новую open-позицию → пытается продать → ордер отклоняется → спам в Telegram.

**Фикс**: `tracker.py:584` — `existing_keys` теперь включает позиции **любого** статуса. Manually closed позиции больше не пере-адоптируются.

### История 4 — Manual-follow патч

**Что было**: пользователь вручную купил 44.78 sh «Litani River No» @ $0.67. Позиция в tracker с `signal_player="manual"`. До фикса `handle_player_sell` на строке 613 блокировал: «player=denizz, pos.signal_player=manual → SKIP cross-player». Manual-позиции не получали follow-sell.

**Фикс**: `exit_manager.py:612-623` — `signal_player="manual"` разрешается для любого активного игрока из `PLAYERS`. Cross-player protection **сохранена** для реальных игроков (car vs denizz всё ещё блокирует).

### История 5 — Trump enrichment walked-the-book

**Что было**: 15:00 пользователь попросил продать 100% Trump-enrichment-Yes (223.74 sh) по рынку. Best bid $0.269, но depth тонкая. Первый ордер (limit $0.26) заполнил только 89.63 sh из 223.74 за 120s (timeout + auto-cancel). Остаток 134.11 sh перепродан вторым ордером (limit $0.24) полностью. Итого $55.48 revenue, PnL в плюсе (реальный entry был $0.15, не $0.358 как в раздутом tracker).

**Урок**: при больших sell'ах на тонких рынках бот ловит top-bids и отменяет остаток по timeout. Для полного execution через book — либо два прохода, либо ставить GTC limit (как делают manual-скрипты `_manual_sell_trump_limit254.py`).

---

## 7. Формула `calculate_bet_size` — подробно

Функция `filters.calculate_bet_size(signal_player, player_invested, price)` (filters.py:474) — **сердце сайзинга**. Возвращает размер нашей ставки в USD для данного состояния denizz'а. Вход: суммарная инвестиция игрока на этом рынке + цена, по которой мы войдём.

### 7.1 Пошаговая логика

```python
def calculate_bet_size(signal_player, player_invested, price=0.5):
    if player_invested < 500:           # ←  фильтр MIN_PLAYER_INVESTED
        return 0                        #    отбрасываем мелкие позиции игрока
    raw = 31.75 * ln(player_invested) + (-177)   # базовая формула
    raw = min(raw, 200)                  # MAX_BET_USD cap BEFORE multipliers
    price_mult = get_price_multiplier(price)     # 1.0 для 0-82c, 0.65 для 82-99c
    raw = raw * price_mult * BET_SCALE           # BET_SCALE = 1.0 в live
    return round(raw, 2)
```

Только **4 строки вычислений**. Всё остальное (top-up ratio, horizon, late-gate) применяется уже в caller'е (`filters.check_signal` или `main.handle_buy` в tier-upgrade path).

### 7.2 Базовая формула

```
our_bet_base = 31.75 × ln(player_invested) + (−177)
```

- `BET_FORMULA_A = 31.75`
- `BET_FORMULA_B = −177.0`

**Калибровка** (из config.py комментария): «anchors denizz $500 → $20, denizz $30K → $150».

Проверяем:
- $500:  31.75 × ln(500) + (−177) = 31.75 × 6.215 − 177 = 197.3 − 177 = **$20.3** ✓
- $30K:  31.75 × ln(30000) + (−177) = 31.75 × 10.309 − 177 = 327.3 − 177 = **$150.3** ✓

### 7.3 Таблица размеров — до cap'а и multiplier'ов

| denizz invested | ln | × 31.75 − 177 | **raw bet** |
|---|---|---|---|
| $500 | 6.21 | 197.3 − 177 | **$20.3** |
| $1,000 | 6.91 | 219.4 − 177 | **$42.4** |
| $2,000 | 7.60 | 241.4 − 177 | **$64.4** |
| $5,000 | 8.52 | 270.5 − 177 | **$93.5** |
| $10,000 | 9.21 | 292.5 − 177 | **$115.5** |
| $20,000 | 9.90 | 314.5 − 177 | **$137.5** |
| $30,000 | 10.31 | 327.3 − 177 | **$150.3** |
| $50,000 | 10.82 | 343.4 − 177 | **$166.4** |
| $100,000 | 11.51 | 365.5 − 177 | **$188.5** |
| $200,000 | 12.21 | 387.5 − 177 | **$210.5** → **капается до $200** |
| $500,000 | 13.12 | 416.5 − 177 | **$239.5** → капается до **$200** |

**Характеристика**: логарифмическая — удваивание denizz'а даёт только +$22 к нашей ставке. Это защита от «бесконечной» экспозиции на мегаставках игрока.

### 7.4 Price multiplier

`PRICE_BET_MULTIPLIERS` — режет размер ставки когда цена входа близка к 99c (там низкий upside):

| Цена входа | Multiplier |
|---|---|
| 0 – 82c | **1.0** (полный размер) |
| 82 – 99c | **0.65** (35% reduction) |

Пример: denizz $10K, вход по $0.85 → raw $115.5 × 0.65 = **$75**.

### 7.5 Tier — это НЕ множитель

В `positions.json` у строк есть поле `"tier": "B | A | S | S+ | manual | upgrade"`. В текущем v2 **tier — просто label для отчётности**, он НЕ влияет на расчёт размера ставки. Сайзинг полностью определяется `calculate_bet_size` + post-multipliers (top-up, horizon, late-gate). Присвоение tier происходит по price range в `filters.check_signal` (S+ для 82+c, S для 70-82c, A для 40-70c, B для ≤40c).

В v1 tier'ы определяли размер напрямую (fixed amounts per tier). В v2 это заменено логарифмической формулой и тиры остались только для backward-compat отчётов и tracker-записей.

### 7.6 Post-multipliers (применяются в caller'е)

После `calculate_bet_size` результат проходит через цепочку множителей в `filters.check_signal` / `main.handle_buy`:

| Этап | Множитель | Когда |
|---|---|---|
| Top-up ratio | 0.0 / 0.5 / 0.75 / 1.0 | Если denizz добавляет к существующей позиции |
| Late-gate (Rule A+) | 1.0 / 0.75 / 0.5 / 0.25 / 0.10 | На основе `current_ask / player_avg` |
| Horizon | 1.0 / 0.8 / 0.7 / 0.4 / 0 | По дням до резолва |
| `MIN_UPGRADE_USD = 5` | hard cutoff для tier-upgrade | increment < $5 → SKIP |
| `MIN_BET_USD = 10` | hard cutoff для нового входа | final < $10 → SKIP |
| `MAX_POSITION_USD = 300` | cap на общую позицию | total > $300 → clamp |

### 7.7 Late-gate (Rule A+) — детализация

Функция `calculate_entry_size_multiplier(player_avg, current_ask)` (filters.py:244):

```python
mult = current_ask / player_avg

if mult <= 1.2:   return (1.0,  "on-time")
if mult <= 1.5:   return (0.75, "late 75% size")
if mult <= 2.0:   return (0.50, "bad 50% size")
if mult <= 3.0:   return (0.25, "terrible 25% size")
else:             return (0.10, "extreme 10% size")
```

**Зачем**: если denizz купил по $0.20, а мы заходим по $0.60 (3× разницы), наш risk/reward сильно хуже. Уменьшаем экспозицию пропорционально.

### 7.8 Пример полного расчёта

**Сценарий**: denizz уже инвестировал $7,000 на рынок «Iran stockpile» (avg $0.24). Сейчас делает новый buy $5,000 @ $0.25 (почти удвоил позицию). У нас позиции на этом рынке ещё нет.

Шаг за шагом (допустим рынок резолвится через 20 дней):

1. `player_invested = 7000`, `price = 0.25`
2. `raw = 31.75 × ln(7000) − 177 = 31.75 × 8.85 − 177 = 281.2 − 177 = $104.2`
3. `price_mult = 1.0` (0.25 < 0.82)
4. `BET_SCALE = 1.0` (live)
5. **После `calculate_bet_size`**: `bet_size = $104.2`
6. Top-up ratio: у нас позиции нет → skip (не applicable)
7. Late-gate: `mult = 0.25 / 0.24 = 1.04 → 1.0x` (on-time)
8. Horizon (20 дней): `1.0x`
9. **Final bet = $104.2**, но cap `MAX_POSITION_USD = $300` — ok.

Бот отправит ордер на **$104.2 @ $0.25** → получит ~416 sh.

---

## 8. Hedge detection — подробно

Hedge — это когда denizz покупает **нашу сторону** рынка, но при этом у него уже есть **большая позиция на противоположной стороне**. Экономический смысл: он не меняет своё directional mnение, а страхуется (фиксирует часть прибыли, если уже в плюсе на primary; или хеджит риск).

Если бы мы **слепо копировали** такой buy — мы бы встали в ту сторону, которая для denizz'а всего лишь страховка, а не убеждение. Плохой сигнал. Hedge detection отсеивает этот случай.

### 8.1 Как детектится hedge

Функция `filters.detect_hedge_signal` (filters.py:527):

```python
opposite = "No" if our_outcome == "Yes" else "Yes"

# 1. Same-condition check
primary_usd = get_player_usd_on_outcome(condition_id, wallet, opposite)
primary_source = "same-condition"

# 2. Cross-market fallback
if primary_usd <= 0 and event_slug:
    # Сканируем наш tracker: держим ли мы противоположную сторону
    # на рынке с тем же event_slug (но другим condition_id)?
    our_opposite_usd = sum(p.cost_usd for p in open_positions
                           if p.event_slug == event_slug
                           and p.outcome == opposite)
    if our_opposite_usd > 0:
        primary_usd = max(our_opposite_usd, player_invested / HEDGE_RATIO_MAX)
        primary_source = "cross-market-tracker"

# 3. Classify
ratio = player_invested / primary_usd
if ratio <= HEDGE_RATIO_MAX:   # 0.12
    is_hedge = True
```

**Порог**: `HEDGE_RATIO_MAX = 0.12`. Если новый buy denizz составляет меньше 12% от его primary (противоположной) позиции — это hedge.

### 8.2 Два пути определения primary

**Путь 1 — same-condition**: denizz держит на том же condition_id позицию противоположного outcome. Например, он купил 10,000 sh Yes по $0.25 на конкретный рынок, теперь докупает 500 sh No на тот же рынок. Это hedge по same-condition: ratio = 500 / 10000 = 5%.

**Путь 2 — cross-market через наш tracker**: у denizz'а **нет** противоположной позиции на этом condition_id, но у **нас** есть позиция противоположной стороны на **другом рынке того же event'а** (один event_slug, разные condition_id — например, "ceasefire by April 7" и "ceasefire by April 30" — это разные condition'ы, но один event_slug). В этом случае мы предполагаем, что denizz хеджит наш portfolio.

### 8.3 Что происходит после детекции — `evaluate_hedge_profitability`

Даже если signal классифицирован как hedge, бот **может скопировать** его, но только при одном условии: это **фиксация прибыли**, а не увеличение риска.

Функция `filters.evaluate_hedge_profitability` (filters.py:624):

1. Находим нашу **primary позицию** (противоположной стороны, same condition_id, или same event_slug):
   - Если у нас **нет primary** → hedge к нашему портфелю не относится → `should_copy = True`, normal filters apply.
   - Если есть primary → смотрим, в прибыли ли она.
2. Считаем текущий gain: `gain_pct = (current_bid − our_entry) / our_entry`.
3. Если `gain_pct ≥ HEDGE_MIN_GAIN_PCT = 0.12` → **копируем hedge** (фиксирует прибыль на primary).
4. Иначе → **SKIP** (hedge не даёт value в минусе).

**Порог**: `HEDGE_MIN_GAIN_PCT = 0.12`. Primary должен быть минимум на +12% выше нашей entry.

### 8.4 Таблица — когда копируем hedge

| У нас primary? | gain_pct | Решение |
|---|---|---|
| Нет | — | Копируем как standalone trade (normal filters) |
| Да, gain ≥ +12% | ≥ 0.12 | **Копируем hedge** (фиксируем прибыль) |
| Да, gain < +12% | < 0.12 | **SKIP** (не имеет смысла хеджить убыточную primary) |
| Да, shares = 0 | — | SKIP (дефектная primary) |

### 8.5 Порядок вызова — как hedge вписан в общий flow

В `filters.check_signal` (STEP 2a):

```python
hedge_info = detect_hedge_signal(cid, signal_player, outcome, invested, event_slug)

if hedge_info["is_hedge"]:
    hedge_eval = evaluate_hedge_profitability(outcome, cid, token_id, event_slug)
    if not hedge_eval["should_copy"]:
        return (False, 0, f"Hedge skip: {hedge_eval['reason']}", market_info)
    # иначе — idём дальше как обычно
# если не hedge → вообще пропускаем evaluate, standalone
```

Т.е. hedge-фильтр **только отсеивает hedges с убыточной primary**. Hedges с прибыльной primary или без primary проходят дальше по общему check_signal (category, price, opposition, slippage, size).

### 8.6 Пример реального hedge

**Сценарий**: у нас 200 sh No @ $0.60 на «Iran conflict ends by April 30» (primary, купили вчера). Сейчас denizz покупает 150 sh Yes @ $0.30 на **том же рынке**. Его position value на No — допустим $8,000 (он тоже держит No как primary).

Детекция:
- `opposite = "No"`
- `primary_usd` (same-condition): player держит $8K No на этом рынке
- `ratio = 150 × 0.30 / 8000 = $45 / $8000 = 0.56%` → **< 12%** → **is_hedge = True**

Profitability check:
- Наш primary: 200 sh No @ $0.60, текущий bid No = $0.70 → `gain_pct = (0.70 − 0.60) / 0.60 = 16.7%`
- **≥ 12%** → **should_copy = True** (hedge локирует нашу прибыль)

Бот копирует buy denizz — покупает Yes на этом рынке. Получается: у нас есть прибыльный No + страхующий Yes. Если рынок резолвится Yes — убыток на No компенсирует выигрыш Yes; если No — наш primary оплачивается, а Yes сгорает. Total risk снижен.

### 8.7 Hedge на практике — Car-специфика (устаревшее)

Hedge detection изначально писался для Car (второй трейдер, сейчас отключён): он регулярно делал merge-preparation buys (покупал Yes + No одновременно, потом мерджил на $1). Эти buys выглядят как «покупка» но имели нулевую directional информацию.

С текущим конфигом (только denizz) hedge detection **редко срабатывает**, т.к. denizz делает чисто directional trades. Но архитектурно фильтр готов к возврату Car / добавлению новых игроков. См. комментарии в `config.py` про удаление Car 2026-04-09.

---

---

# Часть 2. Техническое описание — для разработчика

## 1. Архитектурная карта модулей

```
25_multi_signal_copybot_v2/
├── main.py              Entry orchestrator: load buffers → monitor → periodic loops
├── monitor.py           Polls denizz wallet → emits buy/sell events
├── entry_manager.py     execute_part1: place buy + record position
├── exit_manager.py      check_exits + handle_player_sell + _execute_sell + retries
├── executor.py          CLOB client wrapper (place_limit_buy/sell, wait_for_fill)
├── safe_sell.py         Precision-safe sell size + onchain balance query (NEW 2026-04-15)
├── tracker.py           positions.json read/write + sync_with_onchain
├── filters.py           check_signal, calculate_bet_size, orderbook utils
├── redeemer.py          Claim payouts after market resolution
├── config.py            All parameters, tiers, thresholds, wallet
├── telegram_notify.py   Outgoing TG messages
├── telegram_cmd.py      Incoming TG commands (status, pause, etc.)
├── mode_manager.py      test/live mode toggles
├── _watchdog.py         Process watchdog (currently disabled by user)
├── _reconcile.py        Periodic log-only reconcile (called from _metrics_loop)
├── _metrics_loop.py     Metrics collection every 5 min
├── daily_report.py      13:00 and 19:00 MSK reports
├── positions.json       Persistent state
├── signals.json         Pending 3-part-entry buffer (mostly unused in v2)
├── buy_buffers.json     24h rolling buffer of denizz buys per market
├── bot.log              Rolling log (verbose)
└── tests/               34 pytest tests, fully mocked
    ├── conftest.py
    ├── test_safe_sell.py       12 tests on precision math
    ├── test_sell_retry.py       7 tests on retry flow
    ├── test_manual_follow.py    5 tests on manual-positions
    ├── test_no_regression.py    4 smoke tests
    └── test_min_buy_event.py    6 tests on MIN_BUY_EVENT_USD filter
```

**Вспомогательные скрипты**:
- `_manual_buy_*.py` / `_manual_sell_*.py` — one-shot ручные операции
- `_check_iran_iraq.py` / `_check_all_duplicates.py` / `_audit_manual_positions.py` — read-only проверки
- `_backtest_*.py` — исторические проверки стратегий
- `_prelaunch_check.py` — проверки при старте

## 2. Data flow

### 2.1 BUY-путь

```
monitor.py: _poll_player()
  └── fetch_positions() / fetch_recent_activity()
        ├── detect: new position OR size increased
        └── emit buy_event dict
              └── on_buy callback (main.handle_buy)
                    ├── read event fields (cost_usd, price, title, …)
                    ├── MIN_BUY_EVENT_USD filter           ← main.py:323
                    ├── buffer accumulate (24h window)      ← main.py:327
                    ├── MIN_PLAYER_INVESTED gate ($500)     ← main.py:343
                    ├── if _signaled_keys contains key:
                    │     └── tier-upgrade path
                    │           ├── Rule B (anti-chasing)    ← main.py:386
                    │           ├── calculate_bet_size       ← filters.py:474
                    │           ├── calculate_entry_size_multiplier (late-gate)
                    │           ├── HORIZON_TIERS
                    │           ├── MIN_UPGRADE_USD          ← main.py:458
                    │           └── entry_manager.execute_part1 (thread)
                    ├── else new signal:
                    │     ├── Rule C (post-exit whipsaw)     ← main.py:496
                    │     ├── tracker.can_open_new
                    │     ├── filters.check_signal (price, category, opposition, hedge)
                    │     └── entry_manager.execute_part1
                    └── entry_manager.execute_part1:
                          ├── executor.place_limit_buy (ClobClient → CLOB API)
                          ├── wait_for_fill_with_details
                          ├── tracker.record_position         ← tracker.py:289
                          └── tg.buy_placed / buy_filled
```

### 2.2 SELL-путь

```
monitor.py: _poll_player()
  └── detect: position size decreased or gone
        └── emit sell_event
              └── on_sell callback (exit_manager.handle_player_sell)
                    ├── Step 1: dedup guard (60s window)
                    ├── Step 2-4: on-chain truth
                    │   ├── _get_player_size_onchain (CTF.balanceOf)
                    │   ├── _cache_get(player, cid, token) → previous size
                    │   └── actual_sold = cached - current
                    │       ├── <=0 → phantom, SKIP
                    │       └── cache not found → set baseline, SKIP
                    ├── Step 5: match tracker position
                    │   └── signal_player check
                    │         ├── same → OK
                    │         ├── "manual" → OK (any active player)
                    │         └── cross-player (denizz vs car) → SKIP
                    ├── Step 6: decision matrix
                    │   ├── sold_pct < PLAYER_SELL_DUST_PCT → SKIP
                    │   ├── FOLLOW_SELL_TIERS lookup
                    │   └── FOLLOW_SELL_LOSS_THRESHOLD (in-loss only if ≥60%)
                    └── _execute_sell
                          ├── client.cancel_all (free up shares)
                          ├── executor.place_limit_sell
                          │   └── safe_sell.compute_safe_sell_size
                          │         └── get_wallet_balance (CTF RPC)
                          ├── if error "insufficient_onchain_balance" → close row sold
                          ├── if None → retry with margin × 5
                          ├── if still None → _mark_pending_retry
                          └── wait_for_fill_with_details
                                ├── MATCHED → record_sell + _clear_pending_retry
                                ├── PARTIAL → record partial, retry at 0.98×
                                └── TIMEOUT → cancel; partial recorded if matched>0.5%
```

### 2.3 Periodic loops

| Loop | Interval | Где |
|---|---|---|
| `monitor._poll_player` | `POLL_INTERVAL = 5s` | Per-player thread |
| `exit_manager.check_exits` | `POSITIONS_CHECK_INTERVAL = 60s` | Main thread |
| └ `process_pending_retries` | (внутри check_exits) | Retry `_pending_exit_retry` markers |
| └ `tracker.consolidate_duplicates` | (внутри check_exits) | Merge duplicate (cid,token) rows |
| └ `tracker.sync_with_onchain` | (внутри check_exits, косвенно) | Через `get_open_positions` loop |
| `redeemer.check_and_redeem` | `REDEEM_CHECK_INTERVAL = 300s` | Separate thread |
| `entry_manager.check_pending_parts` | per tick in main loop | Сейчас no-op из-за `PART1_PCT=1.0` |
| `_metrics_loop` (external) | 5 min | `_reconcile.py` в LOG_ONLY |
| `daily_report` | 13:00 и 19:00 MSK | Отдельный thread |

## 3. Key data structures

### 3.1 `positions.json`

```json
{
  "positions": {
    "<key>": {
      "condition_id": "0x...",
      "token_id": "105...",
      "title": "...",
      "outcome": "Yes | No",
      "event_slug": "...",
      "entry_price": 0.247,
      "avg_entry": 0.247,
      "size_shares": 422.88,
      "cost_usd": 104.45,
      "tier": "B | A | S | S+ | manual | upgrade",
      "strategy": "standard | manual",
      "signal_player": "denizz | manual | unknown",
      "parts_filled": 1,
      "parts_planned": 1,
      "order_ids": ["0x..."],
      "timestamp": "2026-04-15T11:03:35+00:00",
      "status": "open | sold | lost | won | merged_into_primary",
      "sells": [
        { "shares": 10, "price": 0.95, "revenue": 9.5, "pnl": 1.2,
          "reason": "denizz_follow_100%_sell100%", "timestamp": "..." }
      ],
      "final_pnl": 0,
      "manual_additions": [],
      "_adopted_from": "onchain_sync | manual_buy_2026-04-15",
      "_pending_exit_retry": {
        "since": "...", "last_attempt": "...", "attempts": 2,
        "last_price": 0.937, "last_reason": "...", "last_error": "..."
      }
    }
  },
  "stats": {
    "total_bets": 152, "wins": 3, "losses": 19129, "sells": 75,
    "total_pnl": -47703.9, "peak_balance": 2700, "current_balance": 408432
  }
}
```

Ключи:
- `0x<hex>` — обычный (order_id в hex)
- `0xsync_<hash>` — адоптированная reverse-sync'ом позиция
- `0xmanual_<hash>` — созданная `_manual_buy_*.py`

### 3.2 In-memory структуры (`main.py`)

```python
_signal_buffers = {"denizz": {buf_key: {
    "buys": [(timestamp, cost_usd), …],     # 24h rolling
    "total_usd": float,                      # sum of buys
    "notified": bool,                         # crossed $500 notification sent?
    "last_tier_bet": float,                  # bookkeeping for upgrade increments
}}}

_signaled_keys = {"denizz": set(buf_keys)}   # markets we've already entered

_entry_lock = threading.Lock()    # prevents parallel handle_buy race
```

### 3.3 `_player_size_cache` (exit_manager)

```python
_player_size_cache = {
    (player, cid, token_id): {"size": float, "ts": int}
}
```

Используется для вычисления `actual_sold = cached_size − current_onchain`. Обновляется после каждого sell-события свежим CTF.balanceOf.

### 3.4 `_recent_exit_fires` (exit_manager)

```python
_recent_exit_fires = {(player, cid, token): timestamp}
```

Dedup для sell-событий (`EXIT_DEDUP_WINDOW_SEC`).

### 3.5 `signals.json`

Буфер для 3-step entry. В v2 не актуален (`ENTRY_PART1_PCT = 1.0`). Оставлен для совместимости с `entry_manager.check_pending_parts`.

### 3.6 `buy_buffers.json`

Persisted слепок `_signal_buffers` и `_signaled_keys`. Загружается при старте через `_load_buffers`.

## 4. Ключевые фильтры — карта file:line

| Фильтр | File | Line | Действие |
|---|---|---|---|
| `MIN_BUY_EVENT_USD = 150` | main.py | ~323 | Ранний SKIP по размеру buy-event |
| `MIN_PLAYER_INVESTED = 500` | main.py | ~343 | Буфер, пока denizz не потратил $500 |
| `_signaled_keys` check | main.py | ~348 | Переход в tier-upgrade path |
| Rule B (anti-chasing) | main.py | ~386 | 1.5× current buy price gate |
| Late-gate multiplier | main.py | ~408 | `calculate_entry_size_multiplier` |
| Slippage check | main.py | ~445 | `_max_slip` by price tier |
| `MIN_UPGRADE_USD = 5` | main.py | ~458 | Минимум tier-upgrade increment |
| Rule C (post-exit whipsaw) | main.py | ~496 | Окно POST_EXIT_WINDOW_HOURS |
| `can_open_new` / `has_position_on_condition` | main.py | ~526 | Tracker limits |
| `check_signal` | filters.py | 731 | Финальная проверка (category, opposition, hedge) |
| `EXCLUDED_KEYWORDS` | filters.py | 394 | Блок по ключевым словам в title/slug |
| `PRICE_FILTER` per player | filters.py | 379 | Цена входа в range игрока |
| `HORIZON_TIERS` | filters.py (via config) | — | Множитель 1→0 по дням до резолва |
| `HEDGE_RATIO_MAX = 0.12` | filters.py | 546 | Hedge detection + profitability gate |
| `STOP_LOSS_TIERS` | exit_manager.py | ~222 | Процент падения цены до стопа |
| `EXIT_SELL_AT_PRICE = 0.99` | exit_manager.py | — | Target-exit |
| `FOLLOW_SELL_TIERS` | exit_manager.py | ~702 | Пропорция нашего exit от denizz % |
| `FOLLOW_SELL_LOSS_THRESHOLD = 0.60` | exit_manager.py | — | В убытке — только при ≥60% sold |
| `PLAYER_SELL_DUST_PCT` | exit_manager.py | ~695 | Микро-sell игнорируется |
| Cross-player / manual-follow | exit_manager.py | 612-623 | `signal_player` vs `player_name` |
| `EXIT_DEDUP_WINDOW_SEC` | exit_manager.py | ~527 | Dedup guard |
| `compute_safe_sell_size` | safe_sell.py | ~76 | Precision-safe клампинг size |
| `SAFETY_MARGIN_SHARES = 0.001` | config.py | — | Default margin |
| Retry-on-fail | exit_manager.py | ~388-415 | `_mark_pending_retry` + `process_pending_retries` |
| Sync reverse-scan `existing_keys` | tracker.py | 584 | Все статусы включены (после патча) |

## 5. Recovery / self-healing

| Механизм | Что делает | Частота |
|---|---|---|
| `tracker.consolidate_duplicates` | Сливает дубликаты по (cid, token) в одну строку | Каждый `check_exits` |
| `tracker.sync_with_onchain` forward scan | Корректирует `size_shares` up/down/disappeared | Implicit per iteration |
| `tracker.sync_with_onchain` reverse scan | Адоптирует новые on-chain позиции как `0xsync_*` | Каждый sync |
| `_pending_exit_retry` + `process_pending_retries` | Повтор sell после transient error | Каждый `check_exits` |
| `_reconcile.py` | Лог drift по (cid,token), auto-close только при on-chain=0 | Каждые 5 min (extern) |
| `redeemer` | Забирает payouts после резолва | Каждые 300s |
| `_watchdog.py` | Авто-перезапуск main.py при краше | 60s (ОТКЛЮЧЁН пользователем) |

## 6. Старт / shutdown

### Startup (`main.__main__`)

1. `logging.basicConfig` (file + stderr)
2. `sys.stdout = _PrintToLog()` — все `print()` уходят в logger
3. `_load_buffers()` из `buy_buffers.json` → восстанавливает `_signal_buffers` + `_signaled_keys`
4. `_rehydrate_from_tracker()` — дополняет `_signaled_keys` из open positions
5. `monitor.poll_loop(on_buy=handle_buy, on_sell=exit_manager.handle_player_sell, on_merge=...)`
6. Background threads: `redeemer`, `report_scheduler`, `_metrics_loop` (extern)
7. Main loop: `check_exits()` каждые `POSITIONS_CHECK_INTERVAL`

### Startup recovery (в monitor)

При старте monitor делает batch-проверку «missed sells» — сравнивает текущее состояние denizz-portfolio с тем, что было в кэше, пытается догнать пропущенные sell-события. Это работает **только если кэш не пустой**. После рестарта кэш пустой → recovery ничего не делает (`SKIP: no cache baseline`). Это известное ограничение — архитектурно не решено в текущей версии.

### Shutdown

- `Ctrl+C` / `taskkill` — ловится в `main.__main__` через `except KeyboardInterrupt`.
- Буферы сохраняются на диск (`_save_buffers`) перед выходом.
- Активные ордера не отменяются автоматически — остаются LIVE на бирже GTC.

## 7. Тесты

```
tests/
├── conftest.py                  shared fixtures (fresh_tracker_data, open_position, mock_clob_client)
├── test_safe_sell.py            12 unit tests on precision math
├── test_sell_retry.py            7 integration tests on retry flow
├── test_manual_follow.py         5 behavioral tests on manual-positions
├── test_no_regression.py         4 smoke tests
└── test_min_buy_event.py         6 tests on new MIN_BUY_EVENT_USD filter
```

**Запуск**: `python -m pytest tests/ -v` (ожидается `34 passed`).

**Зависимости тестов**:
- pytest 9.0.2
- coverage (для `python -m coverage run --source=safe_sell,executor -m pytest`)

**Особенности**:
- Все CLOB и RPC вызовы замоканы (`safe_sell.get_wallet_balance`, `executor._get_client`, `filters.get_orderbook_prices`).
- Positions.json для тестов создаётся в `tmp_path` (pytest fixture).
- `test_min_buy_event.py` импортирует main **до** pytest capture (workaround для `sys.stdout = _PrintToLog()` hijack).

## 8. Патчи сессии 2026-04-15

Все изменения этой сессии помечены комментариями в коде для будущей археологии.

### Патч 1 — safe_sell + retry-on-fail

**Файлы**: `safe_sell.py` (новый), `executor.py` (place_limit_sell), `exit_manager.py` (_execute_sell + _mark/_clear/process_pending_retries), `config.py` (SAFETY_MARGIN_SHARES, RETRY_WINDOW_MIN, RETRY_MAX_ATTEMPTS, RETRY_MIN_SPACING_SEC, RETRY_SAFETY_MARGIN_MULT)

**Цель**: не терять sell-сигнал denizz из-за precision error между tracker (2 знака) и on-chain (6 знаков).

**Как работает**: перед каждым sell вызывается `get_wallet_balance(OUR_WALLET, token_id)` через Polygon CTF.balanceOf. Результат кламятся к `min(requested, onchain) − margin`, floor to 2 decimals. При отказе биржи — ретрай с увеличенной margin; при повторном отказе — flag `_pending_exit_retry` с последующими попытками в течение 30 минут.

**Тесты**: 12 + 7 = 19 штук.

### Патч 2 — tracker reverse-scan existing_keys (all statuses)

**Файл**: `tracker.py:584`

**Что было**:
```python
if pos.get("status") == "open":
    existing_keys.add((cid, token))
```

**Что стало**:
```python
# Include ALL tracked positions (any status) to prevent re-adopting
# positions that were manually closed/marked lost
existing_keys.add((cid, token))
```

**Цель**: не пере-адоптировать manually closed позиции, когда on-chain баланс ещё ненулевой.

### Патч 3 — manual-follow (signal_player)

**Файл**: `exit_manager.py:612-623`

**Что было**: одна проверка — `signal_player != player_name → SKIP`.

**Что стало**: три ветви — same / manual / cross-real-player. Manual-позиции разрешены для любого активного игрока.

**Тесты**: 5 штук в `tests/test_manual_follow.py`.

### Патч 4 — MIN_BUY_EVENT_USD filter

**Файл**: `main.py:323-330`, `config.py` (+ параметр)

**Вставка**: сразу после чтения event-полей в `handle_buy`:

```python
from config import MIN_BUY_EVENT_USD
if float(cost_usd or 0) < MIN_BUY_EVENT_USD:
    print(f"[MAIN:{player_name}] SKIP: buy event ${float(cost_usd or 0):.0f} "
          f"below MIN_BUY_EVENT_USD (${MIN_BUY_EVENT_USD:.0f}) | {title[:50]}")
    return
```

**Цель**: не копировать микро-buy denizz ($2), которые триггерят полноразмерную ставку через re-entry или tier-upgrade.

**Тесты**: 6 штук в `tests/test_min_buy_event.py`.

### Патч 5 — MIN_UPGRADE_USD $15 → $5

**Файл**: `config.py`

Снижен порог tier-upgrade increment с `$15` до `$5`, чтобы ловить более мелкие upgrade'ы denizz. Работает **вместе** с `MIN_BUY_EVENT_USD $150` — двойная защита: сначала event должен быть ≥$150, потом наш увеличивающий bet должен быть ≥$5.

## 9. Что НЕ покрыто этим README

- `detect_merge_prep` — логика обнаружения merge-exit (Car'овский кейс, Car сейчас отключён).
- Telegram-команды (`telegram_cmd.py`) — список команд. Кратко: доступны `/status`, `/pause`, `/resume` etc.
- `daily_report.py` — формат ежедневных отчётов.
- `mode_manager.py` — тест/лайв switching (сейчас всегда live).
- `_backtest_*.py` — истор. проверки, не влияют на runtime.
- `_analytics/` — папка с ручными markdown-отчётами по прошлым исследованиям.
- Детальный протокол Polymarket CLOB (tick size, order types, API endpoints) — бот использует py-clob-client abstraction.
- Restart procedure (watchdog отключён, но в коде остался) — см. `_watchdog.py`.
- Точные механизмы на Polygon (USDC approve, CTF approve, gas) — handled by py-clob-client.

---

*Документ составлен 2026-04-15. При правках кода — обновлять соответствующие строки с file:line в Части 2 и примеры в Части 1.*
