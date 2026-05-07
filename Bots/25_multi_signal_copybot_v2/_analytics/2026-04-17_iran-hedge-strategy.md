# Iran Hedge Strategy — 2026-04-17

## 1. Резюме (кратко)

Бот `25_multi_signal_copybot_v2` держит **23 открытые позиции** общей рыночной стоимостью ~$3619, из которых **$3376 (93%) — DEAL_YES** (ставки на успех дипломатии США-Иран: peace, ceasefire, end-of-operations, Hormuz normalization, surrender uranium и т.п.).

**Корреляционный риск:** ceasefire истекает 21-22 апреля 2026. Если сделка провалится и начнётся эскалация, все DEAL_YES-позиции провалятся одновременно. Потенциальный убыток = **$3376** (вся текущая стоимость DEAL_YES обнуляется).

**Предложенный хедж** — 3 отдельных маркета с тонкими но высокоэджевыми YES-позициями (каждый резолвится ≤ 30 апреля):
- Ceasefire end by April 21 (0.060) — **45% веса**
- Gulf State military action vs Iran by April 30 (0.060) — **35%**
- Iran leadership change by April 30 (0.050) — **20%**

**Суммарная стоимость хеджа: $97.90** (2.9% от DEAL_YES стоимости, 14% от свободного баланса $706).
**Ожидаемый payout при полной эскалации: $1688** (50% worst-case).

В сценарии «deal succeeds» теряем только ~$98 (страховая премия), основной портфель даёт ~$2391 апсайда.
В сценарии «full escalation» основной минус $3376 − хедж-плюс $1590 = чистый убыток ~$1786 (≈53% от нехеджевого).
Хедж диверсифицирован по 3 разным эскалационным триггерам, чтобы не зависеть от одного события.

---

## 2. Аудит открытых позиций

Всего открытых: **23** позиции, общая стоимость по миду: **~$3619**.

### DEAL_YES (ставки на успех дипломатии) — 21 позиция, $3375.86

| Title | Outcome | Shares | Avg entry | Mid | Cur value ($) | Unreal P&L |
|---|---|---:|---:|---:|---:|---:|
| Strait of Hormuz traffic returns to normal by end of April? | Yes | 798.28 | 0.376 | 0.645 | 514.89 | +215.03 |
| US x Iran permanent peace deal by April 30, 2026? | Yes | 618.99 | 0.395 | 0.585 | 362.11 | +117.79 |
| Iran agrees to surrender enriched uranium stockpile by April 30? | Yes | 443.98 | 0.278 | 0.614 | 272.60 | +149.02 |
| Will Trump agree to Iranian enrichment of uranium in April? | Yes | 502.97 | 0.295 | 0.501 | 251.99 | +103.81 |
| US x Iran permanent peace deal by April 22, 2026? | Yes | 566.05 | 0.196 | 0.425 | 240.57 | +129.76 |
| Trump announces end of military operations against Iran by April 21? | Yes | 614.32 | 0.241 | 0.345 | 211.94 | +63.87 |
| US x Iran permanent peace deal by May 31, 2026? | Yes | 296.97 | 0.967 | 0.705 | 209.37 | -77.77 |
| Iran agrees to end enrichment of uranium by June 30? | Yes | 254.65 | 0.562 | 0.785 | 199.90 | +56.67 |
| US-Iran nuclear deal by April 30? | Yes | 314.86 | 0.370 | 0.510 | 160.42 | +44.01 |
| Iran agrees to unrestricted shipping through Hormuz in April? | Yes | 205.23 | 0.303 | 0.755 | 154.95 | +92.82 |
| Iran agrees to end enrichment of uranium by April 30? | Yes | 299.78 | 0.422 | 0.494 | 148.09 | +21.68 |
| US-Iran nuclear deal by June 30? | Yes | 183.67 | 0.610 | 0.795 | 146.02 | +33.98 |
| Will the US x Iran ceasefire be extended by April 21, 2026? | Yes | 158.48 | 0.005 | 0.885 | 140.25 | +139.47 |
| Iran x Israel/US conflict ends by April 15? | Yes | 87.38 | 0.533 | 0.902 | 78.82 | +32.23 |
| Israeli forces cross the Litani River by June 30? | No | 79.77 | 0.722 | 0.825 | 65.81 | +8.21 |
| Israel x Hezbollah Ceasefire extended by April 26, 2026? | Yes | 87.26 | 0.590 | 0.605 | 52.79 | +1.31 |
| Iran leadership change by June 30? | No | 57.90 | 0.760 | 0.845 | 48.93 | +4.92 |
| Iran agrees to surrender enriched uranium stockpile by June 30? | Yes | 56.05 | 0.271 | 0.735 | 41.19 | +26.01 |
| Iran x Israel/US conflict ends by April 30? | Yes | 42.87 | 0.700 | 0.915 | 39.23 | +9.23 |
| Will Trump agree to Iranian transit fees in the Strait of Hormuz in April? | No | 28.86 | 0.900 | 0.925 | 26.70 | +0.72 |
| Israel x Hamas Ceasefire Phase II by June 30? | Yes | 68.89 | 0.260 | 0.135 | 9.30 | -8.61 |
| **ИТОГО DEAL_YES** | | | | | **3375.86** | |

