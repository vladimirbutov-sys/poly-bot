# Промпт для создания бота 98_sure_bot

## Задача

Создай торгового бота для Polymarket, который находит рынки с текущей ценой любого исхода >= 98.5 центов и ставит $1 в согласии с рынком (покупает тот исход, который стоит >= 98.5c).

## Контекст

Мы провели исследование (сканер `97_scanner`): из 3,737 рынков с ценой 97%+ закрылось 3,736 в пользу дорогого исхода и только 1 проиграл (мусорный рынок с ликвидностью $41). Это стратегия с win rate ~100% и ROI 1-2% за сделку. Деньги замораживаются в среднем на 5-9 часов.

## Архитектура

Бот должен содержать следующие файлы:

### config.py
- Все настройки: пороги, фильтры, API endpoints, пути
- Секреты (приватный ключ, кошелек, Telegram) — ТОЛЬКО из .env файла
- Основные параметры:
  - `PRICE_THRESHOLD = 0.985` (минимальная цена исхода для покупки)
  - `MAX_PRICE = 0.996` (НЕ покупать выше этой цены — ROI слишком мал)
  - `BET_SIZE = 1.00` (размер ставки в USD)
  - `BANKROLL = 100.0` (стартовый банкрол)
  - `MIN_LIQUIDITY = 1000` (минимальная ликвидность рынка в USD)
  - `SCAN_INTERVAL = 300` (секунды между сканами)
  - `MIN_VOLUME_24H = 0` (можно поднять позже для фильтра stale)

### scanner.py
Модуль сканирования рынков. Каждые N минут:
1. Запросить все открытые рынки с Gamma API (`https://gamma-api.polymarket.com/markets`) с пагинацией по 500
2. Фильтр: `closed = false`
3. Для каждого рынка: распарсить `outcomePrices` (это JSON-строка, например `'["0.985", "0.015"]'`), найти исход с ценой >= PRICE_THRESHOLD и <= MAX_PRICE
4. Применить фильтры исключений (см. ниже)
5. Вернуть список кандидатов для покупки

### filters.py
Модуль фильтрации. Каждый фильтр — отдельная функция, возвращает `(passed: bool, reason: str)`.

**Фильтры исключений:**

1. **Ликвидность** — пропустить если `liquidityNum < MIN_LIQUIDITY` ($1000). Поле `liquidityNum` из API.

2. **Coin-flip рынки** — пропустить если вопрос содержит ключевые слова: `odd/even`, `odd or even`, `first blood`, `first kill`, `first baron`, `first dragon`, `first tower`, `first rift herald`, `coin flip`. Это рынки-монетки, где цена 98% ничего не значит.

3. **Пороговые рынки вблизи текущего значения** — пропустить если вопрос содержит: `close above`, `close below`, `be above`, `be below`, `be between`, `be greater than`, `be less than`, `price of` в комбинации с ценовыми/числовыми значениями. Это рынки типа "BTC выше $84,000?" где до порога 0.1%. Сюда же входят рынки о курсе нефти, золота, крипты и любых других активов.

4. **Погода с узкими диапазонами** — пропустить если вопрос содержит `temperature` или `highest temp` в сочетании с конкретной температурой (число + °F/°C). Прогноз может ошибиться на 1 градус.

5. **Stale-рынки** — если есть данные `volume24hr` и оно = 0, пропустить. Цена может быть устаревшей.

6. **Уже купленный рынок** — не покупать если уже есть открытая позиция на этот condition_id.

7. **Спортивные live-рынки** — если у рынка есть поле `gameStartTime` и текущее время > gameStartTime, значит матч уже идёт. Пропустить — камбэки случаются. Особенно опасно в хоккее, теннисе, киберспорте.

8. **Проверка баланса** — перед каждой ставкой проверить USDC баланс на кошельке. Если < BET_SIZE — не ставить, ждать пока redeem вернёт средства.

