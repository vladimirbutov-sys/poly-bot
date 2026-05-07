# Сессия 2026-04-16: Code Review + Bugfixes

## Что сделали

### 1. Merge-exit правило — УДАЛЕНО

**Бэктест:** 28 merge-событий, win rate 3.6% (порог для удаления < 40%).
Правило теряло в среднем 1.6 центов/шару. Удалено из `exit_manager.py`:
- Убрали `source = "merge"` маппинг (строки 657-658)
- Убрали `sold_pct_player = 1.0` для merge (строки 677-678)
- Убрали весь merge decision branch (строки 803-825)
- Убрали `source != "merge"` из sanity check (строка 837)

Отчёт: `_analytics/2026-04-15_merge-exit-backtest-review.md`

### 2. Ultra-Review от Opus 4.7

Получили code review от Opus 4.7 (`C:\Users\Honor\Downloads\ULTRAREVIEW_2026-04-16_1.md`).
28 пунктов: 3 CRIT, 9 HIGH, 15 MED, 14 LOW.

**Мой анализ по актуальному коду:**
- 3 из 3 CRIT — подтверждены
- 8 из 9 HIGH — подтверждены, 1 ошибка (HIGH-4: N+1 запросов нет, код уже делает bulk fetch)
- CRIT-2: из 3 заявленных багов в resolve_position реальным оказался только 1 (удвоение current_balance). Баги 2 и 3 не подтвердились — record_sell уже уменьшает size_shares и cost_usd, поэтому расчёты PnL корректные

Полный анализ: `_analytics/2026-04-16_ultrareview-analysis.md`

### 3. Применённые фиксы (10 штук)

#### Фикс 1: Merge-exit удалён
- Файл: `exit_manager.py`
- Риск: нулевой (правило вредило)

#### Фикс 2: CRIT-2 — resolve_position current_balance
- Файл: `tracker.py:520`
- Было: `stats["current_balance"] += pos["size_shares"] + (pos["size_shares"] if won else 0)` — удваивало баланс при win, прибавляло при loss
- Стало: `if won: stats["current_balance"] += pos["size_shares"]` — при win прибавляет payout, при loss не трогает
- Тест: `tests/test_resolve_position.py` (4 теста, все зелёные)

#### Фикс 3: Cache race — кеш "проглатывал" продажи
- Файл: `exit_manager.py:refresh_cache_for_open_positions()`
- Проблема: cache refresh обновлял кеш до post-sell значения ДО того как монитор присылал sell event. handle_player_sell видел delta=0 и тихо пропускал
- Конкретный случай: денизз продал 23,333 шары "Will Trump agree to Iranian enrichment of uranium" за $8,633, бот не последовал
- Фикс: cache refresh НЕ обновляет кеш если баланс уменьшился (ждёт handle_player_sell). Через 120 секунд — принудительное обновление (чтобы кеш не застревал навсегда)

#### Фикс 4: Логирование тихих return в handle_player_sell
- Файл: `exit_manager.py`
- Добавлен print на все ранее "тихие" return: missing wallet/token_id, peak_size=0, cached_size=0, delta=0

#### Фикс 5: HIGH-2 — monitor backoff
- Файл: `monitor.py:400`
- Было: `consecutive_errors = getattr(e, '_consecutive', 0) + 1` — всегда = 1
- Стало: `consecutive_errors += 1` — правильный экспоненциальный backoff

#### Фикс 6: HIGH-7 — guard price<=0 в executor
- Файл: `executor.py:place_limit_buy()`
- Добавлен guard: `if price <= 0.0 or price >= 1.0 or size_usd <= 0.0: return None`

#### Фикс 7: HIGH-6 — thread-safe _get_client
- Файл: `executor.py:_get_client()`
- Добавлен `threading.Lock()` с double-checked locking

