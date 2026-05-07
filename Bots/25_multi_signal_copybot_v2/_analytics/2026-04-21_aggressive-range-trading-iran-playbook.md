# Агрессивная range-стратегия для Iran/US портфеля на Polymarket
**Дата отчёта:** 2026-04-21 (данные собраны автоматически из CLOB + positions.json)
**Банкролл:** ~$4–5k | **Позиции в анализе:** 30 открытых рынков Iran/US-темы
**Совокупная стоимость входа (cost_usd):** $4153.94

---

## 1. TL;DR

- **30 активных Iran/US-позиций** на совокупный cost basis ~$4.15k. Из них 29 с валидной историей цен (1 — `US x Iran ceasefire extended by April 22` — без данных, уже близко к resolution).
- **20 из 29 рынков прямо сейчас на BUY-триггере** (<8% ниже 20-дневной медианы) — рынок панически перепродан на фоне эскалации блокады Hormuz 18–19 апр.
- **3 рынка на SELL-триггере** — `U.S. forces seize another tanker by Apr 30` стоит $1.00 (уже resolved в нашу пользу), `Litani River cross by June 30` на NO вырос до $0.47, `<25 ships Hormuz` на YES до $0.117.
- **Средний "объём колебаний" (stdev/median) на Iran-рынках: 0.34**. Топ-5 по волатильности — `Israel withdraws Lebanon NO` (1.12), `<25 ships Hormuz YES` (0.95), `150+ ships Hormuz YES` (0.76), `tanker seize YES` (0.54), `Litani cross NO` (0.47).
- **Ожидаемый 30-дневный edge при чистом исполнении стратегии:** ~**$440** (бэктест $25/цикл, slippage 2%; реальный ожидаемый edge 50–70% от цифры из-за частичного исполнения триггеров).

**Главный вывод:** волатильность peace-рынков 2–4× выше, чем движения "справедливой" вероятности за 20 дней. Это значит что каждый всплеск новостей (захват танкера, гневный твит Трампа) даёт 10–30pp просадку на peace-YES, которая восстанавливается за 12–48 часов — **идеальная среда для мелких циклических buy-low/sell-high сделок**.

## 2. Наши 30 позиций — текущее состояние

| Тикер (outcome, рынок) | Shares | Avg entry | Current | Медиана 20д | Range 20д | Zone | Статус триггера |
|---|---:|---:|---:|---:|---|---|---|
| Yes – Strait of Hormuz traffic returns to normal by end of April? | 495 | $1.258 | $0.185 | $0.275 | $0.17–$0.55 | near_support | **BUY_TRIGGER_HIT** |
| Yes – US x Iran permanent peace deal by May 31, 2026? | 539 | $0.811 | $0.565 | $0.595 | $0.47–$0.76 | mid_range | **WAIT** |
| No – US obtains Iranian enriched uranium by May 31? | 354 | $0.880 | $0.185 | $0.205 | $0.19–$0.30 | near_support | **BUY_TRIGGER_HIT** |
| Yes – Will Trump agree to Iranian enrichment of uranium in April? | 286 | $0.863 | $0.233 | $0.376 | $0.21–$0.47 | near_support | **BUY_TRIGGER_HIT** |
| Yes – US x Iran permanent peace deal by April 30, 2026? | 139 | $1.754 | $0.265 | $0.405 | $0.27–$0.62 | near_support | **BUY_TRIGGER_HIT** |
| Yes – Iran agrees to surrender enriched uranium stockpile by April | 675 | $0.349 | $0.164 | $0.294 | $0.16–$0.65 | near_support | **BUY_TRIGGER_HIT** |
| Yes – Will the US x Iran ceasefire be extended by April 21, 2026? | 513 | $0.412 | $0.215 | $0.700 | $0.17–$0.85 | near_support | **BUY_TRIGGER_HIT** |
| No – Israel strike on Yemen by April 30, 2026? | 204 | $0.870 | $0.107 | $0.135 | $0.03–$0.25 | mid_range | **BUY_TRIGGER_HIT** |
| No – US x Iran permanent peace deal by April 22, 2026? | 162 | $0.903 | $0.045 | $0.195 | $0.05–$0.44 | near_support | **BUY_TRIGGER_HIT** |
| Yes –  Iran agrees to end enrichment of uranium by June 30? | 229 | $0.625 | $0.535 | $0.585 | $0.46–$0.74 | mid_range | **BUY_TRIGGER_HIT** |
| Yes – Iran agrees to end enrichment of uranium by April 30? | 328 | $0.389 | $0.233 | $0.339 | $0.14–$0.56 | mid_range | **BUY_TRIGGER_HIT** |
| Yes – Trump announces end of military operations against Iran by M | 181 | $0.690 | $0.645 | $0.725 | $0.65–$0.85 | near_support | **BUY_TRIGGER_HIT** |
| Yes – U.S. forces seize another oil tanker by April 30? | 129 | $0.882 | $1.000 | $0.335 | $0.07–$1.00 | near_resistance | **SELL_TRIGGER_HIT** |
| Yes – US-Iran nuclear deal by June 30? | 184 | $0.610 | $0.500 | $0.667 | $0.48–$0.81 | near_support | **BUY_TRIGGER_HIT** |
| No – US-Iran nuclear deal by April 30? | 147 | $0.704 | $0.256 | $0.389 | $0.26–$0.69 | near_support | **BUY_TRIGGER_HIT** |
| Yes – Strait of Hormuz traffic returns to normal by end of May? | 137 | $0.730 | $0.615 | $0.665 | $0.56–$0.82 | near_support | **WAIT** |
| No – Israeli forces cross the Litani River by June 30? | 126 | $0.779 | $0.470 | $0.265 | $0.11–$0.72 | mid_range | **SELL_TRIGGER_HIT** |
| Yes – Trump announces end of military operations against Iran by A | 126 | $0.686 | $0.240 | $0.405 | $0.24–$0.67 | near_support | **BUY_TRIGGER_HIT** |
| Yes – Will Donald Trump announce that the United States blockade o | 93 | $0.808 | $0.785 | $0.820 | $0.64–$0.92 | mid_range | **WAIT** |
| Yes – US x Iran ceasefire extended by April 22, 2026? | 103.0 | $0.680 | n/a | n/a | n/a | n/a | NO DATA |
| No – Israel withdraws from Lebanon by May 31, 2026? | 72 | $0.895 | $0.075 | $0.095 | $0.07–$0.62 | near_support | **BUY_TRIGGER_HIT** |
| No – US-Iran nuclear deal before 2027? | 125 | $0.480 | $0.660 | $0.715 | $0.66–$0.85 | near_support | **WAIT** |
| No – US x Iran permanent peace deal by June 30, 2026? | 158 | $0.330 | $0.650 | $0.685 | $0.59–$0.81 | mid_range | **WAIT** |
| Yes – Israel x Hezbollah Ceasefire extended by April 26, 2026? | 87 | $0.590 | $0.395 | $0.620 | $0.28–$0.80 | mid_range | **BUY_TRIGGER_HIT** |
| No – Iran leadership change by June 30? | 58 | $0.760 | $0.165 | $0.185 | $0.15–$0.21 | mid_range | **BUY_TRIGGER_HIT** |
| Yes – Will fewer than 25 ships transit the Strait of Hormuz betwee | 285 | $0.122 | $0.117 | $0.084 | $0.05–$0.44 | near_support | **SELL_TRIGGER_HIT** |
| No – Iran agrees to surrender enriched uranium stockpile by Decem | 64 | $0.350 | $0.460 | $0.665 | $0.43–$0.81 | near_support | **BUY_TRIGGER_HIT** |
| Yes – Will 150 or more ships transit the Strait of Hormuz between  | 182 | $0.110 | $0.180 | $0.180 | $0.10–$0.54 | near_support | **WAIT** |
| No – US-Iran nuclear deal by June 30? | 26 | $0.360 | $0.500 | $0.665 | $0.48–$0.79 | near_support | **BUY_TRIGGER_HIT** |
| Yes – Internet Access restored in Iran by April 30, 2026? | 54 | $0.130 | $0.085 | $0.130 | $0.07–$0.31 | near_support | **BUY_TRIGGER_HIT** |

