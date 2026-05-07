"""
Filtered Sub-Segment Backtest — 2026-03-23
Same as market_subsegment_backtest.py but APPLIES the bot's actual filters
to see what actually passes through and where remaining risks are.
"""
import json
import re
import sys
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')
sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')

SCANNER_DATA = r"C:\Users\Honor\Desktop\Polymarket\Bots\97_scanner\scanner_data.json"
OUTPUT_FILE = r"C:\Users\Honor\Desktop\Polymarket\Bots\98_sure_bot\_analytics\data\filtered_subsegment_2026-03-23.json"

# Inline classify function (copied from market_subsegment_backtest.py)
GAME_MAP_PATS = [
    r'\bgame\s*[1-9]\b', r'\bgame\s*\d+\b', r'\bmap\s*[1-9]\b', r'\bmap\s*\d+\b',
    r'\bset\s*[1-9]\b', r'\bset\s*\d+\b', r'\bround\s*[1-9]\b', r'\bround\s*\d+\b',
    r'\bperiod\s*[1-9]\b', r'\bhalf\s*[12]\b',
    r'\b(1st|2nd|3rd|4th|5th)\s*(game|map|set|round|period|half|quarter|inning)\b',
    r'\bfirst\s*(game|map|set|round|period|half)\b',
]
PROP_PATS = [
    r'\bfirst\s*(blood|kill|baron|dragon|tower|rift|herald|roshan|goal|point)\b',
    r'\b(total|over|under)\s*\d+\.?\d*\s*(kills|goals|points|assists|rebounds|rounds|maps|games)\b',
    r'\b\d+\+?\s*(kills|goals|points|assists|rebounds|strikeouts|hits|aces|double faults)\b',
    r'\b(odd|even)\b.*\b(total|score|goals|points|kills|rounds)\b',
    r'\btotal\s*(goals|kills|points|score|rounds|maps|games)\b',
    r'\b(over|under)\s*\d', r'\bpenta.?kill\b', r'\bteaser\b', r'\bparlay\b',
    r'\bhandicap\b', r'\bspread\b', r'\bmost\s*(kills|goals|assists|points)\b',
    r'\bmvp\b', r'\bman of the match\b', r'\byellow card\b', r'\bred card\b',
    r'\bcorner\b.*\b(over|under|total)\b', r'\bboth teams (to )?score\b',
    r'\bclean sheet\b', r'\bpenalty\b', r'\bexact score\b', r'\bscore (first|last)\b',
    r'\bhighest scoring\b', r'\b(draw|tie)\b.*\b(no|not)\b',
]
THRESH_CLASS_PATS = [
    r'\b(close|stay|remain|be|go|dip|pump|reach|hit|drop|fall|rise|surge)\s*(above|below|between|under|over|at least|at most)\b',
    r'\bprice of\b',
    r'\b(bitcoin|btc|eth|ethereum|sol|solana|xrp|doge|bnb)\b.*\b\$[\d,]+',
    r'\b\$[\d,]+.*\b(bitcoin|btc|eth|ethereum|sol|solana)\b',
    r'\btemperature\b', r'\bhighest temp\b', r'\bweather\b',
    r'\b(nasdaq|s&p|dow|sp500|spy)\b.*\b(above|below|close)\b',
    r'\bgold\b.*\b(above|below|price)\b', r'\boil\b.*\b(above|below|price)\b',
]
DRAW_PATS = [r'\bend in a draw\b', r'\bend in a tie\b', r'\bdraw\?\s*$']
COUNT_PATS = [
    r'\bhow many\b', r'\bexactly\s*\d+\b', r'\b\d+-\d+\s*(tweets?|posts?|truth social)\b',
    r'\bpost\s*\d+-\d+\b', r'\b(tweets?|posts?)\s*from\b', r'\btweet\b.*\bfrom\b.*\bto\b',
]
ELECTION_PATS = [
    r'\b(win|advance|qualify)\b.*\b(election|primary|runoff|nomination|race)\b',
    r'\bbe the next\s*(president|prime minister|chancellor|mayor|governor|leader)\b',
    r'\bnext prime minister\b', r'\bnext president\b',
    r'\b(democrat|republican|labour|conservative|tory)\b.*\b(win|lose|nomination)\b',
]
MATCH_PATS = [
    r'\bwin\b(?!.*\b(game\s*\d|map\s*\d|set\s*\d|round\s*\d|period\s*\d|half\s*\d|inning)\b)',
    r'\bbeat\b', r'\bdefeat\b', r'\badvance\b', r'\bqualify\b',
    r'\bchampion\b', r'\beliminate\b', r'\bvs\.?\b.*\b\(W\)\b',
]

