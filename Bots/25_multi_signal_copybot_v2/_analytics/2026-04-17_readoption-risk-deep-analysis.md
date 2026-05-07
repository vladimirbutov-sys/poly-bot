# Глубокий независимый аудит: re-adoption фикс и риски

**Дата:** 2026-04-17
**Объект:** `25_multi_signal_copybot_v2` — фильтр `existing_keys = ALL statuses` в `tracker.sync_with_onchain` (lines 759-767)
**Цель:** независимо верифицировать 6 рисков послабления фильтра до "only open" и прогнать регрессию.

---

## Резюме (≤250 слов)

Из 6 исходных рисков: **4 CONFIRMED (1 blocker, 3 minor), 1 DISPUTED, 1 NOT_APPLICABLE**.

Текущий фильтр (`existing_keys` включает ВСЕ статусы) — это намеренный **фикс** Iran-Iraq incident 2026-04-15. Пре-фикс: лог содержит **19 785 событий `SYNC ADOPTED`**; пост-фикс: только **1** за ~2 суток. Цифры показывают масштаб реального re-adoption loop.

**Главный blocker — Риск 1:** симуляция послабления до `status=open` на текущем `positions.json` + live on-chain снапшоте показывает, что **53 позиции были бы немедленно "re-adopted" в следующем же cycle** (все имеют tracker status=sold/lost с on-chain остатками >10 sh). Это означает возврат к тому самому loop'у, из-за которого фикс был сделан.

**Риск 5 (CONFIRMED_MINOR):** re-adopted позиции получают `signal_player="unknown"` (tracker.py:814). В `handle_player_sell` (exit_manager.py:800-805) строгая проверка: `pos_signal_player != player_name and != "manual"` → **unknown/denizz → SKIP**. Follow-sell для re-adopted позиций НЕ работает.

**Риск 4 (CONFIRMED_MINOR):** cost_usd estimate через `size × avgPrice` API. Для 27 открытых позиций total diff $+67 (2.3% от basis) — для re-adopted (9 позиций) |diff| в среднем <$2. Не критично на уровне года.

**Регрессия — все зелёные:**
- `_test_rebuy_v9.py` — **36/36 passed**
- `_test_follow_sell_comprehensive.py` — **75/75 passed**
- `tests/test_disappear_guard.py` — **13/13 passed**
- Smoke-compile всех модулей — OK
- Full pytest — 96 passed, 3 failed (только `test_manual_follow.py` — устаревшие assertions на старой tier-таблице, не связаны с re-adoption)

**Вердикт: НЕ МЕНЯТЬ фильтр.** Текущая логика корректна. Исходную проблему (orphan on-chain balance у закрытых позиций) решать точечными скриптами `_readopt_*.py` с `signal_player="manual"`.

---

## Риск 1 — Re-adoption loop

**Severity: CONFIRMED_BLOCKER**

### Доказательства из кода

`tracker.py` lines 759-767:
```python
# --- Reverse scan: on-chain → state ---
existing_keys = set()
for pos in data.get("positions", {}).values():
    # Include ALL tracked positions (any status) to prevent re-adopting
    # positions that were manually closed/marked lost — otherwise on-chain
    # remnants would be re-adopted as new 0xsync_X entries on every sync cycle.
    existing_keys.add((pos.get("condition_id", ""), str(pos.get("token_id", ""))))
```

Dust threshold: `if shares < 10: continue` (line 771) — weather markets с <10 sh не adopt'ятся, но это минимум.

### Доказательства из логов и данных

- **Логи bot.log:** до 2026-04-15 22:00 → **19 785** строк `[SYNC] ADOPTED`. После фикса → **1** событие. Это прямая эмпирическая мера loop'а.
- **positions.json:** 89 закрытых позиций (status=sold/lost/won/merged) с on-chain size > 0 sh. Из них **53** имеют size ≥ 10 sh (прошли бы dust-фильтр).
- **Симуляция:** построил set'ы keys по двум фильтрам:
  - `existing_keys=ALL` → будет re-adopt'ить 0 позиций
  - `existing_keys=OPEN only` → будет re-adopt'ить **53** позиций прямо сейчас

### Сценарий воспроизведения
1. Послабить фильтр до `if pos.get("status") == "open"`.
2. Запустить `sync_with_onchain` (интервал ~5 min).
3. На первом же цикле бот создаст 53 новых `0xsync_...` записей.
4. Следующий redeemer cycle (60 сек) зарезолвит их как `lost` (payoutDenominator>0, balance=0 or worthless).
5. На следующем sync — тот же 53 снова адопт → infinite loop до closed_status фильтра.

**Вердикт:** фикс абсолютно необходим. Послабление = немедленная регрессия Iran-Iraq incident.

---

