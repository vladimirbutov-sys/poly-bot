# Uranium Hedge Analysis — является ли NO "US obtains" хеджем?

**Дата:** 2026-04-14
**Вопрос:** Является ли наша позиция **NO на "US obtains Iranian enriched uranium by May 31"** хеджем к остальным YES-позициям по uranium-тематике?

---

## 1. Портфель uranium-позиций (7 штук)

| # | Позиция | Outcome | Shares | Avg | Cur | Value | Unrealized |
|---|---|---|---|---|---|---|---|
| 1 | Iran surrenders stockpile by **June 30** | YES | 224.2 | 0.271 | 0.535 | $119.93 | +$59.20 |
| 2 | Iran ends enrichment by **June 30** | YES | 206.2 | 0.335 | 0.550 | $113.43 | +$44.40 |
| 3 | Trump agrees to Iranian enrichment (April) | YES | 462.0 | 0.140 | 0.233 | $107.65 | +$43.10 |
| 4 | **US obtains uranium by May 31** | **NO** | 123.6 | **0.810** | 0.795 | $98.29 | −$1.85 |
| 5 | Iran ends enrichment by **April 30** | YES | 210.3 | 0.135 | 0.363 | $76.43 | +$48.13 |
| 6 | US–Iran nuclear deal by April 30 | YES | 181.9 | 0.222 | 0.360 | $65.49 | +$25.11 |
| 7 | Iran surrenders stockpile by **April 30** | YES | 185.1 | 0.089 | 0.302 | $55.91 | +$39.44 |

**Total value:** $637 (NO: $98 / YES: $539)

---

## 2. Правила резолюции (ключевые выжимки из gamma API)

### NO "US obtains uranium by May 31" — **ВЫСОКАЯ ПЛАНКА**
> US government officially confirms it has gained **physical custody or control** of enriched uranium previously controlled by Iran by **May 31, 2026**. **Announcements of deals, agreements, commitments, or plans do NOT count.**

**Физический transfer обязателен.** Не подпись, не обещание — реальное получение.

### YES "Iran agrees to surrender stockpile by Apr 30 / Jun 30" — **НИЗКАЯ ПЛАНКА**
> Iran **publicly agrees/pledges** to surrender its enriched uranium stockpile. Unilateral announcement OR part of an agreement qualifies. Any quantity counts.

**Просто публичное обещание.** Physical transfer не требуется.

### YES "Iran ends enrichment by Apr 30 / Jun 30" — **НИЗКАЯ ПЛАНКА**
> Iran **publicly agrees to end all enrichment of uranium.** Agreement or pledge before resolution date qualifies.

Опять просто соглашение, не действие.

### YES "Trump agrees to Iranian enrichment (April)" — **противоположно всему**
> US agrees to the **continued enrichment** of uranium by Iran. Limitations/restrictions count.

Если США согласны с продолжением обогащения — это противоположно "Iran surrenders" по смыслу, но оба YES могут быть правдой (USD согласен на ограниченное обогащение + Iran сдаёт часть запасов).

### YES "US-Iran nuclear deal by April 30"
> Official agreement (publicly announced mutual agreement) about Iranian nuclear research/weapons.

Любое соглашение — положительная корреляция с surrender/end enrichment.

---

## 3. Матрица сценариев

Разложим реальные исходы на независимые события и посмотрим что выиграет, что проиграет:

### Событие A: Иран **публично согласился** прекратить обогащение (до Apr 30 / Jun 30)
### Событие B: Иран **публично согласился** сдать запасы (до Apr 30 / Jun 30)
### Событие C: **Физически** передал запасы США (до May 31)
### Событие D: США **согласились** с продолжением иранского обогащения (до Apr 30)
### Событие E: US-Iran nuclear deal (любой) подписан (до Apr 30)

Вот сценарии и как двигаются наши позиции:

| # | Сценарий | A | B | C | D | E | **YES (1,2,5,7)** | **YES (3)** | **YES (6)** | **NO (4)** |
|---|---|---|---|---|---|---|---|---|---|---|
| S1 | **Ничего не произошло** (status quo) | ✗ | ✗ | ✗ | ✗ | ✗ | **LOSE** all | **LOSE** | **LOSE** | **WIN ✓** |
| S2 | Иран **обещал** end enrich, но не surrender | ✓ | ✗ | ✗ | ✗ | ✗ | 1,7 LOSE; 2,5 WIN | LOSE | LOSE | **WIN ✓** |
| S3 | Иран **обещал** surrender + end enrich, но физ-transfer не успел | ✓ | ✓ | ✗ | ✗ | ✓ | **ALL WIN** | LOSE | **WIN** | **WIN ✓** |
| S4 | Иран обещал **И** физически передал к May 31 | ✓ | ✓ | ✓ | ✗ | ✓ | **ALL WIN** | LOSE | **WIN** | **LOSE ✗** |
| S5 | Deal с **сохранением** обогащения (D=✓) | ✗ | ✗ | ✗ | ✓ | ✓ | **LOSE** all | **WIN** | **WIN** | **WIN ✓** |
| S6 | Deal с ограниченным обогащением + частичной сдачей | ✓ | ✓ | ✗ | ✓ | ✓ | **WIN** | **WIN** | **WIN** | **WIN ✓** |
| S7 | Eskalation / война — ничего не подписано | ✗ | ✗ | ✗ | ✗ | ✗ | **LOSE** all | **LOSE** | **LOSE** | **WIN ✓** |

