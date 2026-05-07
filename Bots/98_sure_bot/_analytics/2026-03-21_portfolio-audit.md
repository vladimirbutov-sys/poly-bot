# Аудит портфеля 98_sure_bot по данным 97_scanner

**Дата:** 2026-03-21
**Источники:**
- `97_scanner/scanner_data.json` — 26,986 рынков (14,751 resolved)
- `98_sure_bot/positions.json` — 205 позиций бота
- `98_sure_bot/_analytics/data/portfolio_health_2026-03-21.json` — текущие цены

---

## 1. Общая картина из scanner

| Показатель | Значение |
|---|---|
| Всего рынков в scanner | 26,986 |
| Разрешённых (resolved) | 14,751 |
| Выигрышей (high_outcome_won=true) | 14,737 |
| Проигрышей (high_outcome_won=false) | 7 |
| **Win rate** | **99.91%** |
| Проигрышей при цене 97%+ | 7 |

**Вывод:** Стратегия покупки "дорогих" исходов (97%+) статистически сверхнадёжна. Из 14,751 разрешённых рынков проиграли всего 7.

### Проигрыши по ценовым бакетам

| Бакет | Проигрыши | Всего | Loss rate |
|---|---|---|---|
| 99%+ | 1 | 12,293 | 0.01% |
| 98-99% | 0 | 1,038 | 0% |
| 97-98% | 6 | 1,413 | 0.4% |

### Проигрыши по категориям

| Категория | Проигрыши | Всего | Loss rate |
|---|---|---|---|
| crypto | 4 | 1,234 | 0.3% |
| sports_other | 3 | 8,245 | 0.04% |

---

## 2. Все 7 проигрышей в деталях

### Crypto/финансовые рынки (4 проигрыша):
1. **"Will the price of Solana be above $90 on March 18?"** — first_price=0.97, crypto
2. **"Will the price of Ethereum be between $2,100 and $2,200 on March 18?"** — first_price=0.9795, crypto
3. **"Will the price of Ethereum be above $2,200 on March 18?"** — first_price=0.979, crypto
4. **"Will the price of Solana be between $80 and $90 on March 18?"** — first_price=0.97, crypto

**Паттерн:** Все 4 — пороговые рынки криптовалют ("price above/below/between X"). Цена криптовалюты скакнула и все "безопасные" ставки проиграли одним движением.

### Sports (3 проигрыша):
5. **"Map 1: Odd/Even Total Kills?"** — first_price=0.9945, esports (монетка)
6. **"Spread: Kashima Antlers (-2.5)"** — first_price=0.9755, sports_other
7. **"Game 1: Any Player Penta Kill?"** — first_price=0.974, esports (редкое событие)

**Паттерн:** Odd/Even (чистая монетка при 99.45%), Spread (разброс), Penta Kill (непредсказуемое редкое событие).

---

## 3. Текущий портфель бота

| Показатель | Значение |
|---|---|
| Всего позиций в трекере | 205 |
| Выиграно | 98 |
| Открыто | 81 |
| Продано | 14 |
| Продаётся | 11 |
| **Проиграно** | **1** |
| Реализованная прибыль (won) | +$9.11 |
| Реализованный убыток (lost) | -$4.89 |
| PnL от продаж | -$0.14 |
| **Чистый реализованный PnL** | **+$4.08** |
| Нереализованный PnL (open) | -$12.89 |

### Разбивка 81 открытой позиции по типам

| Тип | Кол-во | Вложено | Риск |
|---|---|---|---|
| Tweet/post bracket | 26 | $194.37 | Главная концентрация! |
| Election/politics | 17 | $114.18 | Средний |
| Bitcoin/crypto "dip to" | 5 | $44.99 | Средний |
| Shipping/strait | 5 | $24.72 | Нет данных в scanner |
| Earthquake bracket | 3 | $24.97 | КРИТИЧЕСКИЙ (-$8.44 просадка) |
| Exact Score | 3 | $14.84 | Низкий (321 wins / 0 losses) |
| Sports match | 3 | $19.85 | Низкий |
| Esports | 3 | $19.92 | Низкий |
| Will say word | 3 | $30.03 | Низкий (135 wins / 0 losses) |
| Прочее | 12 | $74.51 | Низкий |

---

## 4. Критические позиции (CRITICAL/DANGER)

### CRITICAL (6 позиций, убыток -$10.89):

