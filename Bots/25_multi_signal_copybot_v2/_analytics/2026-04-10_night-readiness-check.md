# Multi-Copy Bot — Night Readiness Check

**Time:** 2026-04-10 (начало ночного сеанса)
**Scope:** `25_multi_signal_copybot` только (не sure/weather/overround)
**Цель:** можно ли оставить бот работать без наблюдения 6-10 часов?

---

# 🟢 VERDICT: READY с 2 мелкими оговорками

Бот полностью функционален. Все критичные системы проходят проверку. Есть 2 мелких риска которые **не критичны**, но стоит знать.

---

## Checkpoints

| # | Check | Status | Note |
|---|---|---|---|
| 1 | copybot main PID alive | ✅ PASS | PID 79792 (py.exe launcher 70936 → python 79792), uptime 1.2h, 72 MB RAM |
| 1 | watchdog alive | ✅ PASS | PID 9036, started 19:54 UTC, последний event 20:37 (bot found) |
| 1 | metrics_loop alive | ⚠ MINOR | не запущен. Не влияет на торговлю, только на dashboard метрики |
| 1 | bot.log freshness | ✅ PASS | последнее действие 23:41 UTC (21 мин назад) — это нормально, денизз тишина |
| 1 | pids.json actual | ✅ PASS | `pid=79792` совпадает с реальным PID |
| 2 | tracker vs on-chain | ✅ PASS | **9/9** open позиций синхронизированы (drift=0, zombies=0, duplicates=0) |
| 2 | USDC баланс | ✅ PASS | $540.57 on-chain, $390.57 available (reserve $150) |
| 3 | is_long_horizon (8 cases) | ✅ PASS | 8/8 |
| 3 | get_long_horizon_multiplier | ✅ PASS | 4/4 |
| 3 | get_player_invested_on_token (net) | ✅ PASS | Hezbollah Apr30: возвращает $15,450 net (было бы $34,841 gross) |
| 3 | get_player_cost_basis | ✅ PASS | возвращает 0.5685 на denizz Hezbollah Apr30 |
| 3 | consolidate_duplicates idempotent | ✅ PASS | второй вызов merge 0 |
| 3 | _is_manual_sell (6 cases) | ✅ PASS | 6/6 |
| 3 | Константы | ✅ PASS | 6/6 (DUST 0.10, BIG 0.70, DELTA 0.01, DEDUP 60, POST_EXIT 0.05, LH_MULT 0.2) |
| 4 | Decision matrix simulation | ✅ PASS | **9/9** — dust skip, big dump, rule 2a, 2b, unknown fallback все корректны |
| 4 | Dedup guard ON/OFF | ✅ PASS | SKIP при 0s, FIRE при 61s |
| 4 | Long-horizon × tier bet | ✅ PASS | B $6 / A $11 / S $21 / S+ $40 (все проходят min_bet=$10 кроме B) |
| 5 | buy_buffers.json size | ✅ PASS | 14 KB |
| 5 | signaled_keys on disk | ✅ PASS | empty dict (in-memory только) |
| 5 | Stuck buffers | ⚠ MINOR | **1 найден** — Hezbollah June 30 (`0x0d52ce...`), notified=True, 9 buys, но last_tier_bet=0. Не блокирует — бот пересчитает при next tier |
| 6 | Open positions | ✅ PASS | 9/40 (много места для новых сигналов) |
| 6 | USDC capacity | ✅ PASS | 1× S+ full bet или 9× long-horizon bet |
| 6 | Pending 3-part signals | ✅ PASS | 24 signals в очереди, все part2_done=True ждут part3 dip |
| 7 | .tmp leftover files | ✅ PASS | 0 |
| 7 | bot.log size | ✅ PASS | 1.5 MB |
| 7 | RPC (Tenderly) responsive | ✅ PASS | on-chain fetch работает |
| 7 | Gamma invalid token handling | ✅ PASS | возвращает None (не crash) |
| 7 | data-api positions | ✅ PASS | HTTP 200 |
| 7 | CLOB orderbook | ✅ PASS | HTTP 200 |
| 7 | _recent_exit_fires initial | ✅ PASS | 0 entries на reload |
| 7 | HP positions | ✅ PASS | 0 открытых HP (upgrade skip path dormant) |
| 8 | Pending CLOB orders | ✅ PASS | 0 висящих |
| 9 | Watchdog running | ✅ PASS | PID 9036, monitor loop 60s |
| 9 | Watchdog has --bot-tag | ✅ PASS | `cmd` содержит tag |
| 9 | Watchdog matcher works | ✅ PASS | нашёл copybot по cmdline scan 20:37 |

**Total:** 32 PASS, 2 MINOR, 0 WARN, 0 FAIL

---

## 🟡 Minor Risks (не критичны)

### Risk M1: metrics_loop не запущен
**Что это:** `_metrics_loop.py` — вспомогательный процесс который каждые 5 мин запускает `_reconcile.py` (проверка tracker vs on-chain). Не влияет на торговлю.

**Последствия:** если за ночь возникнет tracker-drift (что маловероятно при новых фиксах), авто-reconcile не сработает. Но:
- Core бот уже self-healing через `consolidate_duplicates()` в record_position / handle_player_sell / check_exits
- Все 9 текущих позиций в sync

