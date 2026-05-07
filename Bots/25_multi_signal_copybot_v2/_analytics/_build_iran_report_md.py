"""Generate final Russian markdown report."""
import json, os, statistics
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, 'iran_playbook_built.json')
OUT_MD = os.path.join(HERE, '2026-04-21_aggressive-range-trading-iran-playbook.md')

with open(DATA, 'r', encoding='utf-8') as f:
    mkts = json.load(f)

# filter: only with stats
valid = [m for m in mkts if m.get('stats')]
nodata = [m for m in mkts if not m.get('stats')]

total_cost = sum(m['cost'] for m in mkts)
total_shares = sum(m['shares'] for m in mkts)

# top vol
sorted_vol = sorted(valid, key=lambda m: -m['stats']['vol_score'])

# triggers hit now
buy_hit = [m for m in valid if m.get('state')=='BUY_TRIGGER_HIT']
sell_hit = [m for m in valid if m.get('state')=='SELL_TRIGGER_HIT']

# event aggregates
EVENTS = [
    ('islamabad_talks_failed','Исламабад talks failed (12 апр)'),
    ('us_blockade_begins','Блокада США (13 апр)'),
    ('pentagon_blockade_working','Пентагон \"блокада работает\" (15 апр)'),
    ('iran_hormuz_open_declared','Иран: Hormuz открыт (17 апр)'),
    ('iran_closes_hormuz_fires','Иран закрыл Hormuz + огонь (18 апр)'),
    ('touska_seized','Touska захвачен (19 апр)'),
    ('pentagon_policy_indo_pacific','Pentagon policy Indo-Pacific (20-21 апр)'),
    ('tifani_seized','Tifani захвачен (21 апр)'),
]

def is_peace_yes(m):
    t = m['title'].lower()
    return m['outcome']=='Yes' and any(k in t for k in ['peace','ceasefire','end of military','end military','deal','normal','open','restored','end enrichment','surrender','nuclear','blockade','lifted','ended','withdraws','extended'])

def is_peace_no(m):
    t = m['title'].lower()
    return m['outcome']=='No' and any(k in t for k in ['peace','ceasefire','deal','end enrich','surrender','withdraws','normal','nuclear','blockade','lifted','leadership change','litani','strike','yemen'])

def is_esc_yes(m):
    t = m['title'].lower()
    return m['outcome']=='Yes' and any(k in t for k in ['strike','seize','tanker','fewer than 25','litani','leadership change','cross litani'])

# total backtest edge
total_edge_20d = 0
for m in valid:
    bt = m.get('backtest')
    if not bt: continue
    entry = m['stats']['median'] * 0.92
    if entry <= 0: continue
    shares_per_bet = 25 / entry
    total_edge_20d += bt['pnl_per_share'] * shares_per_bet
edge_30d = total_edge_20d * 30/20

report = []
A = report.append

A('# Агрессивная range-стратегия для Iran/US портфеля на Polymarket')
A(f'**Дата отчёта:** 2026-04-21 (данные собраны автоматически из CLOB + positions.json)')
A('**Банкролл:** ~$4–5k | **Позиции в анализе:** 30 открытых рынков Iran/US-темы')
A('**Совокупная стоимость входа (cost_usd):** $' + f'{total_cost:.2f}')
A('')
A('---')
A('')