def classify_market(question, category=""):
    q = question.lower().strip()
    cat = (category or "").lower()
    for p in THRESH_CLASS_PATS:
        if re.search(p, q, re.I):
            if any(w in q for w in ['bitcoin','btc','eth','ethereum','sol','solana','xrp','doge','crypto','bnb']):
                return ("threshold","crypto_price")
            if any(w in q for w in ['temperature','temp','weather','rain','snow']):
                return ("threshold","weather")
            if any(w in q for w in ['nasdaq','s&p','dow','sp500','spy','stock','index']):
                return ("threshold","stock_index")
            if any(w in q for w in ['gold','oil','crude','wti','brent']):
                return ("threshold","commodity")
            return ("threshold","other_threshold")
    for p in COUNT_PATS:
        if re.search(p, q, re.I):
            if any(w in q for w in ['tweet','truth social','post','white house']):
                return ("counting","social_media_count")
            if any(w in q for w in ['earthquake','quake']):
                return ("counting","earthquake_count")
            return ("counting","other_count")
    for p in PROP_PATS:
        if re.search(p, q, re.I):
            if cat in ('esports',): return ("prop","esports_prop")
            if cat in ('soccer',): return ("prop","soccer_prop")
            return ("prop","other_prop")
    for p in GAME_MAP_PATS:
        if re.search(p, q, re.I):
            if cat in ('esports',) or any(w in q for w in ['esport','league','dota','csgo','cs2',
                    'valorant','overwatch','stand','gaming','fearx','parivision','gamerlegion',
                    't1','gen.g','jdg']): return ("sub_match","esports_game_map")
            if any(w in q for w in ['tennis','atp','wta','open','slam']):
                return ("sub_match","tennis_set")
            return ("sub_match","other_sub_match")
    for p in DRAW_PATS:
        if re.search(p, q, re.I): return ("draw","draw")
    for p in ELECTION_PATS:
        if re.search(p, q, re.I): return ("match_outcome","election")
    for p in MATCH_PATS:
        if re.search(p, q, re.I):
            if cat in ('esports',) or any(w in q for w in ['esport','gaming','league of legends',
                    'dota','csgo','valorant','stand','fearx']): return ("match_outcome","esports_match")
            if cat in ('soccer',): return ("match_outcome","soccer_match")
            if cat in ('sports_other',) or any(w in q for w in ['basketball','nba','baseball','mlb',
                    'hockey','nhl','football','nfl','golf','pga','championship','tournament',
                    'mocs','bison','ncaa','college','tennis','atp','wta','boxing','ufc','mma']):
                return ("match_outcome","sports_match")
            if cat in ('politics','geopolitics'): return ("match_outcome","election")
            return ("match_outcome","other_match")
    if cat in ('politics','geopolitics'): return ("other","politics_other")
    if cat in ('esports',): return ("other","esports_other")
    if cat in ('sports_other','soccer','basketball','tennis','fighting','american_football'):
        return ("other","sports_other")
    if cat in ('crypto',): return ("other","crypto_other")
    if cat in ('tech',): return ("other","tech_other")
    return ("other","uncategorized")

# === Bot's current filters (replicated from filters.py) ===

PRICE_THRESHOLD_DEFAULT = 0.975
PRICE_THRESHOLD_POLITICS = 0.96
MAX_PRICE = 0.995
MIN_VOLUME = 3000
MIN_LIQUIDITY = 500

COIN_FLIP_PATTERNS = [
    r'\bodd\s+or\s+even\b', r'\bodd/even\b', r'\bfirst\s+blood\b',
    r'\bfirst\s+kill\b', r'\bfirst\s+baron\b', r'\bfirst\s+dragon\b',
    r'\bfirst\s+tower\b', r'\bfirst\s+rift\s+herald\b', r'\bcoin\s+flip\b',
    r'\brampage\b', r'\bfirst\s+roshan\b', r'\bfirst\s+map\b', r'\bup\s+or\s+down\b',
]

