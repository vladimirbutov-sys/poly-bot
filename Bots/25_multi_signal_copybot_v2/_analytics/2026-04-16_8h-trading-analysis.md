# Анализ копирования denizz: 02:00-10:00 UTC 16 апреля 2026

## 1. Сводка всех событий за 8 часов

### Завершенные сделки (закрытые за период)

| Время | Рынок | Действие | Цена | Сумма | P&L | Причина |
|-------|-------|----------|------|-------|-----|---------|
| 02:16 | US x Iran peace deal Apr30 | TIER UPGRADE buy | 0.360 | $28.00 | - | denizz докупил |
| 02:21 | Israel x Hezbollah ceasefire Apr30 | TIER UPGRADE buy | 0.721 | $43.25 | - | denizz докупил |
| 02:29 | Israeli forces Litani River | TIER UPGRADE buy | 0.760 | $46.80 | - | открытая позиция, не закрыта за период |
| 02:45 | Trump agree enrichment | TIER UPGRADE buy | 0.300 | $46.95 | - | denizz докупил |
| 02:54 | Israel x Hezbollah ceasefire Apr30 | TIER UPGRADE buy | 0.700 | $11.88 | - | denizz докупил |
| 03:18 | US x Iran peace Apr22 | TIER UPGRADE buy | 0.250 | $7.46 | - | denizz докупил |
| 03:18 | US x Iran peace Apr30 | TIER UPGRADE buy | 0.390 | $62.60 | - | denizz докупил |
| 03:18 | Israel x Hezbollah ceasefire Apr30 | TIER UPGRADE buy | 0.688 | $6.58 | - | denizz докупил |
| 03:20 | Trump agree enrichment | TIER UPGRADE buy | 0.319 | $12.94 | - | denizz докупил |
| 03:22 | Iran surrender uranium | TIER UPGRADE buy | 0.309 | $59.16 | - | denizz докупил |
| 05:44 | **Israel x Hezbollah ceasefire Apr15** | **SELL (price target 99c)** | **0.990** | **$119.08** | **+$5.17** | Цена достигла 0.99 |
| 06:09-06:18 | Israel suspension Lebanon Apr17 | NEW SIGNAL + 2 upgrades | 0.250-0.270 | $83.25 | - | Новый сигнал от denizz |
| 06:39 | **Strait of Hormuz traffic** | **NEW SIGNAL** | **0.260** | **$72.86** | - | Новый сигнал от denizz |
| 06:56-07:04 | **Strait of Hormuz traffic** | **3x SELL (loss follow)** | **0.240** | **$66.20** | **-$5.51** | denizz продал 87-89% |
| 07:52-08:01 | **Israel suspension Lebanon Apr17** | **2x SELL (loss follow)** | **0.220-0.250** | **$73.09** | **~-$10** | denizz продал 73-100% |
| 08:27 | **Trump unfreeze Iranian assets** | **SELL (loss follow)** | **0.460** | **$43.18** | **-$9.57** | denizz продал 100% |
| 08:57 | Trump agree enrichment | TIER UPGRADE buy | 0.267 | $5.62 | - | denizz докупил |
| 09:50 | Iran surrender uranium | TIER UPGRADE buy | 0.299 | $7.41 | - | denizz докупил |
| 10:06 | **Israel x Hezbollah ceasefire Apr30** | **SELL (loss follow)** | **0.665** | **$127.64** | **-$8.49** | denizz продал 92% |

### Заблокированные действия

| Время | Рынок | Причина блокировки |
|-------|-------|--------------------|
| 02:06 | Iran enrichment | Slippage 0.038 > max 0.030 |
| 02:15 | Trump military operations | MIN_BUY_EVENT_USD < $150 (100+ раз за период!) |
| 02:50 | Trump enrichment | Slippage 0.031 > max 0.030 |
| 03:12, 03:44 | US x Iran peace Apr22 | Part 2 SKIP: price rose >15% |
| 03:42 | Hezbollah ceasefire Apr15 | Slippage 0.015 > max 0.007 |
| 04:12 | Unknown market | Slippage 0.040 > 0.030 |
| 04:12 | Unknown market | Horizon blocked (258d >= 120d) |
| ~03:00-08:00 | Venezuela (Delcy Rodriguez) | MIN_BUY_EVENT < $150 (60+ раз) |
| ~03:00-08:00 | Strait of Hormuz shipping | MIN_BUY_EVENT < $150 |
| ~06:00-09:00 | Various Iran markets | MIN_BUY_EVENT < $150 |

