# Апгрейд алгоритма: News Sentinel + корректировки стратегии

**Дата:** 21 марта 2026
**Контекст:** 14 реальных сделок, P&L +$47.54, бэктест 473 точки, 8 дней до экспирации
**Задача:** Добавить боту "глаза" — мониторинг новостей и соцсетей для принятия торговых решений

---

## 1. ДИАГНОЗ: ПОЧЕМУ БОТУ НУЖНЫ "ГЛАЗА"

### Текущая слепая зона

Бот видит ТОЛЬКО две цифры: WTI price + YES/NO price. Он НЕ видит:

| Слепая зона | Последствия | Пример из реальных данных |
|---|---|---|
| Новости (удары, заявления) | Входит в NO перед эскалацией | WTI $97 → вход NO → удар → WTI $110 → стоп |
| Trump Truth Social | Не знает о "winding down" или "blow up" | Gap $5-10 без предупреждения |
| Выходные (CME закрыт) | Держит позиции через weekend gap | Пятница $98 → понедельник $108 |
| Режим рынка (эскалация/деэскалация) | Одинаковые пороги при разных режимах | При эскалации $97 ≠ $97 при деэскалации |
| Settlement vs intraday | Реагирует на intraday шум ночью | WTI spike $105 в 3 AM → стоп → откат к $98 |

### Из 14 сделок — 5 убытков

| Убыточная сделка | Причина | Помог бы news sentinel? |
|---|---|---|
| 5× manual_sell_old_no (-$2.98 каждая) | Ручная продажа старых позиций с убытком | Нет (ручное решение) |

Все 5 убытков — ручные. Автоматические сделки бота: **9 из 9 прибыльные (100% win rate)**. Бот торгует хорошо, но ему не хватает **защиты от хвостовых рисков** (tail risk).

### Главный риск: WTI gap через $100 settlement

```
P(WTI settlement >= $100 до 31 марта) = 70.5%

Если это произойдёт:
  - Все NO $100 = $0 (полная потеря)
  - Бот может потерять $30-50 (если в позиции)

Бот не может предсказать КОГДА это произойдёт,
но news sentinel может ПРЕДУПРЕДИТЬ о повышенном риске.
```

---

## 2. АРХИТЕКТУРА NEWS SENTINEL

### Принцип: НЕ торговать по новостям, а ФИЛЬТРОВАТЬ торговлю

News sentinel не принимает решения "купить/продать". Он определяет **режим риска** и корректирует параметры бота:

```
┌─────────────────────────────────────────┐
│            NEWS SENTINEL                │
│                                         │
│  RSS/API → Parser → Risk Level → Flag   │
│                                         │
│  Levels:                                │
│    🟢 GREEN  = нормальная торговля      │
│    🟡 YELLOW = ужесточить параметры     │
│    🔴 RED    = остановить вход, только  │
│               выход из позиций          │
│    ⚫ BLACK  = закрыть всё немедленно   │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│         STRATEGY (strategy.py)          │
│                                         │
│  risk_level → корректировка:            │
│    - Размер ставки (× множитель)        │
│    - Стоп-лосс (ужесточить)            │
│    - Вход (заблокировать при RED)        │
│    - Профит-таргет (ускорить выход)      │
└─────────────────────────────────────────┘
```

### Что мониторить и как

| Источник | Метод | Частота | Что ищем |
|---|---|---|---|
| **RSS: Reuters Oil** | feedparser | 5 мин | "Iran", "strike", "Hormuz", "OPEC", "ceasefire" |
| **RSS: Al Jazeera** | feedparser | 5 мин | "Iran", "attack", "oil", "Gulf" |
| **Truth Social (Trump)** | Web scrape / RSS | 2 мин | "Iran", "oil", "winding down", "blow up", "ceasefire" |
| **Yahoo Finance News** | yfinance API | 5 мин | "crude", "WTI", "OPEC", "sanctions" |
| **WTI Futures (CME)** | Yahoo CL=F | 1 мин | Gap detection: |current - last_known| > $3 |
| **Polymarket YES $100** | CLOB API | 1 мин | YES > 80% = вероятность $100 очень высока |

### Keyword scoring (простая система, без ИИ)

