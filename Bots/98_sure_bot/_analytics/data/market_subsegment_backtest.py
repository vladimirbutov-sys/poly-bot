"""
Market Sub-Segment Backtest — 2026-03-23
Classifies all resolved scanner markets by sub-type and analyzes
win rate, resolve time, P&L per segment.

Key question: Should we only bet on MATCH OUTCOME (whole match/event winner)
and skip game/map/set-specific and prop bets?
"""
import json
import re
import sys
import os

# Fix Windows encoding
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')
sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')
from datetime import datetime
from collections import defaultdict

# Paths
SCANNER_DATA = r"C:\Users\Honor\Desktop\Polymarket\Bots\97_scanner\scanner_data.json"
POSITIONS_FILE = r"C:\Users\Honor\Desktop\Polymarket\Bots\98_sure_bot\positions.json"
OUTPUT_FILE = r"C:\Users\Honor\Desktop\Polymarket\Bots\98_sure_bot\_analytics\data\subsegment_backtest_2026-03-23.json"

# Bot config (current)
PRICE_THRESHOLD = 0.96
MAX_PRICE = 0.995
MIN_VOLUME = 3000
MIN_LIQUIDITY = 500

# ─── Classification rules ───

# Game/Map/Set specific patterns (sub-match events)
GAME_MAP_PATTERNS = [
    r'\bgame\s*[1-9]\b', r'\bgame\s*\d+\b',
    r'\bmap\s*[1-9]\b', r'\bmap\s*\d+\b',
    r'\bset\s*[1-9]\b', r'\bset\s*\d+\b',
    r'\bround\s*[1-9]\b', r'\bround\s*\d+\b',
    r'\bperiod\s*[1-9]\b', r'\bhalf\s*[12]\b',
    r'\b(1st|2nd|3rd|4th|5th)\s*(game|map|set|round|period|half|quarter|inning)\b',
    r'\bfirst\s*(game|map|set|round|period|half)\b',
]

# Prop/in-game event patterns
PROP_PATTERNS = [
    r'\bfirst\s*(blood|kill|baron|dragon|tower|rift|herald|roshan|goal|point)\b',
    r'\b(total|over|under)\s*\d+\.?\d*\s*(kills|goals|points|assists|rebounds|rounds|maps|games)\b',
    r'\b\d+\+?\s*(kills|goals|points|assists|rebounds|strikeouts|hits|aces|double faults)\b',
    r'\b(odd|even)\b.*\b(total|score|goals|points|kills|rounds)\b',
    r'\btotal\s*(goals|kills|points|score|rounds|maps|games)\b',
    r'\b(over|under)\s*\d',
    r'\bpenta.?kill\b',
    r'\bteaser\b',
    r'\bparlay\b',
    r'\bhandicap\b',
    r'\bspread\b',
    r'\bmost\s*(kills|goals|assists|points)\b',
    r'\bmvp\b',
    r'\bman of the match\b',
    r'\byellow card\b', r'\bred card\b',
    r'\bcorner\b.*\b(over|under|total)\b',
    r'\bboth teams (to )?score\b',
    r'\bclean sheet\b',
    r'\bpenalty\b',
    r'\bexact score\b',
    r'\bscore (first|last)\b',
    r'\bhighest scoring\b',
    r'\b(draw|tie)\b.*\b(no|not)\b',
]

# Threshold/price patterns (crypto, stocks, weather)
THRESHOLD_PATTERNS = [
    r'\b(close|stay|remain|be|go|dip|pump|reach|hit|drop|fall|rise|surge)\s*(above|below|between|under|over|at least|at most)\b',
    r'\bprice of\b',
    r'\b(bitcoin|btc|eth|ethereum|sol|solana|xrp|doge|bnb)\b.*\b\$[\d,]+',
    r'\b\$[\d,]+.*\b(bitcoin|btc|eth|ethereum|sol|solana)\b',
    r'\btemperature\b',
    r'\bhighest temp\b',
    r'\bweather\b',
    r'\b(nasdaq|s&p|dow|sp500|spy)\b.*\b(above|below|close)\b',
    r'\bgold\b.*\b(above|below|price)\b',
    r'\boil\b.*\b(above|below|price)\b',
]

# Draw/tie patterns
DRAW_PATTERNS = [
    r'\bend in a draw\b',
    r'\bend in a tie\b',
    r'\bdraw\?\s*$',
]

