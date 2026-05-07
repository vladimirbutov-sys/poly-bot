"""
Backtest on REAL historical Polymarket data.

Fetches resolved markets from Gamma API, analyzes win rates by neg_risk,
price threshold, category, and volume/liquidity filters.

Saves raw data to avoid re-fetching on subsequent runs.
"""
import json
import sys
import os
import time
import requests
from datetime import datetime, timezone
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

GAMMA_API = "https://gamma-api.polymarket.com"
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_CACHE = os.path.join(BOT_DIR, "backtest_raw_markets.json")
OUTPUT_FILE = os.path.join(BOT_DIR, "backtest_results.json")
POSITIONS_FILE = os.path.join(BOT_DIR, "positions.json")

BET_SIZE = 10.0
CAPITAL = 574.0
PAGE_SIZE = 500
MAX_PAGES = 200  # safety limit: 100,000 markets max


# =====================================================
# Step 1: Fetch or load raw markets
# =====================================================
def fetch_all_closed():
    """Fetch all closed markets with retry and progress."""
    all_markets = []
    offset = 0
    retries = 0

    while offset < PAGE_SIZE * MAX_PAGES:
        try:
            resp = requests.get(
                f"{GAMMA_API}/markets",
                params={"closed": "true", "limit": PAGE_SIZE, "offset": offset},
                timeout=20,
            )
            resp.raise_for_status()
            batch = resp.json()
        except Exception as e:
            retries += 1
            if retries > 3:
                print(f"  Stopping at offset {offset} after 3 retries: {e}")
                break
            print(f"  Retry {retries} at offset {offset}: {e}")
            time.sleep(5)
            continue

        if not batch:
            break

        retries = 0
        all_markets.extend(batch)

        if len(all_markets) % 5000 == 0 or len(batch) < PAGE_SIZE:
            print(f"  {len(all_markets)} markets loaded...")

        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(0.2)

    return all_markets


if os.path.exists(RAW_CACHE):
    print(f"Loading cached raw markets from {RAW_CACHE}...")
    with open(RAW_CACHE, "r", encoding="utf-8") as f:
        raw_markets = json.load(f)
    print(f"Loaded {len(raw_markets)} cached markets")
else:
    print("Fetching ALL closed markets from Gamma API...")
    raw_markets = fetch_all_closed()
    print(f"Total fetched: {len(raw_markets)}")
    # Save cache
    print("Saving cache...")
    with open(RAW_CACHE, "w", encoding="utf-8") as f:
        json.dump(raw_markets, f, ensure_ascii=False)
    print(f"Cache saved to {RAW_CACHE}")


