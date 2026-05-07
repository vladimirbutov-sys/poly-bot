# Анализ рынка: US forces seize another oil tanker by April 30, 2026

**Дата анализа:** 2026-04-20
**Рынок:** https://polymarket.com/event/us-forces-seize-another-oil-tanker-by-april-15/us-forces-seize-another-oil-tanker-by-april-30
**Slug:** `us-forces-seize-another-oil-tanker-by-april-30`
**Condition ID:** `0x036f32b7b18291ff94d09f0c11830d8b839aafd0148e644207be97a4f9bd5a8a`

---

## 1. TL;DR

- **Цена YES 0.903 (bid 0.876 / ask 0.93)** — рынок заложил ~90% вероятность YES после захвата Touska 19 апреля.
- **Главный парадокс:** Touska — это **контейнеровоз**, шедший из Китая в Иран с "dual-use" грузом (вероятно, перхлорат натрия для ракет). **Нефти на борту не было** ни по одному источнику tier-1. Правило требует "oil tanker OR any other ship actively transporting oil".
- **Вердикт: HOLD / лёгкий BUY NO (маленький размер)**. Формально строгая trасpretация = NO, но рынок и UMA скорее resolved as YES из-за широкой трактовки "nexus to oil blockade". Edge асимметричный, размер маленький.

---

## 2. Параметры рынка

| Параметр | Значение |
|---|---|
| Question | U.S. forces seize another oil tanker by April 30? |
| Market created | 2026-04-03 20:32 UTC |
| Deadline | 2026-04-30 23:59 ET |
| YES best bid / ask | 0.876 / 0.930 |
| Spread | 5.4 cents (широкий) |
| Last trade | 0.944 |
| Volume total | $198,962 |
| Volume 24h | $44,367 |
| Volume 1w | $194,463 |
| Liquidity | $14,204 |
| YES token_id | 99701940500121727292418397429817615595883615255368351271990294980806258260391 |
| NO token_id | 50524326850831840906004985063549131212567630076016465114331905811762975215261 |
| 1-day price change | **+0.60** (взрыв на новости Touska) |
| 1-week price change | +0.478 |
| UMA bond | $500 |
| Resolver | 0x65070BE91477460D8A7AeEb94ef92fe056C2f2A7 |

**Sibling рынки:**
- April 15 — **RESOLVED NO** (closed 2026-04-16, last price 0.002). Ключевой прецедент: в окне 24 марта - 15 апреля UMA не признала ни одно событие квалифицирующим.
- May 15, May 31 — неактивные, объём 0.

---

## 3. Разбор правила пословно

> "U.S. government forces seize an oil tanker **or any other ship actively transporting oil** between market creation and April 30, 2026"

| Критерий | Требование | Touska (19 апр) |
|---|---|---|
| U.S. forces | военные / USCG / law enforcement / intelligence | ✅ USS Spruance + 31st MEU |
| Seize action | боард, контроль, удержание, принудительный редирект | ✅ обстрел, абордаж, захват |
| Oil tanker OR ship transporting oil | **груз должен быть нефтью** | ❌ **контейнеровоз, груз - dual-use химия (вероятно перхлорат натрия)** |
| Window (3 апр → 30 апр) | внутри окна | ✅ 19 апр |
| Credible reporting consensus | tier-1 подтверждение | ✅ CNN, Reuters, AP, WaPo, NBC, Bloomberg |

**Критический блок:** источники (CNN, Al Jazeera, Stars and Stripes, NPR, WaPo) **единодушно** описывают Touska как "container ship" / "cargo ship", шедший из Gaolan port (Zhuhai, Китай) в Bandar Abbas. Никки Хейли и анонимные источники Пентагона говорят про "dual-use items" / химические грузы для ракет. **Ни один tier-1 источник не пишет, что на Touska была нефть.**

---

## 4. Таблица событий-кандидатов