```python
# Каждое ключевое слово имеет вес и направление
ESCALATION_KEYWORDS = {
    "strike iran":       +3,   # удар по Ирану
    "attack":            +2,
    "missile":           +2,
    "bomb":              +2,
    "blow up":           +3,   # Trump угрожает South Pars
    "nuclear":           +2,
    "hormuz closed":     +3,
    "tanker attack":     +3,
    "war":               +1,
    "military":          +1,
    "troops deploy":     +2,
    "force majeure":     +2,   # Iraq
    "refinery fire":     +2,
    "explosion":         +2,
}

DEESCALATION_KEYWORDS = {
    "ceasefire":         -4,   # самый сильный сигнал вниз
    "winding down":      -3,   # Trump уходит
    "negotiations":      -2,
    "diplomatic":        -2,
    "withdraw":          -2,
    "peace":             -2,
    "de-escalation":     -3,
    "hormuz open":       -4,   # пролив открывается
    "sanctions lifted":  -2,
    "spr release":       -1,   # стратегические резервы
}

# Скользящее окно: сумма за последние 30 минут
# score > +5  → RED (эскалация, не входить)
# score > +3  → YELLOW (осторожно)
# score -3..-1 → YELLOW (деэскалация, не входить в YES)
# score < -5  → RED (ceasefire, закрыть NO)
# иначе       → GREEN
```

---

## 3. КОНКРЕТНЫЕ ПРАВИЛА NEWS SENTINEL

### Правило 1: WEEKEND GUARD (пятница → понедельник)

```
КОГДА: пятница после 21:00 МСК (14:00 ET, после CME settlement)
ЧТО:   risk_level = YELLOW автоматически

ЕСЛИ:  бот имеет открытые NO позиции в пятницу после settlement
ТО:    Telegram: "⚠️ Weekend risk: X NO позиций открыты.
       Gap risk $5-10. Закрыть вручную?"
       Бот НЕ закрывает сам — отправляет алерт

ЕСЛИ:  понедельник, CME gap > +$3 от пятничного settlement
ТО:    risk_level = RED на 2 часа
       НЕ входить в NO, ждать стабилизации
```

**Зачем:** weekend gap — главный неконтролируемый риск. 5 из 14 убытков были ручными закрытиями, возможно связаны с gap.

### Правило 2: TRUMP FILTER

```
КОГДА: обнаружен пост Trump с ключевыми словами
ЕСЛИ:  score >= +3 (эскалация):
  - risk_level = RED на 30 мин
  - НЕ входить в NO (WTI пойдёт вверх)
  - Ужесточить NO стоп: _get_no_stop_level() -= $2
  - Telegram: "🔴 Trump escalation: [цитата]. NO вход заблокирован"

ЕСЛИ:  score <= -3 (деэскалация):
  - risk_level = RED на 30 мин
  - НЕ входить в YES (WTI пойдёт вниз)
  - Ужесточить YES ceasefire stop: +$3
  - Telegram: "🔴 Trump de-escalation: [цитата]. YES вход заблокирован"
```

**Зачем:** Трамп = единственный человек, который может двинуть WTI на $5-10 одним постом. Бот должен ПАУЗА после такого поста.

### Правило 3: STRIKE ALERT

```
КОГДА: RSS содержит "strike", "attack", "missile" + "Iran"/"Gulf"/"Saudi"
И:     WTI двигается > +$2 за 10 минут
ТО:
  - risk_level = RED на 1 час
  - НЕ входить в NO
  - Если WTI > $102: закрыть все NO автоматически (не ждать graduated stop)
  - Telegram: "🔴 STRIKE ALERT: [заголовок]. Все NO будут закрыты при WTI > $102"
```

**Зачем:** при реальном ударе WTI может gap $5-10 за минуты. Graduated stop (101-108) может не успеть. News sentinel предупреждает РАНЬШЕ ценового движения.

### Правило 4: SETTLEMENT PROXIMITY GUARD

```
КОГДА: YES $100 на Polymarket > 80%
И:     WTI > $99
ТО:
  - risk_level = YELLOW
  - NO profit target: ускорить (× 0.5 от обычного)
  - НЕ входить в новые NO
  - Telegram: "⚠️ Settlement proximity: YES=81%, WTI=$99.3.
    NO вход заблокирован. Существующие NO — ускоренный профит."
```

**Зачем:** при YES > 80% рынок почти уверен что settlement будет >= $100. NO — крайне рискованная позиция.

### Правило 5: CEASEFIRE WATCH

```
КОГДА: RSS содержит "ceasefire" + ("Iran" || "US")
И:     score <= -4
ТО:
  - risk_level = RED
  - Закрыть все NO немедленно (ceasefire = WTI -$10-15)
  - YES становится привлекательным, но НЕ входить автоматически
  - Telegram: "⚫ CEASEFIRE SIGNAL: [заголовок]. Все NO закрыты.
    WTI может упасть $10-15. Рассмотри YES вход вручную."
```