# =====================================================
# Step 2: Parse markets
# =====================================================
def categorize(question):
    q = question.lower()
    if any(k in q for k in ["vs.", "vs ", "o/u ", "spread:", "game handicap",
        "nba", "nhl", "mlb", "nfl", "mls", "ufc", "atp", "wta",
        "counter-strike", "cs2", "valorant", "dota", "lol:",
        "tennis", "boxing", "cricket", "t20", "ipl", " win on "]):
        return "sports"
    if any(k in q for k in ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana"]):
        return "crypto"
    if any(k in q for k in ["president", "election", "trump", "biden", "congress",
        "governor", "democrat", "republican", "minister", "parliament"]):
        return "politics"
    if any(k in q for k in ["war", "strike", "invasion", "military", "ceasefire",
        "ukraine", "russia", "iran", "israel"]):
        return "geopolitics"
    if any(k in q for k in ["s&p", "nasdaq", "stock", "gold", "oil", "crude",
        "interest rate", "gdp", "inflation"]):
        return "finance"
    return "other"


print("\nParsing markets...")
parsed = []

for market in raw_markets:
    try:
        raw_prices = market.get("outcomePrices")
        if not raw_prices:
            continue
        prices = json.loads(raw_prices) if isinstance(raw_prices, str) else raw_prices

        raw_outcomes = market.get("outcomes")
        if not raw_outcomes:
            continue
        outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes

        if len(prices) != len(outcomes):
            continue

        float_prices = [float(p) for p in prices]
        max_price = max(float_prices)
        max_idx = float_prices.index(max_price)

        if max_price < 0.96:
            continue

        # In resolved markets, the final price reflects the outcome:
        # winner's price -> 1.0, loser's price -> 0.0
        # A price of 0.96+ that STAYED high means it won
        outcome_won = max_price > 0.5

        parsed.append({
            "question": market.get("question", ""),
            "max_price": max_price,
            "outcome": outcomes[max_idx],
            "outcome_won": outcome_won,
            "neg_risk": market.get("negRisk", False),
            "volume": float(market.get("volumeNum", 0) or 0),
            "liquidity": float(market.get("liquidityNum", 0) or 0),
            "category": categorize(market.get("question", "")),
        })
    except (json.JSONDecodeError, ValueError, TypeError, IndexError):
        continue

print(f"Markets with outcome >= 96%: {len(parsed)}")


# =====================================================
# Step 3: Analysis functions
# =====================================================
def analyze(data, label, min_price, skip_nr=False, nr_only=False,
            min_vol=0, min_liq=0):
    w, l, losses = 0, 0, []
    for m in data:
        if m["max_price"] < min_price:
            continue
        if skip_nr and m["neg_risk"]:
            continue
        if nr_only and not m["neg_risk"]:
            continue
        if m["volume"] < min_vol or m["liquidity"] < min_liq:
            continue
        if m["outcome_won"]:
            w += 1
        else:
            l += 1
            losses.append(m)
    t = w + l
    return {
        "label": label, "total": t, "wins": w, "losses": l,
        "win_rate": round(w / t * 100, 4) if t > 0 else 0,
        "loss_1_in_n": t // l if l > 0 else 0,
        "loss_list": losses,
    }


# =====================================================
# Step 4: Run all analyses
# =====================================================
print(f"\n{'='*90}")
print(f"BACKTEST RESULTS — {len(raw_markets)} REAL POLYMARKET MARKETS")
print(f"{'='*90}")

results = [
    analyze(parsed, "ALL, 96%+", 0.96),
    analyze(parsed, "ALL, 97%+", 0.97),
    analyze(parsed, "ALL, 97.5%+", 0.975),
    analyze(parsed, "ALL, 98%+", 0.98),
    analyze(parsed, "NON-NR, 96%+", 0.96, skip_nr=True),
    analyze(parsed, "NON-NR, 97%+", 0.97, skip_nr=True),
    analyze(parsed, "NON-NR, 97.5%+", 0.975, skip_nr=True),
    analyze(parsed, "NON-NR, 98%+", 0.98, skip_nr=True),
    analyze(parsed, "NEG_RISK only, 97.5%+", 0.975, nr_only=True),
    # With bot's volume/liquidity filters
    analyze(parsed, "NON-NR 97.5%+ vol>3K liq>500", 0.975, skip_nr=True, min_vol=3000, min_liq=500),
    analyze(parsed, "ALL 97.5%+ vol>3K liq>500", 0.975, min_vol=3000, min_liq=500),
]

print(f"\n{'Scenario':42s} {'Total':>7s} {'W':>7s} {'L':>5s} {'WR':>8s} {'1 loss per':>10s}")
print("-" * 83)
for r in results:
    ls = f"1 in {r['loss_1_in_n']}" if r["loss_1_in_n"] > 0 else "0 losses"
    print(f"{r['label']:42s} {r['total']:7d} {r['wins']:7d} {r['losses']:5d} {r['win_rate']:7.3f}% {ls:>10s}")

# Category breakdown (non-NR, 97.5%+)
print(f"\n{'='*90}")
print("CATEGORY BREAKDOWN (non-neg_risk, 97.5%+)")
print(f"{'='*90}")

cat_data = defaultdict(lambda: {"w": 0, "l": 0, "lq": []})
for m in parsed:
    if m["neg_risk"] or m["max_price"] < 0.975:
        continue
    c = m["category"]
    if m["outcome_won"]:
        cat_data[c]["w"] += 1
    else:
        cat_data[c]["l"] += 1
        cat_data[c]["lq"].append(m["question"][:70])

print(f"\n{'Category':15s} {'W':>7s} {'L':>5s} {'WR':>8s}")
print("-" * 40)
for c in sorted(cat_data, key=lambda x: -(cat_data[x]["w"] + cat_data[x]["l"])):
    d = cat_data[c]
    t = d["w"] + d["l"]
    print(f"{c:15s} {d['w']:7d} {d['l']:5d} {t and d['w']/t*100 or 0:7.3f}%")
    for q in d["lq"]:
        print(f"  LOSS: {q}")

# All losses detail (non-NR, 97.5%+)
print(f"\n{'='*90}")
print("ALL LOSSES (non-neg_risk, 97.5%+)")
print(f"{'='*90}")
r_nnr = next(r for r in results if r["label"] == "NON-NR, 97.5%+")
for m in r_nnr["loss_list"]:
    print(f"  {m['max_price']:.4f} | {m['category']:10s} | vol=${m['volume']:,.0f} | liq=${m['liquidity']:,.0f} | {m['question'][:60]}")

# =====================================================
# Step 5: P&L projections
# =====================================================
print(f"\n{'='*90}")
print("P&L PROJECTIONS")
print(f"{'='*90}")

# Get actual avg entry price
try:
    with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
        pos = json.load(f)
    won_p = [p for p in pos["positions"].values() if p["status"] == "won"]
    avg_entry = sum(p["entry_price"] for p in won_p) / len(won_p) if won_p else 0.985
except Exception:
    avg_entry = 0.985

ppw = BET_SIZE / avg_entry - BET_SIZE  # profit per win

r_bot = next(r for r in results if r["label"] == "NON-NR 97.5%+ vol>3K liq>500")
wr = r_bot["win_rate"] / 100

print(f"\n  Avg entry: {avg_entry:.4f} | Profit/win: ${ppw:.4f}")
print(f"  Win rate (non-NR, filtered): {r_bot['win_rate']:.3f}% = 1 loss per {r_bot['loss_1_in_n']}")

scenarios = [
    ("Current (neg_risk ON, 45h redeem)", 45, CAPITAL, BET_SIZE, True),
    ("NEW: skip neg_risk (12h redeem)", 12, CAPITAL, BET_SIZE, False),
    ("NEW: skip neg_risk, $15/bet", 12, CAPITAL, 15.0, False),
    ("NEW: skip neg_risk, $1000 capital", 12, 1000, BET_SIZE, False),
]

print(f"\n{'Scenario':45s} {'Bets/mo':>8s} {'Gross':>8s} {'Loss':>8s} {'Net':>8s} {'ROI':>6s}")
print("-" * 85)

proj = []
for name, rh, cap, bet, incl_nr in scenarios:
    slots = int(cap / bet)
    bpm = slots * (24 / rh) * 30
    if incl_nr:
        r_use = next(r for r in results if r["label"] == "ALL 97.5%+ vol>3K liq>500")
        w = r_use["win_rate"] / 100
    else:
        w = wr
    p = bet / avg_entry - bet
    g = bpm * w * p
    lo = bpm * (1 - w) * bet
    n = g - lo
    roi = n / cap * 100
    print(f"{name:45s} {bpm:8.0f} ${g:7.1f} ${lo:7.1f} ${n:7.1f} {roi:5.1f}%")
    proj.append({"name": name, "bets_mo": round(bpm), "net": round(n, 2), "roi": round(roi, 2)})

# =====================================================
# Step 6: Monte Carlo
# =====================================================
print(f"\n{'='*90}")
print("MONTE CARLO (10K sims, non-NR, $10/bet, 12h redeem)")
print(f"{'='*90}")

import random
random.seed(42)

def mc(cap, bet, wr, ppw, n_bets, sims=10000):
    finals = []
    survived = 0
    for _ in range(sims):
        b = cap
        ok = True
        for _ in range(n_bets):
            if b < bet:
                ok = False
                break
            b += ppw if random.random() < wr else -bet
        if ok:
            survived += 1
        finals.append(b - cap)
    finals.sort()
    n = len(finals)
    return {
        "survival": round(survived / sims * 100, 2),
        "median": round(finals[n // 2], 2),
        "p5": round(finals[int(n * 0.05)], 2),
        "p95": round(finals[int(n * 0.95)], 2),
        "worst": round(finals[0], 2),
    }

mc30 = mc(CAPITAL, BET_SIZE, wr, ppw, 3420)
mc90 = mc(CAPITAL, BET_SIZE, wr, ppw, 10260)

print(f"\n  30d (~3420 bets): Survival {mc30['survival']}% | Median ${mc30['median']} | P5 ${mc30['p5']} | P95 ${mc30['p95']} | Worst ${mc30['worst']}")
print(f"  90d (~10260 bets): Survival {mc90['survival']}% | Median ${mc90['median']} | P5 ${mc90['p5']} | P95 ${mc90['p95']} | Worst ${mc90['worst']}")

wins_to_cover = int(BET_SIZE / ppw)
print(f"\n  Wins needed to cover 1 loss: {wins_to_cover}")
print(f"  At 1 loss per {r_bot['loss_1_in_n']} bets: net {r_bot['loss_1_in_n'] - 1} wins between losses")
print(f"  Safety margin: {(r_bot['loss_1_in_n'] - 1) / wins_to_cover:.1f}x (need 1x to break even)")

# =====================================================
# Save
# =====================================================
output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "data_source": f"Gamma API — {len(raw_markets)} closed Polymarket markets",
    "markets_with_96pct_outcome": len(parsed),
    "win_rate_analysis": [{k: v for k, v in r.items() if k != "loss_list"} for r in results],
    "losses_nonnr_975": [
        {"question": m["question"][:80], "price": m["max_price"],
         "category": m["category"], "volume": m["volume"]}
        for m in r_nnr["loss_list"]
    ],
    "categories_nonnr_975": {
        c: {"wins": d["w"], "losses": d["l"],
            "win_rate": round(d["w"] / (d["w"] + d["l"]) * 100, 4) if (d["w"] + d["l"]) > 0 else 0}
        for c, d in cat_data.items()
    },
    "projections": proj,
    "monte_carlo_30d": mc30,
    "monte_carlo_90d": mc90,
}

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\nResults saved to {OUTPUT_FILE}")