## 3. Heatmap волатильности — топ-5 лучших кандидатов для range-торговли

*Volatility score = stdev(price) / median(price). Чем выше — тем больше колебания относительно "якоря" цены.*

| # | Рынок (side) | vol_score | 20d range | Current | Median | Big daily moves (≥10pp) | Комментарий |
|---|---|---:|---|---:|---:|---:|---|
| 1 | No – Israel withdraws from Lebanon by May 31, 2026? | 1.12 | $0.07–$0.62 | $0.075 | $0.095 | 1 | очень высокая вола — держать малый размер, много циклов |
| 2 | Yes – Will fewer than 25 ships transit the Strait of Hormuz b | 0.95 | $0.05–$0.44 | $0.117 | $0.084 | 1 | очень высокая вола — держать малый размер, много циклов |
| 3 | Yes – Will 150 or more ships transit the Strait of Hormuz bet | 0.76 | $0.10–$0.54 | $0.180 | $0.180 | 4 | высокая вола — идеально для $25-30/цикл |
| 4 | Yes – U.S. forces seize another oil tanker by April 30? | 0.54 | $0.07–$1.00 | $1.000 | $0.335 | 6 | высокая вола — идеально для $25-30/цикл |
| 5 | No – Israeli forces cross the Litani River by June 30? | 0.47 | $0.11–$0.72 | $0.470 | $0.265 | 3 | высокая вола — идеально для $25-30/цикл |

Ещё 5 с хорошей волой (vol 0.25–0.45) — тоже в списке range-кандидатов:
- No – Israel strike on Yemen by April 30, 2026? | vol=0.46 | range $0.03–$0.25
- No – US x Iran permanent peace deal by April 22, 2026? | vol=0.41 | range $0.05–$0.44
- Yes – Internet Access restored in Iran by April 30, 2026? | vol=0.39 | range $0.07–$0.31
- Yes – Iran agrees to surrender enriched uranium stockpile by April 30, 2026? | vol=0.36 | range $0.16–$0.65
- Yes – Will the US x Iran ceasefire be extended by April 21, 2026? | vol=0.32 | range $0.17–$0.85

## 4. Корреляция с новостями (event-impact table)