## 2. Итоговый P&L за 8 часов

### Закрытые позиции (реализованный P&L)

| Рынок | Cost | Revenue | P&L |
|-------|------|---------|-----|
| Israel x Hezbollah ceasefire Apr15 | $113.91 | $119.08 | **+$5.17** |
| Strait of Hormuz traffic | $72.86 | $66.20 | **-$6.66** |
| Israel suspension Lebanon Apr17 | $83.25 | $87.86* | **~-$10.16** |
| Trump unfreeze Iranian assets | $52.75 | $43.18 | **-$9.57** |
| Israel x Hezbollah ceasefire Apr30 | $136.13** | $205.74** | **-$8.49** |

*Включая $14.77 от onchain_sync_down (возврат потерянных шаров)
**Включая onchain_sync_down ($78.10) + sell ($127.64); P&L по данным бота

**Реализованный P&L за 8 часов: примерно -$29.71**

### Открытые позиции (нереализованный P&L, докупленные за период)

Все tier upgrades за период добавили к существующим позициям, которые остаются открытыми. Вот текущее состояние ВСЕХ открытых позиций denizz:

| Рынок | Cost | Shares | Entry | Bid сейчас | Unrealized P&L |
|-------|------|--------|-------|------------|----------------|
| Iran leadership change Jun30 | $44.00 | 57.9 | 0.760 | 0.18 | **-$33.58** |
| US obtains uranium May31 | $200.14 | 248.6 | 0.805 | 0.20 | **-$150.42** |
| Iran enrichment Jun30 | $43.23 | 100.8 | 0.429 | 0.61 | **+$18.26** |
| Iran conflict ends Apr15 | $46.59 | 87.4 | 0.533 | 0.862 | **+$28.72** |
| Iran conflict ends Apr30 | $30.00 | 42.9 | 0.700 | 0.88 | **+$7.75** |
| Trump transit fees Hormuz | $25.97 | 28.9 | 0.900 | 0.07 | **-$23.95** |
| Iran conflict ends Apr7 | $88.94 | 88.4 | 0.566 | 0.866 | **-$12.39** |
| Iran surrender uranium Jun30 | $30.37 | 112.1 | 0.271 | 0.49 | **+$24.56** |
| Trump lift blockade Hormuz Apr30 | $45.93 | 82.9 | 0.554 | 0.60 | **+$3.81** |
| US x Iran peace May31 | $112.14 | 287.5 | 0.390 | 0.59 | **+$57.49** |
| Hamas ceasefire Phase II Jun30 | $17.91 | 68.9 | 0.260 | 0.13 | **-$8.95** |
| US x Iran ceasefire extended Apr21 | $111.09 | 158.5 | 0.701 | 0.73 | **+$4.61** |
| Iran surrender uranium Apr30 | $118.00 | 424.5 | 0.278 | 0.277 | **-$0.42** |
| US x Iran peace Apr22 | $158.70 | 808.9 | 0.196 | 0.21 | **+$11.17** |
| Trump enrichment Apr | $128.57 | 443.5 | 0.290 | 0.251 | **-$17.26** |
| US x Iran peace Apr30 | $90.60 | 238.3 | 0.380 | 0.39 | **+$2.34** |

**Нереализованный P&L всего портфеля: -$88.26**

## 3. Анализ каждого решения

### Хорошие решения

**1. Продажа Israel x Hezbollah ceasefire Apr15 по price target 0.99 (+$5.17)**
- Отличное решение. Бот дождался цены 0.99 и зафиксировал прибыль. Рынок потом разрешился в пользу Yes, так что бот мог бы заработать ещё немного, но фиксация прибыли при 0.99 -- это правильный подход.

**2. Tier upgrades на Iran peace/enrichment markets**
- Многочисленные мелкие докупки ($5-63) следовали за denizz. Большинство этих позиций сейчас в плюсе (peace deal May31 +$57, Iran enrichment Jun30 +$18, conflict ends Apr15/Apr30 в плюсе).

### Проблемные решения

**3. Strait of Hormuz traffic -- купил и сразу продал в убыток (-$6.66)**
- Вход в 06:39 по 0.260, denizz начал продавать почти сразу (87% к 06:56 -- через 17 минут!)
- Бот не успел среагировать на то, что denizz передумал
- Проблема: denizz мог покупать для быстрого трейда (скальп), а не для долгосрочной позиции