| Дата | Судно | Флаг | Груз | Действие | Квалифицирует? |
|---|---|---|---|---|---|
| 2026-01-07 | Marinera (Bella 1) | RUS | нефть (VEN) | захват в Атлантике | ❌ до создания рынка |
| 2026-01-07 | M Sophia | PAN | нефть (VEN) | захват в Карибах | ❌ до создания рынка |
| 2026-01-09 | MV Olina | Timor | сырая нефть (VEN) | захват USS Gerald R. Ford | ❌ до создания |
| 2026-01-15 | Veronica | ? | сырая нефть | захват USCG | ❌ до создания |
| 2026-01-21 | Sagitta | ? | нефть | захват | ❌ до создания |
| 2026-02-09 | Aquila II | ? | 700k барр. сырой | INDOPACOM boarding | ❌ до создания |
| 2026-02-24 | Bertha | ? | нефть | захват | ❌ до создания |
| 2026-04-13 → | 27 судов в блокаде Hormuz | разные | — | turn-back / return | ❌ нет seizure |
| **2026-04-19** | **Touska** | **IRAN** | **контейнеры / dual-use химия** | **boarded + captured** | **⚠️ СПОРНО** |

Между 3 апреля и 18 апреля **не найдено ни одного подтверждённого tier-1 захвата нефтяного судна** в окне рынка. Блокада давала только "turn-back" (27 судов), без боарда — это не "seize" по определению.

---

## 5. Матрица fair value

| Сценарий | Вероятность | Fair YES |
|---|---|---|
| A) UMA читает правило СТРОГО — нужна нефть на борту. Touska дисквалифицирована. | 30% | 0.25 (нужно новое событие за 10 дней) |
| B) UMA читает правило ШИРОКО — "any ship in oil-related blockade" = Touska qualifies. | 55% | 0.98 |
| C) Dispute / DVM vote, исход неопределён. | 15% | 0.50 |

**Взвешенный fair:** 0.30×0.25 + 0.55×0.98 + 0.15×0.50 = 0.075 + 0.539 + 0.075 = **0.689**

**Альтернативная оценка (если считать UMA скорее про-YES):**
- P(Touska прокатывает) = 70% → 0.70×0.98 + 0.30×(base rate нового события 40%) = 0.686 + 0.120 = **0.806**

**Диапазон fair value: 0.69 – 0.81**

---

## 6. Расчёт edge

- Market YES ask: **0.930**
- Fair YES (средняя оценка): **0.75**
- **Edge YES = 0.75 - 0.93 = -0.18** (отрицательный → BUY NO сторона)
- Fair NO: **0.25**
- NO ask: **0.124** (1 - 0.876)
- **Edge NO = 0.25 - 0.124 = +0.126** (~+12.6%)

**Номинальный edge на стороне NO ~10-13%**, но с высокой вариативностью трактовки.

---

## 7. Риски

### UMA / DVM dispute
- **Главный риск:** UMA proposer может предложить YES со ссылкой на "seized vessel in oil blockade context". Диспутер должен заплатить $500 bond. Если proposer = YES и никто не оспорит в 2 часа livelinesswindow → auto-YES.
- История UMA: в похожих кейсах со спорной формулировкой оракул чаще идёт по общественному нарративу, а не букве правила (прецеденты: Trump "say X" markets).
- Прецедент апрель-15: UMA **не засчитала** ничего до 15 апреля → формалистский подход возможен.

### Timing risk
- 10 дней до deadline. Блокада Hormuz активна, CENTCOM настроен агрессивно. Новый захват реальной нефтяной танкера (Иран/Венесуэла) вполне вероятен — base rate ~35-45% за 10 дней.
- Если будет "clean" захват нефтяного танкера — YES = 0.99.

### Liquidity risk
- Liquidity $14k, spread 5.4 ct — рынок неглубокий. Размер ставки ограничен.
- Best ask NO 0.124 только 140920 shares → можно взять $17k по этой цене, дальше хуже.

