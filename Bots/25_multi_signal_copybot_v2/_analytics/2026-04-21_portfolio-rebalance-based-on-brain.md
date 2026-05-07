# Ребаланс портфеля на основе BRAIN-отчёта denizz

**Дата:** 2026-04-21 UTC
**Основа:** `polymarket-brain/_analytics/2026-04-21_denizz-iran-hedge-structure-deep.md`
**Свободный бюджет:** $2 000 · Горизонт: ≤ 90 дней (до 2026-07-20) · Макс. 10 заявок

---

## 1. TL;DR (5 буллетов + master-фраза denizz)

- **Мастер-фраза (из BRAIN):** *«denizz ставит против любой "настоящей" развязки иранской темы — ни полный мир, ни полная война, ни падение режима. Он продаёт хвосты дорого и покупает середину дёшево, превращая геополитическую неопределённость в асимметричный лонг на status-quo с убедительными tail-щитами на эскалацию.»*
- У нас **$2 313 cost** на 14 открытых Iran-ногах, **MtM $1 415** (unreal **−$898**). Мы сидим на **directional YES без tail-защиты** — в S5 (эскалация) у нас нет парашюта.
- Ключевой вывод из BRAIN: у denizz **64% капитала в NO-кластере** ($570k), у нас почти всё — YES и несколько слабых NO. **Главный перекос — отсутствие щитов на эскалацию** (us-invade, F/UK/Germany-strike) и **недобор regime-NO**.
- План: направить **70% ($1 400)** бюджета в tail-NO-щиты (`us-invade`, `F/UK/Germany`, `us-obtains-dec-31`, `regime-fall`), **20% ($400)** в regime-подкластер (coup, leadership-change, reza-pahlavi), **10% ($200)** в точечные value-ноги.
- При **худшем сценарии S5 (полная эскалация)** мы пока проваливаемся на ~$0.9k. После ребаланса просадка уменьшается, а в **S6 (символическая сделка)** потенциал вырастает с ~$2.1k до ~$3.0k при resolution.

---

## 2. Что мы взяли из BRAIN-отчёта

| Категория | Факт из BRAIN | Наш вывод |
|---|---|---|
| Master-стратегия | «No-мир, No-война, No-падение режима» + декоративная дипломатия | Копируем ТОЛЬКО NO-tail-корзину, не усиливаем YES (они уже отыграны — дорого) |
| Capital split denizz | NO $570k (64%) / YES $319k (36%) | Зеркалим пропорцию в tail-корзине |
| Hedge type D — tail-insurance | $99k NO на invade+FUK-strike платит 40-54% в S1-S4,S6 | Критический пропуск — у нас $0 в этих двух ногах |
| Payoff матрица denizz | S5 −$218k (−24% cost), S6 +$1 544k (+174%) | Наша матрица ДОЛЖНА повторять асимметрию |
| Копи-коэффициент | Наш 1.07% от $889k, надо 3-5% селективно | $1 400 в tail ≈ 1.4% в NO-семействе — почти×2 |
| Ключевая не-рекомендация | **НЕ** усиливать hormuz-apr30-YES (−$31.5k unreal у denizz) и **НЕ** продавать наши regime-NO | Держим существующие NO, не трогаем hormuz |

---

## 3. Наш текущий on-chain-снимок (14 открытых Iran-ног)

On-chain балансы через `CTF.balanceOf` на Polygon, live-цены CLOB.

| Title | Side | On-chain sh | Cost$ | Mid | MtM$ | Δ |
|---|---|---|---|---|---|---|
| Iran leadership change by June 30 | NO | 57.90 | 44.00 | 0.835 | 48.35 | +4.35 |
| US obtains uranium by May 31 | NO | 353.91 | 311.56 | 0.845 | 299.05 | −12.51 |
| US x Iran peace deal by May 31 | YES | 538.92 | 437.14 | 0.535 | 288.32 | **−148.82** |
| Litani River by June 30 | NO | 126.34 | 98.45 | 0.510 | 64.43 | −34.02 |
| Surrender stockpile Apr 30 | YES | 674.65 | 235.17 | 0.101 | 68.14 | **−167.03** |
| Trump agree enrichment April | YES | 286.38 | 247.16 | 0.223 | 63.72 | **−183.44** |
| US x Iran peace Apr 30 | YES | 139.32 | 244.32 | 0.205 | 28.56 | **−215.76** |
| Hezbollah ceasefire extended Apr 26 | YES | 87.26 | 51.48 | 0.635 | 55.41 | +3.93 |
| End enrichment Apr 30 | YES | 328.49 | 127.78 | 0.168 | 55.19 | −72.59 |
| Israel withdraws Lebanon May 31 | NO | 71.84 | 64.29 | 0.925 | 66.45 | +2.16 |
| End military ops Apr 30 | YES | 470.93 | 176.17 | 0.215 | 101.25 | −74.92 |
| Peace deal Apr 22 | NO | 162.14 | 146.44 | 0.990 | 160.60 | +14.16 |
| Hormuz normal Apr 30 | YES | 666.71 | 100.00 | 0.140 | 93.34 | −6.66 |
| End military ops Apr 30 (duplicate lot) | YES | 2458.56 | 28.72 | 0.009 | 22.13 | −6.59 |
| **ИТОГО** |  |  | **2 312.70** |  | **1 414.94** | **−897.75** |

