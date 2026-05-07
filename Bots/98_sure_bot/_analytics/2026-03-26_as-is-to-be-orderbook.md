# AS-IS / TO-BE: Order Execution Architecture

**Дата:** 2026-03-26
**Цель:** Повысить fill rate с 20% до 50-60% через проверку order book

---

## AS-IS (текущая архитектура)

### Шаг 1: Сканирование (scanner.py)
```
Gamma API -> список рынков с ценами (кэшированные, отстают на 1-5 мин)
```

### Шаг 2: Фильтрация (filters.py)
```
1. Цена >= PRICE_THRESHOLD (96c politics, 97.5c остальные)
2. Цена <= MAX_PRICE (99.5c)
3. Liquidity >= $500
4. Volume >= $500
5. end_date <= 2-3 дня (regular/neg_risk)
6. end_date не пустой
7. Не coin-flip (first blood, odd/even, rampage...)
8. Не threshold market (close above/below, dip to...)
9. Не slow keyword (transit, strait, ships...)
10. Не weather (если test mode $1)
11. Нет открытой позиции на этот condition_id
12. neg_risk frozen < $175 лимит
13. Не отменённый матч (started 6+ hours ago)
```

### Шаг 3: Расчёт цены (executor.py)
```
limit_price = gamma_price + slippage

SLIPPAGE_RULES:
  96.0-97.5c  -> +0.5c  (limit = gamma + 0.005)
  97.5-98.5c  -> +0.4c  (limit = gamma + 0.004)
  98.5-99.0c  -> +0.3c  (limit = gamma + 0.003)
  99.0-99.5c  -> +0.3c  (limit = gamma + 0.003)  <-- эксперимент

Если limit > 99.5c -> skip
```

### Шаг 4: Проверка цены (executor.py)
```
CLOB midpoint = client.get_midpoint(token_id)
Если |gamma_price - midpoint| > 3c -> STALE PRICE SKIP
```

### Шаг 5: Размещение ордера
```
GTC limit order по limit_price
Ждём 300 сек (5 мин), поллинг каждые 10 сек
Если timeout -> cancel, записать NOT FILLED
```

### Проблема
```
Gamma price = 99.2c (кэшированная)
limit = 99.2 + 0.3 = 99.5c
Но в стакане best_ask = 99.7c (реальная)
-> Ордер по 99.5c не исполняется, timeout через 5 мин
-> 79.3% ордеров уходят в timeout (1,461 из 1,843)
```

### Факты из анализа 229 fills:
- 96.5% fills исполнились ровно по limit price
- 92.6% fills заплатили БОЛЬШЕ чем Gamma показывала (+0.34c avg)
- 0.9% fills получили цену лучше limit (2 из 229)
- Price improvement = 0 (мы НЕ экономим на slippage)

---

## TO-BE (предлагаемая архитектура)

### Шаг 1: Сканирование -- БЕЗ ИЗМЕНЕНИЙ
```
Gamma API -> список рынков с ценами
(Gamma нужен для поиска рынков, не для цены)
```

### Шаг 2: Фильтрация -- БЕЗ ИЗМЕНЕНИЙ
```
Все 13 фильтров остаются как есть.
Gamma price по-прежнему используется для первичного отбора:
  - Цена >= 96c/97.5c (проходит в кандидаты)
  - Цена <= 99.5c (ROI threshold)
  - Все остальные фильтры
```

### Шаг 3: Проверка стакана -- НОВЫЙ ШАГ
```
CLOB order book = GET /book?token_id=X

Проверяем:
  a) best_ask существует? (если нет asks -> skip, нет продавцов)
  b) best_ask <= MAX_PRICE (99.5c)? (если нет -> skip, ROI слишком мал)
  c) best_ask >= PRICE_THRESHOLD? (если ask < 96c -> цена ушла, skip)
  d) ask_depth >= MIN_ASK_DEPTH ($5)? (если стакан пустой -> skip)

Если все проверки пройдены -> используем best_ask как РЕАЛЬНУЮ цену
```

### Шаг 4: Расчёт цены -- ИЗМЕНЁН
```
БЫЛО:  limit_price = gamma_price + slippage
СТАЛО: limit_price = best_ask + buffer

Правила (остаются bucket-based, но от best_ask):
  best_ask 96.0-97.5c  -> buffer +0.3c  (max limit = best_ask + 0.003)
  best_ask 97.5-98.5c  -> buffer +0.2c
  best_ask 98.5-99.0c  -> buffer +0.1c
  best_ask 99.0-99.5c  -> buffer +0.1c

Если limit > MAX_PRICE (99.5c) -> limit = 99.5c
Если limit > MAX_PRICE -> skip

ВАЖНО: buffer МЕНЬШЕ чем старый slippage, потому что
мы уже знаем точную цену. Buffer нужен только на случай
если кто-то купит ask за 1-2 сек между проверкой и ордером.
```

