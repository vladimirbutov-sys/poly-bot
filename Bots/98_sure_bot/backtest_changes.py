"""
Backtest: compare OLD rules vs NEW rules (dynamic bet + nr off + ed 7d)
against 6800+ resolved markets from scanner_data.json.

Tests three configurations:
  OLD: $5 fixed bet, neg_risk cap $300, end_date 1 day
  NEW: dynamic bet $5/$10/$15 by liquidity, no neg_risk cap, end_date 7 days
  HYBRID: same as NEW but with $5 fixed (isolate filter impact from bet sizing)
"""
import json
import sys
import os
import re
from datetime import datetime, timezone, timedelta
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ========== Load scanner data (6800+ resolved markets) ==========
SCANNER_DATA = os.path.join(os.path.dirname(__file__), "..", "97_scanner", "scanner_data.json")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc_data = json.load(f)

# ========== Constants ==========
MIN_LIQUIDITY = 500
MIN_VOLUME = 3000
PRICE_THRESHOLD_DEFAULT = 0.975
PRICE_THRESHOLD_POLITICS = 0.96
MAX_PRICE = 0.993

# Dynamic bet sizing thresholds
LIQ_THRESHOLD_MID = 2000
LIQ_THRESHOLD_HIGH = 10000

# Coin-flip, threshold, weather, financial, slow patterns (from filters.py)
COIN_FLIP_PATTERNS = [
    r'\bodd\s+or\s+even\b', r'\bodd/even\b', r'\bfirst\s+blood\b',
    r'\bfirst\s+kill\b', r'\bfirst\s+baron\b', r'\bfirst\s+dragon\b',
    r'\bfirst\s+tower\b', r'\bfirst\s+rift\s+herald\b', r'\bcoin\s+flip\b',
    r'\brampage\b', r'\bfirst\s+roshan\b', r'\bfirst\s+map\b', r'\bup\s+or\s+down\b',
]
THRESHOLD_PATTERNS = [
    r'\bclose\s+above\b', r'\bclose\s+below\b', r'\bbe\s+above\b',
    r'\bbe\s+below\b', r'\bbe\s+between\b', r'\bbe\s+greater\s+than\b',
    r'\bbe\s+less\s+than\b', r'\bprice\s+of\b', r'\breach\b.*\$[\d,]+',
    r'\bhit\b.*\$[\d,]+', r'\bfall\s+(to|below)\b.*\$[\d,]+',
    r'\bdrop\s+(to|below)\b.*\$[\d,]+', r'\brise\s+(to|above)\b.*\$[\d,]+',
]
WEATHER_PATTERNS = [
    r'\btemperature\b.*\d+\s*[°]?\s*[FC]\b',
    r'\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b',
]
SLOW_KEYWORDS = [r'\btop\b', r'\bseason\b', r'\bmost\b', r'\btransit\b',
                 r'\bstrait\b', r'\bships?\b', r'\bweekly\b', r'\bmonthly\b']
FINANCIAL_ASSETS = [
    r'\bbitcoin\b', r'\bethereum\b', r'\bsolana\b', r'\bxrp\b',
    r'\bbtc\b', r'\beth\b', r'\bsol\b', r'\bdogecoin\b',
    r'\bs&p\s*500\b', r'\bnasdaq\b', r'\bcrude\s*oil\b',
    r'\bgold\s*price\b', r'\bnatural\s*gas\b', r'\bmicrostrategy\b',
    r'\btsla\b', r'\bnvda\b', r'\baapl\b', r'\bamzn\b',
]
ESPORTS_BAD_PATTERNS = [
    r'\bo/u\b', r'\bover/under\b', r'\bover\s*/\s*under\b',
    r'\bspread\b', r'\btotal\s+(maps?|kills?|rounds?|points?)\b', r'\bhandi?cap\b',
]

POLITICS_CATEGORIES = {"politics", "geopolitics"}
EARLY_SPORTS_CATEGORIES = {"esports", "sports_other", "basketball", "hockey",
                           "american_football", "tennis", "fighting", "cricket"}


def categorize(question):
    """Keyword-based categorization (same as scanner.py)."""
    q = question.lower()
    pol_kw = ["president", "elect", "vote", "congress", "senate", "governor",
              "political", "trump", "biden", "democrat", "republican", "gop",
              "parliament", "minister", "legislation", "impeach", "partisan"]
    geo_kw = ["war", "sanctions", "nato", "military", "invasion", "ceasefire",
              "treaty", "diplomat", "territory", "annex", "tariff", "geopolit"]
    if any(k in q for k in pol_kw):
        return "politics"
    if any(k in q for k in geo_kw):
        return "geopolitics"
    sports_map = {
        "esports": ["esports", "league of legends", "dota", "cs2", "csgo", "valorant"],
        "soccer": ["soccer", "premier league", "la liga", "bundesliga", "serie a", "champions league", "uefa", "fifa"],
        "basketball": ["nba", "basketball", "ncaa basketball"],
        "hockey": ["nhl", "hockey"],
        "american_football": ["nfl", "football", "super bowl", "ncaa football"],
        "tennis": ["tennis", "atp", "wta", "grand slam"],
        "fighting": ["ufc", "boxing", "mma"],
        "cricket": ["cricket", "ipl", "t20"],
    }
    for cat, keywords in sports_map.items():
        if any(k in q for k in keywords):
            return cat
    return "other"