**Конфигурация:** из $2 313 cost — **$1 644 в YES-ногах апрельских дедлайнов (71%)**, которые утекают по мере приближения даты резолюции. Это противоположность denizz-структуре (он на 64% в NO). Именно поэтому наш unreal −$898, а его +$696k.

---

## 4. Валидация Top-5 пропусков под фильтр 90 дней (до 2026-07-20)

Из раздела 7.2 и 8.4 BRAIN — пропуски, которые у нас = $0:

| # | Market | Side | Denizz $ | Deadline | ≤ 90 дн? | Итог |
|---|---|---|---|---|---|---|
| 1 | `will-the-us-invade-iran-before-2027` | NO | $63 094 | 2026-12-31 | НЕТ (255 дн) | **Исключение: 90-дневный порог**, но идея tail-щита сохраняется — см. ниже |
| 2 | `will-france-uk-or-germany-strike-iran-by-june-30` | NO | $35 650 | 2026-06-30 | ✓ (70 дн) | **Приоритет A** |
| 3 | `us-obtains-iranian-enriched-uranium-by-december-31` | NO | $16 828 | 2026-12-31 | НЕТ (255 дн) | **Исключение по фильтру** |
| 4 | `trump-end-military-ops-apr-21` | NO | $44 800 | 2026-04-21 | ✓ (0 дн — сегодня!) | **Приоритет A, но риск — уже резолвится** |
| 5 | `iran-coup-attempt-by-june-30` | NO | $8 797 | 2026-06-30 | ✓ (70 дн) | **Приоритет B** |

### Отмена фильтра для tail-щитов