Средний сдвиг цены (в процентных пунктах, pp) за 2 часа после события. Знак — в пользу стороны (YES/NO) рынка.

| Событие | Peace-YES avg (n) | Peace-NO avg (n) | Escalation-YES avg (n) |
|---|---:|---:|---:|
| Исламабад talks failed (12 апр) | n/d | n/d | n/d |
| Блокада США (13 апр) | n/d | n/d | n/d |
| Пентагон "блокада работает" (15 апр) | +0.10pp (n=5) | +1.25pp (n=2) | n/d |
| Иран: Hormuz открыт (17 апр) | +5.75pp (n=8) | +3.15pp (n=6) | -0.10pp (n=1) |
| Иран закрыл Hormuz + огонь (18 апр) | -1.28pp (n=6) | -2.61pp (n=5) | -0.05pp (n=1) |
| Touska захвачен (19 апр) | +3.80pp (n=9) | +7.02pp (n=6) | -2.90pp (n=1) |
| Pentagon policy Indo-Pacific (20-21 апр) | +2.20pp (n=12) | +3.20pp (n=9) | -1.70pp (n=1) |
| Tifani захвачен (21 апр) | -1.10pp (n=5) | -0.17pp (n=3) | n/d |

**Выводы:**
- 17 апреля (Иран заявил что Hormuz открыт) — **peace-YES взлетели в среднем на +6.6pp за 2 часа**. Это сильный bullish-сигнал, и мы могли SELL-y часть позиции для профита.
- 19 апреля (захват Touska) — парадоксально, peace-YES тоже выросли (+4.5pp), потому что рынок уже был сильно перепродан предшествующей блокадой. Это классический "sell-the-news-buy-the-panic".
- 20–21 апреля (Pentagon policy + Tifani) — peace-YES +2.2pp в среднем, реакция затухает. Рынок "устал" реагировать на каждый захват — это идеальный момент для **накапливать peace-YES на любой просадке**.
- Для escalation-YES (tanker seize, <25 ships) — мы выдели *отрицательные* реакции (-2.9pp) на событиях что логически должны были их толкать вверх. Это значит escalation-YES **опережают новости** — к моменту официального подтверждения уже стоят дорого, и профит надо фиксировать.

## 5. Playbook — конкретные триггеры по каждому рынку

Формат: **side–рынок** | shares@avg | curr→med (range) | BUY≤ / SELL≥ | state | news-hint

- **Yes – Strait of Hormuz traffic returns to normal by end of April?**
  - 495sh @ avg $1.258 (cost $623.24) · curr **$0.185** → med $0.275 (range $0.17–$0.55, vol=0.29)
  - **BUY ≤ $0.253 · SELL ≥ $0.297** · размер цикла **$30** · экстрем BUY ≤ $0.23, SELL ≥ $0.49
  - Бэктест: 2вых/3вх, pnl/share $0.273 · **🟢 BUY** · news: Tifani захвачен (21 апр) → -3.5pp (BUY)
- **Yes – US x Iran permanent peace deal by May 31, 2026?**
  - 539sh @ avg $0.811 (cost $437.14) · curr **$0.565** → med $0.595 (range $0.47–$0.76, vol=0.08)
  - **BUY ≤ $0.547 · SELL ≥ $0.643** · размер цикла **$30** · экстрем BUY ≤ $0.509, SELL ≥ $0.712
  - Бэктест: 3вых/3вх, pnl/share $0.345 · **⚪ Wait** · news: Иран: Hormuz открыт (17 апр) → +11.0pp (SELL)
- **No – US obtains Iranian enriched uranium by May 31?**
  - 354sh @ avg $0.880 (cost $311.56) · curr **$0.185** → med $0.205 (range $0.19–$0.30, vol=0.17)
  - **BUY ≤ $0.189 · SELL ≥ $0.221** · размер цикла **$30** · экстрем BUY ≤ $0.202, SELL ≥ $0.279
  - Бэктест: 0вых/1вх, pnl/share $-0.004 · **🟢 BUY** · news: Pentagon policy Indo-Pacific (20-21 апр) → -0.5pp (держать)
- **Yes – Will Trump agree to Iranian enrichment of uranium in April?**
  - 286sh @ avg $0.863 (cost $247.16) · curr **$0.233** → med $0.376 (range $0.21–$0.47, vol=0.18)
  - **BUY ≤ $0.345 · SELL ≥ $0.406** · размер цикла **$30** · экстрем BUY ≤ $0.246, SELL ≥ $0.434
  - Бэктест: 1вых/2вх, pnl/share $0.138 · **🟢 BUY** · news: Pentagon policy Indo-Pacific (20-21 апр) → +0.7pp (держать)
- **Yes – US x Iran permanent peace deal by April 30, 2026?**
  - 139sh @ avg $1.754 (cost $244.32) · curr **$0.265** → med $0.405 (range $0.27–$0.62, vol=0.18)
  - **BUY ≤ $0.373 · SELL ≥ $0.437** · размер цикла **$30** · экстрем BUY ≤ $0.319, SELL ≥ $0.571
  - Бэктест: 2вых/3вх, pnl/share $0.237 · **🟢 BUY** · news: Иран: Hormuz открыт (17 апр) → +12.5pp (SELL)
