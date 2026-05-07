# Аналитический профиль player2 — 0x9bbd88...56e72

**Дата:** 2026-04-17  
**Wallet:** `0x9bbd88140ccba06100da00476257d9cffce56e72`  
**Pseudonym:** Female-Tailbud (кошелёк без кастомного ника)  
**URL:** https://polymarket.com/@0x9bbd88140ccba06100da00476257d9cffce56e72-1771508511872?tab=positions

## 1. Резюме

- Период активности: **2026-02-20 → 2026-04-17** (56 дней — очень короткая история).
- События: 1882 всего (TRADE 1632: BUY **1627**, SELL **5**; REDEEM **247** на $35,602; REWARD 2; MAKER_REBATE 1).
- **Критическое наблюдение:** 1627 BUY vs 5 SELL — игрок почти не продаёт; выходит через REDEEM (holding-to-expiry), а не через активные продажи.
- Volume: BUY **$45,088**, SELL $2,681, REDEEM payout $35,602.
- Уникальных позиций (asset): 507, маркетов (cid): 424.
- **P&L (реконструкция):** realized **$+15,000**, unrealized **$+14,298**, rewards/rebates $+6 → **Total $+29,304**.
- WR на resolved маркетах (buy>=$30): **57.0%** (N=128), mean ROI **+49.3%**, median **+33.7%**.
- Специализация: **iran** (33.0% USD volume) — НЕТ выраженной специализации (<40%).
- **HEDGING-РИСК:** 38 маркетов с BUY на обеих сторонах, из них 12 со сбалансированным размером (ratio ≥0.7) — **сильный признак merge-арбитража** (тот же паттерн, из-за которого удалили Car).
- Стиль: scalp_ratio 20.0% (N=5 мало), avg trades/позиция 3.2, batch-fills 369 групп (1208 events) = 74.0%.
- Корреляция с denizz: пересечение 36 маркетов; на них same-side **46%** против 19 opposite — то есть на общих маркетах игрок часто сидит на ПРОТИВОПОЛОЖНОЙ стороне от denizz.

## 2. Базовые метрики

| Метрика | Значение |
|---|---|
| Первая активность | 2026-02-20 |
| Последняя активность | 2026-04-17 |
| Период (дней) | 56 |
| Всего activity events | 1882 |
| TRADE events | 1632 |
| BUY events | 1627 |
| SELL events | 5 |
| REDEEM events | 247 (payout $35,602) |
| REWARD events | 2 ($4.69) |
| MAKER_REBATE events | 1 ($1.25) |
| Уникальных позиций (asset) | 507 |
| Уникальных маркетов (cid) | 424 |
| Открытых позиций (сейчас) | 228 |
| Total BUY USD | $45,088 |
| Total SELL USD | $2,681 |
| BUY USD / 7 дней | $20,404 |
| BUY USD / 30 дней | $40,372 |
| Trades / 7 дней | 415 |
| Trades / 30 дней | 1541 |

## 3. P&L и ROI (реконструкция)

Метод: `/positions` endpoint возвращает ТОЛЬКО открытые позиции (228 строк, все size>0). Поэтому realized P&L реконструирован: для каждой cond = Σ(SELL usdcSize) + Σ(REDEEM usdcSize) − Σ(BUY usdcSize); маркет считаем resolved, если нет открытых позиций по нему.

| Метрика | Значение |
|---|---|
| Realized P&L (reconstructed) | $+15,000.18 |
| Unrealized P&L (open) | $+14,298.25 |
| Rewards + Maker rebates | $+5.94 |
| **Total P&L** | **$+29,304.37** |
| Открытых позиций (size>0) | 228 |
| Открытый cost basis | $21,805 |
| Открытый current value | $36,103 |
| Resolved маркетов всего | 226 |
| Resolved + buy≥$30 (для WR) | 128 |
| WR resolved | 57.0% (73/128) |
| Mean ROI resolved | +49.32% |
| Median ROI resolved | +33.67% |
| Sharpe-like | 0.338 |

### Топ-5 прибыльных (resolved conditions)