**4. Israel suspension Lebanon Apr17 -- крупный убыток (~-$10)**
- Вход в 06:09-06:18 по 0.25-0.27, через час denizz продал 73%
- Бот продал по 0.22 (ниже входа)
- avg_entry в positions.json = 2.937 -- **БАГ в коде**, невозможное значение для бинарного рынка

**5. Trump unfreeze Iranian assets (-$9.57)**
- Правильное решение следовать за denizz (он продал 100%)
- Но цена упала с 0.562 до 0.460 -- потеря 18%

**6. Israel x Hezbollah ceasefire Apr30 (-$8.49)**
- denizz продал 92%, бот последовал
- Продажа по 0.665 при входе ~0.709 -- убыток 6%

## 4. Конкретные предложения

### Предложение 1: Защита от "скальпов" denizz (ВЫСОКИЙ приоритет)
**Что:** Добавить задержку перед входом в новый сигнал (например, 10-15 минут). Если denizz продаёт >50% позиции в первые 30 минут -- не входить.
**Пример:** Strait of Hormuz -- denizz купил и через 17 минут начал продавать. Бот вошёл сразу и потерял $6.66.
**Риск:** Можем пропустить хорошие быстрые сигналы, но на данных за 8 часов быстрые сигналы denizz были убыточными.

### Предложение 2: Исправить баг avg_entry (КРИТИЧЕСКИЙ)
**Что:** В positions.json позиция "Israel suspension Lebanon Apr17" имеет avg_entry=2.937, что невозможно для бинарного рынка (макс 1.0). Это приводит к неправильному расчёту P&L (-$225 вместо реальных ~-$10).
**Где:** Скорее всего баг в коде расчёта avg_entry при tier upgrades с разными ценами. Нужно проверить формулу в entry_manager.py.
**Риск:** Нулевой. Это чисто исправление бага.

### Предложение 3: Снизить MIN_BUY_EVENT_USD с $150 до $75-100 (СРЕДНИЙ приоритет)
**Что:** За 8 часов было 200+ пропущенных сигналов с фильтром MIN_BUY_EVENT. Некоторые из них (Venezuela/Delcy Rodriguez $140, Iran surrender $136, Iran enrichment $95) были близки к порогу.
**Пример:** Iran agrees to surrender enriched uranium ($136) был пропущен при $150 пороге, но denizz-у верилось в эту ставку достаточно.
**Риск:** Больше мелких ставок, выше комиссии. Но порог $150 отсекает потенциально хорошие сигналы. Рекомендую $100.

### Предложение 4: Ускорить follow-sell при убытках (НИЗКИЙ приоритет)
**Что:** Сейчас бот ждёт пока denizz продаст 60% перед продажей в убытке. На Lebanon offensive бот держал позицию при 53-56% sell denizz почти 2 часа, а потом продал по ещё худшей цене при 73%.
**Пример:** Если бы продали при 55% (в 06:55), цена была ~0.25, а при 73% (07:52) уже 0.22.
**Риск:** Ложные срабатывания -- denizz иногда продаёт 50% и потом докупает обратно. Рекомендую снизить порог до 50% только для позиций в убытке более 15%.

## 5. Вывод

За 8 часов бот совершил:
- **12 покупок** (2 новых сигнала + 10 tier upgrades) на общую сумму ~$420
- **6 продаж** на сумму ~$429
- **Реализованный P&L: -$29.71**
- **Нереализованный P&L портфеля: -$88.26**

Главные потери: Lebanon offensive (~-$10), Trump unfreeze (-$9.57), Hezbollah Apr30 (-$8.49), Strait of Hormuz (-$6.66). Единственный плюс -- Hezbollah Apr15 (+$5.17).

Denizz за этот период был в основном в режиме "распродажи" -- продавал крупные позиции (Israel military action sold 74%, Strait of Hormuz 91%, Lebanon 100%, Hezbollah Apr30 92%). Бот правильно следовал за продажами, но входы в новые позиции (Strait of Hormuz, Lebanon) оказались убыточными из-за быстрого разворота denizz.

**Критический баг**: avg_entry=2.937 в позиции Lebanon -- нужно исправить немедленно, так как это искажает P&L отчётность.