# "How many" / counting patterns (tweet counts, post counts, etc.)
COUNTING_PATTERNS = [
    r'\bhow many\b',
    r'\bexactly\s*\d+\b',
    r'\b\d+-\d+\s*(tweets?|posts?|truth social)\b',
    r'\bpost\s*\d+-\d+\b',
    r'\b(tweets?|posts?)\s*from\b',
    r'\btweet\b.*\bfrom\b.*\bto\b',
]

# Election / political specific
ELECTION_PATTERNS = [
    r'\b(win|advance|qualify)\b.*\b(election|primary|runoff|nomination|race)\b',
    r'\bbe the next\s*(president|prime minister|chancellor|mayor|governor|leader)\b',
    r'\bnext prime minister\b',
    r'\bnext president\b',
    r'\b(democrat|republican|labour|conservative|tory)\b.*\b(win|lose|nomination)\b',
]

# Match/event outcome patterns (whole match/event winner)
MATCH_OUTCOME_PATTERNS = [
    r'\bwin\b(?!.*\b(game\s*\d|map\s*\d|set\s*\d|round\s*\d|period\s*\d|half\s*\d|inning)\b)',
    r'\bbeat\b',
    r'\bdefeat\b',
    r'\badvance\b',
    r'\bqualify\b',
    r'\bchampion\b',
    r'\beliminate\b',
    r'\bvs\.?\b.*\b\(W\)\b',  # "Team A vs Team B (W)" pattern in title
]


def classify_market(question: str, category: str = "") -> tuple:
    """
    Classify a market question into (type, subtype).
    Returns (main_type, sub_type).
    """
    q = question.lower().strip()
    cat = category.lower() if category else ""

    # 1. Threshold / price markets
    for pat in THRESHOLD_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            if any(w in q for w in ['bitcoin', 'btc', 'eth', 'ethereum', 'sol', 'solana',
                                      'xrp', 'doge', 'crypto', 'bnb']):
                return ("threshold", "crypto_price")
            if any(w in q for w in ['temperature', 'temp', 'weather', 'rain', 'snow']):
                return ("threshold", "weather")
            if any(w in q for w in ['nasdaq', 's&p', 'dow', 'sp500', 'spy', 'stock', 'index']):
                return ("threshold", "stock_index")
            if any(w in q for w in ['gold', 'oil', 'crude', 'wti', 'brent']):
                return ("threshold", "commodity")
            return ("threshold", "other_threshold")

    # 2. Counting markets (tweets, posts, etc.)
    for pat in COUNTING_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            if any(w in q for w in ['tweet', 'truth social', 'post', 'white house']):
                return ("counting", "social_media_count")
            if any(w in q for w in ['earthquake', 'quake']):
                return ("counting", "earthquake_count")
            return ("counting", "other_count")

    # 3. Prop bets (in-game events)
    for pat in PROP_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            if cat in ('esports',) or any(w in q for w in ['esport', 'league of legends',
                    'dota', 'csgo', 'cs2', 'valorant', 'overwatch']):
                return ("prop", "esports_prop")
            if cat in ('soccer',) or any(w in q for w in ['goal', 'soccer', 'football',
                    'premier league', 'la liga', 'serie a', 'bundesliga']):
                return ("prop", "soccer_prop")
            return ("prop", "other_prop")

    # 4. Game/Map/Set specific (sub-match)
    for pat in GAME_MAP_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            if cat in ('esports',) or any(w in q for w in ['esport', 'league', 'dota',
                    'csgo', 'cs2', 'valorant', 'overwatch', 'stand', 'gaming',
                    'fearx', 'parivision', 'gamerlegion', 't1', 'gen.g', 'jdg']):
                return ("sub_match", "esports_game_map")
            if any(w in q for w in ['tennis', 'atp', 'wta', 'open', 'slam']):
                return ("sub_match", "tennis_set")
            return ("sub_match", "other_sub_match")

    # 5. Draw markets
    for pat in DRAW_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            return ("draw", "draw")

    # 6. Election / political outcome
    for pat in ELECTION_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            return ("match_outcome", "election")

    # 7. Match/event outcome (whole match winner)
    for pat in MATCH_OUTCOME_PATTERNS:
        if re.search(pat, q, re.IGNORECASE):
            # Sub-classify by sport/category
            if cat in ('esports',) or any(w in q for w in ['esport', 'gaming',
                    'league of legends', 'dota', 'csgo', 'valorant', 'stand', 'fearx']):
                return ("match_outcome", "esports_match")
            if cat in ('soccer',):
                return ("match_outcome", "soccer_match")
            if cat in ('sports_other',) or any(w in q for w in ['basketball', 'nba',
                    'baseball', 'mlb', 'hockey', 'nhl', 'football', 'nfl', 'golf',
                    'pga', 'championship', 'tournament', 'mocs', 'bison', 'ncaa',
                    'college', 'tennis', 'atp', 'wta', 'boxing', 'ufc', 'mma']):
                return ("match_outcome", "sports_match")
            if cat in ('politics', 'geopolitics'):
                return ("match_outcome", "election")
            return ("match_outcome", "other_match")

    # 8. Fallback classification by category
    if cat in ('politics', 'geopolitics'):
        return ("other", "politics_other")
    if cat in ('esports',):
        return ("other", "esports_other")
    if cat in ('sports_other', 'soccer', 'basketball', 'tennis', 'fighting',
               'american_football'):
        return ("other", "sports_other")
    if cat in ('crypto',):
        return ("other", "crypto_other")
    if cat in ('tech',):
        return ("other", "tech_other")

    return ("other", "uncategorized")