### Шаг 5: Проверка stale price -- УПРОЩЕНА
```
БЫЛО:  get_midpoint() + проверка divergence с Gamma
СТАЛО: не нужна отдельно -- мы уже используем CLOB данные из Шага 3

Защита от stale Gamma по-прежнему работает:
  - Gamma показывает 98c, но best_ask = 85c
  - Шаг 3 check (c): 85c < 96c threshold -> skip
  - Та же защита, но точнее
```

### Шаг 6: Размещение ордера -- ОПТИМИЗИРОВАН
```
GTC limit order по limit_price (= best_ask + buffer)

БЫЛО:  timeout 300 сек, поллинг каждые 10 сек
СТАЛО: timeout 60 сек, поллинг каждые 5 сек

Почему 60 сек:
  - Мы ставим по реальному ask -> fill должен быть за 1-5 сек
  - Если за 60 сек не исполнился -> ask ушёл, нет смысла ждать
  - Быстрый cancel -> капитал свободен -> следующая ставка
```

---

## Сравнительная таблица

| Аспект | AS-IS | TO-BE |
|---|---|---|
| **Источник цены для ордера** | Gamma API (кэш) | CLOB best_ask (live) |
| **Проверка стакана** | Нет | Да (GET /book) |
| **Проверка глубины** | Нет | Да (ask_depth >= $5) |
| **Slippage / Buffer** | 0.2-0.5c от Gamma | 0.1-0.3c от best_ask |
| **Stale price check** | get_midpoint + divergence | Встроен в проверку стакана |
| **Timeout** | 300 сек | 60 сек |
| **Поллинг** | каждые 10 сек | каждые 5 сек |
| **Ожидаемый fill rate** | 20% | 50-60% |
| **Бесполезные ордера** | 79% timeout | ~40% skip заранее |
| **Дополнительные API-вызовы** | 0 | +1 GET /book на ставку |

---

## Что НЕ меняется

1. Все 13 фильтров в filters.py -- без изменений
2. PRICE_THRESHOLD (96c / 97.5c) -- без изменений
3. MAX_PRICE (99.5c) -- без изменений
4. BET_SIZE по типам ($10/$5/$5/$1/$1) -- без изменений
5. GTC order type -- без изменений
6. SCAN_INTERVAL (5 мин) -- без изменений
7. MIN_SHARES (5) -- без изменений
8. MAX_NEG_RISK_FROZEN ($175) -- без изменений
9. MAX_END_DATE (2-3 дня) -- без изменений
10. MAX_PRICE_DIVERGENCE (3c) -- логика встроена, порог сохранён

---

## Ожидаемый эффект

### Fill rate
| Метрика | AS-IS | TO-BE |
|---|---|---|
| Попыток/день | 183 | ~100 (отсеиваем пустые стаканы) |
| Fill rate | 20% | 50-60% |
| Fills/день | 37 | **50-60** |
| Позиций в работе | 48-62 | **65-80** |

### P&L
| Метрика | AS-IS | TO-BE |
|---|---|---|
| Profit/fill | $0.05 | $0.04-0.05 (buffer меньше) |
| Fills/день | 37 | 55 (средний сценарий) |
| P&L/день | $1.85 | **$2.50-2.75** |
| P&L/месяц | $55-70 | **$75-83** |
| ROI | 0.59% | ~0.50% (больше капитала в работе) |

### Bankroll
| Метрика | AS-IS | TO-BE |
|---|---|---|
| Frozen capital | $500 | $600-700 |
| Нужен доп. капитал | -- | +$100-200 |

---

## Риски

1. **GET /book добавляет 1-2 сек на каждый рынок.** При 100 проверках/день = ~2 мин. Несущественно.
2. **Между проверкой book и ордером кто-то может купить ask.** Для этого buffer 0.1-0.3c.
3. **Rate limit на GET /book.** CLOB API лимит ~100 req/sec -- при 20 проверках за 5-мин скан (~0.07 req/sec) проблем нет.
4. **Если ask нет (стакан пустой) -- бот пропустит рынок.** Но старый бот тоже бы не исполнился. Разница: мы не тратим 5 мин на timeout.

---

## Файлы для изменения

| Файл | Изменения |
|---|---|
| executor.py | Добавить `get_orderbook()`, изменить `get_limit_price()` на `get_limit_from_ask()`, сократить timeout |
| main.py | Вставить проверку стакана между фильтрами и размещением ордера |
| config.py | Добавить `MIN_ASK_DEPTH`, `ORDER_TTL_SECONDS: 60`, новые `BUFFER_RULES` |
| filters.py | Без изменений |
| scanner.py | Без изменений |