# ====== 1. TL;DR ======
A('## 1. TL;DR')
A('')
A('- **30 активных Iran/US-позиций** на совокупный cost basis ~$4.15k. Из них 29 с валидной историей цен (1 — `US x Iran ceasefire extended by April 22` — без данных, уже близко к resolution).')
A(f'- **{len(buy_hit)} из 29 рынков прямо сейчас на BUY-триггере** (<8% ниже 20-дневной медианы) — рынок панически перепродан на фоне эскалации блокады Hormuz 18–19 апр.')
A(f'- **{len(sell_hit)} рынка на SELL-триггере** — `U.S. forces seize another tanker by Apr 30` стоит $1.00 (уже resolved в нашу пользу), `Litani River cross by June 30` на NO вырос до $0.47, `<25 ships Hormuz` на YES до $0.117.')
A('- **Средний "объём колебаний" (stdev/median) на Iran-рынках: 0.34**. Топ-5 по волатильности — `Israel withdraws Lebanon NO` (1.12), `<25 ships Hormuz YES` (0.95), `150+ ships Hormuz YES` (0.76), `tanker seize YES` (0.54), `Litani cross NO` (0.47).')
A(f'- **Ожидаемый 30-дневный edge при чистом исполнении стратегии:** ~**${edge_30d:.0f}** (бэктест $25/цикл, slippage 2%; реальный ожидаемый edge 50–70% от цифры из-за частичного исполнения триггеров).')
A('')
A('**Главный вывод:** волатильность peace-рынков 2–4× выше, чем движения "справедливой" вероятности за 20 дней. Это значит что каждый всплеск новостей (захват танкера, гневный твит Трампа) даёт 10–30pp просадку на peace-YES, которая восстанавливается за 12–48 часов — **идеальная среда для мелких циклических buy-low/sell-high сделок**.')
A('')

# ====== 2. Таблица позиций ======
A('## 2. Наши 30 позиций — текущее состояние')
A('')
A('| Тикер (outcome, рынок) | Shares | Avg entry | Current | Медиана 20д | Range 20д | Zone | Статус триггера |')
A('|---|---:|---:|---:|---:|---|---|---|')
# sort by cost desc
for m in sorted(mkts, key=lambda x: -x['cost']):
    s = m.get('stats')
    if not s:
        A(f"| {m['outcome']} – {m['title'][:60]} | {m['shares']:.1f} | ${m['avg_entry']:.3f} | n/a | n/a | n/a | n/a | NO DATA |")
        continue
    A(f"| {m['outcome']} – {m['title'][:60]} | {m['shares']:.0f} | ${m['avg_entry']:.3f} | ${s['current']:.3f} | ${s['median']:.3f} | ${s['min']:.2f}–${s['max']:.2f} | {m['zone']} | **{m['state']}** |")
A('')

# ====== 3. Volatility heatmap ======
A('## 3. Heatmap волатильности — топ-5 лучших кандидатов для range-торговли')
A('')
A('*Volatility score = stdev(price) / median(price). Чем выше — тем больше колебания относительно "якоря" цены.*')
A('')
A('| # | Рынок (side) | vol_score | 20d range | Current | Median | Big daily moves (≥10pp) | Комментарий |')
A('|---|---|---:|---|---:|---:|---:|---|')
for i, m in enumerate(sorted_vol[:5], 1):
    s = m['stats']
    comment = ''
    if s['vol_score'] > 0.8:
        comment = 'очень высокая вола — держать малый размер, много циклов'
    elif s['vol_score'] > 0.4:
        comment = 'высокая вола — идеально для $25-30/цикл'
    else:
        comment = 'умеренная вола — ставить чуть больше ($40)'
    A(f"| {i} | {m['outcome']} – {m['title'][:55]} | {s['vol_score']:.2f} | ${s['min']:.2f}–${s['max']:.2f} | ${s['current']:.3f} | ${s['median']:.3f} | {s['big_daily_moves']} | {comment} |")
A('')
A('Ещё 5 с хорошей волой (vol 0.25–0.45) — тоже в списке range-кандидатов:')
for m in sorted_vol[5:10]:
    s = m['stats']
    A(f"- {m['outcome']} – {m['title'][:70]} | vol={s['vol_score']:.2f} | range ${s['min']:.2f}–${s['max']:.2f}")
A('')