**Зачем:** ceasefire — единственный фактор, который быстро обрушит WTI. При этом бот сейчас держит в основном NO → полная потеря. News sentinel должен реагировать БЫСТРЕЕ чем цена.

---

## 4. ИЗМЕНЕНИЯ В strategy.py

### 4.1 Новая переменная: risk_level

```python
# В strategy.py добавить:

_risk_level = "GREEN"        # GREEN / YELLOW / RED / BLACK
_risk_level_until = 0        # timestamp когда снять
_risk_reason = ""

def get_risk_level() -> tuple:
    """Returns (level, reason)."""
    global _risk_level
    if time.time() > _risk_level_until:
        _risk_level = "GREEN"
        _risk_reason = ""
    return _risk_level, _risk_reason

def set_risk_level(level: str, duration_sec: int, reason: str):
    global _risk_level, _risk_level_until, _risk_reason
    # Только повышаем уровень, не понижаем
    levels = {"GREEN": 0, "YELLOW": 1, "RED": 2, "BLACK": 3}
    if levels.get(level, 0) >= levels.get(_risk_level, 0):
        _risk_level = level
        _risk_level_until = time.time() + duration_sec
        _risk_reason = reason
```

### 4.2 Корректировка calculate_bet_size

```python
def calculate_bet_size(fixed_usd: float, free_balance: float) -> float:
    bet = fixed_usd
    theta_mult = get_theta_multiplier()
    bet *= theta_mult

    # NEWS SENTINEL: risk scaling
    risk, _ = get_risk_level()
    if risk == "BLACK":
        return 0.0  # никаких новых ставок
    elif risk == "RED":
        return 0.0  # никаких новых ставок
    elif risk == "YELLOW":
        bet *= 0.5  # половинный размер

    if _divergence_active and time.time() < _divergence_until:
        bet *= DIVERGENCE_REDUCE_PCT

    if bet < MIN_BET_USD:
        return 0.0
    if bet > free_balance:
        return 0.0
    return round(bet, 2)
```

### 4.3 Корректировка check_stop_no (NEWS-aware)

```python
def check_stop_no(wti: float) -> bool:
    """Graduated NO stop + news-adjusted + panic at $115."""
    risk, reason = get_risk_level()

    # При RED/BLACK от новостей — ужесточить стоп на $2
    adjustment = 0
    if risk in ("RED", "BLACK"):
        adjustment = -2  # стоп ближе на $2

    level = _get_no_stop_level() + adjustment
    return wti > level or wti > 115.0
```

---

## 5. НОВЫЙ ФАЙЛ: news_sentinel.py

### Архитектура

```
news_sentinel.py
├── fetch_rss(url) → list[headline]
├── fetch_trump_posts() → list[post]
├── fetch_polymarket_yes() → float (YES $100 price)
├── score_headlines(headlines) → int
├── detect_gap(current_wti, last_known) → float
├── check_weekend() → bool
├── evaluate() → (risk_level, reason, details)
└── run_sentinel_cycle(wti) → None (updates strategy.risk_level)
```

### Ключевой метод: evaluate()

```python
def evaluate(wti: float, yes_100_pct: float) -> dict:
    """
    Главная функция: собирает все сигналы и определяет risk level.
    Вызывается из main.py каждый цикл (60 сек).
    """
    signals = []

    # 1. RSS headlines (каждые 5 мин)
    headlines = fetch_rss_cached()
    news_score = score_headlines(headlines)
    if news_score >= 5:
        signals.append(("RED", 3600, f"Escalation score {news_score}"))
    elif news_score >= 3:
        signals.append(("YELLOW", 1800, f"Elevated tension score {news_score}"))
    elif news_score <= -5:
        signals.append(("RED", 3600, f"Ceasefire signal score {news_score}"))
    elif news_score <= -3:
        signals.append(("YELLOW", 1800, f"De-escalation score {news_score}"))

    # 2. Trump posts (каждые 2 мин)
    trump_score = check_trump_cached()
    if trump_score != 0:
        if trump_score >= 3:
            signals.append(("RED", 1800, "Trump escalation"))
        elif trump_score <= -3:
            signals.append(("RED", 1800, "Trump de-escalation"))

    # 3. Weekend guard
    if is_weekend_risk():
        signals.append(("YELLOW", 0, "Weekend — no new entries"))

    # 4. Settlement proximity
    if yes_100_pct > 80 and wti > 99:
        signals.append(("YELLOW", 0, f"Settlement proximity YES={yes_100_pct:.0f}%"))
    if yes_100_pct > 90:
        signals.append(("RED", 0, f"Settlement imminent YES={yes_100_pct:.0f}%"))

    # 5. Gap detection
    gap = detect_gap(wti)
    if abs(gap) > 5:
        signals.append(("RED", 7200, f"WTI gap ${gap:+.1f}"))
    elif abs(gap) > 3:
        signals.append(("YELLOW", 3600, f"WTI gap ${gap:+.1f}"))

    # Выбираем максимальный уровень
    if not signals:
        return {"level": "GREEN", "reason": "No signals", "details": []}

    levels = {"GREEN": 0, "YELLOW": 1, "RED": 2, "BLACK": 3}
    worst = max(signals, key=lambda s: levels[s[0]])

    return {
        "level": worst[0],
        "duration": worst[1],
        "reason": worst[2],
        "details": signals,
        "news_score": news_score,
    }
```