def load_scanner_data():
    """Load scanner data and extract resolved markets."""
    print("Loading scanner_data.json...")
    with open(SCANNER_DATA, "r", encoding="utf-8") as f:
        raw = json.load(f)

    markets_dict = raw.get("markets", raw)
    print(f"Total markets in scanner: {len(markets_dict)}")

    resolved = []
    for mid, m in markets_dict.items():
        snaps = m.get("snapshots", [])
        if not snaps:
            continue

        # Find max price seen
        max_price = m.get("max_price_seen", 0)
        if max_price < PRICE_THRESHOLD:
            continue

        # Check if resolved (last snapshot should indicate resolution)
        last_snap = snaps[-1]
        first_snap = snaps[0]

        # Determine if market resolved as win or loss for the high-price outcome
        # In scanner, "resolved" means the market closed
        # We need to check if the high-priced outcome won (price went to 1.0) or lost (price went to 0.0)
        final_prices = last_snap.get("prices", [])
        if not final_prices or len(final_prices) < 2:
            continue

        # Find which outcome was the "high" one
        high_outcome = m.get("high_outcome", "")
        outcomes = m.get("outcomes", [])

        # Check if resolved: one price should be ~1.0 or ~0.0
        max_final = max(float(p) for p in final_prices)
        min_final = min(float(p) for p in final_prices)

        if max_final < 0.95:  # not resolved yet
            continue

        # Determine win/loss
        # Find the index of the high-priced outcome
        first_prices = first_snap.get("prices", [])
        if not first_prices or len(first_prices) < 2:
            continue

        high_idx = 0
        if len(first_prices) >= 2 and float(first_prices[1]) > float(first_prices[0]):
            high_idx = 1

        final_high_price = float(final_prices[high_idx])
        won = final_high_price > 0.5  # if final price > 0.5, the high outcome won

        # Get the entry price (max price at which bot would enter)
        entry_price = max_price
        if entry_price > MAX_PRICE:
            # Find the highest price still within range
            best_entry = 0
            for snap in snaps:
                sp = snap.get("prices", [])
                if sp and len(sp) > high_idx:
                    p = float(sp[high_idx])
                    if PRICE_THRESHOLD <= p <= MAX_PRICE:
                        best_entry = max(best_entry, p)
            if best_entry == 0:
                continue
            entry_price = best_entry

        if entry_price < PRICE_THRESHOLD or entry_price > MAX_PRICE:
            continue

        # Calculate resolve time
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

        # Get volume/liquidity from snapshots
        volume = m.get("volume", 0)
        liquidity = 0
        for snap in snaps:
            liq = snap.get("liquidity", 0)
            if liq and liq > liquidity:
                liquidity = liq

        question = m.get("question", "")
        category = m.get("category", "")
        end_date = m.get("end_date", "")
        neg_risk = m.get("neg_risk", False)

        # Check end_date bucket
        end_date_hours = None
        if end_date and first_ts:
            try:
                ed = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
                ft = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
                end_date_hours = (ed - ft).total_seconds() / 3600
            except (ValueError, TypeError):
                pass

        main_type, sub_type = classify_market(question, category)

        resolved.append({
            "market_id": mid,
            "question": question,
            "category": category,
            "main_type": main_type,
            "sub_type": sub_type,
            "entry_price": entry_price,
            "won": won,
            "resolve_hours": resolve_hours,
            "volume": float(volume) if volume else 0,
            "liquidity": liquidity,
            "neg_risk": neg_risk if isinstance(neg_risk, bool) else False,
            "end_date_hours": end_date_hours,
        })

    print(f"Resolved markets eligible for bot: {len(resolved)}")
    return resolved