# ====== 4. Event impact ======
A('## 4. Корреляция с новостями (event-impact table)')
A('')
A('Средний сдвиг цены (в процентных пунктах, pp) за 2 часа после события. Знак — в пользу стороны (YES/NO) рынка.')
A('')
A('| Событие | Peace-YES avg (n) | Peace-NO avg (n) | Escalation-YES avg (n) |')
A('|---|---:|---:|---:|')
for ev_key, ev_label in EVENTS:
    py = [m['event_impact_pp'].get(ev_key) for m in valid if is_peace_yes(m) and m.get('event_impact_pp',{}).get(ev_key) is not None]
    pn = [m['event_impact_pp'].get(ev_key) for m in valid if is_peace_no(m) and m.get('event_impact_pp',{}).get(ev_key) is not None]
    ey = [m['event_impact_pp'].get(ev_key) for m in valid if is_esc_yes(m) and m.get('event_impact_pp',{}).get(ev_key) is not None]
    def fmt(v):
        if not v: return 'n/d'
        return f'{sum(v)/len(v):+.2f}pp (n={len(v)})'
    A(f"| {ev_label} | {fmt(py)} | {fmt(pn)} | {fmt(ey)} |")
A('')
A('**Выводы:**')
A('- 17 апреля (Иран заявил что Hormuz открыт) — **peace-YES взлетели в среднем на +6.6pp за 2 часа**. Это сильный bullish-сигнал, и мы могли SELL-y часть позиции для профита.')
A('- 19 апреля (захват Touska) — парадоксально, peace-YES тоже выросли (+4.5pp), потому что рынок уже был сильно перепродан предшествующей блокадой. Это классический "sell-the-news-buy-the-panic".')
A('- 20–21 апреля (Pentagon policy + Tifani) — peace-YES +2.2pp в среднем, реакция затухает. Рынок "устал" реагировать на каждый захват — это идеальный момент для **накапливать peace-YES на любой просадке**.')
A('- Для escalation-YES (tanker seize, <25 ships) — мы выдели *отрицательные* реакции (-2.9pp) на событиях что логически должны были их толкать вверх. Это значит escalation-YES **опережают новости** — к моменту официального подтверждения уже стоят дорого, и профит надо фиксировать.')
A('')

# ====== 5. Playbook per market ======
A('## 5. Playbook — конкретные триггеры по каждому рынку')
A('')
A('Формат: **side–рынок** | shares@avg | curr→med (range) | BUY≤ / SELL≥ | state | news-hint')
A('')
for m in sorted(mkts, key=lambda x: -x['cost']):
    s = m.get('stats')
    if not s:
        A(f"- **{m['outcome']} – {m['title']}** | {m['shares']:.0f}@${m['avg_entry']:.3f} | NO DATA — ручной exit рекомендуется (вероятно near resolution).")
        continue
    buy = m['buy_trigger']; sell = m['sell_trigger']
    bt = m.get('backtest',{}) or {}
    imp = m.get('event_impact_pp',{}) or {}
    state_icon = {'BUY_TRIGGER_HIT':'🟢 BUY','SELL_TRIGGER_HIT':'🔴 SELL','WAIT':'⚪ Wait'}.get(m.get('state'),'?')
    size = 25 if s['vol_score']>0.4 else 30
    # news hint: take largest absolute event move
    news_hint = ''
    if imp:
        largest = sorted(imp.items(), key=lambda x: -abs(x[1]))[:1]
        for name, pp in largest:
            label = dict(EVENTS).get(name, name)
            action = 'BUY' if pp<-3 else ('SELL' if pp>3 else 'держать')
            news_hint = f" · news: {label} → {pp:+.1f}pp ({action})"
    A(f"- **{m['outcome']} – {m['title']}**")
    A(f"  - {m['shares']:.0f}sh @ avg ${m['avg_entry']:.3f} (cost ${m['cost']:.2f}) · curr **${s['current']:.3f}** → med ${s['median']:.3f} (range ${s['min']:.2f}–${s['max']:.2f}, vol={s['vol_score']:.2f})")
    A(f"  - **BUY ≤ ${buy} · SELL ≥ ${sell}** · размер цикла **${size}** · экстрем BUY ≤ ${m.get('extreme_buy')}, SELL ≥ ${m.get('extreme_sell')}")
    A(f"  - Бэктест: {bt.get('exits','?')}вых/{bt.get('entries','?')}вх, pnl/share ${bt.get('pnl_per_share',0):.3f} · **{state_icon}**{news_hint}")