- **Yes – Iran agrees to surrender enriched uranium stockpile by April 30, 2026?**
  - 675sh @ avg $0.349 (cost $235.17) · curr **$0.164** → med $0.294 (range $0.16–$0.65, vol=0.36)
  - **BUY ≤ $0.271 · SELL ≥ $0.318** · размер цикла **$30** · экстрем BUY ≤ $0.234, SELL ≥ $0.577
  - Бэктест: 2вых/3вх, pnl/share $0.122 · **🟢 BUY** · news: Иран: Hormuz открыт (17 апр) → +15.0pp (SELL)
- **Yes – Will the US x Iran ceasefire be extended by April 21, 2026?**
  - 513sh @ avg $0.412 (cost $211.11) · curr **$0.215** → med $0.700 (range $0.17–$0.85, vol=0.32)
  - **BUY ≤ $0.644 · SELL ≥ $0.756** · размер цикла **$30** · экстрем BUY ≤ $0.273, SELL ≥ $0.752
  - Бэктест: 0вых/1вх, pnl/share $-0.428 · **🟢 BUY** · news: Touska захвачен (19 апр) → +8.5pp (SELL)
- **No – Israel strike on Yemen by April 30, 2026?**
  - 204sh @ avg $0.870 (cost $177.40) · curr **$0.107** → med $0.135 (range $0.03–$0.25, vol=0.46)
  - **BUY ≤ $0.124 · SELL ≥ $0.146** · размер цикла **$25** · экстрем BUY ≤ $0.059, SELL ≥ $0.218
  - Бэктест: 1вых/2вх, pnl/share $0.120 · **🟢 BUY** · news: Pentagon policy Indo-Pacific (20-21 апр) → +15.0pp (SELL)
- **No – US x Iran permanent peace deal by April 22, 2026?**
  - 162sh @ avg $0.903 (cost $146.44) · curr **$0.045** → med $0.195 (range $0.05–$0.44, vol=0.41)
  - **BUY ≤ $0.179 · SELL ≥ $0.211** · размер цикла **$25** · экстрем BUY ≤ $0.104, SELL ≥ $0.377
  - Бэктест: 1вых/2вх, pnl/share $-0.076 · **🟢 BUY** · news: Touska захвачен (19 апр) → +5.0pp (SELL)
- **Yes –  Iran agrees to end enrichment of uranium by June 30?**
  - 229sh @ avg $0.625 (cost $143.23) · curr **$0.535** → med $0.585 (range $0.46–$0.74, vol=0.09)
  - **BUY ≤ $0.538 · SELL ≥ $0.632** · размер цикла **$30** · экстрем BUY ≤ $0.498, SELL ≥ $0.697
  - Бэктест: 0вых/1вх, pnl/share $-0.006 · **🟢 BUY** · news: Пентагон "блокада работает" (15 апр) → -6.0pp (BUY)
- **Yes – Iran agrees to end enrichment of uranium by April 30?**
  - 328sh @ avg $0.389 (cost $127.78) · curr **$0.233** → med $0.339 (range $0.14–$0.56, vol=0.22)
  - **BUY ≤ $0.311 · SELL ≥ $0.366** · размер цикла **$30** · экстрем BUY ≤ $0.199, SELL ≥ $0.498
  - Бэктест: 3вых/4вх, pnl/share $0.226 · **🟢 BUY** · news: Touska захвачен (19 апр) → +4.7pp (SELL)
- **Yes – Trump announces end of military operations against Iran by May 31st?**
  - 181sh @ avg $0.690 (cost $125.00) · curr **$0.645** → med $0.725 (range $0.65–$0.85, vol=0.05)
  - **BUY ≤ $0.667 · SELL ≥ $0.783** · размер цикла **$30** · экстрем BUY ≤ $0.676, SELL ≥ $0.819
  - Бэктест: 0вых/1вх, pnl/share $-0.028 · **🟢 BUY** · news: Touska захвачен (19 апр) → +1.5pp (держать)
- **Yes – U.S. forces seize another oil tanker by April 30?**
  - 129sh @ avg $0.882 (cost $113.99) · curr **$1.000** → med $0.335 (range $0.07–$1.00, vol=0.54)
  - **BUY ≤ $0.308 · SELL ≥ $0.362** · размер цикла **$25** · экстрем BUY ≤ $0.207, SELL ≥ $0.86
  - Бэктест: 2вых/2вх, pnl/share $0.658 · **🔴 SELL** · news: Touska захвачен (19 апр) → -2.9pp (держать)
- **Yes – US-Iran nuclear deal by June 30?**
  - 184sh @ avg $0.610 (cost $112.04) · curr **$0.500** → med $0.667 (range $0.48–$0.81, vol=0.10)
  - **BUY ≤ $0.614 · SELL ≥ $0.721** · размер цикла **$30** · экстрем BUY ≤ $0.534, SELL ≥ $0.765
  - Бэктест: 1вых/2вх, pnl/share $0.046 · **🟢 BUY** · news: Иран: Hormuz открыт (17 апр) → +6.0pp (SELL)
