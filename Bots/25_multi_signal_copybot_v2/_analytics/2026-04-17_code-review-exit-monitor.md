# Code review: exit_manager.py + monitor.py (follow-sell)

Дата: 2026-04-17
Ревьюер: независимый (свежий взгляд)
Scope: exit_manager.py, monitor.py, релевантные части config.py, executor.py, tracker.py, main.py
Цель: оценить надёжность follow-sell логики перед пиком 21-22 апреля (expiry ceasefire US-Iran).

---

## 1. Резюме

Код в целом здравый и защищён несколькими слоями проверок (on-chain truth, dedup 60s, phantom detection, retry pending). Архитектура правильная: monitor — только "подсказка", все решения по размеру продажи делает exit_manager на основе CTF.balanceOf.

Но при внимательном чтении нашёл:

- **3 BLOCKER** — реальная возможность потерять sell-сигнал или продать не то/не то количество
- **5 MAJOR** — серьёзные, но не на 100% гарантированно срабатывают
- **6 MINOR** — мусор, избыточность, нестыковки комментариев и кода

Главные проблемы:
1. `tracker.load()`/`tracker.save()` без блокировки — несколько потоков продаж пишут одновременно → lost-update в positions.json.
2. `_execute_sell` вызывает `client.cancel_all()` глобально — режет и чужие pending лимиты (entry-ордера) и параллельные SELL-ы.
3. `_recent_exit_fires` dedup проверяется и устанавливается без блокировки — два потока на одно и то же (player, cid, token) могут оба пройти guard.

К пиковой нагрузке 21-22 апреля код **готов с оговорками**: в нормальном сценарии (1 sell на рынок, редко) всё сработает. В сценарии burst (denizz быстро сбрасывает несколько позиций одновременно) — возможна потеря сигнала или дублирование из-за race conditions.

---

## 2. Карта потока данных

```
monitor._poll_player  (один поток на игрока, daemon)
    ├── fetch_recent_activity()  — каждые POLL_INTERVAL=5с
    │     └── если trade.type=="TRADE" и SELL/size<0 →
    │           on_sell(player, event)
    │             = main.handle_sell(player, event)
    │               └── threading.Thread(target=_do_exit, daemon=True).start()
    │                     └── exit_manager.handle_player_sell(player, event)
    │                           ├── dedup guard 60s (_recent_exit_fires)
    │                           ├── on-chain balance via CTF.balanceOf
    │                           ├── sold_pct = (cached - current) / cached
    │                           ├── match tracker position by (cid, token)
    │                           ├── FOLLOW_SELL_TIERS_PROFIT/LOSS lookup
    │                           └── _execute_sell(data, key, pos, shares, price, reason)
    │                                 ├── client.cancel_all()    ← ГЛОБАЛЬНО
    │                                 ├── tracker.load() → clamp shares
    │                                 ├── executor.place_limit_sell()
    │                                 │     ├── safe_sell.compute_safe_sell_size()
    │                                 │     └── CLOB post_order GTC
    │                                 ├── wait_for_fill_with_details(timeout=300s)
    │                                 └── tracker.record_sell()   ← load/save без lock
    │
    ├── snapshot diff каждые 5 циклов (≈25с)
    │     └── on-chain verify → on_sell(...)
    │
    └── startup recovery (только на старте)
          └── old sells after pos.timestamp → on_sell(...)

Параллельно:
main.periodic_checks  (отдельный поток)
    └── exit_manager.check_exits()   — каждые POSITIONS_CHECK_INTERVAL=60с
          ├── process_pending_retries()
          │     └── _execute_sell()   ← тот же путь
          ├── stop-loss / price target  → _execute_sell()
          └── refresh_cache_for_open_positions()  (on-chain RPC)
```

Ключевое: `_execute_sell` может быть вызван одновременно **минимум из 3 источников**:
- per-sell-event thread (main.handle_sell → _do_exit)
- periodic_checks thread (stop-loss, price target, retry)
- startup-recovery fire (уже через _do_exit)

Нигде нет exit-lock.

---

## 3. BLOCKER проблемы

### BLOCKER-1: Нет блокировки при concurrent load/save positions.json
**Файл:** tracker.py:105-119, exit_manager.py:502-534, :583-647
**Описание:** `tracker.load()` и `tracker.save()` — это обычный JSON read + atomic rename. Нет никакого lock. Внутри `_execute_sell` картина типичная:

