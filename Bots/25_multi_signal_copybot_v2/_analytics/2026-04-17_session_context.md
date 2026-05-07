# Контекст сессии 12-17 апреля 2026 — 25_multi_signal_copybot_v2

## Что это за бот

Copy-bot для Polymarket. Копирует сделки игрока **denizz** (кошелёк `0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73`). Бот отслеживает активность denizz через Polymarket Data API, фильтрует сигналы и размещает ордера через CLOB API. Банкролл ~$2500.

Рабочая директория: `C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\`

---

## Архитектура бота

3 процесса (запускаются через watchdog):
- **main.py** — основной цикл: мониторинг событий denizz, фильтрация, размещение ордеров, tier-upgrade
- **_metrics_loop.py** — сбор метрик
- **_watchdog.py** — следит за процессами, рестартит при падении, VERIFY sync каждые 10 мин

Ключевые модули:
- **config.py** — все параметры и пороги
- **tracker.py** — трекинг позиций, on-chain sync, P&L
- **filters.py** — фильтрация сигналов, расчёт размера ставки, детекция хеджей
- **exit_manager.py** — follow-sell логика, stop-loss, peak-based cumulative sell tracking
- **monitor.py** — fetch_recent_activity от denizz

---

## Исправленные баги за сессию

### 1. Ghost-позиции раздували drawdown
Resolved-маркеты с нулевым payout оставались "открытыми" в tracker → drawdown считался как $104K убытка → бот блокировал новые входы.
**Решение:** drawdown check удалён полностью из `tracker.py:can_open_new()`. Задача контроля рисков решается stop-loss по каждой позиции.

### 2. MAX_CONCURRENT ложно блокировал входы
Ghost-позиции занимали 40 слотов из MAX_CONCURRENT.
**Решение:** MAX_CONCURRENT check удалён полностью.

### 3. Monitor limit=20 — пропуск сигналов продажи
Denizz генерировал 60+ событий/мин при mass-buy → sell-события выпадали из окна 20 записей → задержка детекции до 48 мин.
**Решение:** `monitor.py` — limit увеличен с 20 до 100.

### 4. Hedge false positive из-за float precision
`ratio = player_invested / (player_invested / HEDGE_RATIO_MAX)` — IEEE-754 даёт ≠ HEDGE_RATIO_MAX в ~17% случаев.
**Решение:** Вместо epsilon добавлено жёсткое правило: если мы держим противоположную сторону на том же event_slug → отказ от входа (STEP 4b-pre в `filters.py`).

### 5. Timeseries hedge dust false positive
15 shares NO ($10) на December-варианте триггерили hedge detection для 88K shares YES ($30K) April-варианта.
**Решение:** Добавлен 3% dust threshold (`HEDGE_DUST_RATIO = 0.03`) в `detect_timeseries_hedge()`.

### 6. "Already signaled" после ручной продажи
`last_tier_bet` не обновлялся при ручной продаже → бот отказывался повторно входить.
**Решение:** Variant 1 (`USE_ONCHAIN_COST`) — читает cost из tracker вместо buy buffer.

---

## Текущие параметры (config.py)

```python
# Формула ставки: bet = A * ln(invested) + B
BET_FORMULA_A = 31.75
BET_FORMULA_B = -177.0
MIN_BET_FORMULA = 20.0  # минимальная ставка (может быть 10)
MAX_BET_USD = 200        # максимальная ставка

# Stop-loss тиры
STOP_LOSS_TIERS = [
    (0.02, 0.15, 0.60),   # цена 2-15¢ → -60%
    (0.15, 0.70, 0.60),   # цена 15-70¢ → -60%
    (0.70, 0.82, 0.45),   # цена 70-82¢ → -45%
    (0.82, 0.99, 0.35),   # цена 82-99¢ → -35%
]

# Top-up ratio тиры (отношение новой ставки к существующей позиции denizza)
TOPUP_RATIO_TIERS = [
    (0.00, 0.03, 0.0),    # <3% от портфеля → пропускаем (шум)
    (0.03, 0.10, 0.5),    # 3-10% → 50% от формулы
    (0.10, 0.30, 0.75),   # 10-30% → 75%
    (0.30, 999.0, 1.0),   # >30% → 100%
]