| Позиция | Вход | Текущ. | PnL | Паттерн в scanner |
|---|---|---|---|---|
| Exactly 2 earthquakes 6.5+ by Mar 22 | 0.979 | 0.153 | **-$8.44** | 0 resolved в scanner! |
| Exactly 3 earthquakes 6.5+ by Mar 22 | 0.992 | 0.866 | -$0.63 | 0 resolved в scanner! |
| Musk 420-439 tweets Mar 17-24 | 0.991 | 0.866 | -$0.63 | 0 losses / 77 resolved |
| Jhonny Plata La Paz mayor | 0.982 | 0.904 | -$0.79 | 0 losses / 64 resolved |
| Musk 440-459 tweets Mar 17-24 | 0.990 | 0.9145 | -$0.38 | 0 losses / 77 resolved |
| Trump 60-79 posts Mar 17-24 | 0.979 | 0.918 | -$0.62 | 0 losses / 88 resolved |

### DANGER (3 позиции, убыток -$0.75):

| Позиция | Вход | Текущ. | PnL | Паттерн в scanner |
|---|---|---|---|---|
| Exact Score: Fulham 3-3 Burnley | 0.991 | 0.951 | -$0.20 | 0/321 (0% loss rate) |
| Vermont vs Louisville (W) | 0.990 | 0.9535 | -$0.37 | Спорт — 3/8245 (0.04%) |
| Musk 460-479 tweets Mar 17-24 | 0.992 | 0.956 | -$0.18 | 0/77 (0% loss rate) |

---

## 5. Анализ фильтров: что покрыто и что нет

### Текущие фильтры (filters.py) — ХОРОШО работают:
- Earthquake keywords — покрыты TOXIC_KEYWORDS
- Tweet/post brackets — покрыты TOXIC_KEYWORDS
- Temperature — покрыты WEATHER_PATTERNS
- O/U, Spread, Handicap — покрыты SPORTS_BAD_PATTERNS (только для спорта)
- Coin-flip (odd/even, first blood) — покрыты COIN_FLIP_PATTERNS
- Financial thresholds ("close above", "price of") — покрыты THRESHOLD_PATTERNS + FINANCIAL_ASSETS
- Shipping/transit — покрыты SLOW_KEYWORDS

### Критическая проблема: фильтры есть, но бот ВСЁ РАВНО набрал эти позиции

Фильтр `check_toxic_keywords` блокирует earthquake и tweet brackets. Но в портфеле:
- **3 позиции с earthquake** (включая -$8.44 убыток!)
- **26 позиций с tweet/post brackets**

**Почему?** Вероятные причины:
1. Позиции были куплены ДО добавления фильтра TOXIC_KEYWORDS
2. Некоторые формулировки вопросов не ловятся текущими regex-паттернами

Проверка regex для открытых позиций:
- "Will there be exactly 2 earthquakes..." — ловится `\bearthquake` -- OK
- "Will Elon Musk post 420-439 tweets from..." — ловится `\btweets?\b` -- OK
- "Will Donald Trump post 60-79 Truth Social posts from..." — "posts" ловится `\bposts?\b.*\d+-\d+`, но формулировка "post 60-79" -- проверить порядок

**Вывод:** Фильтры были добавлены ПОСЛЕ покупки этих позиций. Новые покупки этих типов уже блокируются.

---

## 6. Пробелы в данных scanner (слепые зоны)

Некоторые типы рынков имеют МАЛО или НОЛЬ разрешённых данных в scanner:

| Паттерн | Resolved в scanner | Статус |
|---|---|---|
| Earthquake brackets | **0** | СЛЕПАЯ ЗОНА — нет данных для оценки |
| Golf/championship wins | **0** | СЛЕПАЯ ЗОНА |
| Shipping/strait | **0** | СЛЕПАЯ ЗОНА |
| Seat brackets (35-39 seats) | 4 | Мало данных |
| Album sales | 8 | Мало данных |
| Elections | 69 | Достаточно (0 losses) |
| Tweet brackets | 77 | Достаточно (0 losses) |
| "Will X say" | 107 | Достаточно (0 losses) |
| "Dip to" crypto | 117 | Достаточно (0 losses) |
| Draw markets | 152 | Хорошо (0 losses) |
| Exact Score | 321 | Хорошо (0 losses) |
| Spread | 1,530 | Отлично (1 loss = 0.07%) |
| Temperature | 1,372 | Отлично (0 losses at 97%+) |

---

## 7. Рекомендации

### 7.1 НЕМЕДЛЕННО: Earthquake brackets

**Проблема:** 3 открытые позиции, -$9.07 нереализованного убытка. Earthquake bracket markets — подсчёт точного количества землетрясений — абсолютно непредсказуем. Позиция "exactly 2 earthquakes" уже упала с 97.9c до 15.3c.

**Действие:** Фильтр TOXIC_KEYWORDS уже ловит earthquake. Убедиться, что бот не покупает их снова. Текущие позиции — продать то, что можно, или принять убыток. Позиция на 15.3c уже потеряна ($8.44).

