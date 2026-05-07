# Глубокая сверка портфеля с denizz (проверка on-chain + история)

**Дата:** 2026-04-21 14:17  
**Источник данных:** data-api.polymarket.com `/positions` + `/activity` + Polygon CTF.balanceOf
**Метод:** on-chain verify (baldance≥1 sh) — ground truth

## Сводка

| Категория | Кол-во | Значение |
|---|---:|---|
| Наши открытые позиции (size≥0.5) | **40** | |
| 🟢 Держим оба (мы + denizz) | **19** | cost $2931 |
| 🔵 Только у нас | **21** | cost $1716 |
|   └ denizz никогда не держал | 18 | $952 |
|   └ denizz держал и вышел | 2 | $652 |
|   └ denizz держал, частично продал | 1 | $112 |
|   └ другое/incomplete | 0 | $0 |

## 🟢 Держим оба (19)

| Рынок | Side | Sh | Cost | Denizz sh |
|---|---|---:|---:|---:|
| [Strait of Hormuz traffic returns to normal by end of April?](https://polymarket.com/event/strait-of-hormuz-traffic-returns-to-normal-by-april-30/strait-of-hormuz-traffic-returns-to-normal-by-april-30) | Yes | 1016 | $623 | 129904 sh |
| [US obtains Iranian enriched uranium by May 31?](https://polymarket.com/event/us-obtains-iranian-enriched-uranium-by/us-obtains-iranian-enriched-uranium-by-may-31-396) | No | 354 | $312 | 253091 sh |
| [Will Trump agree to Iranian enrichment of uranium in April?](https://polymarket.com/event/what-will-the-us-agree-to/will-trump-agree-to-iranian-enrichment-of-uranium-in-april) | Yes | 354 | $247 | 187386 sh |
| [US x Iran permanent peace deal by April 30, 2026?](https://polymarket.com/event/us-x-iran-permanent-peace-deal-by/us-x-iran-permanent-peace-deal-by-april-30-2026) | Yes | 619 | $244 | 108584 sh |
| [Iran agrees to surrender enriched uranium stockpile by April 30, 2026?](https://polymarket.com/event/iran-agrees-to-surrender-enriched-uranium-stockpile-by/iran-agrees-to-surrender-enriched-uranium-stockpile-by-april-30-2026) | Yes | 675 | $235 | 184390 sh |
| [Will the US x Iran ceasefire be extended by April 21, 2026?](https://polymarket.com/event/us-x-iran-ceasefire-extended-by/will-the-us-x-iran-ceasefire-be-extended-by-april-21-2026-365) | Yes | 513 | $211 | 11319 sh |
| [Israel strike on Yemen by April 30, 2026?](https://polymarket.com/event/israel-strike-on-yemen-by-593/israel-strike-on-yemen-by-april-30-2026-212-911) | No | 204 | $177 | 5268 sh |
| [ Iran agrees to end enrichment of uranium by June 30?](https://polymarket.com/event/iran-agrees-to-end-enrichment-of-uranium-by-june-30/iran-agrees-to-end-enrichment-of-uranium-by-june-30) | Yes | 255 | $143 | 27383 sh |
| [Iran agrees to end enrichment of uranium by April 30?](https://polymarket.com/event/iran-agrees-to-end-enrichment-of-uranium-by-april-30/iran-agrees-to-end-enrichment-of-uranium-by-april-30) | Yes | 328 | $128 | 70162 sh |
| [US-Iran nuclear deal by April 30?](https://polymarket.com/event/us-iran-nuclear-deal-by-april-30/us-iran-nuclear-deal-by-april-30) | Yes | 205 | $116 | 22281 sh |
| [Israeli forces cross the Litani River by June 30?](https://polymarket.com/event/israeli-forces-cross-the-litani-river-by-june-30/israeli-forces-cross-the-litani-river-by-june-30) | No | 126 | $98 | 19402 sh |
| [Trump announces end of military operations against Iran by April 30th?](https://polymarket.com/event/trump-announces-end-of-military-operations-against-iran-by/trump-announces-end-of-military-operations-against-iran-by-april-30th-753-882-164-769-641-926) | Yes | 264 | $87 | 19880 sh |
| [Israel withdraws from Lebanon by May 31, 2026?](https://polymarket.com/event/israel-withdraws-from-lebanon-by/israel-withdraws-from-lebanon-by-may-31-2026) | No | 72 | $64 | 33245 sh |
| [US-Iran nuclear deal before 2027?](https://polymarket.com/event/us-iran-nuclear-deal-before-2027/us-iran-nuclear-deal-before-2027) | No | 125 | $60 | 5102 sh |
| [Israel x Hezbollah Ceasefire extended by April 26, 2026?](https://polymarket.com/event/israel-x-hezbollah-ceasefire-extended-by/israel-x-hezbollah-ceasefire-extended-by-april-26-2026) | Yes | 87 | $51 | 6878 sh |
| [Will Netanyahu talk to Joseph Aoun by April 30?](https://polymarket.com/event/will-netanyahu-talk-to-joseph-aoun-by/will-netanyahu-talk-to-joseph-aoun-by-april-30) | No | 58 | $46 | 918 sh |
| [Iran leadership change by June 30?](https://polymarket.com/event/iran-leadership-change-by/iran-leadership-change-by-june-30-689-922) | No | 58 | $44 | 5562 sh |
| [Iran agrees to surrender enriched uranium stockpile by December 31, 2026?](https://polymarket.com/event/iran-agrees-to-surrender-enriched-uranium-stockpile-by/iran-agrees-to-surrender-enriched-uranium-stockpile-by-december-31-2026) | No | 64 | $22 | 14185 sh |
| [US x Iran permanent peace deal by April 22, 2026?](https://polymarket.com/event/us-x-iran-permanent-peace-deal-by/us-x-iran-permanent-peace-deal-by-april-22-2026) | Yes | 133 | $20 | 3712 sh |

## 🟡 denizz держал и **частично продал** (1)

| Рынок | Side | Sh | Cost | История denizz |
|---|---|---:|---:|---|
| [US-Iran nuclear deal by June 30?](https://polymarket.com/event/us-iran-nuclear-deal-by-june-30/us-iran-nuclear-deal-by-june-30) | Yes | 184 | $112 | partial: bought $16155, sold $17825, now on-chain 0 |

## 🔴 denizz держал и **полностью вышел** (2)

_Это те позиции где бот не последовал за exit_ом denizz'а. Разобраться почему (баги follow-sell)._

| Рынок | Side | Sh | Cost | История denizz |
|---|---|---:|---:|---|
| [US x Iran permanent peace deal by May 31, 2026?](https://polymarket.com/event/us-x-iran-permanent-peace-deal-by/us-x-iran-permanent-peace-deal-by-may-31-2026) | Yes | 539 | $437 | exited 2026-04-16, sold $27766 (bought $21803) |
| [Iran x Israel/US conflict ends by April 30?](https://polymarket.com/event/iran-x-israelus-conflict-ends-by/iran-x-israelus-conflict-ends-by-april-30-766-662-668-546) | Yes | 193 | $215 | exited 2026-04-12, sold $95142 (bought $32268) |

## ⚪ denizz **никогда не держал** (18)

_Эти позиции мы открыли вручную или адоптировали через sync, не копируя denizz._

| Рынок | Side | Sh | Cost | История denizz |
|---|---|---:|---:|---|
| [US x Iran diplomatic meeting by April 22, 2026?](https://polymarket.com/event/us-x-iran-diplomatic-meeting-by-329/us-x-iran-diplomatic-meeting-by-april-22-2026-321-831) | Yes | 162 | $175 | never |
| [Trump announces end of military operations against Iran by May 31st?](https://polymarket.com/event/trump-announces-end-of-military-operations-against-iran-by/trump-announces-end-of-military-operations-against-iran-by-may-31st-651-724-212) | Yes | 181 | $125 | never |
| [Strait of Hormuz traffic returns to normal by end of May?](https://polymarket.com/event/strait-of-hormuz-traffic-returns-to-normal-by-end-of-may/strait-of-hormuz-traffic-returns-to-normal-by-end-of-may) | Yes | 137 | $100 | never |
| [Will J.D. Vance attend the next US x Iran diplomatic meeting?](https://polymarket.com/event/who-will-attend-the-next-us-x-iran-diplomatic-meeting/will-jd-vance-attend-the-next-us-x-iran-diplomatic-meeting) | Yes | 109 | $90 | never |
| [Will Donald Trump announce that the United States blockade of the Strait of Horm](https://polymarket.com/event/trump-announces-us-blockade-of-hormuz-lifted-by/will-donald-trump-announce-that-the-united-states-blockade-of-the-strait-of-hormuz-has-been-lifted-by-may-31-2026-313) | Yes | 93 | $75 | never |
| [Will Trump visit Pakistan by April 30?](https://polymarket.com/event/will-trump-visit-pakistan-by-april-30/will-trump-visit-pakistan-by-april-30-143) | No | 88 | $74 | never |
| [US x Iran ceasefire extended by April 22, 2026?](https://polymarket.com/event/us-x-iran-ceasefire-extended-by/us-x-iran-ceasefire-extended-by-april-22-2026) | Yes | 103 | $70 | never |
| [Will Russia capture all of Huliaipole by April 30?](https://polymarket.com/event/will-russia-capture-all-of-huliaipole-by-february-28/will-russia-capture-all-of-huliaipole-by-april-30) | Yes | 127 | $45 | never |
| [Will Trump's approval rating hit 35% in 2026?](https://polymarket.com/event/how-low-will-trumps-approval-rating-go-in-2026/will-trumps-approval-rating-hit-35-in-2026) | Yes | 100 | $40 | never |
| [Will fewer than 25 ships transit the Strait of Hormuz between April 20-April 26?](https://polymarket.com/event/how-many-ships-transit-the-strait-of-hormuz-this-week-apr-20-26/will-fewer-than-25-ships-transit-the-strait-of-hormuz-between-april-20-april-26) | Yes | 285 | $35 | never |
| [QatarEnergy announces/resumes LNG production in Qatar by April 30?](https://polymarket.com/event/qatarenergy-announcesresumes-lng-production-in-qatar-by-april-30/qatarenergy-announcesresumes-lng-production-in-qatar-by-april-30) | No | 45 | $30 | never |
| [Will 150 or more ships transit the Strait of Hormuz between April 20-April 26?](https://polymarket.com/event/how-many-ships-transit-the-strait-of-hormuz-this-week-apr-20-26/will-150-or-more-ships-transit-the-strait-of-hormuz-between-april-20-april-26) | Yes | 182 | $20 | never |
| [Russia x Ukraine ceasefire by June 30, 2026?](https://polymarket.com/event/russia-x-ukraine-ceasefire-by-june-30-2026/russia-x-ukraine-ceasefire-by-june-30-2026) | Yes | 250 | $20 | never |
| [Will Russia capture Lyman by June 30, 2026?](https://polymarket.com/event/will-russia-capture-lyman-in-2025/will-russia-capture-lyman-by-june-30-2026-413) | Yes | 68 | $15 | never |
| [US x Iran diplomatic meeting by April 21, 2026?](https://polymarket.com/event/us-x-iran-diplomatic-meeting-by-329/us-x-iran-diplomatic-meeting-by-april-21-2026) | Yes | 79 | $14 | never |
| [Will Russia enter Rai-Oleksandrivka by April 30, 2026?](https://polymarket.com/event/will-russia-enter-rai-oleksandrivka-by-february-28/will-russia-enter-rai-oleksandrivka-by-april-30-2026) | Yes | 48 | $10 | never |
| [Internet Access restored in Iran by April 30, 2026?](https://polymarket.com/event/internet-access-restored-in-iran-by/internet-access-restored-in-iran-by-april-30-2026) | Yes | 54 | $7 | never |
| [Will Russia capture all of Hryshyne by April 30?](https://polymarket.com/event/will-russia-capture-all-of-hryshyne-by-april-30/will-russia-capture-all-of-hryshyne-by-april-30) | Yes | 100 | $7 | never |