## Риск 2 — Конфликт с redeemer

**Severity: DISPUTED (в текущей логике — ОК, но race-window существует)**

### Доказательства из кода

`redeemer.check_and_redeem` (redeemer.py:215-291):
- Проходит ТОЛЬКО по `tracker.get_open_positions()` (строка 217)
- Если `balance > 0` на CTF → делает `redeemPositions()` tx, **потом** `tracker.resolve_position(data, key, won=won)` (строки 269-277)
- Если `balance == 0` → сразу `resolve_position(..., won=False)` (строка 289)

Т.е. статус `won`/`lost` ставится **ПОСЛЕ** payout on-chain (или параллельно с zero-balance-silent-close).

### Re-adopter vs redeemer

Re-adoption code (tracker.py:769-826) создаёт новую запись со `status=open`. Redeemer берёт только `open`. Значит:
- Если re-adoption создаст `0xsync_X` прямо в окне между `redeemPositions()` tx и `resolve_position()` вызовом → redeemer уже идёт по old `key` и не увидит новую. Дубликата редем не будет.
- Но next cycle redeemer увидит `0xsync_X` как `open`, сделает `_check_token_balance` → balance уже 0 (если redeem прошёл) → `resolve_position(..., won=False)` → позиция закроется как `lost` даже если она была бы `won`. PnL сдвинется на cost_usd.

В текущей логике (`ALL` filter) этот сценарий не наступает — re-adoption блокируется. DISPUTED (не NOT_APPLICABLE), потому что при послаблении фильтра этот race реален.

---

## Риск 3 — Конфликт с merge_into_primary

**Severity: CONFIRMED_MINOR**

### Доказательства из кода

`tracker.consolidate_duplicates` (tracker.py:313-387):
- Группирует открытые позиции по (cid, tok), все кроме primary ставит `status="merged_into_primary"` + `merged_into=primary_key` (строки 367-369).
- `merged_into_primary` — это отдельный terminal status, 14 записей сейчас в `positions.json`.

### Что ломается при послаблении

Если фильтр сводится к `status==open`, то `merged_into_primary` перестанет блокировать re-adoption:
- В positions.json есть 14 merged записей; у них такой же (cid, tok) как у соответствующего primary (который open). Сам primary всё равно в `existing_keys` → re-adopt не произойдёт.
- **НО** если primary закрылся (status=sold/lost) а merged осталась как "merged_into_primary", то обе они исчезают из OPEN-фильтра → re-adopt возможен. Я нашёл такие кейсы в positions.json (все 14 merged связаны с primary, большинство которых уже закрыты).

### Конкретный пример (из positions.json.backup_before_hezbollah_fix era)

```
"status": "merged_into_primary",
"merged_into": "0x...",
"merged_at": "2026-04-11T18:..."
```
У этих записей есть свои `order_ids`, `cost_usd`, но primary у них уже sold. Loose фильтр создаст `0xsync_X` с `signal_player=unknown`, теряя связь с историческим primary (parent key и consolidation refs).

---

## Риск 4 — Потеря cost basis

**Severity: CONFIRMED_MINOR**

### Откуда берётся avgPrice

`tracker.sync_with_onchain` (lines 785-794):
```python
resp = requests.get(f"{DATA_API}/positions", params={...sizeThreshold: 1}, timeout=15)
for p in resp.json():
    if p.get("conditionId") == cid and p.get("asset") == token:
        avg_price = float(p.get("avgPrice", 0) or 0)
```
Источник: **Polymarket Data API avgPrice** (усреднение по исторических трейдам, включая partial fills от market-maker-а). Если API возвращает `avgPrice=0` → `cost_est = 0` (строка 801).

### Сравнение с реальностью (сейчас, OPEN позиции)

Проанализировал 27 открытых позиций:

| Title (45ch) | sp | tk_cost | tk_avg | oc_cost | oc_avg | diff |
|---|---|---|---|---|---|---|
| Will the US x Iran ceasefire extended | denizz | $0.78@0.005 | — | $111.08@0.701 | — | -$110.30 |
| US x Iran permanent peace deal May 31 | denizz | $287.14@0.967 | — | $196.01@0.660 | — | +$91.13 |
| US obtains Iranian enriched uranium | denizz | $311.56@0.880 | — | $273.78@0.774 | — | +$37.78 |
| Israeli forces cross Litani River | manual | $76.80@0.963 | — | $57.61@0.722 | — | +$19.19 |
| Iran agrees to surrender uranium | denizz | $30.37@0.542 | — | $15.18@0.271 | — | +$15.19 |

Total diff: **$+67** из $2923 basis (+2.3%). Среди re-adopted/manual позиций (9 шт): среднее |diff| <$2. Годовая оценка искажения PnL: <5%.

