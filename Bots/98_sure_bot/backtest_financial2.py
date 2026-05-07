"""Backtest v2: check ALL 915 financial markets, not just 200."""
import sys
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')
import json, requests, re, time

FINANCIAL_ASSETS = [
    r'\bbitcoin\b', r'\bethereum\b', r'\bsolana\b', r'\bxrp\b',
    r'\bbtc\b', r'\beth\b', r'\bsol\b', r'\bdogecoin\b', r'\bcardano\b',
    r'\baapl\b', r'\bamzn\b', r'\bgoogl\b', r'\bmeta\b', r'\bnflx\b',
    r'\bmsft\b', r'\btsla\b', r'\bnvda\b', r'\bapple\b', r'\bamazon\b',
    r'\bgoogle\b', r'\bnetflix\b', r'\bmicrosoft\b', r'\btesla\b',
    r'\bnvidia\b', r'\bopendoor\b',
    r'\bs&p\s*500\b', r'\bnasdaq\b', r'\bdow\s*jones\b',
    r'\bcrude\s*oil\b', r'\bgold\s*price\b', r'\bsilver\s*price\b',
    r'\bnatural\s*gas\b', r'\bwti\b', r'\bbrent\b',
    r'\bmicrostrategy\b',
]
COIN_FLIP = [r'\bup\s+or\s+down\b', r'\bup/down\b', r'\bodd\s+or\s+even\b']

def is_financial(q):
    q = q.lower()
    return any(re.search(p, q) for p in FINANCIAL_ASSETS)
def is_coinflip(q):
    q = q.lower()
    return any(re.search(p, q) for p in COIN_FLIP)

print("Fetching closed markets...")
all_markets = []
offset = 0
while True:
    resp = requests.get("https://gamma-api.polymarket.com/markets",
        params={"closed": "true", "limit": 500, "offset": offset,
                "order": "endDate", "ascending": "false"}, timeout=30)
    batch = resp.json()
    if not batch: break
    all_markets.extend(batch)
    last_end = batch[-1].get("endDate", "")
    if last_end and last_end < "2026-03-01": break
    if len(batch) < 500: break
    offset += 500

print(f"Fetched {len(all_markets)} closed markets")

financial_resolved = []
for m in all_markets:
    q = m.get("question", "")
    if not is_financial(q): continue
    if is_coinflip(q): continue
    vol = float(m.get("volumeNum", 0) or 0)
    if vol < 3000: continue
    uma = m.get("umaResolutionStatus", "")
    if uma != "resolved": continue

    raw_prices = m.get("outcomePrices")
    if not raw_prices: continue
    resolved_prices = json.loads(raw_prices)
    raw_outcomes = m.get("outcomes")
    if not raw_outcomes: continue
    outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes
    raw_token_ids = m.get("clobTokenIds")
    if not raw_token_ids: continue
    token_ids = json.loads(raw_token_ids) if isinstance(raw_token_ids, str) else raw_token_ids

    winning_idx = None
    for i, rp in enumerate(resolved_prices):
        if float(rp) >= 0.99:
            winning_idx = i
            break
    if winning_idx is None: continue

    financial_resolved.append({
        "question": q, "vol": vol, "outcomes": outcomes,
        "token_ids": token_ids, "winning_idx": winning_idx,
        "end_date": m.get("endDate", ""), "neg_risk": m.get("negRisk", False),
    })

print(f"Resolved financial markets: {len(financial_resolved)}")

CLOB_HISTORY = "https://clob.polymarket.com/prices-history"

results = {"won": 0, "lost": 0, "profit": 0}
by_vol = {}
lost_list = []
checked = 0

print(f"Checking ALL {len(financial_resolved)} markets price history...")

for idx, fm in enumerate(financial_resolved):
    if idx % 50 == 0 and idx > 0:
        print(f"  ...checked {idx}/{len(financial_resolved)}, found {checked} in bot range so far")

    for i, token_id in enumerate(fm["token_ids"]):
        if i >= len(fm["outcomes"]): break
        try:
            resp = requests.get(CLOB_HISTORY, params={
                "market": token_id, "interval": "all", "fidelity": "60",
            }, timeout=15)
            if resp.status_code != 200: continue
            data = resp.json()
            if isinstance(data, dict) and "history" in data:
                data = data["history"]
            if not data: continue
        except Exception:
            continue

        prices_list = [pt.get("p", 0) for pt in data[-10:]]
        if not prices_list: continue

        avg_price = sum(prices_list[-5:]) / len(prices_list[-5:])
        if not (0.975 <= avg_price <= 0.993): continue

        outcome_won = (i == fm["winning_idx"])
        if outcome_won:
            profit = 5.0 / avg_price - 5.0
            results["won"] += 1
        else:
            profit = -5.0
            results["lost"] += 1
            lost_list.append({
                "q": fm["question"][:65],
                "outcome": fm["outcomes"][i],
                "price": avg_price,
                "vol": fm["vol"],
                "end": fm["end_date"][:10],
            })
        results["profit"] += profit

        if fm["vol"] >= 50000: bucket = "50k+"
        elif fm["vol"] >= 20000: bucket = "20k-50k"
        elif fm["vol"] >= 10000: bucket = "10k-20k"
        elif fm["vol"] >= 5000: bucket = "5k-10k"
        else: bucket = "3k-5k"

        if bucket not in by_vol: by_vol[bucket] = {"won": 0, "lost": 0}
        if outcome_won: by_vol[bucket]["won"] += 1
        else: by_vol[bucket]["lost"] += 1
        checked += 1

    time.sleep(0.05)

total = results["won"] + results["lost"]
print(f"\n{'='*70}")
print(f"BACKTEST RESULTS: Financial markets at 97.5-99.3%")
print(f"Period: March 1-19, 2026")
print(f"{'='*70}")
print(f"Markets checked:  {len(financial_resolved)}")
print(f"In bot range:     {total}")
print(f"Won:              {results['won']}")
print(f"Lost:             {results['lost']}")
if total > 0:
    wr = results["won"] / total * 100
    print(f"Win rate:         {wr:.1f}%")
    print(f"Total P&L:        ${results['profit']:+.2f}")
    print(f"Avg profit/bet:   ${results['profit']/total:+.2f}")

print(f"\nBy volume bucket:")
for bucket in ["3k-5k", "5k-10k", "10k-20k", "20k-50k", "50k+"]:
    if bucket not in by_vol: continue
    d = by_vol[bucket]
    t = d["won"] + d["lost"]
    if t == 0: continue
    wr = d["won"] / t * 100
    print(f"  {bucket:>10}: {t:>3} bets | {d['won']:>3}W / {d['lost']:>3}L | WR {wr:.1f}%")

if lost_list:
    print(f"\nLOST BETS ({len(lost_list)}):")
    for ex in lost_list:
        print(f"  price={ex['price']:.3f} vol=${ex['vol']:>8,.0f} | {ex['outcome']:>4} | {ex['q']}")
else:
    print(f"\nNo losses found in {total} bets!")