def matches_any(text, patterns):
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def apply_filters(market, config):
    """Apply filters to a market. Returns (passed, reason, bet_size)."""
    question = market.get("question", "")
    q_lower = question.lower()
    category = categorize(question)
    liquidity = market.get("liquidity", 0) or 0
    volume = market.get("volume", 0) or 0
    neg_risk = market.get("neg_risk", False)
    end_date_str = market.get("end_date", "")
    max_price = market.get("max_price_seen", 0)

    max_ed_days = config["max_end_date_days"]
    use_nr_cap = config["use_neg_risk_cap"]
    nr_cap = config.get("nr_cap", 300)
    fixed_bet = config.get("fixed_bet", None)  # None = dynamic

    # Price check: must have reached our threshold
    if category in POLITICS_CATEGORIES:
        if max_price < PRICE_THRESHOLD_POLITICS:
            return False, "Price too low (politics)", 0
        entry_price = max(PRICE_THRESHOLD_POLITICS, 0.96)
    else:
        if max_price < PRICE_THRESHOLD_DEFAULT:
            return False, "Price too low", 0
        entry_price = PRICE_THRESHOLD_DEFAULT

    # Liquidity
    if liquidity < MIN_LIQUIDITY:
        return False, "Low liquidity", 0

    # Volume
    if volume < MIN_VOLUME:
        return False, "Low volume", 0

    # End date
    if end_date_str:
        try:
            ed = end_date_str.replace("Z", "+00:00")
            if "T" in ed:
                end_dt = datetime.fromisoformat(ed)
            else:
                end_dt = datetime.strptime(ed, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)

            # Use first_seen as "now" for historical simulation
            fs = market.get("first_seen", "")
            if fs:
                now = datetime.fromisoformat(fs.replace("Z", "+00:00"))
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
            else:
                now = datetime.now(timezone.utc)

            days_ahead = (end_dt - now).total_seconds() / 86400

            # Politics: up to 7 days always
            if category in POLITICS_CATEGORIES:
                if days_ahead > 7:
                    return False, "End date too far (politics)", 0
            # Sports with game_start
            elif category in EARLY_SPORTS_CATEGORIES:
                gst = market.get("game_start_time", "")
                if gst:
                    try:
                        gst_dt = datetime.fromisoformat(gst.replace("Z", "+00:00"))
                        if gst_dt.tzinfo is None:
                            gst_dt = gst_dt.replace(tzinfo=timezone.utc)
                        hours_before_end = (end_dt - gst_dt).total_seconds() / 3600
                        if hours_before_end >= 6:
                            if days_ahead > 3:
                                return False, "End date too far (sports)", 0
                        elif days_ahead > max_ed_days:
                            return False, "End date too far", 0
                    except:
                        if days_ahead > max_ed_days:
                            return False, "End date too far", 0
                elif days_ahead > max_ed_days:
                    return False, "End date too far", 0
            else:
                if days_ahead > max_ed_days:
                    return False, "End date too far", 0

            # Stuck: more than 3 days past end_date
            if days_ahead < -3:
                return False, "Stuck market", 0
        except:
            return False, "Bad end_date", 0

    # Coin-flip
    if matches_any(q_lower, COIN_FLIP_PATTERNS):
        return False, "Coin-flip", 0

    # Threshold
    if matches_any(q_lower, THRESHOLD_PATTERNS):
        return False, "Threshold market", 0

    # Weather
    if matches_any(question, WEATHER_PATTERNS):
        return False, "Weather", 0

    # Financial
    if matches_any(q_lower, FINANCIAL_ASSETS):
        if volume < 50000:
            return False, "Financial asset", 0

    # Slow keywords
    if matches_any(q_lower, SLOW_KEYWORDS):
        return False, "Slow keyword", 0

    # Esports win only
    if category == "esports":
        if matches_any(q_lower, ESPORTS_BAD_PATTERNS):
            return False, "Esports non-win", 0

    # Bet size
    if fixed_bet:
        bet = fixed_bet
    else:
        if liquidity >= LIQ_THRESHOLD_HIGH:
            bet = 15
        elif liquidity >= LIQ_THRESHOLD_MID:
            bet = 10
        else:
            bet = 5

    return True, "OK", bet


# ========== Run backtest ==========
markets = sc_data.get("markets", {})
resolved = {mid: m for mid, m in markets.items()
            if m.get("resolution") and isinstance(m["resolution"], dict) and m["resolution"].get("closed")}

print("=" * 80)
print("BACKTEST: OLD vs NEW rules on", len(resolved), "resolved markets")
print("=" * 80)

configs = {
    "OLD ($5, nr cap $300, ed 1d)": {
        "max_end_date_days": 1,
        "use_neg_risk_cap": True,
        "nr_cap": 300,
        "fixed_bet": 5,
    },
    "NEW (dynamic bet, nr off, ed 7d)": {
        "max_end_date_days": 7,
        "use_neg_risk_cap": False,
        "fixed_bet": None,  # dynamic
    },
    "HYBRID ($5 fixed, nr off, ed 7d)": {
        "max_end_date_days": 7,
        "use_neg_risk_cap": False,
        "fixed_bet": 5,
    },
}