THRESHOLD_PATTERNS = [
    r'\bclose\s+above\b', r'\bclose\s+below\b', r'\bbe\s+above\b', r'\bbe\s+below\b',
    r'\bbe\s+between\b', r'\bbe\s+greater\s+than\b', r'\bbe\s+less\s+than\b',
    r'\bprice\s+of\b', r'\breach\b.*\$[\d,]+', r'\bhit\b.*\$[\d,]+',
    r'\bfall\s+(to|below)\b.*\$[\d,]+', r'\bdrop\s+(to|below)\b.*\$[\d,]+',
    r'\brise\s+(to|above)\b.*\$[\d,]+',
]

WEATHER_PATTERNS = [
    r'\btemperature\b.*\d+\s*[°]?\s*[FC]\b', r'\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b',
    r'\d+\s*[°]?\s*[FC]\b.*\btemperature\b', r'\d+\s*[°]?\s*[FC]\b.*\bhighest\s+temp\b',
]

TOXIC_KEYWORDS = [
    r'\bearthquake', r'\bseismic\b', r'\bmagnitude\s+\d',
    r'\btornado', r'\btornadoes\b',
    r'\btweets?\b', r'\bposts?\b.*\d+-\d+',
    r'\d+-\d+\s*(tweets?|posts?)',
    r'\btweet\b', r'\bretweet\b',
    r'how\s+many.*\bpost', r'how\s+many.*\btweet',
    r'number\s+of\s+(tweets?|posts?)',
]

SLOW_KEYWORDS = [
    r'\btop\b', r'\bseason\b', r'\bmost\b',
    r'\btransit\b', r'\bstrait\b', r'\bships?\b',
    r'\bweekly\b', r'\bmonthly\b',
]

FINANCIAL_ASSETS = [
    r'\bbitcoin\b', r'\bethereum\b', r'\bsolana\b', r'\bxrp\b',
    r'\bbtc\b', r'\beth\b', r'\bsol\b', r'\bdogecoin\b', r'\bcardano\b',
    r'\bpolygon\b', r'\bavalanch\b', r'\blitecoin\b', r'\bpolkadot\b',
    r'\bchainlink\b', r'\buniswap\b', r'\bshiba\b',
    r'\baapl\b', r'\bamzn\b', r'\bgoogl\b', r'\bmeta\b', r'\bnflx\b',
    r'\bmsft\b', r'\btsla\b', r'\bnvda\b', r'\bapple\b', r'\bamazon\b',
    r'\bgoogle\b', r'\bnetflix\b', r'\bmicrosoft\b', r'\btesla\b',
    r'\bnvidia\b', r'\bopendoor\b',
    r'\bs&p\s*500\b', r'\bnasdaq\b', r'\bnyse\b', r'\bdow\s*jones\b',
    r'\bdjia\b', r'\bndx\b', r'\bspx\b', r'\bhang\s*seng\b', r'\bhsi\b',
    r'\brussell\b', r'\bnikkei\b', r'\bftse\b',
    r'\bcrude\s*oil\b', r'\bgold\s*price\b', r'\bsilver\s*price\b',
    r'\bnatural\s*gas\b', r'\bwti\b', r'\bbrent\b',
    r'\btreasury\s*yield\b', r'\bfed\s*rate\b', r'\bmicrostrategy\b',
]
MIN_VOLUME_FINANCIAL = 50000

SPORTS_BAD_PATTERNS = [
    r'\bo/u\b', r'\bover/under\b', r'\bover\s*/\s*under\b',
    r'\bspread\b', r'\btotal\s+(maps?|kills?|rounds?|points?|goals?)\b',
    r'\bhandi?cap\b',
]

ALL_SPORTS_CATEGORIES = {"esports", "sports_other", "basketball", "hockey",
                         "american_football", "tennis", "fighting", "cricket", "soccer"}
POLITICS_CATEGORIES = {"politics", "geopolitics"}