```
data = tracker.load()      # поток A читает
...                        # одновременно поток B читает ту же версию
pos2["size_shares"] = 0
tracker.save(data)         # поток A пишет
                           # поток B пишет — затирает изменения A
```

**Сценарий:** 21 апреля denizz выкидывает 2 разных токена в течение 10 секунд (например, Iran-nuclear YES и US-Iran-ceasefire NO). monitor замечает оба события, main.handle_sell запускает 2 daemon-потока:
- Поток A обрабатывает Iran-nuclear, делает `record_sell` — `size_shares=0`, `status=sold`
- Поток B параллельно читает ту же `data` до записи A, делает `record_sell` для US-Iran, сохраняет свою версию
- Результат: запись A (Iran-nuclear sold) **потеряна** — позиция остаётся `open` в трекере с нулевыми shares. При следующей check_exits будет попытка продать на 0 shares, всё тихо скипнется, а по бухгалтерии позиция висит открытой. PnL искажается, onchain синхронизация потом исправит shares но не статус.

Также в `_execute_sell` сам код несколько раз делает load → mutate → save (строки 502, 520, 559, 584, 598, 620, 625, 641, 646). Каждая такая пара уязвима к гонке с параллельным selle/retry/stop-loss.

**Fix:**
```python
# в tracker.py
import threading
_io_lock = threading.RLock()

def load():
    with _io_lock:
        ...
def save(data):
    with _io_lock:
        ...
```
И обёрнуть `_execute_sell` целиком в общий `_exit_lock = threading.Lock()` из main.py — так один sell за раз, проще рассуждать.

---

### BLOCKER-2: `client.cancel_all()` глобально убивает чужие entry-ордера
**Файл:** exit_manager.py:493-500
**Описание:** Перед каждой продажей вызывается `client.cancel_all()` — это отменяет **ВСЕ pending лимиты на аккаунте**, включая:
- Лимитные buy-ордера entry_manager (place_limit_buy в entry_manager.py:92, :230, :262)
- Параллельные sell-ордера на ДРУГИЕ токены, которые только что были поставлены

**Сценарий 1 (потеря entry):** 21 апреля 15:00 — entry_manager ставит лимитный BUY на 100 USD на US-Iran-ceasefire (для top-up). В 15:00:03 denizz продаёт Iran-nuclear — exit_manager.handle_player_sell запускается, вызывает `cancel_all()`, заодно **убивает buy-ордер на ceasefire**. Top-up не случается, мы теряем entry. Цена ушла — мы не в позиции, когда должны быть.

**Сценарий 2 (burst sell):** Два денизз-sell в течение 2 секунд. Поток A ставит SELL-ордер на токен X (`place_limit_sell` вернулся — ордер в стакане). Поток B вызывает `cancel_all()` перед своим sell на токен Y → **убивает SELL-ордер A**. `wait_for_fill_with_details` у A повисит до timeout=300с и вернёт CANCELLED. Код тогда идёт на retry по ветке "Nothing filled → new_price = price * 0.98" — **продаём по заниженной цене**. На $4000 bankroll с 5-10% позициями это -$10-30 потерь на каждый такой случай.

**Fix:** использовать `cancel_order(order_id)` на конкретные exit-стейлы, либо иметь список bot-owned order_ids и отменять только их. Минимум — не делать cancel_all перед каждым sell, делать его только если обнаружен конфликт. Ещё лучше — завести `_exit_lock`, чтобы sell-ы шли последовательно.

---

### BLOCKER-3: `_recent_exit_fires` dedup не атомарен
**Файл:** exit_manager.py:677-684
**Описание:**
```python
last_fire = _recent_exit_fires.get(dedup_key, 0)
now_ts = time.time()
if now_ts - last_fire < EXIT_DEDUP_WINDOW_SEC:
    return
_recent_exit_fires[dedup_key] = now_ts
```
Между `.get()` и `[...] = now_ts` нет замка. Два потока (main.handle_sell → _do_exit и periodic retry) могут оба увидеть `last_fire=0`, оба пройти guard, оба вызвать `_execute_sell`.

