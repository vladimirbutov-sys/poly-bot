"""Check win/loss status of all frozen neg_risk positions."""
import sys
import json
import requests

sys.stdout.reconfigure(encoding='utf-8')

with open('positions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

won = 0
lost = 0
unknown = 0
won_usd = 0.0
lost_usd = 0.0
unknown_usd = 0.0
losses = []

for key, pos in data['positions'].items():
    if pos.get('status') != 'open' or not pos.get('neg_risk'):
        continue
    token_id = pos.get('token_id', '')
    title = pos.get('title', '?')
    cost = pos.get('cost_usd', 0)
    try:
        r = requests.get('https://gamma-api.polymarket.com/markets',
                         params={'clob_token_ids': token_id}, timeout=15)
        markets = r.json()
        if markets:
            m = markets[0]
            outcome_prices = m.get('outcomePrices', '[]')
            if isinstance(outcome_prices, str):
                outcome_prices = json.loads(outcome_prices)

            clob_ids = m.get('clobTokenIds', '[]')
            if isinstance(clob_ids, str):
                clob_ids = json.loads(clob_ids)

            if token_id in clob_ids:
                idx = clob_ids.index(token_id)
                price = float(outcome_prices[idx]) if idx < len(outcome_prices) else -1

                if price > 0.9:
                    won += 1
                    won_usd += cost
                elif price < 0.1:
                    lost += 1
                    lost_usd += cost
                    losses.append(f'  LOSS: {title[:60]} (${cost:.2f}) price={price:.3f}')
                else:
                    unknown += 1
                    unknown_usd += cost
                    losses.append(f'  ???:  {title[:60]} (${cost:.2f}) price={price:.3f}')
            else:
                unknown += 1
                unknown_usd += cost
    except Exception as e:
        unknown += 1
        unknown_usd += cost

print(f'WIN:     {won} positions | ${won_usd:.2f}')
print(f'LOSS:    {lost} positions | ${lost_usd:.2f}')
print(f'UNKNOWN: {unknown} positions | ${unknown_usd:.2f}')
print()
if losses:
    print('Problematic:')
    for line in losses:
        print(line)
else:
    print('All frozen bets look like winners!')
