# news_spike — News informer + Spike detector для copybot-v2

Модуль реализует **две задачи** в одном процессе:

### 🔵 Задача 1 — News informer
Мониторит источники новостей по Иран/США/Израиль и отправляет Telegram-алерты с Claude-оценкой.

**Источники (из `configs/sources_iran.json`):**
- **Telegram:** 27 каналов (Tier 1: 12, Tier 2: 11, Tier 3: 4) — en/fa/ar/he/ru
- **Twitter/X:** @araghchi (МИД Ирана, тир-1) — критически важный источник
- **Truth Social:** @realDonaldTrump через RSS trumpstruth.org (polling 15 сек)

**Pipeline:**
1. Polling источников → `on_message` callback
2. Фильтр по 146 ключевым словам (5 языков)
3. MD5-дедупликация (`data/seen_hashes.json`, max 5000)
4. **Crisis Bypass:** Tier-1 + crisis keyword → мгновенный alert без Claude
5. Иначе → Claude Haiku оценка (escalation/de-escalation, HIGH/MEDIUM/LOW)
6. Topic dedup (20 мин окно)
7. Telegram alert + log

### 🟠 Задача 2 — Spike detector
Мониторит **21 наш Iran/US рынок** (из `configs/target_markets_iran.json`) и алертит при движении **≥5 п.п. за 5 мин**.

- Poll каждые 30 сек через MarketCache (Gamma API)
- Cooldown 5 мин на один рынок
- Event-level dedup (чтобы не дублировать алерты по одному событию с разных сторон)

### ❌ Что НЕ запускается
- `auto_hedge.py` — автоматический хедж (не скопирован)
- `auto_spike_rider.py` — автотрейдинг на постах Трампа (не скопирован)
- `digest.py` — ежедневные дайджесты (не скопирован)

Только **алерты в Telegram**, никаких торговых действий.

---

## Запуск

```bash
cd news_spike
python run_news_spike.py
```

## Остановка

Ctrl+C. Хеши обработанных сообщений сохранятся в `data/seen_hashes.json`.

## Конфигурация

### `.env` (скопирован из 9_NON_west_signals...)
- `TG_BOT_TOKEN` / `TG_CHAT_ID` — Telegram bot для алертов
- `X_BEARER_TOKEN` — Twitter API v2 для @araghchi
- `ANTHROPIC_API_KEY` — Claude Haiku для оценки новостей
- `MIN_CONFIDENCE=MEDIUM` — минимум для отправки алерта
- `POLYMARKET_WALLET` / `POLYMARKET_PRIVATE_KEY` — НЕ используется в alert-only режиме

### `configs/`
- `sources_iran.json` — 27 TG каналов + @araghchi + 146 keywords
- `target_markets_iran.json` — 21 наш Iran/US рынок (генерируется из `../positions.json`)

### `data/` (создаётся автоматически)
- `seen_hashes.json` — дедупликация (max 5000)
- `signals.jsonl` — все обработанные сигналы (JSONL лог)
- `news_spike.log` — основной лог
- `markets.json` — кэш рынков от Gamma API

---

## Структура

```
news_spike/
├── run_news_spike.py          ← ТОЧКА ВХОДА (минимальный orchestrator)
├── _signal_bot_original.py.ref ← оригинал из 9_bot (для справки)
├── README.md                   ← этот файл
├── README_ORIGINAL.md          ← README из 9_bot
├── requirements.txt
├── .env
├── configs/
│   ├── sources_iran.json      ← 27 TG + @araghchi + keywords
│   └── target_markets_iran.json ← наши 21 Iran/US рынков
├── core/
│   ├── config.py              ← загрузка .env
│   ├── iran_market_cache.py   ← MarketCache (Gamma API polling)
│   ├── iran_evaluator.py      ← Claude Haiku оценка
│   ├── alerter.py             ← Telegram send + форматирование
│   ├── signal_logger.py       ← JSONL лог
│   └── ...
└── monitors/
    ├── base.py                ← BaseMonitor (фреймворк)
    ├── telegram_monitor.py    ← TG scraper (t.me/s/)
    ├── twitter_monitor.py     ← Twitter API v2
    ├── truth_social_monitor.py ← Trumpstruth RSS
    └── odds_monitor.py        ← Price spike detector
```

---

## Что адаптировано относительно 9_bot

1. **odds_monitor.py** — импорт TARGET_MARKETS заменён на загрузку из `configs/target_markets_iran.json`
2. **Новый `run_news_spike.py`** — упрощённый entrypoint без auto_hedge / spike_rider / digest
3. **Target markets** — наши 21 открытые Iran/US позиции вместо 10 из Spike Rider

---

## Следующие шаги

1. **Запустить в dry-run** (текущая версия)
2. **Наблюдать алерты** в Telegram несколько часов
3. **Настроить фильтры** (MIN_CONFIDENCE, cooldown) по результатам
4. **Если нужна интеграция с торговлей** — подключить `executor.py` из родительского `25_multi_signal_copybot_v2` (например, автоматический sell при 🔴 эскалация-сигнале)