**Сценарий:** У нас висит `_pending_exit_retry` от неудачной продажи 2 минуты назад. periodic_checks ≈сейчас запускает `process_pending_retries()` → `_execute_sell(reason="retry_pending(...)")`. В ту же миллисекунду monitor видит новый snapshot-delta на том же токене → `on_sell` → `_do_exit` thread → handle_player_sell. Дедап не спасает (проверяется только в handle_player_sell, retry идёт напрямую в _execute_sell). Результат — **два sell-ордера одновременно** на одну позицию → `cancel_all()` в первом рубит второго, либо оба пытаются продать, `safe_sell.compute_safe_sell_size` уклонится от одного, но в промежутке между проверкой и post_order есть окно.

Даже в простом сценарии — две sell-активности от denizz с разницей <5 секунд (tx в одном блоке, разный price) — благодаря недавнему fix по dedupe `tx+cond+ts+size+price` они пройдут как два разных trade_key → два `on_sell`. Дальше по коду:

- Dedup guard между ними — 60s, первый проходит, второй нет. ОК, на тесте не плохо.
- НО если `_execute_sell` первого ещё не завершился (висит на `wait_for_fill_with_details`, timeout 300s), то второй был заблокирован dedup — и по итогу второго сигнала бот **не продаёт вообще**, хотя denizz суммарно выкинул больше чем первая порция.

**Fix:**
1. Обернуть dedup в `threading.Lock`.
2. Внутри `process_pending_retries` перед `_execute_sell` проверять `_recent_exit_fires` + выставлять; либо (проще) ставить его в `_execute_sell` один раз для любого источника.
3. Рассмотреть — короче dedup (15-20s) или пересчитывать sold_pct каждый раз, т.к. за 60s denizz может сбросить ещё 30% и мы это пропустим.

---

## 4. MAJOR проблемы

### MAJOR-1: `sold_pct` считается от `cached_size`, а не от `peak_size`
**Файл:** exit_manager.py:736-743
**Описание:** Комментарий на строке 736 говорит "this sell event, not cumulative from peak". Но FOLLOW_SELL_TIERS построены так, что "denizz продал 80% позиции" = нужно продать 100% нашей. Если денизз делает два частичных sell (60% потом 40% от остатка), то:
- 1-й sell: cached=100 → current=40, delta=60, sold_pct=60% → FOLLOW_SELL_TIERS_PROFIT[0.60-0.70] = sell 75%
- 2-й sell: cached=40 → current=0, delta=40, sold_pct=100% → sell 100% от остатка (25% исходной)

Суммарно — мы продали 25% + 75%*25% = 43.75% от первоначальной позиции. А denizz продал 100%. Это **сильное отставание** при каскадных продажах.

При этом код знает про `peak_size` — он даже его считает (строки 704-719), но **не использует** для расчёта sold_pct. Возможно намеренно? Но тогда комментарий про "cumulative from peak" обманчив — peak_size вычисляется и обновляется, но нигде не используется в решении.

**Сценарий 21 апреля:** denizz на expiry US-Iran-ceasefire сбрасывает 30%, потом ещё 30%, потом ещё 40% в течение 15 минут. Каждый раз sold_pct будет 30-40% (от текущего cached, не от peak), и мы каждый раз продаём ~35% текущего остатка. Итог: после 3-х его продаж мы продали ~73% исходной, а он — всё.

**Fix:** Либо документировать что это намеренно (конфигурация tiers уже компенсирует), либо использовать `sold_pct_from_peak = (peak - current) / peak` как решающий, а `delta_sold` — только для phantom check.

---

### MAJOR-2: Профит/лосс оценивается по bid, но bid сдвигается от нашей же продажи
**Файл:** exit_manager.py:789-794, 860-865
**Описание:** `we_in_profit` определяется по `prices[0]` (best bid), который взят **до** нашей продажи. Если наш размер значимый (напр. наша позиция = 50% ликвидности стакана), лимит-sell уведёт bid вниз. Мы классифицируем себя "в профите", выбираем FOLLOW_SELL_TIERS_PROFIT (более мягкий), но по факту fill идёт в убыток.

Менее критично чем BLOCKERS, но при мелкой ликвидности на exotic рынках 21 апреля это может запутать tier selection.

**Fix:** Использовать VWAP из нескольких уровней стакана, либо mid-price (bid+ask)/2, для классификации profit/loss.

---

### MAJOR-3: `_mark_pending_retry` может зациклиться в retry с той же причиной провала
**Файл:** exit_manager.py:413-464
**Описание:** Цикл retry завершается только через:
- `window_elapsed_min > RETRY_WINDOW_MIN` (30 мин)
- `attempts >= RETRY_MAX_ATTEMPTS` (6)