#### Фикс 8: HIGH-8 — удалён мёртвый check_hedge_exits
- Файл: `exit_manager.py:875-924`
- Удалена функция + переменная `_last_hedge_recheck`
- Никто не вызывал, импортировала несуществующий `HEDGE_RECHECK_INTERVAL`

#### Фикс 9: MED-11 — удалён мёртвый конфиг
- Файл: `config.py:314-315`
- Удалены `LIMIT_ORDER_TTL` и `LIMIT_ORDER_CHECK_INTERVAL` (нигде не использовались)

#### Фикс 10: CRIT-3 — sleep между реедемами 5→15 сек
- Файл: `redeemer.py:291`
- Увеличена пауза между redeem транзакциями для предотвращения nonce collisions

### 4. Фикс Telegram-спама от тестов
- Файл: `tests/test_manual_follow.py`
- Добавлен мок `tg.send` чтобы pytest не отправлял реальные Telegram-сообщения

### 5. Тесты
- Полный suite: **111 passed, 3 pre-existing failures** (test_manual_follow.py — были и до наших изменений)
- Новые тесты: `tests/test_resolve_position.py` — 4 теста на баланс при resolve

---

## Что НЕ сделали (отложено)

### Отложено — затрагивает торговую логику:
| # | Фикс | Причина |
|---|------|---------|
| HIGH-1 | Retry price для дешёвых токенов (round(0.05*0.98)=0.05) | Меняет расчёт цены продажи |
| HIGH-5 | return None при пустом стакане | 15+ мест вызова, нужен полный аудит |
| HIGH-9 | Async TG notifications | Меняет threading модель |
| HIGH-3 | Bounded seen_keys (5000 max) | Может пропустить дубликат |
| MED-6 | Свежая цена при pending retry | Меняет цену продажи |
| MED-14 | Guard days < 0 в horizon filter | Может заблокировать торговлю |
| MED-5 | Кеш позиций в detect_timeseries_hedge | Меняет hedge detection |
| CRIT-1 | FillResult + actual fill prices | Большой рефактор 1-2 дня |
| MED-13 | Удалить wait_for_fill | Используется в sell_all_now.py (НЕ мёртвый) |

### A/B тест лимитных ордеров
- Тихое логирование запущено с 2026-04-16 ~11:08
- Данные копятся в `limit_ab_log.csv`
- Day 5 чекпоинт: 2026-04-21 — запустить `python _report_limit_ab.py --day 5`

---

## Ключевые находки

1. **Бот торгует правильно** (входы/выходы на основе on-chain данных), но **считает PnL неточно** (CRIT-1: limit price вместо actual fill price, CRIT-2: удвоение баланса — починено)

2. **Cache race** — серьёзный баг, из-за которого бот пропускал продажи денизза. Починен. Конкретный пример: пропущена продажа uranium enrichment на $8,633

3. **Opus 4.7 ревью** — качественное (27 из 28 пунктов подтверждены), но иногда ошибается в деталях (HIGH-4 не существовал, CRIT-2 баги 2+3 не подтвердились)

4. **internal counter vs on-chain**: $407,582 vs $496.44 — internal counter сломан историческими данными от бага CRIT-2. Новые resolve будут считаться правильно, старые данные уже испорчены

---

## Файлы изменены в этой сессии

- `exit_manager.py` — merge-exit удалён, cache race fix, логирование, check_hedge_exits удалён
- `tracker.py` — resolve_position balance fix
- `monitor.py` — consecutive_errors fix
- `executor.py` — thread-safe _get_client, guard price<=0
- `config.py` — мёртвый конфиг удалён
- `redeemer.py` — sleep 5→15
- `tests/test_resolve_position.py` — НОВЫЙ (4 теста)
- `tests/test_manual_follow.py` — добавлен TG мок

## Аналитика создана
- `_analytics/2026-04-15_merge-exit-backtest-review.md`
- `_analytics/2026-04-16_ultrareview-analysis.md`