# ====== 6. Portfolio risk ======
A('## 6. Правила риска на уровне портфеля')
A('')
A('1. **Общий лимит range-экспозиции:** $1 500 одновременно (сверх текущих core-позиций). Это не даёт превратить range-торговлю в новый основной портфель.')
A('2. **Дневной стоп-лосс:** если минус $100 за сутки по range-циклам — **пауза до следующего UTC-дня**.')
A('3. **Запрет averaging down > 50%:** нельзя докупать более чем на 50% от первоначального cost-basis в одну сессию. Например если вошли $30, максимум +$15 на просадке.')
A('4. **Correlation cap:** не держать одновременно 3+ свежих bullish peace-YES позиций (`US x Iran permanent peace May 31`, `US x Iran ceasefire extended`, `end military ops`) — они двигаются синхронно, это не диверсификация, а плечо.')
A('5. **Resolution risk:** **обязательный полный exit за 48 часов до deadline рынка**. На deadline bid-ask может schluka 20pp, и профита от range-цикла не будет.')
A('6. **News blackout:** после крупного объявления (захват танкера, выступление Трампа) — **1 час пауза**, потом перепроверка триггеров. Никаких сделок в первые 15 минут.')
A('7. **Max concentration per market:** не более $150 суммарного cost basis на один рынок (core + range).')
A('8. **Min edge filter:** сделка разрешена только если edge vs медианы ≥ 8% (после slippage). Меньше — не торговать.')
A('')

# ====== 7. Backtest results ======
A('## 7. Результаты бэктеста за 20 дней')
A('')
A('Правила: BUY при цене ≤ 92% от 20-дневной медианы, SELL при цене ≥ 108%. Slippage 2% на сделку. Размер $25 на цикл.')
A('')
A('| Рынок | Entries | Exits | PnL / share | PnL при $25/цикл |')
A('|---|---:|---:|---:|---:|')
rows = []
for m in valid:
    bt = m.get('backtest')
    if not bt: continue
    entry = m['stats']['median'] * 0.92
    shares_per_bet = 25 / entry if entry > 0 else 0
    pnl_usd = bt['pnl_per_share'] * shares_per_bet
    rows.append((m, bt, pnl_usd))
rows.sort(key=lambda r: -r[2])
for m, bt, pnl_usd in rows:
    A(f"| {m['outcome']} – {m['title'][:55]} | {bt['entries']} | {bt['exits']} | ${bt['pnl_per_share']:.3f} | ${pnl_usd:+.2f} |")
A(f"| **ИТОГО** | — | — | — | **${sum(r[2] for r in rows):+.2f}** |")
A('')
A(f'**Экстраполяция на 30 дней:** ${total_edge_20d * 1.5:+.2f}')
A('')
A('**Предостережения бэктеста:**')
A('- Бэктест предполагает идеальное исполнение (попал именно в минимум цены и вышел именно в максимуме цикла). В реальности ожидается 50–70% от этой цифры.')
A('- Бэктест включает 2% slippage — на Polymarket реальный slippage на малом bet-size ($25) чаще 1–2%, на крупном ($100+) 3–5%.')
A('- Некоторые рынки показывают отрицательный PnL бэктеста (одна покупка, цена не восстановилась к SELL-порогу за 20 дней) — это нормально в тренде, но ограничивает частоту.')
A('')

# ====== 8. Implementation ======
A('## 8. Implementation — что делать СЕЙЧАС')
A('')
A('**Немедленные действия (активные триггеры на утро 21 апр):**')
A('')
A('### Приоритет A — SELL triggers (фиксируем профит)')
for m in sell_hit:
    s = m['stats']
    A(f"- **{m['outcome']} – {m['title'][:70]}**")
    A(f"  - Current ${s['current']:.3f} ≥ sell-триггер ${m['sell_trigger']}. ")
    if m['outcome']=='Yes' and 'tanker' in m['title'].lower():
        A(f"  - **Уже $1.00** — рынок фактически разрешился в нашу пользу. Ждать resolution или продать если есть bid ≥ 0.99.")
    else:
        A(f"  - Продать **50–70% позиции** по bid ≥ ${m['sell_trigger']}. Остаток держать как tail-insurance.")
