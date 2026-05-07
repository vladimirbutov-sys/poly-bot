# Backtest: Stop-Loss Rule (Change 4a)
**Дата:** 2026-04-16 12:40
**Трейдер:** Denizz
**Обработано позиций:** 50 из 390 resolved

## Правило стоп-лосса

| Тир входа | Стоп-лосс % |
|---|---|
| 2-15c | -60% |
| 15-70c | -60% |
| 70-82c | -45% |
| 82-99c | -35% |

## Таблица 1: Сводка по тирам

| Тир | Всего позиций | Стоп сработал бы | Из них прибыльные (ложный стоп) | Из них убыточные (верный стоп) | % ложных |
|---|---|---|---|---|---|
| 2-15c | 7 | 6 | 0 | 6 | 0% |
| 15-70c | 26 | 13 | 3 | 10 | 23% |
| 70-82c | 11 | 2 | 0 | 2 | 0% |
| 82-99c | 6 | 1 | 0 | 1 | 0% |
| **ИТОГО** | **50** | **22** | **3** | **19** | **14%** |

## Таблица 2: Ложные стопы (прибыльные позиции, которые бы вырезал стоп)

| Название | Тир | Вход | Мин. цена | Просадка | Итог PnL | Упущенная прибыль |
|---|---|---|---|---|---|---|
| US-Iran nuclear deal by March 31? | 15-70c | 0.257 | 0.001 | 99.8% | $146 | $0 |
| Will Hamas agree to disarm by March 31? | 15-70c | 0.193 | 0.001 | 99.7% | $169 | $0 |
| Foreign intervention in Gaza by March 31? | 15-70c | 0.266 | 0.001 | 99.8% | $784 | $0 |

## Таблица 3: Верные стопы (убыточные позиции, где стоп спас бы деньги)

| Название | Тир | Вход | Мин. цена | Итог убыток | Стоп сэкономил бы |
|---|---|---|---|---|---|
| US x Iran ceasefire by April 7? | 82-99c | 0.961 | 0.001 | $-38173 | $24360 |
| US forces enter Iran by December 31? | 15-70c | 0.282 | 0.001 | $-49478 | $19868 |
| Will Israel launch a major ground offensive in Leb | 15-70c | 0.222 | 0.001 | $-22441 | $8977 |
|  Iran agrees to end enrichment of uranium by March | 15-70c | 0.175 | 0.001 | $-8372 | $1677 |
| Will Israel or the US target Isfahan Nuclear Techn | 15-70c | 0.700 | 0.001 | $-5214 | $677 |
| Trump announces end of military operations against | 2-15c | 0.092 | 0.003 | $-2066 | $655 |
| Will another country recognize Somaliland by March | 15-70c | 0.270 | 0.001 | $-1444 | $578 |
| Iran x Israel/US conflict ends by March 31? | 15-70c | 0.200 | 0.001 | $-1278 | $511 |
| Will Iran strike Oman again in March? | 70-82c | 0.741 | 0.001 | $-740 | $407 |
| Will the Iranian regime fall by March 31? | 2-15c | 0.101 | 0.001 | $-724 | $290 |
| Iran x Israel/US conflict ends by March 15? | 2-15c | 0.053 | 0.001 | $-683 | $273 |
| Will Hezbollah conduct military action against Isr | 15-70c | 0.552 | 0.035 | $-367 | $146 |
| Will Hezbollah conduct military action against Isr | 15-70c | 0.650 | 0.002 | $-275 | $110 |
| Will Israel take military action in Lebanon on Apr | 15-70c | 0.422 | 0.001 | $-226 | $90 |
| Israel x Hamas Ceasefire Phase II by March 31? | 15-70c | 0.160 | 0.001 | $-192 | $81 |
| Masoud Pezeshkian out by March 31? | 2-15c | 0.123 | 0.003 | $-39 | $15 |
| US forces enter Iran by April 30? | 2-15c | 0.026 | 0.001 | $-36 | $14 |
| Will Hezbollah conduct military action against Isr | 70-82c | 0.750 | 0.001 | $-6 | $0 |
| Israel x Hamas ceasefire cancelled by March 31, 20 | 2-15c | 0.129 | 0.001 | $-1 | $0 |

## Таблица 4: Чистый эффект

| Метрика | Значение |
|---|---|
| Сэкономлено верными стопами | $58,729 |
| Потеряно из-за ложных стопов | $0 |
| **Чистый эффект** | **$+58,729** |

## Вердикт

Stop-loss правило 4a **чистый плюс**: экономит $58,729 больше, чем теряет.

Ложные стопы: 3 (14% от сработавших)
Верные стопы: 19