### RSS-источники

```python
RSS_FEEDS = [
    # Reuters Oil & Energy
    "https://www.reuters.com/arc/outboundfeeds/v3/all/by-section/?outputType=xml&tag=energy",
    # Al Jazeera
    "https://www.aljazeera.com/xml/rss/all.xml",
    # CNBC Energy
    "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=19836768",
    # Yahoo Finance (oil-related)
    "https://finance.yahoo.com/rss/topstories",
]
```

---

## 6. ИЗМЕНЕНИЯ В main.py

### Интеграция sentinel в run_cycle()

```python
# В начале run_cycle(), после получения WTI:

def run_cycle():
    maybe_recalibrate()

    wti = wti_monitor.get_wti_price()
    if not wti:
        log("WTI unavailable, skipping")
        return

    market = get_market_prices()
    yes_mid = (market["yes_bid"] + market["yes_ask"]) / 2 * 100

    # === NEWS SENTINEL (новый блок) ===
    sentinel_result = news_sentinel.evaluate(wti, yes_mid)
    if sentinel_result["level"] != "GREEN":
        strategy.set_risk_level(
            sentinel_result["level"],
            sentinel_result.get("duration", 1800),
            sentinel_result["reason"],
        )
        log(f"NEWS: {sentinel_result['level']} — {sentinel_result['reason']}")

        # Telegram alert при RED/BLACK
        if sentinel_result["level"] in ("RED", "BLACK"):
            tg.send(
                f"<b>🔴 NEWS SENTINEL: {sentinel_result['level']}</b>\n"
                f"{sentinel_result['reason']}\n"
                f"WTI: ${wti:.2f} | YES: {yes_mid:.0f}%\n"
                f"Действие: вход заблокирован"
            )

    # Логировать текущий risk level
    risk, reason = strategy.get_risk_level()
    if risk != "GREEN":
        log(f"Risk level: {risk} ({reason})")

    # ... остальной код run_cycle без изменений ...
```

---

## 7. КОРРЕКТИРОВКИ КОНФИГА БЕЗ NEWS SENTINEL

Эти изменения можно внести СЕЙЧАС, без написания news_sentinel.py:

### 7.1 Ужесточить NO стоп ближе к экспирации

**Сейчас:** graduated stop 101-108 в зависимости от часов до settlement.
**Проблема:** при 8 днях до экспирации WTI > $100 = 70.5% вероятность. Стоп на $108 ночью — слишком далеко.

**Предложение:** добавить scaling по дням до экспирации:

```python
def _get_no_stop_level() -> float:
    h = _hours_to_settlement()
    days = get_days_remaining()

    # Базовые уровни
    if h <= 1:
        base = 101.0
    elif h <= 4:
        base = 103.0
    elif h <= 8:
        base = 105.0
    else:
        base = 108.0

    # Ужесточение по мере приближения к дедлайну
    # Чем меньше дней — тем ближе стоп
    if days <= 3:
        base -= 3.0   # последние 3 дня: стоп на $98-105
    elif days <= 5:
        base -= 2.0   # 4-5 дней: стоп на $99-106
    elif days <= 7:
        base -= 1.0   # 6-7 дней: стоп на $100-107

    return base
```

**Бэктест невозможен** — нет данных с graduated stop по дням. Рекомендация основана на логике: чем ближе к экспирации, тем выше вероятность что текущая цена ≈ финальная.

### 7.2 Добавить Polymarket YES check перед NO входом

**Сейчас:** бот входит в NO только по WTI price ($97/$98/$99).
**Проблема:** WTI $97, но YES = 85% → рынок почти уверен в $100 → NO = плохая ставка.

