# Backtest: Stop-Loss Rule (Change 4a)
**Дата:** 2026-04-11 18:37
**Трейдер:** Denizz
**Обработано позиций:** 50 из 390 resolved

## Правило стоп-лосса

| Тир входа | Стоп-лосс % |
|---|---|
| 2-15c | -60% |
| 15-50c | -50% |
| 50-82c | -45% |
| 82-99c | -40% |

## Таблица 1: Сводка по тирам

| Тир | Всего позиций | Стоп сработал бы | Из них прибыльные (ложный стоп) | Из них убыточные (верный стоп) | % ложных |
|---|---|---|---|---|---|
| 2-15c | 6 | 5 | 0 | 5 | 0% |
| 15-50c | 19 | 12 | 3 | 9 | 25% |
| 50-82c | 19 | 5 | 0 | 5 | 0% |
| 82-99c | 6 | 1 | 0 | 1 | 0% |
| **ИТОГО** | **50** | **23** | **3** | **20** | **13%** |

## Таблица 2: Ложные стопы (прибыльные позиции, которые бы вырезал стоп)

| Название | Тир | Вход | Мин. цена | Просадка | Итог PnL | Упущенная прибыль |
|---|---|---|---|---|---|---|
| US x Iran ceasefire by April 30? | 15-50c | 0.380 | 0.175 | 53.9% | $18493 | $24210 |
| US-Iran nuclear deal by March 31? | 15-50c | 0.257 | 0.001 | 99.8% | $146 | $0 |
| Will Hamas agree to disarm by March 31? | 15-50c | 0.193 | 0.001 | 99.7% | $169 | $0 |

## Таблица 3: Верные стопы (убыточные позиции, где стоп спас бы деньги)

| Название | Тир | Вход | Мин. цена | Итог убыток | Стоп сэкономил бы |
|---|---|---|---|---|---|
| US forces enter Iran by December 31? | 15-50c | 0.282 | 0.001 | $-49478 | $24835 |
| US x Iran ceasefire by April 7? | 82-99c | 0.961 | 0.001 | $-38173 | $22486 |
| Will Iran close the Strait of Hormuz by March 31? | 15-50c | 0.189 | 0.001 | $-24480 | $13161 |
| Will Israel launch a major ground offensive in Leb | 15-50c | 0.222 | 0.001 | $-22441 | $11221 |
|  Iran agrees to end enrichment of uranium by March | 15-50c | 0.175 | 0.001 | $-8372 | $2097 |
| Will Israel or the US target Isfahan Nuclear Techn | 50-82c | 0.700 | 0.001 | $-5214 | $930 |
| US strikes Iraq by March 7? | 15-50c | 0.422 | 0.001 | $-1728 | $878 |
| Trump announces end of military operations against | 2-15c | 0.092 | 0.003 | $-2066 | $655 |
| Iran x Israel/US conflict ends by March 31? | 15-50c | 0.200 | 0.001 | $-1278 | $639 |
| Will Iran strike Oman again in March? | 50-82c | 0.741 | 0.001 | $-740 | $407 |
| Will the Iranian regime fall by March 31? | 2-15c | 0.101 | 0.001 | $-724 | $290 |
| Iran x Israel/US conflict ends by March 15? | 2-15c | 0.053 | 0.001 | $-683 | $273 |
| Will Hezbollah conduct military action against Isr | 50-82c | 0.552 | 0.035 | $-367 | $201 |
| Will Hezbollah conduct military action against Isr | 50-82c | 0.650 | 0.002 | $-275 | $151 |
| Will Israel take military action in Lebanon on Apr | 15-50c | 0.422 | 0.001 | $-226 | $113 |
| Israel x Hamas Ceasefire Phase II by March 31? | 15-50c | 0.160 | 0.001 | $-192 | $101 |
| Masoud Pezeshkian out by March 31? | 2-15c | 0.123 | 0.003 | $-39 | $15 |
| US forces enter Iran by April 30? | 2-15c | 0.026 | 0.001 | $-36 | $14 |
| Will Hezbollah conduct military action against Isr | 50-82c | 0.750 | 0.001 | $-6 | $0 |
| US x Iran ceasefire by March 15? | 15-50c | 0.317 | 0.001 | $-6427 | $0 |

## Таблица 4: Чистый эффект

| Метрика | Значение |
|---|---|
| Сэкономлено верными стопами | $78,467 |
| Потеряно из-за ложных стопов | $24,210 |
| **Чистый эффект** | **$+54,258** |

## Вердикт

Stop-loss правило 4a **чистый плюс**: экономит $54,258 больше, чем теряет.

Ложные стопы: 3 (13% от сработавших)
Верные стопы: 20

> **Примечание:** обработано 50 позиций с данными о ценах из 390 resolved (API вызовов: 175). Для полного бэктеста запустите с `--limit 0`.