def apply_bot_filters(question: str, category: str, price: float, volume: float,
                       liquidity: float, neg_risk: bool) -> tuple:
    """Apply all bot filters. Returns (passed, reason)."""
    q = question.lower()
    cat = category.lower() if category else ""

    # Filter 0: min price
    if cat in POLITICS_CATEGORIES:
        if price < PRICE_THRESHOLD_POLITICS:
            return False, "price_politics"
    else:
        if price < PRICE_THRESHOLD_DEFAULT:
            return False, "price_default"

    if price > MAX_PRICE:
        return False, "price_too_high"

    # Filter 1: liquidity (skip — scanner doesn't always have this)

    # Filter 2: coin flip
    for pat in COIN_FLIP_PATTERNS:
        if re.search(pat, q):
            return False, "coin_flip"

    # Filter 3: threshold
    for pat in THRESHOLD_PATTERNS:
        if re.search(pat, q):
            return False, "threshold"

    # Filter 4: weather
    for pat in WEATHER_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            return False, "weather"

    # Filter 5: volume
    if volume > 0 and volume < MIN_VOLUME:
        return False, "low_volume"

    # Filter: toxic keywords
    for pat in TOXIC_KEYWORDS:
        if re.search(pat, q):
            return False, "toxic"

    # Filter: slow keywords
    for pat in SLOW_KEYWORDS:
        if re.search(pat, q):
            return False, "slow"

    # Filter: financial assets (vol < 50K)
    for pat in FINANCIAL_ASSETS:
        if re.search(pat, q):
            if volume < MIN_VOLUME_FINANCIAL:
                return False, "financial_low_vol"
            break

    # Filter: sports win only
    if cat in ALL_SPORTS_CATEGORIES:
        for pat in SPORTS_BAD_PATTERNS:
            if re.search(pat, q):
                return False, "sports_non_win"

    return True, "passed"


def load_and_filter():
    """Load scanner data, apply bot filters, classify."""
    print("Loading scanner_data.json...")
    with open(SCANNER_DATA, "r", encoding="utf-8") as f:
        raw = json.load(f)

    markets_dict = raw.get("markets", raw)
    print(f"Total markets: {len(markets_dict)}")

    all_markets = []
    filtered_out = defaultdict(int)
    passed_markets = []

    for mid, m in markets_dict.items():
        snaps = m.get("snapshots", [])
        if not snaps:
            continue

        max_price = m.get("max_price_seen", 0)
        if max_price < PRICE_THRESHOLD_POLITICS:
            continue

        last_snap = snaps[-1]
        first_snap = snaps[0]
        final_prices = last_snap.get("prices", [])
        if not final_prices or len(final_prices) < 2:
            continue

        max_final = max(float(p) for p in final_prices)
        if max_final < 0.95:
            continue

        first_prices = first_snap.get("prices", [])
        if not first_prices or len(first_prices) < 2:
            continue

        high_idx = 0
        if len(first_prices) >= 2 and float(first_prices[1]) > float(first_prices[0]):
            high_idx = 1

        final_high_price = float(final_prices[high_idx])
        won = final_high_price > 0.5

        # Find best entry price within bot's range
        best_entry = 0
        for snap in snaps:
            sp = snap.get("prices", [])
            if sp and len(sp) > high_idx:
                p = float(sp[high_idx])
                if 0.96 <= p <= MAX_PRICE:
                    best_entry = max(best_entry, p)

        if best_entry < 0.96:
            continue

        question = m.get("question", "")
        category = m.get("category", "")
        volume = float(m.get("volume", 0) or 0)
        neg_risk = m.get("neg_risk", False)
        if not isinstance(neg_risk, bool):
            neg_risk = False

        liquidity = 0
        for snap in snaps:
            liq = snap.get("liquidity", 0)
            if liq and liq > liquidity:
                liquidity = liq

        # Resolve time
        first_ts = first_snap.get("timestamp", "")
        last_ts = last_snap.get("timestamp", "")
        resolve_hours = None
        if first_ts and last_ts:
            try:
                t1 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                t2 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
                resolve_hours = (t2 - t1).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        main_type, sub_type = classify_market(question, category)

        market = {
            "market_id": mid,
            "question": question,
            "category": category,
            "main_type": main_type,
            "sub_type": sub_type,
            "entry_price": best_entry,
            "won": won,
            "resolve_hours": resolve_hours,
            "volume": volume,
            "liquidity": liquidity,
            "neg_risk": neg_risk,
        }

        all_markets.append(market)

        # Apply bot filters
        passed, reason = apply_bot_filters(question, category, best_entry,
                                            volume, liquidity, neg_risk)
        if passed:
            passed_markets.append(market)
        else:
            filtered_out[reason] += 1

    print(f"\nTotal resolved (price >= 96c): {len(all_markets)}")
    print(f"Passed bot filters: {len(passed_markets)}")
    print(f"\nFiltered out by reason:")
    for reason, count in sorted(filtered_out.items(), key=lambda x: -x[1]):
        losses_in = sum(1 for m in all_markets if not m["won"]
                        and apply_bot_filters(m["question"], m["category"], m["entry_price"],
                                               m["volume"], m["liquidity"], m["neg_risk"])[1] == reason)
        print(f"  {reason:20s}: {count:>5} markets ({losses_in} losses caught)")

    return all_markets, passed_markets