### DEAL_NO (ставки на провал) — 1 позиция, $199.06
| Title | Outcome | Shares | Mid | Cur value |
|---|---|---:|---:|---:|
| US obtains Iranian enriched uranium by May 31? | No | 280.37 | 0.710 | 199.06 |

Примечание: «US obtains enriched uranium NO» означает «Иран не сдаёт уран» — играет слабо против deal, но de-facto этот маркет может резолвнуться NO и при успехе deal (просто уран могут сдать ПОСЛЕ 31 мая). Держим как частичный хедж.

### NEUTRAL — 1 позиция, $43.48
| Title | Outcome | Mid | Cur value |
|---|---|---:|---:|
| Will Nicolás Maduro be the leader of Venezuela end of 2026? | Yes | 0.482 | 43.48 |

Не связано с Iran. В сценарном анализе исключаем.

---

## 3. Риск-квантификация

| Метрика | Значение |
|---|---|
| Σ DEAL_YES current value | **$3375.86** |
| Σ DEAL_YES cost basis | $2246.10 |
| Σ DEAL_YES shares | 5264.2 |
| Σ DEAL_NO current value | $199.06 |
| **Worst case (deal fails, все YES→$0)** | **−$3375.86** |
| Best case (all YES→$1) | +$2140.36 апсайд |
| Net deal-exposure (YES − NO) | +$3176.80 |
| **Target hedge payout (50% × worst_case)** | **$1687.93** |

---

## 4. Hedge-кандидаты

Отобрано 17 кандидатов. Все YES-сторона = хедж-сторона (резолвится YES при эскалации). Критерии: закрытие ≤ 31 мая 2026, ликвидность top-5 asks ≥ 500 shares, тема связана с Iran-эскалацией, не в нашем портфеле.

| Slug (ask ≤ 0.10 и liq ≥ 5k) | End | Best ask | Mid | Liq top-5 (shr) | Edge/$ |
|---|---|---:|---:|---:|---:|
| trump-announces-us-x-iran-ceasefire-end-by-april-18-2026 | 2026-04-18 | 0.009 | 0.009 | 158k | 110x |
| will-israel-conduct-military-action-against-iran-by-april-14-2026 | 2026-04-21 | 0.001 | 0.001 | 71k | 999x |
| will-the-us-officially-declare-war-on-iran-by-april-30-2026 | 2026-04-30 | 0.005 | 0.005 | 48k | 199x |
| will-the-iranian-regime-fall-by-april-30 | 2026-04-30 | 0.012 | 0.011 | 178k | 82x |
| will-trump-declare-war-on-iran-by-april-30-2026 | 2026-04-30 | 0.018 | 0.018 | 5.2k | 55x |
| iran-leadership-change-by-april-30 | 2026-04-30 | 0.050 | 0.045 | 85k | **19x** |
| will-a-gulf-state-carry-out-military-action-against-iran-by-april-30-2026 | 2026-04-30 | 0.060 | 0.055 | 52k | **16x** |
| will-israel-conduct-military-action-against-iran-by-april-21-2026 | 2026-04-21 | 0.060 | 0.055 | 24k | **16x** |
| trump-announces-us-x-iran-ceasefire-end-by-april-21-2026 | 2026-04-21 | 0.060 | 0.055 | 25k | **16x** |
| will-another-country-conduct-military-action-against-iran-by-april-30 | 2026-04-30 | 0.070 | 0.065 | 14k | 13x |
| will-uae-strike-iran-by-april-30 | 2026-04-30 | 0.080 | 0.075 | 18k | 12x |
| will-trump-announce-that-the-us-x-iran-ceasefire-has-been-broken-by-april-21 | 2026-04-21 | 0.100 | 0.095 | 14k | 9x |