Оба условия в `process_pending_retries` проверяются через `continue`, т.е. **не сбрасывают** `_pending_exit_retry` флаг — только "не пытаются на этом круге". На следующем круге (60s later) опять проверка — опять `continue`. Флаг торчит в positions.json до закрытия позиции. Не блокер, но если окно истекло и попытки закончились — мы **тихо перестаём пробовать продать**. Ни алерта, ни TG.

**Сценарий:** denizz продал 100% в 21:00. Наш sell упал (API flake). 6 попыток за 30 мин — все падают (CLOB down или стакан протух). В 21:30 бот перестаёт пробовать, флаг остался, позиция "open" с 50 shares, цена ушла с 0.80 до 0.20. На следующее утро — -$30, потому что никто не дёрнул алерт.

**Fix:**
- Когда attempts≥MAX или window expires — отправить TG-alert "STUCK EXIT: {title}".
- Проверять при каждом check_exits — если у позиции уже давно протух retry-marker и цена продолжает падать, сделать emergency market-sell (наилучший bid минус spread).

---

### MAJOR-4: В snapshot path (monitor.py:353-363, 388-398) НЕ передаётся `sell_price`
**Файл:** monitor.py:353-363, :388-398
**Описание:** Snapshot-ветка формирует event без поля `sell_price`. В exit_manager.py:797 `player_sell_price = float(event.get("sell_price", 0) or 0)` = 0.0. Далее:
- Строка 807-816: `player_avg > 0.01 and player_sell_price > 0.01` — условие не выполняется → `player_in_profit / player_in_loss = None`.
- Строка 860: `if player_sell_price > 0.01 and not we_in_profit` — условие не выполнится, проверка "наша цена хуже чем у игрока на 40%+" **пропускается**.

**Сценарий:** snapshot-path срабатывает, если activity-path пропустил (пагинация). Тогда решение о tier делается только на основании sold_pct и нашего PnL, без проверки насколько наша цена хуже. Мы можем продать очень дёшево в плохом стакане.

**Fix:** В snapshot-path дёргать CLOB для текущей цены игрока (последняя сделка), либо просто помечать sell_price как `our_sell_price` для консистентности, либо оставить как есть но логировать явно "snapshot path — price gap check skipped".

---

### MAJOR-5: Periodic cache refresh может затереть свежую on-chain продажу ДО обработки
**Файл:** exit_manager.py:256-273 (refresh_cache_for_open_positions)
**Описание:** Главная защита от "пропустили sell по delta=0" — это cache_age > 120s force-update. Но смотрим сценарий:
1. Monitor получает sell event, запускает handle_player_sell в 0s.
2. В handle_player_sell в строке 714 мы делаем `_cache_set(..., current_onchain)` **сразу** — как только узнали текущий баланс. (ещё до решения о продаже).
3. Затем идёт тяжёлая работа: fetch orderbook, fetch player cost basis, executor.place_limit_sell → wait_for_fill_with_details (timeout **300s**).
4. За эти 300s periodic `refresh_cache_for_open_positions` срабатывает (каждые 60s).
5. Если denizz за это время сделал **ещё одну продажу** (cache → current_2 ниже), то ветка `onchain < old` (строка 263) НЕ обновит cache. Но cache_age тикает от нашего последнего `_cache_set` в (2), т.е. ~300s > 120 → force-update применится.
6. НО, между (2) и force-update интервал 60-120s, и если monitor получит второй snapshot-delta в это окно, то handle_player_sell для него прочитает **устаревший cached_size из нашего же `_cache_set` в (2)**. delta_sold = small. sold_pct мал. Tier skip. Второй sell пропущен.

Это реальный сценарий для burst sell. На тесте обычный скейл не воспроизведёт, 21 апреля вероятен.

**Fix:** В handle_player_sell делать `_cache_set(..., current_onchain)` **после** успешного fill (либо после record_sell), а не до.

---

## 5. MINOR проблемы