def calc_stats(markets):
    if not markets:
        return {"count": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "pnl": 0, "roi_pct": 0, "median_resolve_h": 0}
    wins = sum(1 for m in markets if m["won"])
    losses = len(markets) - wins
    total_pnl = 0
    total_cost = 0
    for m in markets:
        bet = 8.0 if m.get("neg_risk") else 15.0
        shares = bet / m["entry_price"]
        if m["won"]:
            total_pnl += shares - bet
        else:
            total_pnl -= bet
        total_cost += bet

    resolve_times = [m["resolve_hours"] for m in markets
                     if m.get("resolve_hours") and m["resolve_hours"] > 0]
    median_r = sorted(resolve_times)[len(resolve_times)//2] if resolve_times else 0

    return {
        "count": len(markets),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins/len(markets)*100, 2) if markets else 0,
        "loss_rate": round(losses/len(markets)*100, 3) if markets else 0,
        "pnl": round(total_pnl, 2),
        "cost": round(total_cost, 2),
        "roi_pct": round(total_pnl/total_cost*100, 2) if total_cost else 0,
        "median_resolve_h": round(median_r, 1),
    }


def analyze_filtered(passed):
    """Analyze markets that pass all bot filters."""
    by_main = defaultdict(list)
    by_sub = defaultdict(list)
    for m in passed:
        by_main[m["main_type"]].append(m)
        by_sub[m["sub_type"]].append(m)

    print(f"\n{'='*80}")
    print("MARKETS THAT PASS ALL BOT FILTERS — by Main Type")
    print(f"{'='*80}")
    print(f"{'Type':<20} {'Count':>6} {'W':>5} {'L':>3} {'WR%':>7} {'LR%':>7} "
          f"{'PnL':>9} {'ROI%':>7} {'MedRes':>7}")
    print("-"*80)

    main_stats = {}
    for t in sorted(by_main.keys(), key=lambda x: len(by_main[x]), reverse=True):
        s = calc_stats(by_main[t])
        main_stats[t] = s
        print(f"{t:<20} {s['count']:>6} {s['wins']:>5} {s['losses']:>3} "
              f"{s['win_rate']:>6.2f}% {s['loss_rate']:>6.3f}% "
              f"${s['pnl']:>+8.2f} {s['roi_pct']:>+6.2f}% {s['median_resolve_h']:>6.1f}h")

    total_s = calc_stats(passed)
    print("-"*80)
    print(f"{'TOTAL':<20} {total_s['count']:>6} {total_s['wins']:>5} {total_s['losses']:>3} "
          f"{total_s['win_rate']:>6.2f}% {total_s['loss_rate']:>6.3f}% "
          f"${total_s['pnl']:>+8.2f} {total_s['roi_pct']:>+6.2f}% {total_s['median_resolve_h']:>6.1f}h")

    print(f"\n{'='*80}")
    print("MARKETS THAT PASS ALL BOT FILTERS — by Sub-Type")
    print(f"{'='*80}")
    print(f"{'Sub-type':<25} {'Count':>6} {'W':>5} {'L':>3} {'WR%':>7} {'LR%':>7} "
          f"{'PnL':>9} {'ROI%':>7} {'MedRes':>7}")
    print("-"*80)

    sub_stats = {}
    for t in sorted(by_sub.keys(), key=lambda x: len(by_sub[x]), reverse=True):
        s = calc_stats(by_sub[t])
        sub_stats[t] = s
        print(f"{t:<25} {s['count']:>6} {s['wins']:>5} {s['losses']:>3} "
              f"{s['win_rate']:>6.2f}% {s['loss_rate']:>6.3f}% "
              f"${s['pnl']:>+8.2f} {s['roi_pct']:>+6.2f}% {s['median_resolve_h']:>6.1f}h")

    # Show remaining losses
    losses = [m for m in passed if not m["won"]]
    if losses:
        print(f"\n{'='*80}")
        print(f"REMAINING LOSSES ({len(losses)}) — these slip through all filters!")
        print(f"{'='*80}")
        for m in losses:
            bet = 8.0 if m.get("neg_risk") else 15.0
            print(f"\n  [{m['main_type']}/{m['sub_type']}] {m['question'][:70]}")
            print(f"    Price: {m['entry_price']:.3f} | Cat: {m['category']} | "
                  f"Vol: ${m['volume']:.0f} | NegRisk: {m['neg_risk']} | Loss: -${bet:.2f}")
    else:
        print("\n✅ NO LOSSES pass through all filters!")

    return main_stats, sub_stats, losses