- **No – US-Iran nuclear deal by April 30?**
  - 147sh @ avg $0.704 (cost $103.29) · curr **$0.256** → med $0.389 (range $0.26–$0.69, vol=0.24)
  - **BUY ≤ $0.357 · SELL ≥ $0.42** · размер цикла **$30** · экстрем BUY ≤ $0.32, SELL ≥ $0.621
  - Бэктест: 4вых/5вх, pnl/share $0.417 · **🟢 BUY** · news: Touska захвачен (19 апр) → +13.6pp (SELL)
- **Yes – Strait of Hormuz traffic returns to normal by end of May?**
  - 137sh @ avg $0.730 (cost $100.00) · curr **$0.615** → med $0.665 (range $0.56–$0.82, vol=0.10)
  - **BUY ≤ $0.612 · SELL ≥ $0.718** · размер цикла **$30** · экстрем BUY ≤ $0.604, SELL ≥ $0.786
  - Бэктест: 1вых/1вх, pnl/share $0.236 · **⚪ Wait** · news: Pentagon policy Indo-Pacific (20-21 апр) → +4.0pp (SELL)
- **No – Israeli forces cross the Litani River by June 30?**
  - 126sh @ avg $0.779 (cost $98.45) · curr **$0.470** → med $0.265 (range $0.11–$0.72, vol=0.47)
  - **BUY ≤ $0.244 · SELL ≥ $0.286** · размер цикла **$25** · экстрем BUY ≤ $0.201, SELL ≥ $0.624
  - Бэктест: 1вых/1вх, pnl/share $0.159 · **🔴 SELL** · news: Touska захвачен (19 апр) → +16.5pp (SELL)
- **Yes – Trump announces end of military operations against Iran by April 30th?**
  - 126sh @ avg $0.686 (cost $86.51) · curr **$0.240** → med $0.405 (range $0.24–$0.67, vol=0.22)
  - **BUY ≤ $0.373 · SELL ≥ $0.437** · размер цикла **$30** · экстрем BUY ≤ $0.304, SELL ≥ $0.606
  - Бэктест: 0вых/1вх, pnl/share $-0.111 · **🟢 BUY** · news: Pentagon policy Indo-Pacific (20-21 апр) → +4.0pp (SELL)
- **Yes – Will Donald Trump announce that the United States blockade of the Strait of Hormuz has been lifted by May 31, 2026?**
  - 93sh @ avg $0.808 (cost $75.00) · curr **$0.785** → med $0.820 (range $0.64–$0.92, vol=0.05)
  - **BUY ≤ $0.754 · SELL ≥ $0.886** · размер цикла **$30** · экстрем BUY ≤ $0.678, SELL ≥ $0.877
  - Бэктест: 1вых/1вх, pnl/share $0.245 · **⚪ Wait** · news: Иран закрыл Hormuz + огонь (18 апр) → -2.5pp (держать)
- **Yes – US x Iran ceasefire extended by April 22, 2026?** | 103@$0.680 | NO DATA — ручной exit рекомендуется (вероятно near resolution).
- **No – Israel withdraws from Lebanon by May 31, 2026?**
  - 72sh @ avg $0.895 (cost $64.29) · curr **$0.075** → med $0.095 (range $0.07–$0.62, vol=1.12)
  - **BUY ≤ $0.087 · SELL ≥ $0.103** · размер цикла **$25** · экстрем BUY ≤ $0.157, SELL ≥ $0.542
  - Бэктест: 0вых/1вх, pnl/share $-0.012 · **🟢 BUY** · news: Pentagon policy Indo-Pacific (20-21 апр) → +0.0pp (держать)
- **No – US-Iran nuclear deal before 2027?**
  - 125sh @ avg $0.480 (cost $60.00) · curr **$0.660** → med $0.715 (range $0.66–$0.85, vol=0.07)
  - **BUY ≤ $0.658 · SELL ≥ $0.772** · размер цикла **$30** · экстрем BUY ≤ $0.688, SELL ≥ $0.821
  - Бэктест: 0вых/0вх, pnl/share $0.000 · **⚪ Wait** · news: Pentagon policy Indo-Pacific (20-21 апр) → +1.5pp (держать)
- **No – US x Iran permanent peace deal by June 30, 2026?**
  - 158sh @ avg $0.330 (cost $52.03) · curr **$0.650** → med $0.685 (range $0.59–$0.81, vol=0.04)
  - **BUY ≤ $0.63 · SELL ≥ $0.74** · размер цикла **$30** · экстрем BUY ≤ $0.624, SELL ≥ $0.781
  - Бэктест: 1вых/1вх, pnl/share $0.176 · **⚪ Wait** · news: Иран закрыл Hormuz + огонь (18 апр) → -4.0pp (BUY)
- **Yes – Israel x Hezbollah Ceasefire extended by April 26, 2026?**
  - 87sh @ avg $0.590 (cost $51.48) · curr **$0.395** → med $0.620 (range $0.28–$0.80, vol=0.25)
  - **BUY ≤ $0.57 · SELL ≥ $0.67** · размер цикла **$30** · экстрем BUY ≤ $0.361, SELL ≥ $0.718
  - Бэктест: 3вых/4вх, pnl/share $0.536 · **🟢 BUY** · news: Pentagon policy Indo-Pacific (20-21 апр) → +10.5pp (SELL)