def load_bot_positions():
    """Load actual bot positions for comparison."""
    print("Loading positions.json...")
    with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    positions = []
    for pid, pos in data.get("positions", {}).items():
        status = pos.get("status", "")
        if status not in ("won", "lost"):
            continue

        question = pos.get("title", "")
        category = pos.get("category", "")
        main_type, sub_type = classify_market(question, category)

        positions.append({
            "order_id": pid,
            "question": question,
            "category": category,
            "main_type": main_type,
            "sub_type": sub_type,
            "entry_price": pos.get("entry_price", 0),
            "cost_usd": pos.get("cost_usd", 0),
            "pnl": pos.get("pnl", 0),
            "won": status == "won",
            "neg_risk": pos.get("neg_risk", False),
        })

    print(f"Bot resolved positions: {len(positions)}")
    return positions


def calc_stats(markets: list, bet_size_reg=15.0, bet_size_neg=8.0) -> dict:
    """Calculate aggregate stats for a group of markets."""
    if not markets:
        return {"count": 0, "wins": 0, "losses": 0, "win_rate": 0,
                "pnl": 0, "avg_resolve_h": 0, "median_resolve_h": 0,
                "loss_rate": 0, "roi_pct": 0}

    wins = sum(1 for m in markets if m["won"])
    losses = len(markets) - wins
    total = len(markets)

    # Estimate P&L
    total_pnl = 0
    total_cost = 0
    for m in markets:
        bet = bet_size_neg if m.get("neg_risk") else bet_size_reg
        shares = bet / m["entry_price"]
        cost = bet
        if m["won"]:
            payout = shares * 1.0  # each share redeems at $1
            pnl = payout - cost
        else:
            pnl = -cost
        total_pnl += pnl
        total_cost += cost

    # Resolve times
    resolve_times = [m["resolve_hours"] for m in markets
                     if m.get("resolve_hours") is not None and m["resolve_hours"] > 0]
    avg_resolve = sum(resolve_times) / len(resolve_times) if resolve_times else 0
    median_resolve = sorted(resolve_times)[len(resolve_times) // 2] if resolve_times else 0

    roi = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    return {
        "count": total,
        "wins": wins,
        "losses": losses,
        "win_rate": wins / total * 100 if total > 0 else 0,
        "loss_rate": losses / total * 100 if total > 0 else 0,
        "pnl": round(total_pnl, 2),
        "cost": round(total_cost, 2),
        "roi_pct": round(roi, 2),
        "avg_resolve_h": round(avg_resolve, 1),
        "median_resolve_h": round(median_resolve, 1),
    }


def analyze_subsegments(markets: list):
    """Group markets by main_type and sub_type, calc stats for each."""
    by_main = defaultdict(list)
    by_sub = defaultdict(list)

    for m in markets:
        by_main[m["main_type"]].append(m)
        by_sub[m["sub_type"]].append(m)

    print("\n" + "=" * 80)
    print("ANALYSIS BY MAIN TYPE")
    print("=" * 80)
    print(f"{'Type':<20} {'Count':>6} {'W':>5} {'L':>3} {'WR%':>7} {'LR%':>7} "
          f"{'PnL':>9} {'ROI%':>7} {'MedRes':>7}")
    print("-" * 80)

    main_stats = {}
    for t in sorted(by_main.keys(), key=lambda x: len(by_main[x]), reverse=True):
        s = calc_stats(by_main[t])
        main_stats[t] = s
        print(f"{t:<20} {s['count']:>6} {s['wins']:>5} {s['losses']:>3} "
              f"{s['win_rate']:>6.2f}% {s['loss_rate']:>6.3f}% "
              f"${s['pnl']:>+8.2f} {s['roi_pct']:>+6.2f}% {s['median_resolve_h']:>6.1f}h")

    # Total
    total_s = calc_stats(markets)
    print("-" * 80)
    print(f"{'TOTAL':<20} {total_s['count']:>6} {total_s['wins']:>5} {total_s['losses']:>3} "
          f"{total_s['win_rate']:>6.2f}% {total_s['loss_rate']:>6.3f}% "
          f"${total_s['pnl']:>+8.2f} {total_s['roi_pct']:>+6.2f}% {total_s['median_resolve_h']:>6.1f}h")

    print("\n" + "=" * 80)
    print("ANALYSIS BY SUB-TYPE")
    print("=" * 80)
    print(f"{'Sub-type':<25} {'Count':>6} {'W':>5} {'L':>3} {'WR%':>7} {'LR%':>7} "
          f"{'PnL':>9} {'ROI%':>7} {'MedRes':>7}")
    print("-" * 80)

    sub_stats = {}
    for t in sorted(by_sub.keys(), key=lambda x: len(by_sub[x]), reverse=True):
        s = calc_stats(by_sub[t])
        sub_stats[t] = s
        print(f"{t:<25} {s['count']:>6} {s['wins']:>5} {s['losses']:>3} "
              f"{s['win_rate']:>6.2f}% {s['loss_rate']:>6.3f}% "
              f"${s['pnl']:>+8.2f} {s['roi_pct']:>+6.2f}% {s['median_resolve_h']:>6.1f}h")

    return main_stats, sub_stats


def analyze_losses(markets: list):
    """Detailed analysis of all losses."""
    losses = [m for m in markets if not m["won"]]
    if not losses:
        print("\nNo losses found!")
        return

    print(f"\n{'=' * 80}")
    print(f"LOSS ANALYSIS — {len(losses)} losses")
    print(f"{'=' * 80}")

    for m in losses:
        bet = 8.0 if m.get("neg_risk") else 15.0
        print(f"\n  [{m['main_type']}/{m['sub_type']}] {m['question'][:70]}")
        print(f"    Price: {m['entry_price']:.3f} | Category: {m['category']} | "
              f"Vol: ${m['volume']:.0f} | NegRisk: {m['neg_risk']}")
        print(f"    Loss: -${bet:.2f} | Resolve: {m.get('resolve_hours', '?')}h")


def scenario_comparison(markets: list):
    """Compare scenarios: all markets vs match_outcome only vs filtered."""
    print(f"\n{'=' * 80}")
    print("SCENARIO COMPARISON")
    print(f"{'=' * 80}")

    scenarios = {
        "A. Current (all)": markets,
        "B. Match outcome only": [m for m in markets if m["main_type"] == "match_outcome"],
        "C. No sub_match": [m for m in markets if m["main_type"] != "sub_match"],
        "D. No props": [m for m in markets if m["main_type"] != "prop"],
        "E. No sub_match + no props": [m for m in markets
                                         if m["main_type"] not in ("sub_match", "prop")],
        "F. No threshold": [m for m in markets if m["main_type"] != "threshold"],
        "G. No counting": [m for m in markets if m["main_type"] != "counting"],
        "H. Match+draw+election only": [m for m in markets
                                         if m["main_type"] in ("match_outcome", "draw")],
        "I. Sports match only": [m for m in markets
                                  if m["sub_type"] in ("sports_match", "esports_match",
                                                       "soccer_match")],
    }

    print(f"\n{'Scenario':<30} {'Count':>6} {'W':>5} {'L':>3} {'WR%':>7} "
          f"{'PnL':>9} {'ROI%':>7} {'MedRes':>7} {'Losses removed':>15}")
    print("-" * 100)

    base_losses = sum(1 for m in markets if not m["won"])
    for name, subset in scenarios.items():
        s = calc_stats(subset)
        removed = len(markets) - len(subset)
        losses_removed = base_losses - s["losses"]
        print(f"{name:<30} {s['count']:>6} {s['wins']:>5} {s['losses']:>3} "
              f"{s['win_rate']:>6.2f}% ${s['pnl']:>+8.2f} {s['roi_pct']:>+6.2f}% "
              f"{s['median_resolve_h']:>6.1f}h {losses_removed:>+14}L")


def bot_positions_analysis(positions: list):
    """Analyze actual bot trades by sub-type."""
    if not positions:
        print("\nNo bot positions to analyze.")
        return {}

    print(f"\n{'=' * 80}")
    print(f"BOT ACTUAL TRADES — {len(positions)} resolved")
    print(f"{'=' * 80}")

    by_sub = defaultdict(list)
    for p in positions:
        by_sub[p["sub_type"]].append(p)

    print(f"{'Sub-type':<25} {'Count':>6} {'W':>5} {'L':>3} {'WR%':>7} {'PnL':>9}")
    print("-" * 60)

    bot_stats = {}
    for t in sorted(by_sub.keys(), key=lambda x: len(by_sub[x]), reverse=True):
        group = by_sub[t]
        wins = sum(1 for p in group if p["won"])
        losses = len(group) - wins
        pnl = sum(p.get("pnl", 0) for p in group)
        wr = wins / len(group) * 100 if group else 0
        bot_stats[t] = {"count": len(group), "wins": wins, "losses": losses,
                         "win_rate": wr, "pnl": round(pnl, 2)}
        print(f"{t:<25} {len(group):>6} {wins:>5} {losses:>3} {wr:>6.2f}% ${pnl:>+8.2f}")

    # Show bot losses
    bot_losses = [p for p in positions if not p["won"]]
    if bot_losses:
        print(f"\nBot losses ({len(bot_losses)}):")
        for p in bot_losses:
            print(f"  [{p['main_type']}/{p['sub_type']}] {p['question'][:60]}")
            print(f"    Price: {p['entry_price']:.3f} | PnL: ${p['pnl']:.2f} | "
                  f"NegRisk: {p['neg_risk']}")

    return bot_stats


def price_bucket_by_type(markets: list):
    """Cross-tabulate price buckets vs market types."""
    print(f"\n{'=' * 80}")
    print("PRICE BUCKETS × MARKET TYPE (losses only)")
    print(f"{'=' * 80}")

    buckets = [
        ("96.0-97.5c", 0.96, 0.975),
        ("97.5-98.0c", 0.975, 0.98),
        ("98.0-98.5c", 0.98, 0.985),
        ("98.5-99.0c", 0.985, 0.99),
        ("99.0-99.5c", 0.99, 0.995),
    ]
    types = sorted(set(m["main_type"] for m in markets))

    print(f"{'Bucket':<12}", end="")
    for t in types:
        print(f" {t:>14}", end="")
    print(f" {'TOTAL':>8}")
    print("-" * (12 + 15 * len(types) + 9))

    for bname, lo, hi in buckets:
        print(f"{bname:<12}", end="")
        row_total = 0
        for t in types:
            group = [m for m in markets
                     if m["main_type"] == t and lo <= m["entry_price"] < hi]
            losses = sum(1 for m in group if not m["won"])
            total = len(group)
            row_total += losses
            if losses > 0:
                print(f" {losses}/{total:>5}({losses/total*100:.1f}%)", end="")
            else:
                print(f"     0/{total:>5}", end="")
        print(f" {row_total:>7}L")


def main():
    # Load data
    scanner_markets = load_scanner_data()
    bot_positions = load_bot_positions()

    # Filter by bot criteria (volume, liquidity)
    eligible = [m for m in scanner_markets
                if m["volume"] >= MIN_VOLUME or m["volume"] == 0]  # 0 = missing data, don't exclude
    print(f"After volume filter (>=${MIN_VOLUME}): {len(eligible)}")

    # Main analysis
    main_stats, sub_stats = analyze_subsegments(eligible)

    # Loss analysis
    analyze_losses(eligible)

    # Scenario comparison
    scenario_comparison(eligible)

    # Bot positions analysis
    bot_stats = bot_positions_analysis(bot_positions)

    # Price bucket cross-tab
    price_bucket_by_type(eligible)

    # Save results
    results = {
        "timestamp": datetime.utcnow().isoformat(),
        "total_markets": len(eligible),
        "total_losses": sum(1 for m in eligible if not m["won"]),
        "main_type_stats": main_stats,
        "sub_type_stats": sub_stats,
        "bot_trade_stats": bot_stats,
        "losses": [
            {
                "question": m["question"],
                "main_type": m["main_type"],
                "sub_type": m["sub_type"],
                "entry_price": m["entry_price"],
                "category": m["category"],
                "volume": m["volume"],
                "neg_risk": m["neg_risk"],
            }
            for m in eligible if not m["won"]
        ],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