for config_name, config in configs.items():
    wins = 0
    losses = 0
    total_profit = 0
    total_invested = 0
    total_bets = 0
    bet_sizes = []
    categories_seen = Counter()
    loss_details = []
    filter_reasons = Counter()

    for mid, m in resolved.items():
        res = m["resolution"]
        passed, reason, bet_size = apply_filters(m, config)

        if not passed:
            filter_reasons[reason] += 1
            continue

        # Determine if this market was a win or loss
        final_prices = res.get("final_prices", [])
        winner = res.get("winner", "")
        high_outcome = m.get("high_outcome", "")

        # We always buy the high-probability outcome
        # If high_outcome matches winner -> we won
        if high_outcome and winner:
            won = (high_outcome == winner)
        elif final_prices:
            # highest final price should be ~1.0 for the winning outcome
            won = max(final_prices) > 0.9
        else:
            continue  # can't determine

        category = categorize(m.get("question", ""))
        categories_seen[category] += 1

        # Calculate P&L
        max_price = m.get("max_price_seen", 0.985)
        entry_price = min(max_price, 0.99)  # realistic entry
        if category in POLITICS_CATEGORIES:
            entry_price = max(entry_price, PRICE_THRESHOLD_POLITICS)
        else:
            entry_price = max(entry_price, PRICE_THRESHOLD_DEFAULT)

        shares = bet_size / entry_price
        if won:
            profit = shares * (1.0 - entry_price)  # shares resolve to $1 each
            wins += 1
        else:
            profit = -bet_size  # lose entire bet
            losses += 1
            loss_details.append({
                "question": m.get("question", "")[:70],
                "category": category,
                "entry": entry_price,
                "bet": bet_size,
            })

        total_profit += profit
        total_invested += bet_size
        total_bets += 1
        bet_sizes.append(bet_size)

    win_rate = wins / (wins + losses) * 100 if (wins + losses) > 0 else 0
    avg_bet = sum(bet_sizes) / len(bet_sizes) if bet_sizes else 0

    print(f"\n{'=' * 80}")
    print(f"  {config_name}")
    print(f"{'=' * 80}")
    print(f"  Markets passed filters: {total_bets}")
    print(f"  Wins: {wins} | Losses: {losses} | Win rate: {win_rate:.3f}%")
    print(f"  Total invested: ${total_invested:,.0f}")
    print(f"  Total profit:   ${total_profit:+,.2f}")
    print(f"  ROI:            {total_profit / total_invested * 100 if total_invested else 0:+.2f}%")
    print(f"  Avg bet size:   ${avg_bet:.1f}")

    print(f"\n  By category:")
    for cat, count in categories_seen.most_common():
        print(f"    {cat:25s}: {count:5d} bets")

    if loss_details:
        print(f"\n  Losses ({len(loss_details)}):")
        for ld in loss_details:
            print(f"    [{ld['category']:12s}] ${ld['bet']:>2.0f} @ {ld['entry']:.3f} | {ld['question']}")

    print(f"\n  Top filter rejection reasons:")
    for reason, count in filter_reasons.most_common(8):
        print(f"    {reason:30s}: {count:5d}")

# ========== Risk comparison ==========
print(f"\n{'=' * 80}")
print("RISK COMPARISON: max drawdown scenarios")
print("=" * 80)

for config_name, config in configs.items():
    # Simulate sequential betting to find max drawdown
    capital = 500
    peak = capital
    max_drawdown = 0
    bets_placed = 0

    for mid, m in sorted(resolved.items(), key=lambda x: x[1].get("first_seen", "")):
        res = m["resolution"]
        passed, reason, bet_size = apply_filters(m, config)
        if not passed:
            continue

        high_outcome = m.get("high_outcome", "")
        winner = res.get("winner", "")
        final_prices = res.get("final_prices", [])

        if high_outcome and winner:
            won = (high_outcome == winner)
        elif final_prices:
            won = max(final_prices) > 0.9
        else:
            continue

        category = categorize(m.get("question", ""))
        max_price = m.get("max_price_seen", 0.985)
        entry_price = min(max_price, 0.99)
        if category in POLITICS_CATEGORIES:
            entry_price = max(entry_price, PRICE_THRESHOLD_POLITICS)
        else:
            entry_price = max(entry_price, PRICE_THRESHOLD_DEFAULT)

        shares = bet_size / entry_price
        if won:
            capital += shares * (1.0 - entry_price)
        else:
            capital -= bet_size

        if capital > peak:
            peak = capital
        dd = peak - capital
        if dd > max_drawdown:
            max_drawdown = dd
        bets_placed += 1

    print(f"  {config_name:45s}: {bets_placed:5d} bets | final ${capital:>8.2f} | max drawdown ${max_drawdown:>6.2f}")

print(f"\n{'=' * 80}")
print("BACKTEST COMPLETE")
print("=" * 80)