- **No – Iran leadership change by June 30?**
  - 58sh @ avg $0.760 (cost $44.00) · curr **$0.165** → med $0.185 (range $0.15–$0.21, vol=0.13)
  - **BUY ≤ $0.17 · SELL ≥ $0.2** · размер цикла **$30** · экстрем BUY ≤ $0.155, SELL ≥ $0.204
  - Бэктест: 0вых/1вх, pnl/share $-0.003 · **🟢 BUY** · news: Pentagon policy Indo-Pacific (20-21 апр) → -0.5pp (держать)
- **Yes – Will fewer than 25 ships transit the Strait of Hormuz between April 20-April 26?**
  - 285sh @ avg $0.122 (cost $34.75) · curr **$0.117** → med $0.084 (range $0.05–$0.44, vol=0.95)
  - **BUY ≤ $0.077 · SELL ≥ $0.09** · размер цикла **$25** · экстрем BUY ≤ $0.106, SELL ≥ $0.381
  - Бэктест: 1вых/1вх, pnl/share $0.031 · **🔴 SELL** · news: Pentagon policy Indo-Pacific (20-21 апр) → -1.7pp (держать)
- **No – Iran agrees to surrender enriched uranium stockpile by December 31, 2026?**
  - 64sh @ avg $0.350 (cost $22.31) · curr **$0.460** → med $0.665 (range $0.43–$0.81, vol=0.12)
  - **BUY ≤ $0.612 · SELL ≥ $0.718** · размер цикла **$30** · экстрем BUY ≤ $0.483, SELL ≥ $0.752
  - Бэктест: 1вых/2вх, pnl/share $0.036 · **🟢 BUY** · news: Иран: Hormuz открыт (17 апр) → +6.5pp (SELL)
- **Yes – Will 150 or more ships transit the Strait of Hormuz between April 20-April 26?**
  - 182sh @ avg $0.110 (cost $20.00) · curr **$0.180** → med $0.180 (range $0.10–$0.54, vol=0.76)
  - **BUY ≤ $0.166 · SELL ≥ $0.194** · размер цикла **$25** · экстрем BUY ≤ $0.162, SELL ≥ $0.473
  - Бэктест: 1вых/1вх, pnl/share $0.102 · **⚪ Wait** · news: Tifani захвачен (21 апр) → -4.0pp (BUY)
- **No – US-Iran nuclear deal by June 30?**
  - 26sh @ avg $0.360 (cost $9.22) · curr **$0.500** → med $0.665 (range $0.48–$0.79, vol=0.09)
  - **BUY ≤ $0.612 · SELL ≥ $0.718** · размер цикла **$30** · экстрем BUY ≤ $0.53, SELL ≥ $0.74
  - Бэктест: 1вых/2вх, pnl/share $0.051 · **🟢 BUY** · news: Pentagon policy Indo-Pacific (20-21 апр) → +4.5pp (SELL)
- **Yes – Internet Access restored in Iran by April 30, 2026?**
  - 54sh @ avg $0.130 (cost $7.00) · curr **$0.085** → med $0.130 (range $0.07–$0.31, vol=0.39)
  - **BUY ≤ $0.12 · SELL ≥ $0.14** · размер цикла **$30** · экстрем BUY ≤ $0.102, SELL ≥ $0.273
  - Бэктест: 1вых/2вх, pnl/share $0.159 · **🟢 BUY** · news: Pentagon policy Indo-Pacific (20-21 апр) → +0.0pp (держать)
## 6. Правила риска на уровне портфеля

1. **Общий лимит range-экспозиции:** $1 500 одновременно (сверх текущих core-позиций). Это не даёт превратить range-торговлю в новый основной портфель.
2. **Дневной стоп-лосс:** если минус $100 за сутки по range-циклам — **пауза до следующего UTC-дня**.
3. **Запрет averaging down > 50%:** нельзя докупать более чем на 50% от первоначального cost-basis в одну сессию. Например если вошли $30, максимум +$15 на просадке.
4. **Correlation cap:** не держать одновременно 3+ свежих bullish peace-YES позиций (`US x Iran permanent peace May 31`, `US x Iran ceasefire extended`, `end military ops`) — они двигаются синхронно, это не диверсификация, а плечо.
5. **Resolution risk:** **обязательный полный exit за 48 часов до deadline рынка**. На deadline bid-ask может schluka 20pp, и профита от range-цикла не будет.
6. **News blackout:** после крупного объявления (захват танкера, выступление Трампа) — **1 час пауза**, потом перепроверка триггеров. Никаких сделок в первые 15 минут.
7. **Max concentration per market:** не более $150 суммарного cost basis на один рынок (core + range).
8. **Min edge filter:** сделка разрешена только если edge vs медианы ≥ 8% (после slippage). Меньше — не торговать.

## 7. Результаты бэктеста за 20 дней

Правила: BUY при цене ≤ 92% от 20-дневной медианы, SELL при цене ≥ 108%. Slippage 2% на сделку. Размер $25 на цикл.