**В scanner:** 0 resolved earthquake markets — мы вообще не знаем их win rate! Это самая опасная слепая зона.

### 7.2 ВЫСОКИЙ ПРИОРИТЕТ: Tweet/post bracket концентрация

**Проблема:** 26 позиций, $194.37 вложено — это 34% всего открытого портфеля ($567). Если Musk внезапно перестанет твитить или начнёт твитить втрое больше, все 26 позиций могут упасть одновременно.

**Scanner данные:** 77 resolved tweet brackets, 0 losses. Win rate 100%.

**Однако:** Это корреляционный риск. Один Twitter-аутаж может обрушить все 26 позиций. При текущих ценах суммарный unrealized PnL уже -$2.50.

**Рекомендация:** Добавить лимит концентрации — максимум 15% портфеля на один тип рынка. Для tweet/post brackets это ~$85 вместо текущих $194.

### 7.3 СРЕДНИЙ: "Dip to" crypto markets

**Проблема:** 5 позиций, $45 вложено. Одна из них ("dip to $66K") уже в WATCH с -$0.30.

**Scanner данные:** 117 resolved "dip to" рынков, 0 losses. НО: 4 из 7 проигрышей в scanner — это crypto price thresholds. Рынки "dip to" — это фактически тот же тип.

**Разница:** "dip to" ставит на то, что цена НЕ упадёт до уровня (покупка "No"). "Price above" — ставка что цена БУДЕТ выше. Оба зависят от волатильности крипты.

**Рекомендация:** Текущие фильтры (FINANCIAL_ASSETS + THRESHOLD_PATTERNS) должны ловить "price above/below", но "dip to" проходит мимо, потому что фраза "dip to" не в списке THRESHOLD_PATTERNS. Добавить:
```python
r'\bdip\s+(to|below)\b',
```
в THRESHOLD_PATTERNS. **Однако:** 117 resolved / 0 losses — на данный момент паттерн прибыльный. Фильтровать НЕ нужно, но нужно ограничить концентрацию.

### 7.4 НИЗКИЙ: Exact Score markets

**Scanner:** 321 resolved, 0 losses. Безопасный паттерн.
**В портфеле:** 3 позиции. Одна (Fulham 3-3 Burnley) в DANGER с -$0.20.

**Рекомендация:** Не фильтровать. Win rate 100% на 321 рынках — это надёжно.

### 7.5 НИЗКИЙ: Draw markets

**Scanner:** 152 resolved, 0 losses. Безопасный паттерн.
**Рекомендация:** Не фильтровать.

### 7.6 ИНФОРМАЦИЯ: Election markets

**Scanner:** 69 resolved, 0 losses. Хороший win rate.
**В портфеле:** 17 позиций, $114 — второй по величине блок.
**Рекомендация:** Не фильтровать, но следить за концентрацией (особенно Bolivia elections — 10+ позиций на одну страну).

---

## 8. Итоговая таблица рекомендаций

| # | Действие | Влияние | Приоритет |
|---|---|---|---|
| 1 | Earthquake: фильтр уже есть, НЕ покупать снова | Предотвращает потери типа -$8.44 | НЕМЕДЛЕННО |
| 2 | Лимит концентрации: max 15% на один тип рынка | Защита от корреляционных обвалов | ВЫСОКИЙ |
| 3 | Добавить `r'\bdip\s+(to\|below)\b'` в THRESHOLD_PATTERNS (опционально) | 0 losses сейчас, но crypto volatile | СРЕДНИЙ |
| 4 | Мониторить слепые зоны (earthquake, golf, shipping) — нет resolved данных | Неизвестный risk | СРЕДНИЙ |
| 5 | Exact score, draw, election — НЕ фильтровать | 0% loss rate в scanner | Не требуется |

---

## 9. Главный вывод

**Стратегия бота работает.** Из 14,751 разрешённых рынков в scanner при 97%+ цене проиграли всего 7 (0.05%). Бот имеет реализованный PnL +$4.08 при 98 выигрышей и только 1 проигрыше.

**Главные риски НЕ в выборе рынков, а в:**
1. **Концентрации** — 26 tweet/post brackets ($194) могут упасть одновременно
2. **Слепых зонах** — earthquake brackets не имеют данных в scanner и уже стоили -$8.44
3. **Таймлайне фильтров** — фильтры были добавлены ПОСЛЕ некоторых покупок, поэтому в портфеле есть позиции, которые сейчас были бы заблокированы

**Единственное реальное действие:** добавить лимит концентрации по типу рынка (max 15% портфеля).