### executor.py
Модуль размещения ордеров через Polymarket CLOB API.
- Использовать `py_clob_client` (pip install py-clob-client)
- Размещать limit order (не market order — для контроля проскальзывания)
- Ждать fill до 5 минут, затем отменить
- **ВАЖНО: обрабатывать partial fills.** После таймаута проверить сколько shares реально куплено (не предполагать что ордер исполнился полностью или не исполнился). Записать в трекер реальное количество купленных shares.
- API: `https://clob.polymarket.com`, chain_id=137 (Polygon)

**Правила проскальзывания (максимально допустимая цена покупки):**

| Цена исхода на рынке | Макс. проскальзывание | Пример |
|---|---|---|
| 0.985 — 0.990 | 0.3c (0.003) | Рынок 0.985 → покупаем не дороже 0.988 |
| 0.990 — 0.996 | 0.1c (0.001) | Рынок 0.992 → покупаем не дороже 0.993 |
| > 0.996 | НЕ СТАВИМ | ROI слишком мал для любого проскальзывания |

Цена лимитного ордера = цена исхода + допустимое проскальзывание для его диапазона.

Пример из рабочего бота:
```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

client = ClobClient(CLOB_HOST, key=PRIVATE_KEY, chain_id=137, signature_type=0, funder=WALLET)
client.set_api_creds(client.create_or_derive_api_creds())

order_args = OrderArgs(token_id=token_id, price=round(price, 2), size=shares, side="BUY")
signed_order = client.create_order(order_args)
response = client.post_order(signed_order, OrderType.GTC)
```

Минимум 5 shares на ордер (требование Polymarket). Если `$1 / price < 5`, нужно увеличить ставку до `5 * price`.

### tracker.py
Учёт позиций в JSON-файле `positions.json`:
- Запись: order_id, condition_id, token_id, title, price, cost_usd, size_shares, timestamp, status (open/won/lost)
- Статистика: wins, losses, total_pnl, current_balance
- **ВАЖНО: при повторном скане (каждые 5 мин) бот найдёт те же рынки снова. Обязательно проверять condition_id по уже открытым позициям, чтобы не покупать дважды.**

### redeemer.py
Автоматический вывод средств после закрытия рынка:
- Каждые 5 минут проверять открытые позиции
- Для каждой — проверить on-chain: `payoutDenominator > 0` значит рынок resolved
- Если resolved — вызвать `redeemPositions` на контракте CTF
- Контракты Polygon:
  - CTF: `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`
  - USDC: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
  - NegRiskAdapter: `0xC5d563A36AE78145C45a50134d48A1215220f80a`
- Для neg_risk рынков — вызывать redeem через NegRiskAdapter (без USDC аргумента)
- Определить WON/LOST: сравнить USDC баланс до и после redeem

### telegram_notify.py
Уведомления в Telegram:
- Новая ставка: рынок, цена, сумма
- Результат: WIN/LOSS, прибыль/убыток
- Ошибки

### main.py
Главный цикл:
1. Запустить redeemer в фоновом потоке
2. В основном цикле каждые SCAN_INTERVAL секунд:
   - Проверить баланс USDC
   - Сканировать рынки
   - Применить фильтры
   - Для каждого кандидата: проверить нет ли открытой позиции → купить → записать
3. Логирование в файл и консоль
4. Graceful shutdown по Ctrl+C

## Технические детали

- Python 3.12, Windows
- Зависимости: `requests`, `py-clob-client`, `python-dotenv`, `web3`
- RPC: `https://polygon.gateway.tenderly.co`
- Кодировка консоли: добавить в начало `sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')`
- Sleep в цикле — по 60 секунд (чтобы не ломаться при sleep/hibernate Windows)
- .env файл должен содержать: POLYMARKET_WALLET, POLYMARKET_PRIVATE_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

## Текущие параметры (апрель 2026)

### Размеры ставок
- Обычный (regular): $20
- Neg_risk: $15
- Погодные: $10
- Тест 96.5-97.5% non-politics: $5
- Slow: $5