### Асимметрия
- BUY NO по 0.124: потенциальный выигрыш +87 ct (если NO), потеря -12.4 ct (если YES). R/R = 7:1.
- Но P(YES) ≥ 70% → EV = 0.70×(-0.124) + 0.30×(+0.876) = -0.087 + 0.263 = +0.176 (позитивно для NO в строгом сценарии)
- EV BUY NO (при fair 0.25): +0.126 на доллар ставки.

### Прочие неоднозначности
- "Seize" включает "forcefully rerouting to U.S.-controlled port" — 27 разворотов блокадой НЕ квалифицируют, т.к. они идут в иранские порты, а не в U.S.-controlled.
- "Another" в названии — маркетинг, в правиле этого нет; не играет роли для UMA.

---

## 8. Позиции китов

- **denizz** (0xbaa2bcb5...2c73): **нет позиции** на этом рынке (data-api возвращает []).
- **gopfan2** (0xf2f6af4f...5817): **нет позиции** на этом рынке.

Отсутствие китов снижает информационный сигнал — большие игроки не размещены. Это также снижает риск "кит-driven dump" на NO.

---

## 9. Финальная рекомендация

### Вердикт: **BUY NO (малый размер)** — Confidence MEDIUM-LOW

**Обоснование:**
1. Туска формально НЕ соответствует строгому чтению правила (контейнеровоз, не нефть).
2. Прецедент с 15-апрельским рынком (закрыт NO) показывает, что UMA не растягивает формулировку.
3. Edge в NO ~12-18% номинально, R/R 7:1.
4. НО: риск широкой трактовки UMA + высокая вероятность нового "clean" захвата за 10 дней.

**План входа:**
- **Target entry:** NO по 0.12 – 0.13 (лимитный ордер на 0.125)
- **Размер:** $100 – $200 (это spike / event-bet, не core).
- **Stop-think level:** если YES пробивает 0.97 на tier-1 новости об UMA proposed YES → закрыть с убытком, не держать до деадлайна.
- **Exit на прибыль:** если новости подтвердят "Touska не оил" и цена NO пойдёт к 0.30+ → частичная фиксация.

### Альтернативный сценарий
Если не готов делать contrarian-ставку против 0.90 рынка — **HOLD / SKIP**. Это classic "dirty rule" рынок, где edge существует только если веришь в формальное чтение UMA. Размер should be small.

### НЕ рекомендуется
- BUY YES по 0.93 — отрицательный edge, downside -93 ct при dispute.

---

## Источники (tier-1)

- Al Jazeera: https://www.aljazeera.com/news/2026/4/20/us-captures-iranian-ship-touska-amid-mediation-efforts-all-we-know
- CNN: https://www.cnn.com/2026/04/20/middleeast/iran-cargo-ship-seized-explainer-intl-hnk-ml
- Washington Post: https://www.washingtonpost.com/world/2026/04/19/trump-iran-war-hormuz-strait-negotiations/
- CNBC: https://www.cnbc.com/2026/04/19/trump-navy-iran-ship-gulf-of-oman.html
- NPR: https://www.npr.org/2026/04/19/nx-s1-5790378/iran-us-hormuz-closed-impossible
- Stars and Stripes: https://www.stripes.com/branches/navy/2026-04-19/us-seizes-iran-cargo-ship-21426952.html
- Bloomberg: https://www.bloomberg.com/news/articles/2026-04-19/trump-says-us-seized-iranian-ship-blew-hole-in-its-engine-room
- Wikipedia (Operation Southern Spear): https://en.wikipedia.org/wiki/United_States_oil_blockade_during_Operation_Southern_Spear
- Wikipedia (2026 Strait of Hormuz crisis): https://en.wikipedia.org/wiki/2026_Strait_of_Hormuz_crisis
- The Week (cargo): https://www.theweek.in/news/middle-east/2026/04/21/what-was-the-dual-use-item-that-iranian-flagged-container-ship-touska-carried.html