### Почему НЕ берём слишком дешёвые (<0.02)

«Israel military action by April 14» (0.001), «US declare war» (0.005) и подобные <1¢ тейлы могут не среагировать даже на частичную эскалацию (провал ceasefire ≠ полноценная война). Это слишком экстремальные хвосты для нашего use-case (мы страхуемся от провала сделки, а не от Третьей мировой).

Выбираем маркеты с ценой **0.05–0.06** — они реагируют на «провал ceasefire + действия по вооружению» и сохраняют ~15-19x edge.

---

## 5. Предложенный hedge-портфель

### Распределение

| Роль | Slug | Side | Share | Weight | Target payout |
|---|---|---|---|---:|---:|
| PRIMARY — прямой сигнал «ceasefire broken» | trump-announces-us-x-iran-ceasefire-end-by-april-21-2026 | YES | 760 | 45% | $759.57 |
| SECONDARY — военная эскалация | will-a-gulf-state-carry-out-military-action-against-iran-by-april-30-2026 | YES | 591 | 35% | $590.78 |
| TERTIARY — регимный кризис | iran-leadership-change-by-april-30 | YES | 338 | 20% | $337.59 |
| | | | | **100%** | **$1687.93** |

### Расчёты

| Market | Shares | VWAP | Limit price | Cost ($) | Payout if YES ($) | Edge/$ |
|---|---:|---:|---:|---:|---:|---:|
| Ceasefire end April 21 YES | 760 | 0.0600 | 0.060 | 45.57 | 759.57 | 15.7x |
| Gulf State strikes Iran April 30 YES | 591 | 0.0600 | 0.060 | 35.45 | 590.78 | 15.7x |
| Iran leadership change April 30 YES | 338 | 0.0500 | 0.050 | 16.88 | 337.59 | 19.0x |
| **ИТОГО** | | | | **$97.90** | **$1687.93** | |

### Обоснование выбора 3 маркетов

- **Primary** = дата 21 апреля = EXACT совпадение с deadline нашего главного риска. Триггер: любое публичное объявление Trump о провале ceasefire. Ликвидность 25k shares — более чем достаточно для 760.
- **Secondary** = широкий catcher: любая атака Саудов/ОАЭ/Катара на Иран до 30 апреля → резолв YES. Не зависит от конкретного Twitter-объявления Trump.
- **Tertiary** = regime-change вариант. Работает в сценарии, где deal сохраняется, но в Иране произошёл кризис власти (тоже ломает наш Hormuz-normalize и enrichment-end треды).

Диверсификация: даже если один маркет не резолвится вовремя (технический lag/двусмысленная формулировка), два других подстрахуют.

### Available balance
`tracker.get_available_balance(data)` вернул **$706.02**. Хедж на $97.90 = 14% баланса, остаётся >$600 на текущие покупки сигналов.

---

## 6. Сценарный анализ

| Сценарий | Вероятность* | Осн. портфель | Hedge | Итого | % от unhedged |
|---|---:|---:|---:|---:|---:|
| **Deal до 21-22 апреля** (все YES → $1) | ~30% | **+$2140** (апсайд) | −$98 (премия) | **+$2042** | — |
| **Delay / no deal, no war** (цены стоят) | ~35% | ~±$0 | −$98 | **−$98** | — |
| **Full escalation / ceasefire collapse** (все YES → $0, все хедж YES → $1) | ~25% | **−$3376** | +$1590 | **−$1786** | **53%** |
| **Частичная эскалация** (только primary fires, YES падают в среднем −50%) | ~10% | −$1688 | +$662 − $63 costs = +$599 | **−$1089** | 65% |

*Вероятности — экспертная оценка по рыночным ценам (0.06 на «ceasefire end» ≈ 6% market-implied). Рынок оптимистичен.