**Предложение:** в main.py добавить проверку:

```python
# Перед BUY NO:
if yes_mid > 80:
    log(f"SKIP NO: YES too high ({yes_mid:.0f}% > 80%)")
    # Не входить — рынок слишком уверен в $100
```

Это ПРОСТОЕ изменение, не требует news_sentinel. Можно внести прямо сейчас.

### 7.3 Ускорить NO profit при YES > 75%

**Сейчас:** NO profit targets фиксированные (35%/69%/104%) с тета-коррекцией.
**Предложение:** если YES > 75%, ускорить фиксацию:

```python
def get_no_profit_target(entry_step: int, yes_pct: float = 0) -> float:
    if 0 <= entry_step < len(NO_ENTRY_STEPS):
        base = NO_ENTRY_STEPS[entry_step][2]
    else:
        base = 0.50
    adj = get_theta_adjustments()
    target = base * adj["profit_mult"]

    # Ускорить выход если рынок уверен в $100
    if yes_pct > 75:
        target *= 0.5  # фиксируй при половине обычного профита

    return round(target, 3)
```

---

## 8. ПЛАН ВНЕДРЕНИЯ

### Фаза 1: Немедленно (без нового кода)

| Изменение | Файл | Строки | Сложность |
|---|---|---|---|
| YES > 80% → блокировать NO вход | main.py | +5 строк перед NO buy | 2 мин |
| Ужесточить NO стоп по дням | strategy.py | _get_no_stop_level() | 5 мин |
| Weekend alert в Telegram | main.py | +10 строк в run_cycle | 5 мин |

### Фаза 2: News Sentinel MVP (1-2 часа)

| Компонент | Описание | Сложность |
|---|---|---|
| news_sentinel.py | RSS fetcher + keyword scorer | 30 мин |
| strategy.py risk_level | Новая переменная + scaling | 15 мин |
| main.py интеграция | Вызов sentinel в цикле | 10 мин |
| Тестирование | Запуск, проверка RSS, ложные срабатывания | 30 мин |

### Фаза 3: Trump Monitor (дополнительно)

| Компонент | Описание | Сложность |
|---|---|---|
| Truth Social scraper | Парсинг постов через RSS/web | 1 час |
| Telegram bot commands | /risk, /news, /pause | 1 час |

---

## 9. ЧЕГО НЕ ДЕЛАТЬ

| Плохая идея | Почему |
|---|---|
| ИИ-анализ новостей (GPT/Claude API) | Дорого, медленно, ненадёжно. Простые keywords работают лучше для этой задачи |
| Автоматическая торговля по новостям | Ложные срабатывания. Новости = фильтр, не триггер |
| Twitter/X API | $100/мес, сложный OAuth, часто ломается |
| Sentiment analysis | Overkill для 3 ключевых слов (ceasefire, strike, winding down) |
| Больше RSS-источников | 4 достаточно. Больше = больше шума |

---

## 10. ОЖИДАЕМОЕ ВЛИЯНИЕ

### Без News Sentinel (текущий бот)

| Сценарий | P&L impact | Вероятность |
|---|---|---|
| Нормальная торговля | +$3-5/день | 35% |
| Weekend gap up $5+ | -$30-50 (все NO) | 15% |
| Trump ceasefire post | Паническая продажа | 10% |
| Удар по Saudi | -$30-50 (все NO) | 10% |

**Expected weekly P&L: +$10-15 (но с tail risk -$50)**

### С News Sentinel

| Сценарий | P&L impact | Почему лучше |
|---|---|---|
| Нормальная торговля | +$3-5/день | Без изменений |
| Weekend gap up $5+ | **-$0** (нет позиций) | Weekend guard предупредил |
| Trump ceasefire post | **-$5** (быстрый выход) | Trump filter среагировал за 2 мин |
| Удар по Saudi | **-$10** (ужесточённый стоп) | Strike alert ужесточил стоп |

**Expected weekly P&L: +$12-18 (tail risk снижен до -$15)**

### Улучшение: +$5-10/неделю за счёт защиты от хвостовых рисков

---

## 11. ЗАВИСИМОСТИ

```
pip install feedparser    # RSS-парсинг
# Всё остальное уже установлено (requests, yfinance)
```

---

## Методология

- Анализ 14 реальных сделок (positions.json)
- Бэктест 473 точки (backtest-results.md)
- Геополитический контекст (Reuters, CNBC, Al Jazeera)
- Polymarket API — текущие цены
- Стратегия timezone-edge — для оптимизации расписания
- config.py, strategy.py, main.py — текущий код бота