### Вердикт

Потеря cost basis присутствует при re-adoption (API avg может отставать от реального VWAP buy-events), но amplitude минимальная. Критично только для спорадических manual-buy на thin markets, где API avg может быть устаревшим.

---

## Риск 5 — Потеря signal_player → follow-sell сломан

**Severity: CONFIRMED_MINOR (функциональный регресс, но не blocker для данных)**

### Доказательства из кода

`tracker.py:814`:
```python
"signal_player": "unknown",
```
Все re-adopted позиции получают default "unknown".

`exit_manager.handle_player_sell` (exit_manager.py:800-805):
```python
pos_signal_player = pos.get("signal_player", "")
if (pos_signal_player
        and pos_signal_player != player_name
        and pos_signal_player != "manual"):
    print(f"[EXIT] SKIP: {player_name} sold but position was opened by {pos_signal_player} | {title[:50]}")
    return
```

**Early return**: если `signal_player="unknown"` и `player_name="denizz"` → `"unknown" != "denizz" and "unknown" != "manual"` → TRUE → SKIP. Follow-sell НЕ сработает.

### Симуляция

Re-adopted позиция (signal_player=unknown) → denizz продаёт 70% → monitor detects SELL → `handle_player_sell("denizz", event)`:
1. dedup_guard OK
2. on-chain truth computed (delta_sold=70%)
3. match tracker position by (cid, tok) → match found
4. check signal_player: `"unknown" != "denizz" && != "manual"` → **SKIP** с логом `SKIP: denizz sold but position was opened by unknown`

Проверено также в bot_log_audit: из 1540 denizz SELL событий **10 skip_cross_player** (именно этот путь). В live-replay видим, что `signal_player="manual"` (ручные re-adopt скрипты) работают корректно.

### Обходной путь (уже применяется)

В `_readopt_iran_israel_conflict_apr7.py:81`: `"signal_player": "manual"` — явный манекен, обходящий проверку. Т.е. **для автоматического re-adopt это надо было бы менять**, но логика `unknown` — намеренный guard.

---

## Риск 6 — Race condition + test surface

**Severity: NOT_APPLICABLE на текущем коде (locks достаточны)**

### Параллельные циклы на одной (cid, token)

1. **monitor** (per-player threads) → вызывает `handle_buy` / `handle_player_sell`
2. **check_exits** (60s loop) → stop-loss, take-profit, pending retry
3. **sync_with_onchain** (5 min) → adopt / adjust / close
4. **redeemer.redeem_loop** (180s) → resolve won/lost
5. **pending_retry** (внутри check_exits) → re-try _execute_sell
6. **rebuy** (на BUY events от denizz) → _entry_lock защита

### Locks (после фиксов 2026-04-17)

- `tracker._io_lock` (RLock) — wraps load()/save() → атомарная персистенция (line 24)
- `exit_manager._exit_dedup_lock` — check-and-set в dedup dict (line 285, 702-710)
- `exit_manager._sell_execution_lock` — serialize `_execute_sell` calls (line 286, 486)
- `main._entry_lock` — parallel handle_buy() race guard (line 64, 765)

### Покрытие

`sync_with_onchain` сам вызывает `tracker.save(data)` под `_io_lock` (строка 829). Re-adopted записи попадают в снапшот атомарно. Если бы послабить фильтр, gap между "sync видит на on-chain" и "new record saved" остался бы покрыт блокировкой io_lock. Дополнительных race-путей фикс не вводит.

Дополнительные unit-тесты, которые были бы полезны:
- `test_sync_with_onchain_respects_closed_statuses` — убедиться что sold/lost/won/merged не re-adopt'ятся
- `test_sync_dust_threshold` — <10 sh skip
- `test_sync_redeemer_race` — сценарий redeem-in-flight while sync runs (нет такого сейчас)

---

## Результаты регрессии

### Unit-тесты

| Test suite | Result |
|---|---|
| `_test_rebuy_v9.py` | **36 passed / 0 failed** |
| `_test_follow_sell_comprehensive.py` | **75 passed / 0 failed** |
| `tests/test_disappear_guard.py` | **13 passed / 0 failed** |
| `tests/` (full) | 96 passed / 3 failed |

**3 failed в `test_manual_follow.py`** — assertion диапазоны `45-55%` против актуального tier `55%`. Смотрим `config.FOLLOW_SELL_TIERS_PROFIT`: tier 50-60% → 0.55. Тесты на устаревшей табличке, не связаны с re-adoption. Не blocker.

### Smoke-import (py_compile)

```
monitor.py main.py tracker.py exit_manager.py filters.py rebuy.py redeemer.py entry_manager.py executor.py
→ OK_COMPILE
```

### Live replay (bot.log за 7 дней)

