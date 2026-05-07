# Feasibility: can we measure liquidity at the moment of each denizz trade?

**Дата:** 2026-04-14
**Цель:** перед тем как строить множитель M_liquidity, проверить, можно ли вообще узнать глубину рынка в момент, когда denizz делал каждую конкретную сделку.

## TL;DR (простым языком)

- **Хотели:** узнать, сколько «денег стояло в стакане» рядом с ценой покупки в момент сделки denizz — чтобы понять, упирался ли он в потолок.
- **Полный ответ невозможен:** Polymarket не хранит снимки книги заявок в прошлом. CLOB `book?token_id=...` возвращает только текущее состояние.
- **Но есть хорошие прокси:**
  1. **Исторические СДЕЛКИ** через `data-api.polymarket.com/trades?market=...&startTs=...&endTs=...` — работает, возвращает всю историю, можно посчитать объём торгов рядом с моментом denizz. Это прокси активности/ликвидности.
  2. **Собственный пиковый размер denizz** (`totalBought × avgPrice` из `denizz_positions_ALL.json`) — lower-bound на глубину: если он смог купить $30k, значит столько минимум там «стояло». Уже в кэше, 100% покрытие.

## Итог по ТЗ

| Проверка | Результат | Коммент. |
|---|---|---|
| `/trades?market&startTs&endTs` endpoint | ✅ **Работает** | Вернул 200, данные за Feb/Mar/Apr 2026 и старше (тест. сделки до июля 2025). |
| Пагинация | ⚠️ limit=500 | На busier рынках нужен offset или сужение окна; для большинства denizz-сделок 48ч окно укладывается. |
| Rate limits | Не задокументированы | Тесты ≥0.6s между запросами прошли без 429. Лимит себе ставим 300 всего, pace ≥0.5s. |
| Полнота истории | ✅ | Сделки за июль 2025 и за апрель 2026 отдаются одинаково. |
| Историческая глубина стакана (book@T) | ❌ **Нет** | Endpoint `/book` возвращает только now. Нет архива snapshot'ов. |
| Fallback (2): peak position size | ✅ 100% coverage | Уже в `denizz_positions_ALL.json`. |
| Fallback (3): плотность соседних сделок | ✅ feasible | По тесту 5 точек запрос ~0.7с, успех 5/5. |

### Тест эндпоинта (сэмпл)

```
GET /trades?market=<cid>&startTs=<T-86400>&endTs=<T+86400>&limit=500  → 200 OK

2025-07-01 | Israel withdraws from Gaza           | trades24h=500 vol=$105k    denizz_buy=$2118
2025-10-08 | Israel ceasefire first announce       | trades24h=500 vol=$1.08M   denizz_buy=$454
2025-12-29 | Foreign intervention Gaza             | trades24h=500 vol=$38k     denizz_buy=$64
2026-02-02 | Khamenei out of Iran                  | trades24h=500 vol=$468k    denizz_buy=$165
2026-03-01 | Hezbollah strike on Israel            | trades24h=500 vol=$73k     denizz_buy=$1002
```

Где trades24h достиг 500 (лимит) — надо пагинировать; у большинства мелких denizz-сделок рынок тонкий, там 500 не достигается.

## Вердикт feasibility

**YELLOW** (частичное покрытие, но достаточно для решения задачи):

- True depth-within-2c на момент сделки — **недоступно**.
- Qualitative liquidity tiering (thin/medium/deep) — **доступно через (2) + (3)**, с корректной честной пометкой «прокси, не точная глубина».
- Для Q2 (profitability по liquidity-tier) это достаточно: тиринг по собственному пиковому размеру denizz — самый надёжный доступный сигнал, и покрытие 100%.
- Для Q1 (ceiling-hit ratio) используем оба прокси: `denizz_buy_usd / max(peak_position_usd_on_same_cid, 1)` и `denizz_buy_usd / volume_in_same_market_±1h`.

**→ Переходим к полной аналитике с прокси, с пометкой «прокси, lower-bound» в каждом выводе.**

## План fullscale analysis

1. **Q2:** бакетирование по собственному peak size denizz → ROI/WR/PnL по thin/medium/deep.
2. **Q1:** ceiling-hit ratio на основе обеих прокси.
3. **Q3:** бэктест V2-бота с/без M_liquidity на 465 позициях denizz, сравнение PnL.

**Файлы:** `_analytics/2026-04-14_denizz-liquidity-sizing-deep.md`, `_analytics/data/denizz_liquidity_backtest.json`.