USE_ONCHAIN_COST = True  # Variant 1: читать cost из tracker вместо buy buffer
ONCHAIN_COST_GRACE_SEC = 45
TIER_UPGRADE_THROTTLE_SEC = 60
MIN_UPGRADE_USD = 15.0
```

---

## Follow-sell логика (exit_manager.py)

- При старте бота вызывается `init_player_peaks()` — загружает пиковые балансы denizz для всех открытых позиций из истории activity API
- `_player_peak_cache` хранит {(condition_id, token_id): peak_balance}
- При sell-событии denizz: `sold_pct = (peak - current) / peak` — кумулятивный процент продажи от пика
- Sell тиры определяют какую долю нашей позиции продавать

---

## Фильтрация сигналов (filters.py)

Порядок проверок (STEP):
1. Базовые проверки (маркет активен, не resolved)
2. Минимальная ставка denizz
3. Хедж-детекция (same-condition, cross-market, timeseries с 3% dust)
4. Split: api_position_usd и buffer_total
4b-pre. HARD opposite-side block (если у нас есть противоположная сторона на том же event)
4c. Top-up ratio filter
5-6. Расчёт размера ставки по формуле
7a. Применение top-up ratio multiplier

---

## Ключевые исследования

### Denizz P&L анализ
- На бакетах $5K+ WR denizz = 22-33% — низкий, но высокая дисперсия (крупные выигрыши компенсируют)
- Scalp-трейды (вход/выход <2 часов) составляют значительную часть — обсуждалась задержка входа 5-10 мин для фильтрации

### Формула ставки — бэктест
- Протестированы 6 вариантов формулы
- V1/V6 ($100 cap) показали лучший результат для банкролла $2500
- Формула B (двухступенчатая) хуже формулы A (линейный логарифм)
- Текущие A=31.75, B=-177.0 — компромисс

### Merge→exit правило
- Бэктест был неубедительный (50% WR, 6 samples) — нужно больше данных

---

## Незавершённые задачи

1. **Dry-run Variant 1** — запущен отдельный процесс `_dry_run_variant1.py`, логирует в `_analytics/dry_run_variant1.jsonl`. Нужно 24-48ч данных, но пользователь уже включил `USE_ONCHAIN_COST = True` в production.

2. **10% price-gap retry** — идея: если наш bid сильно хуже sell-цены denizz, подождать 60с перед продажей. Не реализовано.

3. **Entry delay 5-10 мин** — фильтрация scalp-трейдов denizz. Не реализовано.

4. **Formula V6 ($10/$100)** — бэктест показал оптимальность для $2500, но не внедрено.

5. **SYNC MISMATCH** — watchdog стабильно фиксирует 1 позицию (~$19) on-chain, отсутствующую в state бота. Некритично, но стоит разобраться.

---

## Мониторинг 17 апреля (60 мин, 13 итераций)

**Вердикт: бот здоров.**
- Дубликатов процессов не обнаружено ни разу
- Рестартов watchdog не было
- Ошибок в bot.log нет
- Единственное замечание: SYNC MISMATCH $19 (1 позиция)

---

## Ручные сделки за сессию

За 12-17 апреля было выполнено множество ручных операций:
- Лимитные продажи по 4 позициям (100%)
- Покупка NO $30 "Trump endorse Israeli ceasefire"
- Множество buy/sell ордеров на Iran-related маркеты
- Покупка NO $50 "US obtains Iranian enriched uranium by May 31" (64.11 shares @ 78¢)
- Продажа 35% "US x Iran permanent peace deal by April 22" YES @ 24¢

---

## Важные файлы

- `config.py` — все параметры
- `tracker.py` — трекинг позиций
- `filters.py` — фильтрация и sizing
- `exit_manager.py` — follow-sell и stop-loss
- `main.py` — основной цикл
- `monitor.py` — мониторинг denizz
- `_watchdog.py` — watchdog процесс
- `positions.json` — текущие позиции
- `_test_peak_calculation.py` — тесты peak logic (все проходят)
- `_test_variant1.py` — тесты Variant 1 (все проходят)
- `_dry_run_variant1.py` — dry-run процесс
- `_analytics/` — папка с аналитикой и бэктестами