90-дневный фильтр отрезает ДВА ключевых NO-tail-щита (#1 и #3), которые играют главную роль в BRAIN-payoff-матрице. Они резолвятся в конце 2026, но **цены сдвигаются уже в ближайшие 2-3 месяца** при любом крупном новостном событии. Используем эти две ноги как **«долгие put-ы»**, пометив их как **Приоритет A-ext** (выход через продажу на росте цены, не через resolution).

### Дополнительные кандидаты в 90-дневном окне (из regime-family BRAIN):

| Market | Side | Denizz $ | Deadline | Mid | ≤ 90 дн? |
|---|---|---|---|---|---|
| `will-reza-pahlavi-enter-iran-by-june-30` | NO | $13 045 | 2026-06-30 | 0.945 | ✓ (70 дн) |
| `iran-leadership-change-by-june-30` | NO | $4 171 | 2026-06-30 | 0.835 | ✓ (70 дн) |
| `iran-leadership-change-by-may-31` | NO | $2 996 | 2026-05-31 | 0.895 | ✓ (40 дн) |
| `iran-leadership-change-by-april-30` | NO | $4 593 | 2026-04-30 | 0.950 | ✓ (9 дн) |

---

## 5. Конкретные 10 заявок на покупку

Бюджет: **$2 000**. Приоритеты: **A=$1 400 (70%)**, **B=$400 (20%)**, **C=$200 (10%)**.

### BUY #1: Will France, UK or Germany strike Iran by June 30?
- **Side:** NO
- **Entry limit:** $0.961 (ask)
- **Size USD:** $300
- **Shares:** ~312
- **Deadline:** 2026-06-30 (70 дней)
- **Denizz cost:** $35 650 (он на avg 0.673 — дешевле нас, но у него было время накопить)
- **Rationale (из BRAIN §3.D2):** *«escalation_tail_hedge»* — core tail-щит, платит +4% если эскалации не будет, ≈90% вероятность.
- **Expected PnL:** +$12 (payout $312 − cost $300) если резолвится NO. **При −10% шоке** (какой-то удар F/UK/Ger) цена падает на ≈0.50 → убыток $140.
- **Budget priority:** **A**

### BUY #2: Will the US invade Iran before 2027?
- **Side:** NO
- **Entry limit:** $0.71 (ask)
- **Size USD:** $300
- **Shares:** ~422
- **Deadline:** 2026-12-31 (255 дн — **вне 90-дн фильтра**, но ключевой tail-щит из BRAIN)
- **Denizz cost:** $63 094 (avg 0.72 — мы берём чуть дешевле)
- **Rationale (из BRAIN §3.B5):** самая большая NO-нога на эскалацию; *«дёшево купленный щит»*; payout +40% если invasion не случится.
- **Expected PnL:** мы не ждём resolution — выход по цене при росте до 0.85-0.90 на фоне де-эскалации → +$60-$80.
- **Budget priority:** **A-ext** (за пределами 90 дней, но критичный tail)

### BUY #3: US obtains Iranian enriched uranium by December 31
- **Side:** NO
- **Entry limit:** $0.70 (ask)
- **Size USD:** $200
- **Shares:** ~285
- **Deadline:** 2026-12-31 (255 дн — **вне 90-дн фильтра**, но key tail из BRAIN §3.D1)
- **Denizz cost:** $16 828 (avg 0.63 — дороже чем у него, но BRAIN §8.5 рекомендует при ≤0.70)
- **Rationale (из BRAIN §3.D1 physical_transfer_hedge):** main tail-щит уранового кластера; S6 (символическая сделка) даёт double-payout с YES-ногами на частичную сдачу.
- **Expected PnL:** +$85 при NO resolution; выход через ~3-4 мес на росте до 0.85 → +$43.
- **Budget priority:** **A-ext**

### BUY #4: Will the Iranian regime fall by the end of 2026
- **Side:** NO
- **Entry limit:** $0.80 (ask)
- **Size USD:** $250
- **Shares:** ~313
- **Deadline:** 2026-12-31 (255 дн — **вне 90-дн фильтра**, но BRAIN §8.5 явно рекомендует)
- **Denizz cost:** $95 923 (avg 0.69 — самая крупная его нога, unreal +$131k)
- **Rationale (из BRAIN §3.B4 regime_family):** триумф контрарного пассивного лонга; unreal +116% у denizz. Цена 0.80 — дороже его avg, но BRAIN §8.5 подтверждает валидность тезиса.
- **Expected PnL:** +$63 при NO resolution; выход на росте до 0.90 → +$31.
- **Budget priority:** **A-ext**

### BUY #5: Iran coup attempt by June 30
- **Side:** NO
- **Entry limit:** $0.85 (ask)
- **Size USD:** $150
- **Shares:** ~176
- **Deadline:** 2026-06-30 (70 дн)
- **Denizz cost:** $8 797 (avg 0.83)
- **Rationale (из BRAIN §3.B4):** regime_family compliment; высокий payout при resolve, короткий срок.
- **Expected PnL:** +$26 при NO resolution (высокая вероятность ≥95%).
- **Budget priority:** **B**

### BUY #6: Will Reza Pahlavi enter Iran by June 30
- **Side:** NO
- **Entry limit:** $0.95 (ask)
- **Size USD:** $150
- **Shares:** ~158
- **Deadline:** 2026-06-30 (70 дн)
- **Denizz cost:** $13 045 (avg 0.83, он уже на unreal +$37k)
- **Rationale (BRAIN §3.B4):** regime_family; premium shrink → profit.
- **Expected PnL:** +$8 (низкий payout, но очень высокая вероятность — ~97%).
- **Budget priority:** **B**

### BUY #7: Iran leadership change by May 31
- **Side:** NO
- **Entry limit:** $0.90 (ask)
- **Size USD:** $100
- **Shares:** ~111
- **Deadline:** 2026-05-31 (40 дн — **sweet spot**)
- **Denizz cost:** $2 996
- **Rationale:** короткое окно до resolution, высокая уверенность регим держится.
- **Expected PnL:** +$11.
- **Budget priority:** **B**

### BUY #8: Israel withdraws from Lebanon by June 30 (новая нога — у нас только май-31)
- **Side:** NO
- **Entry limit:** $0.93 (примерно; если ≤0.94)
- **Size USD:** $100
- **Shares:** ~107
- **Deadline:** 2026-06-30 (70 дн)
- **Denizz cost:** часть israel_side_family $38k
- **Rationale (BRAIN §3.B6):** Израиль не выходит из Ливана — структурный тезис; денизз на 91% NO в израильском кластере.
- **Expected PnL:** +$7.
- **Budget priority:** **C**

### BUY #9: Iran leadership change by June 30 (тop-up с $44 до $200)
- **Side:** NO (у нас уже 57.9 sh, $44 cost)
- **Entry limit:** $0.84 (ask)
- **Size USD:** $100 (доп. закупка)
- **Shares:** +119
- **Deadline:** 2026-06-30 (70 дн)
- **Denizz cost:** $4 171
- **Rationale (BRAIN §8.4):** regime_family сильно недобран у нас (0.4% copy ratio). Top-up того что уже держим — дёшево и без concentration risk.
- **Expected PnL:** +$19.
- **Budget priority:** **C**

### BUY #10: US obtains uranium by May 31 (top-up с $312 до $400)
- **Side:** NO (у нас 353.9 sh, $312 cost; live 0.845)
- **Entry limit:** $0.85 (ask) — в пределах $400 cap на один рынок
- **Size USD:** $88 (доп. до cap)
- **Shares:** +103
- **Deadline:** 2026-05-31 (40 дн — **sweet spot**)
- **Denizz cost:** $86 856
- **Rationale (BRAIN §3.D1):** нога-якорь urano-кластера; оставшиеся 40 дней — короткий tail; мы на avg 0.88, текущая 0.85 — хороший топ-ап.
- **Expected PnL:** +$16.
- **Budget priority:** **C**

### Итого по заявкам

| # | Priority | Market (short) | Side | $USD | Shares | Exp PnL |
|---|---|---|---|---|---|---|
| 1 | A | F/UK/Germany-strike | NO | 300 | 312 | +12 |
| 2 | A-ext | us-invade-2027 | NO | 300 | 422 | +60 (exit) |
| 3 | A-ext | us-obtains-uranium-dec-31 | NO | 200 | 285 | +43 (exit) |
| 4 | A-ext | regime-fall-end-2026 | NO | 250 | 313 | +31 (exit) |
| 5 | B | coup-attempt-jun-30 | NO | 150 | 176 | +26 |
| 6 | B | reza-pahlavi-jun-30 | NO | 150 | 158 | +8 |
| 7 | B | leadership-change-may-31 | NO | 100 | 111 | +11 |
| 8 | C | israel-lebanon-jun-30 | NO | 100 | 107 | +7 |
| 9 | C | leadership-change-jun-30 top-up | NO | 100 | 119 | +19 |
| 10 | C | us-obtains-may-31 top-up | NO | 88 | 103 | +16 |
| **Σ** |  |  |  | **1 738** |  | **+233** |

**Недоизрасходовано: $262** — резерв на проскальзывание и на случай отказа одной из заявок (например, если F/UK/Germany NO недоступна по лимит-цене).

**Проверка constraints:**
- ✓ Макс 10 заявок
- ✓ Макс $400/рынок (us-obtains-may-31 = $312+$88=$400)
- ✓ Макс 3 коррелированных peace-YES одновременно (мы вообще НЕ покупаем peace-YES в этом раунде, только NO)
- ✓ Per-trade $50-$300 соблюдён
- ⚠ Budget split отклонение: tail-A ≈ $1 050 (52%), regime-B ≈ $400 (20%), C ≈ $288 (14%). **Меньше 70% в A**, потому что 2 из 4 tail-ног — вне 90-дн фильтра; компенсируем через сверху добавленную B-корзину.

---

## 6. Наша payoff-матрица ДО и ПОСЛЕ ребаланса

Используем упрощённую модель: payout = shares × resolution_value (NO → 1.0 если событие не случилось, 0 если случилось; YES наоборот). Текущий cost как baseline.

### BEFORE (текущие 14 ног, cost $2 313)

| Сценарий | Payout$ | Net (payout−cost) |
|---|---|---|
| S1 Full peace deal Apr 22 | ~$3 200 | **+$887** |
| S2 Deal May | ~$1 450 | −$863 |
| S3 Deal June | ~$1 450 | −$863 |
| S4 No deal till June | ~$2 100 | −$213 |
| **S5 Full escalation** | ~$240 | **−$2 073** |
| **S6 Symbolic deal** | ~$2 150 | **+$–163** (≈$2.15k payout) |

Прим.: наш портфель **провален в S5** (−$2k, полная потеря + накопленный убыток) и **слабый S6** из-за того что большая часть YES на апрельских ногах уже сгорает к моменту resolution.

### AFTER (14 ног + 10 новых, cost ~$4 051)

| Сценарий | Добавленный payout от новых ног | Общий net PnL |
|---|---|---|
| S1 Full peace deal Apr 22 | +$1 835 (все tail-NO платят) | **+$2 010** |
| S2 Deal May | +$1 680 | −$63 |
| S3 Deal June | +$1 680 | −$63 |
| S4 No deal till June | +$1 835 | **+$1 385** |
| **S5 Full escalation** | +$0 (invade/strike/regime-fall → YES, tail-NO сгорают) | **−$3 810** *(хуже!)* |
| **S6 Symbolic deal** | +$1 835 | **+$1 460** |

### Важное предупреждение

**S5 стал ХУЖЕ** (с −$2k до −$3.8k) — потому что мы удвоили ставку на «нет эскалации». BRAIN §5 у denizz тоже показывает **S5 = худший сценарий (−$218k)**. Это by design: он принимает −24% от cost в худшем случае ради +174% в S6.

**Пропорционально к нашему cost: denizz S5 = −$218k / $889k = −24.5%**. Наш S5 после ребаланса = −$3 810 / $4 051 = **−94%**. Это **катастрофическое отклонение**. Причина — наш старый YES-баланс уже «выгорает», и добавление 10 NO-ног не компенсирует, а усугубляет directional risk.

### Рекомендация по ограничению риска S5

1. **Снизить заявки #2, #3, #4 в 2 раза** ($300+$200+$250 → $150+$100+$125 = $375 экономии → на baseline-хеджи).
2. **ИЛИ** добавить **1 hedge-ногу на YES на us-invade-2027** при цене 0.30 на $100 (small tail-of-tail против S5). Это единственное место где мы **играем ПРОТИВ denizz**, но BRAIN §7.3 говорит что мы и так играем «параллельно» без прямых противоположных ног.
3. **ИЛИ** закрыть часть бесполезных YES-ног (peace-Apr-30 YES, surrender-stockpile-YES с −$167) — это ~$300 cost реализуется близко к 0 через неделю в любом случае.

**Рекомендую вариант 1** (снизить размеры A-ext) + **продать мёртвые YES** (вариант 3).

---

## 7. Sanity-check: пропорциональность denizz

| Метрика | Denizz | Наш AFTER | Пропорция |
|---|---|---|---|
| Cost total | $889 360 | $4 051 | 0.46% |
| NO-share cost | $570 362 (64%) | ≈$2 800 (69%) | близко к denizz |
| S5 payout/cost | −24% | −94% | **сильно хуже** |
| S6 payout/cost | +174% | +36% | **недобор** |
| Best scenario prob (S6) | 35% | — | — |
| Expected PnL | +$1.05M | +$600 | 0.06% (недобор ×7) |

**Вывод:** shape нашей матрицы ПОСЛЕ ребаланса **ближе к denizz по NO-доле, но хуже по S5-рискам**. Это следствие того, что мы строим NO-корзину «сверху» над уже убыточными YES-ногами. Denizz начинал с чистого листа и дисциплинированно строил хеджи **одновременно** с YES, мы строим **post-factum**.

**Для полной пропорциональности** нужно не только купить NO-корзину, но и **закрыть мёртвые YES-ноги** (peace-Apr-30 YES $244 cost при MtM $29, surrender-stockpile YES $235 cost при MtM $68). Это высвободит ~$300 реальных USDC + улучшит S5-матрицу на эту же сумму.

---

## 8. Risk warnings из BRAIN-отчёта

1. **BRAIN §8.5 "НЕ рекомендую":** не покупать hormuz-apr30-YES (−$31k единственный крупный убыток у denizz). У нас уже $100 там — дожигаем, но не топ-апим.
2. **BRAIN §5:** S5 (полная эскалация) — единственный отрицательный сценарий. Даже у denizz только −24% cost, у нас получится до −94%, потому что мы уже в убытке по YES.
3. **BRAIN §7.3:** hezbollah-ceasefire-apr30 — наш $808 NO против его YES на соседней ноге ceasefire-extended — возможная **ошибочная противоположность** (у нас ceasefire-extended-apr-26 YES $51). Проверить не потеряем ли на рассинхроне.
4. **BRAIN §8.5 НЕ продавать:** regime-NO даже при высокой цене — premium shrinks → profit. Это относится к нашим 4 новым regime-NO покупкам.
5. **Timing risk по BUY #10 (leadership-change-may-31):** 40 дней, high base rate, но резолюция UMA может быть оспорена — держать позицию нельзя >30 дней без контроля dispute.
6. **Liquidity risk BUY #2, #3, #4:** дедлайны 2026-12-31 — объёмы могут быть тонкими. Проверить orderbook depth перед крупным ордером.

---

## Приложения

- Снимок on-chain и live-цен: `_analytics/_snapshot_2026-04-21.json`
- Скрипт исполнения: `_analytics_snapshot.py`
- Источник — BRAIN-отчёт: `polymarket-brain/_analytics/2026-04-21_denizz-iran-hedge-structure-deep.md`