def suggest_new_filters(losses):
    """Analyze remaining losses and suggest new filter patterns."""
    if not losses:
        print("\nNo new filters needed — all losses already caught!")
        return

    print(f"\n{'='*80}")
    print("SUGGESTED NEW FILTERS")
    print(f"{'='*80}")

    # Group by pattern
    patterns_found = defaultdict(list)
    for m in losses:
        q = m["question"].lower()
        if any(w in q for w in ['dip to', 'dip below', 'pump to']):
            patterns_found["dip_pump"].append(m)
        elif any(w in q for w in ['o/u', 'over/under']):
            patterns_found["over_under_non_sports"].append(m)
        elif 'spread' in q:
            patterns_found["spread_non_sports"].append(m)
        elif any(w in q for w in ['mrbeast', 'youtube', 'views', 'subscribers']):
            patterns_found["social_media_views"].append(m)
        elif any(w in q for w in ['between', 'exactly']):
            patterns_found["bracket_counting"].append(m)
        elif 'fery' in q or 'bu' in q:  # specific tennis names
            patterns_found["tennis_upset"].append(m)
        elif 'vs' in q or 'vs.' in q:
            patterns_found["generic_vs"].append(m)
        else:
            patterns_found["unknown"].append(m)

    for pattern, markets in patterns_found.items():
        loss_cost = sum(8.0 if m.get("neg_risk") else 15.0 for m in markets)
        print(f"\n  Pattern: {pattern} ({len(markets)} losses, -${loss_cost:.2f})")
        for m in markets[:3]:
            print(f"    {m['question'][:65]}")

        if pattern == "dip_pump":
            print("  → SUGGEST: Add r'\\bdip\\s+(to|below)\\b' to THRESHOLD_PATTERNS")
        elif pattern == "social_media_views":
            print("  → SUGGEST: Add r'\\bviews\\b', r'\\bsubscribers\\b' to TOXIC_KEYWORDS")
        elif pattern == "over_under_non_sports":
            print("  → SUGGEST: Extend SPORTS_BAD_PATTERNS to ALL categories, not just sports")


def main():
    all_markets, passed = load_and_filter()
    main_stats, sub_stats, losses = analyze_filtered(passed)

    suggest_new_filters(losses)

    # Save
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_resolved": len(all_markets),
        "passed_filters": len(passed),
        "filtered_out": len(all_markets) - len(passed),
        "remaining_losses": len(losses),
        "main_type_stats": main_stats,
        "sub_type_stats": sub_stats,
        "remaining_loss_details": [
            {
                "question": m["question"],
                "main_type": m["main_type"],
                "sub_type": m["sub_type"],
                "entry_price": m["entry_price"],
                "category": m["category"],
                "volume": m["volume"],
                "neg_risk": m["neg_risk"],
            }
            for m in losses
        ],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