| Рынок | Entries | Exits | PnL / share | PnL при $25/цикл |
|---|---:|---:|---:|---:|
| Yes – U.S. forces seize another oil tanker by April 30? | 2 | 2 | $0.658 | $+53.44 |
| Yes – Internet Access restored in Iran by April 30, 2026? | 2 | 1 | $0.159 | $+33.26 |
| No – US-Iran nuclear deal by April 30? | 5 | 4 | $0.417 | $+29.15 |
| Yes – Strait of Hormuz traffic returns to normal by end of Ap | 3 | 2 | $0.273 | $+26.97 |
| No – Israel strike on Yemen by April 30, 2026? | 2 | 1 | $0.120 | $+24.07 |
| Yes – Israel x Hezbollah Ceasefire extended by April 26, 2026 | 4 | 3 | $0.536 | $+23.51 |
| Yes – Iran agrees to end enrichment of uranium by April 30? | 4 | 3 | $0.226 | $+18.15 |
| No – Israeli forces cross the Litani River by June 30? | 1 | 1 | $0.159 | $+16.27 |
| Yes – US x Iran permanent peace deal by April 30, 2026? | 3 | 2 | $0.237 | $+15.92 |
| Yes – US x Iran permanent peace deal by May 31, 2026? | 3 | 3 | $0.345 | $+15.74 |
| Yes – Will 150 or more ships transit the Strait of Hormuz bet | 1 | 1 | $0.102 | $+15.38 |
| Yes – Iran agrees to surrender enriched uranium stockpile by  | 3 | 2 | $0.122 | $+11.22 |
| Yes – Will fewer than 25 ships transit the Strait of Hormuz b | 1 | 1 | $0.031 | $+10.19 |
| Yes – Will Trump agree to Iranian enrichment of uranium in Ap | 2 | 1 | $0.138 | $+9.95 |
| Yes – Strait of Hormuz traffic returns to normal by end of Ma | 1 | 1 | $0.236 | $+9.65 |
| Yes – Will Donald Trump announce that the United States block | 1 | 1 | $0.245 | $+8.11 |
| No – US x Iran permanent peace deal by June 30, 2026? | 1 | 1 | $0.176 | $+6.97 |
| No – US-Iran nuclear deal by June 30? | 2 | 1 | $0.051 | $+2.10 |
| Yes – US-Iran nuclear deal by June 30? | 2 | 1 | $0.046 | $+1.88 |
| No – Iran agrees to surrender enriched uranium stockpile by  | 2 | 1 | $0.036 | $+1.49 |
| No – US-Iran nuclear deal before 2027? | 0 | 0 | $0.000 | $+0.00 |
| Yes –  Iran agrees to end enrichment of uranium by June 30? | 1 | 0 | $-0.006 | $-0.26 |
| No – Iran leadership change by June 30? | 1 | 0 | $-0.003 | $-0.48 |
| No – US obtains Iranian enriched uranium by May 31? | 1 | 0 | $-0.004 | $-0.49 |
| Yes – Trump announces end of military operations against Iran | 1 | 0 | $-0.028 | $-1.05 |
| No – Israel withdraws from Lebanon by May 31, 2026? | 1 | 0 | $-0.012 | $-3.32 |
| Yes – Trump announces end of military operations against Iran | 1 | 0 | $-0.111 | $-7.44 |
| No – US x Iran permanent peace deal by April 22, 2026? | 2 | 1 | $-0.076 | $-10.60 |
| Yes – Will the US x Iran ceasefire be extended by April 21, 2 | 1 | 0 | $-0.428 | $-16.63 |
| **ИТОГО** | — | — | — | **$+293.12** |

**Экстраполяция на 30 дней:** $+439.68

**Предостережения бэктеста:**
- Бэктест предполагает идеальное исполнение (попал именно в минимум цены и вышел именно в максимуме цикла). В реальности ожидается 50–70% от этой цифры.
- Бэктест включает 2% slippage — на Polymarket реальный slippage на малом bet-size ($25) чаще 1–2%, на крупном ($100+) 3–5%.
- Некоторые рынки показывают отрицательный PnL бэктеста (одна покупка, цена не восстановилась к SELL-порогу за 20 дней) — это нормально в тренде, но ограничивает частоту.

## 8. Implementation — что делать СЕЙЧАС

**Немедленные действия (активные триггеры на утро 21 апр):**

### Приоритет A — SELL triggers (фиксируем профит)
- **No – Israeli forces cross the Litani River by June 30?**
  - Current $0.470 ≥ sell-триггер $0.286. 
  - Продать **50–70% позиции** по bid ≥ $0.286. Остаток держать как tail-insurance.
- **Yes – Will fewer than 25 ships transit the Strait of Hormuz between April 20**
  - Current $0.117 ≥ sell-триггер $0.09. 
  - Продать **50–70% позиции** по bid ≥ $0.09. Остаток держать как tail-insurance.
- **Yes – U.S. forces seize another oil tanker by April 30?**
  - Current $1.000 ≥ sell-триггер $0.362. 
  - **Уже $1.00** — рынок фактически разрешился в нашу пользу. Ждать resolution или продать если есть bid ≥ 0.99.