### Ценовые пороги
- Политика/геополитика: 96.0% — 99.5%
- Остальное: 96.5% — 99.5% (96.5-97.5% в тестовом режиме по $5)

### Лимиты капитала
- Max neg_risk frozen: $350
- Max total frozen: $1000
- Max end_date: 3 дня (regular и neg_risk)
- Max end_date в прошлом: 3 дня

## Фильтры (порядок проверки)

### filters.py (проверяются для каждого кандидата):
1. **check_min_price** — цена ниже порога для категории
2. **check_neg_risk** — neg_risk заморожено > $350
3. **check_liquidity** — ликвидность < $500
4. **check_end_date** — end_date слишком далеко/в прошлом. UMA proposed = пропуск
5. **check_sports_cancelled** — game_start_time > 6ч назад (любая категория!) или end_date > 6ч назад (спорт)
6. **check_financial_asset** — крипто/акции если volume < $50K
7. **check_toxic_keywords** — землетрясения, торнадо, tweet brackets
8. **check_delayed_resolution** — описание содержит отложенную резолюцию
9. **check_title_date_vs_end_date** — дата в заголовке > 3 дней позже end_date
10. **check_coin_flip** — odd/even, first blood
11. **check_sports_win_only** — спорт: только "Will X win", блок O/U, spread, handicap
12. **check_stale** — volume < $500
13. **check_already_bought** — уже есть позиция

### main.py (дополнительные проверки перед ордером):
14. **_is_sub_match** — game/map/set, win by KO, exact score
15. **_is_election** — выборы, губернаторы (медленная резолюция)
16. **_is_slow** — top, season, rotten tomatoes, box office
17. **Дубль по event_key** — 1 позиция на событие
18. **MAX_TOTAL_FROZEN** — все открытые > $1000
19. **USDC баланс** — недостаточно средств
20. **Verify CLOB price** — расхождение Gamma vs CLOB > 3c
21. **Overround фильтр** — для neg_risk мультиисходов: ratio >= max(Sum(Yes) * 0.5, 1.0) → SKIP
22. **On-chain проверка** — уже держим токены (защита от partial fill накопления)

## Overround фильтр (мультиисходные турниры)

На турнирных рынках (гольф, теннис, выборы) Sum(Yes) всех участников часто > 100%.
Это значит что No-цены завышены. Для каждого кандидата:

```
ratio = CLOB_Yes / (1 - No_price)  # реальная vs подразумеваемая Yes цена
threshold = max(Sum(Yes) * 0.5, 1.0)
if ratio >= threshold → SKIP (No переоценено)
```

Sum(Yes) считается из Gamma API данных (без доп. запросов, кэш на скан-цикл).

## Важные нюансы

1. **outcomePrices и outcomes — это JSON-строки**, а не списки. Нужно парсить: `json.loads(market["outcomePrices"])`
2. **clobTokenIds — тоже JSON-строка**. Парсить так же. clobTokenIds[i] — это token_id для outcomes[i]
3. **negRisk** — если True, redeem через NegRiskAdapter, если False — через CTF напрямую
4. **Nonce при redeem**: использовать `w3.eth.get_transaction_count(address, 'pending')` и ставить паузу 5 секунд между транзакциями
5. **Gamma API пагинация**: `offset` + `limit=500`, ходить пока `len(response) == 500`
6. **Дубли при повторном скане** — бот сканирует каждые 5 минут и будет находить те же рынки. Проверка по condition_id в tracker — обязательна
7. **Partial fills** — после таймаута проверять on-chain баланс. Если shares есть — сохранить позицию, не удалять. Перед покупкой — проверять что мы ещё не держим токены on-chain (защита от накопления)
8. **game_start_time** — проверяется для ВСЕХ категорий, не только спортивных. Gamma API может вернуть stale цены после завершения матча с неправильной категоризацией