| Title | BUY$ | SELL$ | REDEEM$ | PnL$ | ROI% |
|---|---|---|---|---|---|
| Will the Freedom Movement (GS) win the most seats in the 2026 Slo | $600 | $0 | $4,114 | $+3,514 | +585.7% |
| Trump announces US x Iran ceasefire end by April 15, 2026? | $1,476 | $0 | $4,781 | $+3,305 | +223.9% |
| Will Fidesz-KDNP win at least 70 seats? | $457 | $0 | $1,502 | $+1,045 | +228.7% |
| Will Israel take military action in Gaza on March 28, 2026? | $400 | $0 | $1,341 | $+941 | +234.9% |
| Military action against Iran continues through March 31, 2026? | $282 | $0 | $1,170 | $+888 | +314.8% |

### Топ-5 убыточных (resolved conditions)

| Title | BUY$ | SELL$ | REDEEM$ | PnL$ | ROI% |
|---|---|---|---|---|---|
| Will the 7-day moving average of Strait of Hormuz transits be bet | $300 | $0 | $0 | $-300 | -100.0% |
| Will the Supreme Court rule on Trump's tarriffs by February 25? | $391 | $0 | $0 | $-391 | -100.0% |
| Will annual inflation increase by 3.3% in March? | $400 | $0 | $0 | $-400 | -100.0% |
| Will the US not strike Iran by February 28, 2026? | $462 | $0 | $0 | $-462 | -100.0% |
| Will Russia enter Dovha Balka by April 30? | $497 | $0 | $0 | $-497 | -100.0% |

## 4. Разбивка по ценовым бакетам (resolved, средняя BUY-цена на cond)

| Бакет | N | WR | Mean ROI | BUY volume | PnL |
|---|---|---|---|---|---|
| 02-15c | 9 | 22.2% | +55.6% | $2,523 | $+1,908 |
| 15-30c | 55 | 45.5% | +24.1% | $8,924 | $+2,648 |
| 30-50c | 56 | 69.6% | +70.9% | $10,070 | $+9,309 |
| 50-70c | 8 | 87.5% | +64.4% | $417 | $+301 |
| 70-85c | 0 | — | — | — | — |
| 85-99c | 0 | — | — | — | — |

## 5. Разбивка по категориям

| Категория | N_all cid | USD vol | % vol | N_res | WR | Mean ROI | PnL |
|---|---|---|---|---|---|---|---|
| iran | 115 | $14,866 | 33.0% | 49 | 63.3% | +52.2% | $+6,764 |
| other | 119 | $10,302 | 22.8% | 43 | 69.8% | +88.9% | $+5,891 |
| elections | 90 | $9,531 | 21.1% | 12 | 50.0% | +78.3% | $+3,618 |
| politics | 52 | $4,784 | 10.6% | 7 | 42.9% | -7.7% | $-75 |
| geopolitics | 18 | $2,616 | 5.8% | 2 | 50.0% | +7.6% | $+279 |
| russia_ukraine | 22 | $1,696 | 3.8% | 10 | 20.0% | -47.3% | $-1,069 |
| crypto_macro | 3 | $769 | 1.7% | 3 | 0.0% | -100.0% | $-769 |
| tech | 3 | $310 | 0.7% | 1 | 0.0% | -100.0% | $-273 |
| entertainment | 2 | $214 | 0.5% | 1 | 0.0% | -100.0% | $-200 |

**Специализация:** `iran` — 33.0% USD volume. НЕТ выраженной специализации (<40%).

## 6. Стиль торговли

| Метрика | Значение |
|---|---|
| Средний BUY (фильтр ≥$30) | $56 |
| Медианный BUY | $48 |
| Trades на позицию (asset) — среднее | 3.22 |
| Trades на позицию — медиана | 2.0 |
| Horizon (часов first BUY → first SELL) — среднее | 135.2 |
| Horizon медиана | 21.6 |
| Scalp ratio (<2ч) | 20.0% (N=5, выборка крошечная т.к. всего 5 sell-ивентов) |
| Batch-fill группы (tx+cid+ts >1) | 369 групп, 1208 events из 1632 (74.0%) |
| Hedging: BUY YES+NO на одном cond | 38 маркетов |
| Из них сбалансированные (min/max ≥0.7) | **12** — признак merge-арбитража |