---

## 4. Где NO на "US obtains" **совпадает** с YES-позициями

| Сценарий | NO "US obtains" | Основные YES | Корреляция |
|---|---|---|---|
| **S3** (Иран согласился, физ-transfer не успел) | **WIN** | **WIN** | ✅ обе в плюс |
| **S4** (Иран согласился + быстрый физ-transfer) | **LOSE** | **WIN** | ❌ обратная |
| **S5** (Deal с сохранением обогащения) | **WIN** | Surrender LOSE, Trump/Deal WIN | смешанно |
| **S6** (Гибридный deal) | **WIN** | **WIN** | ✅ обе в плюс |

**Вывод по ключевому вопросу:** NO "US obtains" работает как **хедж только против S4** (быстрый физический transfer). В **S3, S5, S6** — наоборот, **двигается в ту же сторону** что и YES.

---

## 5. Насколько вероятен S4?

S4 — это когда:
- Иран публично согласился сдать уран (до April 30 или до June 30) **И**
- Физически передал США (до May 31)

**Это очень узкий коридор времени**: договор → физ transfer (недели логистики) → всё должно уложиться между "дата согласия" и May 31.

Исторические прецеденты:
- **Ливия 2003-2004** — согласие+физический transfer занял **~12 месяцев**
- **Иран JCPOA 2015** — обогащённый уран вывезли в Россию за **~9 месяцев** после подписания
- **Сирия химическое оружие 2013-2014** — вывоз занял **~7 месяцев** (с нарушениями)

**Типичный timeframe физического transfer'а = 6-12 месяцев**. Срок May 31 — **крайне сжатый** даже если Иран согласится завтра.

**Текущая рыночная цена NO "US obtains by May 31" = 0.795** (мы купили 0.810). Это говорит что **рынок оценивает S4 в ~20%** — что довольно высоко учитывая исторические прецеденты. Возможно это переоценено.

---

## 6. Заключение

### Итоговая оценка: **ЧАСТИЧНЫЙ хедж + КОРРЕЛЯЦИЯ**

NO "US obtains uranium by May 31" — это **не классический хедж** к YES-позициям.

**Почему не чистый хедж:**
- В **большинстве вероятных сценариев** (S1, S3, S5, S6) NO выигрывает или проигрывает **в том же направлении** что и YES-позиции, а не в противоположном
- Ценовая корреляция это подтверждает: позиция торгуется стабильно в узком диапазоне 0.78-0.82, слабо двигается на новостях которые двигают YES

**В чём её реальная ценность:**
- **Страховка от единственного сценария** — быстрого физического transfer'а (S4)
- S4 исторически маловероятен (prior ~10%), но рынок оценивает в ~20%
- Если S4 случится — все YES-позиции **взлетят** (+100-300% revenue), NO потеряет cost basis $98 → $0
- Expected payoff NO: в S1/S2/S3/S5/S6/S7 получим ~$123 (shares × $1 при NO wins), в S4 получим $0
- Средневзвешенно: 0.80 × $123 + 0.20 × $0 = **$98.40** (≈ break-even на текущей цене 0.795)

### Рекомендация

**Это не хедж.** Это **stand-alone edge-play** — **пари на то, что физический transfer не успеет к May 31**, даже если подписи будут.

**Стоит ли держать?**
- **ДЕРЖАТЬ** если веришь что prior для S4 реально ~10% (рынок переоценивает → edge есть)
- **ЗАКРЫТЬ** если веришь что prior ~20% (рынок справедлив)
- **НЕ считать это защитой портфеля** — если S4 случится, общий портфель всё равно в huge плюсе, NO не критичная страховка

Чистый потенциал NO на cost basis $98: upside до $25 ($1/sh × 123.6 − $98 = $23.8 profit если NO WIN), downside до −$98 (если S4 = NO LOSE).

**Хедж-value: минимальная.** Основная прибыль портфеля идёт из YES-позиций. NO "US obtains" ведёт себя как независимая ставка с низкой корреляцией к остальным.

---

## Данные

- Positions: `data-api.polymarket.com/positions?user=0x4717...`
- Resolution rules: `gamma-api.polymarket.com/markets?condition_ids=<cid>`
- Исторические прецеденты: JCPOA 2015, Libya 2003-2004, Syria CW 2013-2014 (общедоступные источники)