1. **exit_manager.py:340 `if False:  # DRY_RUN killed`** — мёртвый код, то же на строке 487. Чисти.
2. **exit_manager.py:675 `if True:`** — декоративный if True, внутри весь dedup-guard. Вероятно остаток от feature-flag. Уберите обёртку.
3. **exit_manager.py:283-288** — старые константы `PLAYER_EXIT_SELL_PCT_THRESHOLD`, `PLAYER_SELL_DUST_PCT` объявлены, но не используются (tier matrix через config). Можно удалить.
4. **monitor.py:269** `"old_size": 0, "new_size": 0` для activity-ветки, хотя в handle_player_sell on-chain всё равно перечитывается. Не баг, но misleading для грепа логов.
5. **exit_manager.py:874-875** `handle_target_sell = handle_player_sell` — alias без использования (нигде не гуглится). Мёртвая совместимость.
6. **exit_manager.py:3-10** — docstring говорит "Exit rules: ..." и перечисляет 5 правил. Правило 4 ("Position held 20+ days") **удалено** (см. line 372 `# Time-stop removed in v2`). Комментарий устарел.

---

## 6. Что удивило

1. **Daemon thread per sell event.** Каждый `main.handle_sell` стартует новый daemon thread. Нет ограничения на их количество, нет пула. При burst сценарии (10 sell-ов за минуту) — 10 параллельных потоков одновременно дёргают on-chain RPC, CLOB, positions.json. При крэше бота в этот момент daemon-ы убиваются с половиной записанных изменений (atomic `os.replace` в save — ок, но если поток в середине серии load→save — может остаться полу-обновлённая запись).

2. **Startup-recovery не уважает dedup-окно.** Если бот упадёт и перезапустится через 10 минут, recovery пройдётся по активити и позовёт `on_sell` для всего, что после pos.timestamp. Но _recent_exit_fires пустой → guard пропускает → handle_player_sell делает on-chain check → `cached_size == current_onchain` (т.к. init_player_cache только что записал current) → delta=0 → PHANTOM skip. ОК, защищено. Но это хрупкий invariant — достаточно одного change в последовательности инициализации (например init_player_cache сделать **после** poll_loop) и защита отвалится.

3. **`init_player_peaks` делает по 1+ API call на каждую открытую позицию.** При 20-30 позициях в разгар expiry это 20-30 секунд на старте, и всё последовательно. Нет fallback если data-api тормозит. Для фикса 21-22 апреля — не критично, но стоит распараллелить через `concurrent.futures.ThreadPoolExecutor`.

4. **`FOLLOW_SELL_TIERS_PROFIT` и `_LOSS` различаются только первой строкой** (profit: 10%+ считается, loss: 20%+). В остальном идентичны. Для loss positions при мелком дребезге цены нас легко выбросит из позиции на 25% доли при sold_pct=20% — жалко, если денизз потом вернулся обратно. Tune'ить или понять что это намеренно.

5. **В monitor.py активити-ветка (line 248) сравнивает `size < 0` как альтернативу `SELL`**. Но `size = float(trade.get("size", 0) or 0)` — если API отдаёт size как positive для SELL с `side="SELL"`, то `size < 0` будет false, `side == "SELL"` — true. OK. Но если в какой-то версии API возвращает `size=-0.0` или пустую строку, `float("")` упадёт исключением → весь тред попадёт в `except e` с backoff 10с. Не критично, но hygiene.

---

## Краткое резюме (до 180 слов)

**3 BLOCKER / 5 MAJOR / 6 MINOR.**

Главные 3 проблемы:
1. **Нет блокировки на positions.json** — два параллельных sell-потока могут перезаписать друг друга, позиция останется "open" с 0 shares, PnL уйдёт в ноль.
2. **`client.cancel_all()` перед каждым sell** — глобальная команда, убивает соседние entry-ордера и параллельные SELL-ы. В burst-сценарии (несколько продаж denizz подряд) ломает сами себя.
3. **Dedup guard не атомарен + не синхронизирован с retry-путём** — два потока могут пройти guard одновременно; retry обходит guard совсем.

Менее критично, но важно: `sold_pct` считается от last-cache, а не от peak — при каскадных продажах мы отстаём от denizz на ~30-40%. Retry silently сдаётся после 6 попыток без TG-алерта. В snapshot-пути не передаётся sell_price → пропускается проверка "наша цена на 40%+ хуже чем у игрока".

**Вердикт на 21-22 апреля:** в "нормальном" сценарии (1 sell в 10 минут) код справится. В burst-сценарии (несколько sell-ов за минуту на разных токенах) есть 30-50% шанс потерять один сигнал или продать по заниженной цене. Рекомендую минимум — добавить `threading.Lock` в tracker и `_exit_lock` в exit_manager перед пиком.