### Распределение размеров BUY

| Бакет | Кол-во |
|---|---|
| <$100 | 512 |
| $100-500 | 21 |
| $500-2K | 0 |
| $2K-10K | 0 |
| $10K+ | 0 |

Итог: 512 из 533 BUY-ивентов (≥$30) — в категории <$100; ни одного BUY ≥$500. Игрок дробит покупки крошечными ордерами.

## 7. Корреляция с denizz

| Метрика | Значение |
|---|---|
| Маркетов у player2 | 424 |
| Маркетов у denizz | 119 |
| Пересечение (cid) | 36 |
| Same-side first-BUY | 16 |
| Opposite-side first-BUY | 19 |
| Unknown | 1 |
| % same-side (от известных) | 45.7% |

**Интерпретация:** SAME-side 46% — умеренная пересекаемость. Нет ни дополняющей, ни прямо противоположной корреляции.

## 8. Сравнительная таблица denizz vs player2

| Метрика | denizz | player2 |
|---|---|---|
| Lifetime Total P&L | $+399,565 | $+29,304 |
| Realized P&L (reconstructed) | $-117,366 | $+15,000 |
| Unrealized (open) | $+516,930 | $+14,298 |
| WR resolved (buy≥$30) | 29.3% (N=58) | 57.0% (N=128) |
| Total BUY USD | $2,500,699 | $45,088 |
| Total SELL USD | $1,562,468 | $2,681 |
| BUY / SELL events | 4557 / 2247 | 1627 / 5 |
| N маркетов (cid) | 119 | 424 |
| Специализация | iran (94%) | iran (33%) |
| Scalp ratio (<2ч) | 33.0% | 20.0% |
| Avg trades/asset | 46.60 | 3.22 |
| Batch-fill events | 0 | 1208 |
| Hedge markets (YES+NO buys ≥$30) | 25 | 38 |
| Сбалансированный hedge (merge-arb признак) | 5 | 12 |

## 9. Финальная рекомендация

### 🔴 НЕ ДОБАВЛЯТЬ

**Обоснование:**
- Нет выраженной специализации (лид. категория iran 33.0%).
- **12 сбалансированных hedge-маркетов** — паттерн merge-арбитража (аналогично Car, удалённого 2026-04-09 после Iran April 7).
- Всего 5 SELL-ивентов — игрок не продаёт, exit-сигналы копировать невозможно.
- Batch-fills 74.0% trades — большая часть ордеров идёт пачками (арбитражный/ботовый паттерн).

**Ключевой риск** — это тот же сценарий, из-за которого удалили Car 2026-04-09:
> *"Car does merge-prep arbitrage (buys Yes+No, then merges to \$1) — we copied the buys as real direction signals and got burned"* (config.py).

У player2: **12** сбалансированных маркетов с BUY на обе стороны (min/max ≥0.7). Это не directional trader, а buy-and-hold / merge-arb style (BUY:SELL ratio 1627:5 = 325:1). Боту нужны exit-сигналы, а их практически нет.

## 10. Ограничения и риски (методологические)

- Выборка resolved = 128 с buy≥$30. Достаточная.
- `/positions` возвращает только OPEN позиции — для realized P&L используем реконструкцию (BUY/SELL/REDEEM usdcSize по cond).
- Маркет считаем resolved, если нет ни одной открытой позиции по нему (может включать частично закрытые маркеты с merge).
- REDEEM events несут usdcSize = выплата по выигравшему outcome; 111 REDEEM-ов с нулевой суммой = проигравший outcome.
- Классификация категорий — по title через keyword-matching из config.CATEGORY_KEYWORDS. Без ключей → `other`.
- Horizon/scalp ratio считаются только по first BUY→first SELL; выборка крошечная (5 SELL-ивентов всего).
- API `/profile/...` возвращает 404 — ник не подтверждён, используем pseudonym из activity (Female-Tailbud).
- Только 56 дней истории (≤2 месяцев). Стиль может эволюционировать.
- Сравнение с denizz по локальным дампам: activity ALL 6922 events, positions 53 rows.