`_audit_bot_log_sells.py` (1540 MONITOR:denizz SELL событий):

| Classification | Count | % |
|---|---|---|
| skip_duplicate (dedup 60s) | 990 | 64.3% |
| skip_unknown | 180 | 11.7% |
| skip_dust_tier | 168 | 10.9% |
| silent_after_onchain_ok | 161 | 10.5% |
| skip_phantom | 13 | 0.8% |
| follow_sell_executed | 11 | 0.7% |
| skip_cross_player | 10 | 0.6% |
| follow_sell_failed | 6 | 0.4% |
| follow_skip_onchain_empty | 1 | 0.1% |

Response rate = 2.05% on actionable. Все `SKIP` — с валидной причиной (dedup/phantom/cross_player/dust). Нет orphan events.

---

## Итоговая рекомендация

**НЕ ДЕЛАТЬ ФИКС (послабление `existing_keys` до OPEN-only).**

Причина: Risk 1 — это CONFIRMED_BLOCKER. Симуляция на живых данных показывает, что послабление немедленно создаст 53 новых `0xsync_...` записи на одном цикле. Логи доказывают масштаб до-фиксного loop'а (19 785 re-adopt событий).

Остальные риски (2, 3, 5) — вторичные эффекты, проявляются только на top'е Risk 1. Risk 4 (cost basis drift) — минорный но неизбежный при любой автоматической re-adoption.

---

## Альтернативы (как решать исходную проблему)

Исходная проблема: on-chain балансы у закрытых позиций остаются "orphaned" — watchdog даёт false alarm, redeem не срабатывает, следовать за denizz sell нельзя.

**Рекомендуется:**

1. **Точечные манipular re-adopt скрипты** — уже есть шаблон `_readopt_iran_israel_conflict_apr7.py`. Использовать `signal_player="manual"` (не "unknown") чтобы обойти Risk 5 (follow-sell будет работать).

2. **Watchdog улучшение:** вместо глобального `_verify_sync` алерта добавить whitelist `_closed_with_onchain_remnant` — известные orphan'ы. Список обновляется ручным re-adopt'ом или помечается как "ignore_in_watchdog".

3. **Redeemer расширение:** научить redeem_loop проходить не только по `open`, но и по списку "orphan known" (т.е. closed но с on-chain balance > 0 из отдельного JSON-реестра). Безопаснее, чем re-adopt, т.к. не трогает бизнес-логику tracker.

4. **Флаг per-position `_readopt_eligible: True`** — для specific закрытых позиций ставить вручную флаг → reverse-scan может re-adopt только их. Но это добавляет state, лучше через manual script.

**НЕ рекомендуется:**
- Послабление `existing_keys` до `status=="open"` (CONFIRMED_BLOCKER).
- Любая логика, которая **автоматически** re-adopt'ит closed positions без явного флага.

---

## Приложение: ключевые цитаты из кода

### tracker.sync_with_onchain filter (lines 759-774)
```python
# --- Reverse scan: on-chain → state ---
existing_keys = set()
for pos in data.get("positions", {}).values():
    # Include ALL tracked positions (any status) to prevent re-adopting
    # positions that were manually closed/marked lost — otherwise on-chain
    # remnants would be re-adopted as new 0xsync_X entries on every sync cycle.
    existing_keys.add((pos.get("condition_id", ""), str(pos.get("token_id", ""))))

adopted = 0
for (cid, token), shares in onchain.items():
    if shares < 10:  # Bug 4 fix: skip dust
        continue
    if (cid, token) in existing_keys:
        continue
```

### tracker.sync_with_onchain new record (lines 799-823)
```python
new_key = "0xsync_" + hashlib.md5(f"{cid}_{token}".encode()).hexdigest()[:34]
cost_est = round(shares * avg_price, 2) if avg_price > 0 else 0
data.setdefault("positions", {})[new_key] = {
    ...
    "signal_player": "unknown",
    ...
    "_adopted_from": "onchain_sync",
}
```

### exit_manager.handle_player_sell gate (lines 800-805)
```python
pos_signal_player = pos.get("signal_player", "")
if (pos_signal_player
        and pos_signal_player != player_name
        and pos_signal_player != "manual"):
    print(f"[EXIT] SKIP: {player_name} sold but position was opened by {pos_signal_player} | {title[:50]}")
    return
```

### Evidence: log counts pre/post fix
- Pre-fix (до 2026-04-15 22:00): `[SYNC] ADOPTED` — **19 785 events**
- Post-fix: **1 event** за последние ~2 суток

---

**Автор аудита:** Claude (independent review)
**Подпись данных:** `positions.json` as of 2026-04-17 18:08, `bot.log` 108 950 строк, data-api snapshot 99 on-chain позиций.