A('')
A('### Приоритет B — BUY triggers c высокой волатильностью (vol_score ≥ 0.25, свежие циклы)')
high_vol_buy = [m for m in buy_hit if m['stats']['vol_score'] >= 0.25]
high_vol_buy.sort(key=lambda m: -m['stats']['vol_score'])
for m in high_vol_buy[:8]:
    s = m['stats']
    size = 25 if s['vol_score']>0.4 else 30
    target = m['sell_trigger']
    roi_pct = (target - s['current'])/s['current']*100
    A(f"- **{m['outcome']} – {m['title'][:65]}** | vol={s['vol_score']:.2f} | curr ${s['current']:.3f} → buy ${m['buy_trigger']} → sell ${target} | **ROI цикла: +{roi_pct:.1f}%** | размер **${size}**")
A('')
A('### Приоритет C — BUY triggers с низкой волатильностью (vol_score < 0.25) — подождать более глубокой просадки')
low_vol_buy = [m for m in buy_hit if m['stats']['vol_score'] < 0.25]
for m in low_vol_buy:
    s = m['stats']
    A(f"- {m['outcome']} – {m['title'][:65]} | vol={s['vol_score']:.2f} | curr ${s['current']:.3f} — мелкая просадка, размер максимум $15–20 или пропустить.")
A('')
A('### Резолюшен-контроль')
A(f"- **Рынок без данных:** `US x Iran ceasefire extended by April 22, 2026?` — до resolution 1 день. Проверить вручную через CLOB UI и либо продать, либо держать до expiry.")
A('- **Рынки с апрельским deadline (April 22/26/30)** — обязательно проверить позиции за 48h до deadline и выйти из range-циклов.')
A('')

# ====== 9. Интеграция с news_spike ======
A('## 9. Интеграция с существующим news_spike-ботом')
A('')
A('- 🔵 **News alert** (твит Трампа, заголовок от Рейтер) → бот проверяет активные триггеры range-стратегии, и если цена ушла за новый BUY/SELL-уровень — шлёт уведомление.')
A('- 🟠 **Odds alert ≥5pp за 30 мин** → проверить не пробит ли support/resistance (supports/resistances из этого playbook). Если да — новый цикл открыт.')
A('- 🟣 **Opportunity alert** (скачок объёма или крупная сделка denizz/car) → оценить как кандидата на range-цикл: если рынок в списке из 30 и vol_score ≥ 0.25 — открыть мини-позицию $20–25.')
A('')
A('Конкретная логика для интеграции в `news_spike/handler.py`:')
A('```python')
A('# псевдокод для проверки range-trigger')
A('def check_range_trigger(token_id, current_px, side):')
A('    playbook = load_iran_playbook()  # наш iran_playbook_built.json')
A('    m = playbook.get(token_id)')
A('    if not m: return None')
A('    if current_px <= m["buy_trigger"]: return ("BUY", m["sell_trigger"])')
A('    if current_px >= m["sell_trigger"]: return ("SELL", m["buy_trigger"])')
A('    return None')
A('```')
A('')

# disclaimer
A('---')
A('')
A('**Disclaimer:** Not financial advice. Данные собраны 2026-04-21 из публичных API (Polymarket CLOB). Все триггеры — это статистические уровни на основе 20-дневной истории, они не гарантируют прибыли. Prediction markets имеют риск полной потери депозита и риск резолюшена не в вашу пользу. Перед исполнением проверьте live-цены вручную.')

content = '\n'.join(report)
with open(OUT_MD, 'w', encoding='utf-8') as f:
    f.write(content)

# word count check
words = len(content.split())
print(f'Saved {OUT_MD}')
print(f'Word count: {words}')
print(f'Buy triggers: {len(buy_hit)}, Sell triggers: {len(sell_hit)}')
print(f'30d edge: ${edge_30d:.2f}')