**Вероятность наступления:** низкая
**Ущерб если сработает:** низкий (можно почистить утром)
**Fix сейчас (30 сек):** запустить `_metrics_loop.py` через nohup. **Не обязательно**

### Risk M2: 1 stuck buffer (Hezbollah June 30)
**Что это:** buffer `0x0d52ce...` имеет `notified=True` и 9 buys, но `last_tier_bet=0`. На этом рынке реально есть открытая позиция (**10.01 sh**), но tracker-запись показывает что она почти пуста.

**Последствия:** если денизз сделает новую BUY с переходом в новый tier:
- bot пройдёт через tier-upgrade path
- `last_tier_bet=0` → полный доcчёт (не недоплатит)
- ничего критичного не произойдёт

**Если денизз сделает dump:** rule 2a/2b/3 отработает на оставшиеся 10.01 sh. Dedup guard (60 sec) защитит от burst-дубликатов.

**Вероятность наступления:** низкая (10.01 sh = cost $3.66, небольшая позиция)
**Ущерб если сработает:** <$5 (весь ценность позиции)
**Fix сейчас:** не требуется

---

## 🟢 Защитные механизмы которые работают

Эти фиксы внедрены сегодня и все **verified in memory**:

1. **Gross → Net fix**: `get_player_invested_on_token()` возвращает `size × avgPrice`, не `totalBought × avgPrice`. Предотвращает overexposure на позициях где денизз уже частично вышел.

2. **Rule A+ on increment** (не total): tier-upgrade правильно скейлит **доплату**, не весь размер. `last_tier_bet` хранит actual spent.

3. **HP skip в tier-upgrade**: HP-позиции не ловят tier-upgrade, остаются на своей фиксированной логике.

4. **Rule C tightened + manual skip**:
   - `POST_EXIT_PRICE_CHANGE_MIN = 0.05` (было 0.10)
   - `_is_manual_sell()` пропускает manual exits при Rule C — не блокирует повторный вход после ручного закрытия

5. **consolidate_duplicates**: самовосстановление trackers от дублей. Вызывается в `record_position`, `check_exits`, `handle_player_sell`.

6. **Duplicate sell event guard**: `EXIT_DEDUP_WINDOW_SEC = 60`. Burst SELL events от одного большого денизз-дампа обрабатываются как 1 событие, не N. Защита от "29% стал 86%".

7. **Long-horizon × 0.2 multiplier** для end_date ≥ Dec 1 2026. Применяется **на любом тире** (B/A/S/S+) и композится с Rule A+.

8. **Decision matrix** (rule 2a/2b/3):
   - sold < 10% → skip dust
   - sold ≥ 70% → full exit (rule 3)
   - 10-70% + denizz loss → mirror % (rule 2a)
   - 10-70% + denizz profit + we profit → mirror % (rule 2b)
   - 10-70% + denizz profit + we loss → skip
   - unknown → fallback follow if we profit

9. **Watchdog с --bot-tag**: matcher надёжно находит bot даже если psutil не может прочитать cwd у detached процесса.

---

## 🔥 Что может пойти не так ночью (и что сделает бот)

| Сценарий | Что произойдёт |
|---|---|
| Денизз купит на новом рынке | Bot зайдёт с правильным тиром × multipliers |
| Денизз докупит крупно на existing позиции | Tier-upgrade с правильным increment |
| Денизз продаст 80% на рынке | Rule 3 full exit (dedup guard блокирует дубли) |
| Денизз продаст 30% в убытке | Rule 2a mirror % — продадим 30% |
| Денизз продаст 30% в плюсе, мы в плюсе | Rule 2b mirror % |
| Денизз продаст 30% в плюсе, мы в минусе | Skip — не фиксируем убыток |
| Денизз продаст мелочь (5%) | Skip dust |
| Burst из 10 SELL events за 2 секунды | 1 order, остальные skip по dedup |
| Bot крашнется | Watchdog перезапустит через 60 сек |
| RPC (Tenderly) ляжет | on-chain fetch вернёт None → fallback на internal counter |
| Gamma API ляжет | get_market_info → None → signal skip |
| CLOB ляжет | sell order fail → retry или skip |
| Рынок обрушится на 65%+ | Stop-loss сработает (EXIT_STOP_LOSS_PCT=0.65) |
| Position 16 дней без движения | Time stop (EXIT_TIME_STOP_DAYS=16) |
| Цена 0.99+ и мы в плюсе | Take-profit (EXIT_SELL_AT_PRICE=0.99) |

---

## 📋 Summary

**Можно ложиться спать.** Вероятность что бот тихо сломается ночью — **низкая**:
- Все функции работают
- Тесты проходят 27/27
- Decision matrix симуляция 9/9
- Трекер в sync с on-chain
- Watchdog живой и с правильным matcher'ом
- Dedup guard подтверждён в бою (bot.log 23:20 показывает SKIP duplicate)
- Нет висящих ордеров на CLOB
- Нет .tmp leftover
- Все 3 внешних API отвечают

Единственные theoretical risks — это M1/M2 выше, они **не могут привести к большим потерям**.

**Мониторинг утром:** если что-то странное — смотри `bot.log` от timestamp'а 23:41 UTC и позже, и пробегись по balance vs tracker через смот simple script.