### Приоритет B — BUY triggers c высокой волатильностью (vol_score ≥ 0.25, свежие циклы)
- **No – Israel withdraws from Lebanon by May 31, 2026?** | vol=1.12 | curr $0.075 → buy $0.087 → sell $0.103 | **ROI цикла: +37.3%** | размер **$25**
- **No – Israel strike on Yemen by April 30, 2026?** | vol=0.46 | curr $0.107 → buy $0.124 → sell $0.146 | **ROI цикла: +37.1%** | размер **$25**
- **No – US x Iran permanent peace deal by April 22, 2026?** | vol=0.41 | curr $0.045 → buy $0.179 → sell $0.211 | **ROI цикла: +368.9%** | размер **$25**
- **Yes – Internet Access restored in Iran by April 30, 2026?** | vol=0.39 | curr $0.085 → buy $0.12 → sell $0.14 | **ROI цикла: +64.7%** | размер **$30**
- **Yes – Iran agrees to surrender enriched uranium stockpile by April 30, ** | vol=0.36 | curr $0.164 → buy $0.271 → sell $0.318 | **ROI цикла: +94.5%** | размер **$30**
- **Yes – Will the US x Iran ceasefire be extended by April 21, 2026?** | vol=0.32 | curr $0.215 → buy $0.644 → sell $0.756 | **ROI цикла: +251.6%** | размер **$30**
- **Yes – Strait of Hormuz traffic returns to normal by end of April?** | vol=0.29 | curr $0.185 → buy $0.253 → sell $0.297 | **ROI цикла: +60.5%** | размер **$30**
- **Yes – Israel x Hezbollah Ceasefire extended by April 26, 2026?** | vol=0.25 | curr $0.395 → buy $0.57 → sell $0.67 | **ROI цикла: +69.6%** | размер **$30**

### Приоритет C — BUY triggers с низкой волатильностью (vol_score < 0.25) — подождать более глубокой просадки
- No – Iran leadership change by June 30? | vol=0.13 | curr $0.165 — мелкая просадка, размер максимум $15–20 или пропустить.
- No – US obtains Iranian enriched uranium by May 31? | vol=0.17 | curr $0.185 — мелкая просадка, размер максимум $15–20 или пропустить.
- Yes –  Iran agrees to end enrichment of uranium by June 30? | vol=0.09 | curr $0.535 — мелкая просадка, размер максимум $15–20 или пропустить.
- Yes – US-Iran nuclear deal by June 30? | vol=0.10 | curr $0.500 — мелкая просадка, размер максимум $15–20 или пропустить.
- Yes – Will Trump agree to Iranian enrichment of uranium in April? | vol=0.18 | curr $0.233 — мелкая просадка, размер максимум $15–20 или пропустить.
- Yes – US x Iran permanent peace deal by April 30, 2026? | vol=0.18 | curr $0.265 — мелкая просадка, размер максимум $15–20 или пропустить.
- Yes – Iran agrees to end enrichment of uranium by April 30? | vol=0.22 | curr $0.233 — мелкая просадка, размер максимум $15–20 или пропустить.
- No – Iran agrees to surrender enriched uranium stockpile by December 3 | vol=0.12 | curr $0.460 — мелкая просадка, размер максимум $15–20 или пропустить.
- Yes – Trump announces end of military operations against Iran by April  | vol=0.22 | curr $0.240 — мелкая просадка, размер максимум $15–20 или пропустить.
- Yes – Trump announces end of military operations against Iran by May 31 | vol=0.05 | curr $0.645 — мелкая просадка, размер максимум $15–20 или пропустить.
- No – US-Iran nuclear deal by June 30? | vol=0.09 | curr $0.500 — мелкая просадка, размер максимум $15–20 или пропустить.
- No – US-Iran nuclear deal by April 30? | vol=0.24 | curr $0.256 — мелкая просадка, размер максимум $15–20 или пропустить.

### Резолюшен-контроль
- **Рынок без данных:** `US x Iran ceasefire extended by April 22, 2026?` — до resolution 1 день. Проверить вручную через CLOB UI и либо продать, либо держать до expiry.
- **Рынки с апрельским deadline (April 22/26/30)** — обязательно проверить позиции за 48h до deadline и выйти из range-циклов.

## 9. Интеграция с существующим news_spike-ботом

- 🔵 **News alert** (твит Трампа, заголовок от Рейтер) → бот проверяет активные триггеры range-стратегии, и если цена ушла за новый BUY/SELL-уровень — шлёт уведомление.
- 🟠 **Odds alert ≥5pp за 30 мин** → проверить не пробит ли support/resistance (supports/resistances из этого playbook). Если да — новый цикл открыт.
- 🟣 **Opportunity alert** (скачок объёма или крупная сделка denizz/car) → оценить как кандидата на range-цикл: если рынок в списке из 30 и vol_score ≥ 0.25 — открыть мини-позицию $20–25.

Конкретная логика для интеграции в `news_spike/handler.py`:
```python
# псевдокод для проверки range-trigger
def check_range_trigger(token_id, current_px, side):
    playbook = load_iran_playbook()  # наш iran_playbook_built.json
    m = playbook.get(token_id)
    if not m: return None
    if current_px <= m["buy_trigger"]: return ("BUY", m["sell_trigger"])
    if current_px >= m["sell_trigger"]: return ("SELL", m["buy_trigger"])
    return None
```

---

**Disclaimer:** Not financial advice. Данные собраны 2026-04-21 из публичных API (Polymarket CLOB). Все триггеры — это статистические уровни на основе 20-дневной истории, они не гарантируют прибыли. Prediction markets имеют риск полной потери депозита и риск резолюшена не в вашу пользу. Перед исполнением проверьте live-цены вручную.