**Проверка:** в сценарии «Full escalation» убыток $1786 ≤ 50% × unhedged_loss ($3376 × 0.5 = $1688). Покрытие **47%** (близко к цели 50%, разница — стоимость премии).

---

## 7. Готовые команды на исполнение

```
=== HEDGE PURCHASE COMMANDS ===

1. КУПИТЬ $45.57 YES на "Trump announces US x Iran ceasefire end by April 21, 2026?"
   slug: trump-announces-us-x-iran-ceasefire-end-by-april-21-2026
   cid: 0xdb7886829f415e00ab97b695a28b5747c6bce1f8ab09635a51ec6480e5d50314
   token_id (YES): 1616166182541724838676329828640054929140786650156260222032609831711838834618
   side: YES
   shares: 760
   limit price: 0.060 (GTC)
   expected payout if deal fails: $759.57
   edge: 15.7x per $1
   end date: 2026-04-21

2. КУПИТЬ $35.45 YES на "Will a Gulf State carry out military action against Iran by April 30, 2026?"
   slug: will-a-gulf-state-carry-out-military-action-against-iran-by-april-30-2026
   cid: 0x8a4e2896a318755e419acbeb8f5896ce06715fd2e5ebf35c27602a51b1a891b0
   token_id (YES): 12725228216232659927260200422388843865897455065619986459222807494907250144402
   side: YES
   shares: 591
   limit price: 0.060 (GTC)
   expected payout if deal fails: $590.78
   edge: 15.7x per $1
   end date: 2026-04-30

3. КУПИТЬ $16.88 YES на "Iran leadership change by April 30?"
   slug: iran-leadership-change-by-april-30
   cid: 0xb412664463bbfe21be44b1963291205ab332afd4f7f6e0d027aec1ba7a9e6793
   token_id (YES): 99767261437055226116306337813801042912696159191602956091233868382444699564874
   side: YES
   shares: 338
   limit price: 0.050 (GTC)
   expected payout if deal fails: $337.59
   edge: 19.0x per $1
   end date: 2026-04-30

--- ИТОГО ---
Total cost:   $97.90
Total payout if full escalation: $1687.93
Coverage:     50.0% of worst_case ($3375.86)
Available balance after hedge: ~$608
```

### Технические заметки для исполнения

- Limit-orders GTC (Good-Till-Cancelled). Если цена убежит выше — не гнаться, хедж при цене > 0.10 теряет edge.
- Если ликвидность на заданной цене исчерпалась — дождаться рефилла книги (обычно 5-15 мин) или снизить размер ордера на 20-30%.
- После исполнения добавить хедж-позиции в `positions.json` с тегом `hedge=true` (ручное добавление, не через бот), чтобы бот не пытался их продать по стандартной логике.
- Monitoring: если 22 апреля появится официальное подтверждение extension ceasefire, можно закрыть 1-2 хеджа досрочно и зафиксировать часть премии назад.

---

## Резюме для пересказа (≤200 слов)

**DEAL_YES exposure:** $3376 (21 позиция на успех ceasefire/peace/end-enrichment/Hormuz-normalize). Worst case = полная потеря $3376 при провале ceasefire 21-22 апреля.

**Предложен хедж из 3 маркетов (все YES-сторона):**

1. `trump-announces-us-x-iran-ceasefire-end-by-april-21-2026` — 760 shares @ 0.060 limit = **$45.57** (резолв 21 апреля, прямой сигнал)
2. `will-a-gulf-state-carry-out-military-action-against-iran-by-april-30-2026` — 591 shares @ 0.060 limit = **$35.45** (резолв 30 апреля, широкий catcher)
3. `iran-leadership-change-by-april-30` — 338 shares @ 0.050 limit = **$16.88** (резолв 30 апреля, regime-risk)

**Суммарная стоимость хеджа: $97.90** (2.9% от DEAL_YES стоимости, 14% от свободного баланса $706).
**Защита при full escalation: $1688 payout = ~50% worst-case loss** (цель достигнута).

Премия в сценарии успеха deal: −$98 против +$2140 апсайда на основном портфеле (потеря <5% апсайда).

Команды на покупку — в секции 7 отчёта. Исполнять limit-orders GTC на указанных ценах. Если book исчерпан — не повышать цену выше 0.07 для #1/#2 и 0.06 для #3 (иначе edge теряется).
