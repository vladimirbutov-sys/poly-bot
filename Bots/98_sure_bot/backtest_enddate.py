"""
Backtest: END_DATE default 7 days → 3 days.

Strategy: take all markets that pass base filters (without end_date),
then analyze how end_date filter affects them at different thresholds.

This shows exactly how many profitable markets we lose/keep at each setting.
"""
import json
import sys
import re
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SCANNER_DATA = "C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json"
OUTPUT_FILE = "C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/backtest_enddate_2026-03-20.json"

BET_SIZE = 10.0

POLITICS_CATEGORIES = {"politics", "geopolitics"}
EARLY_SPORTS_CATEGORIES = {"esports", "sports_other", "basketball", "hockey",
                           "american_football", "tennis", "fighting", "cricket"}
ALL_SPORTS_CATEGORIES = EARLY_SPORTS_CATEGORIES | {"soccer"}

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
FINANCIAL_ASSETS = [
    r'\bbitcoin\b', r'\bethereum\b', r'\bsolana\b', r'\bxrp\b',
    r'\bbtc\b', r'\beth\b', r'\bsol\b', r'\bdogecoin\b',
    r'\baapl\b', r'\bamzn\b', r'\bgoogl\b', r'\bnflx\b',
    r'\bmsft\b', r'\btsla\b', r'\bnvda\b',
    r'\bs&p\s*500\b', r'\bnasdaq\b', r'\bdow\s*jones\b',
    r'\bcrude\s*oil\b', r'\bgold\s*price\b', r'\bnatural\s*gas\b',
]
SLOW_KEYWORDS = [r'\btop\b', r'\bseason\b', r'\bmost\b',
    r'\btransit\b', r'\bstrait\b', r'\bships?\b', r'\bweekly\b', r'\bmonthly\b']
WEATHER_PATTERNS = [
    r'\btemperature\b.*\d+\s*[°]?\s*[FC]\b',
    r'\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b',
]


def matches_any(text, patterns):
    text_lower = text.lower()
    for p in patterns:
        if re.search(p, text_lower):
            return True
    return False


def parse_dt(s):
    if not s:
        return None
    try:
        s = str(s).replace("Z", "+00:00")
        if "T" in s:
            dt = datetime.fromisoformat(s)
        else:
            dt = datetime.strptime(s, "%Y-%m-%d")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except:
        return None


# =====================================================
# Load data
# =====================================================
print("Loading scanner data...")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc = json.load(f)

markets_raw = sc.get("markets", {})
print(f"Total markets: {len(markets_raw)}")

# =====================================================
# Build resolved dataset that passes base filters (NO end_date filter)
# This matches what previous backtest did
# =====================================================
resolved = []
for mid, m in markets_raw.items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue

    max_price = m.get("max_price_seen", 0)
    first_price = m.get("first_price", 0) or 0
    won = m.get("high_outcome_won")
    if won is None:
        high_outcome = m.get("high_outcome", "")
        winner = res.get("winner", "")
        if high_outcome and winner:
            won = (high_outcome == winner)
        else:
            continue

    category = (m.get("category", "other") or "other").lower()
    question = m.get("question", "")
    neg_risk = m.get("neg_risk", False)
    volume = m.get("volume", 0) or 0
    liquidity = m.get("liquidity", 0) or 0

    # === BASE FILTERS (same as previous backtest, no end_date) ===

    # neg_risk
    if neg_risk:
        continue

    # Price thresholds
    if category in POLITICS_CATEGORIES:
        if max_price < 0.96:
            continue
    else:
        if max_price < 0.975:
            continue

    # Max price (use first_price as entry proxy like previous backtest)
    entry_price = first_price if first_price >= 0.975 else max_price
    if entry_price > 0.993:
        continue

    # Volume & liquidity
    if volume < 3000:
        continue
    if liquidity < 500:
        continue

    # Text filters
    if matches_any(question, COIN_FLIP_PATTERNS):
        continue
    if matches_any(question, THRESHOLD_PATTERNS):
        continue
    if matches_any(question, WEATHER_PATTERNS):
        continue
    if matches_any(question, SLOW_KEYWORDS):
        continue
    if matches_any(question, FINANCIAL_ASSETS) and volume < 50000:
        continue

    # Esports O/U (current filter)
    if category == "esports" and matches_any(question, [
        r'\bo/u\b', r'\bover/under\b', r'\bover\s*/\s*under\b',
        r'\bspread\b', r'\btotal\s+(maps?|kills?|rounds?|points?)\b',
        r'\bhandi?cap\b',
    ]):
        continue

    # Compute resolve time
    first_seen = parse_dt(m.get("first_seen", ""))
    resolved_at = parse_dt(res.get("resolved_at", "") or res.get("closed_time", ""))
    resolve_hours = None
    if first_seen and resolved_at:
        resolve_hours = max(0, (resolved_at - first_seen).total_seconds() / 3600)

    # Compute days_until_end at time of first scan
    end_date = parse_dt(m.get("end_date", ""))
    days_until_end = None
    if first_seen and end_date:
        days_until_end = (end_date - first_seen).total_seconds() / 86400

    # Determine end_date category (how end_date filter treats this market)
    enddate_rule = "default"
    if category in POLITICS_CATEGORIES:
        enddate_rule = "politics"
    elif category in EARLY_SPORTS_CATEGORIES:
        gst = parse_dt(m.get("game_start_time", ""))
        if gst and end_date:
            hours_before_end = (end_date - gst).total_seconds() / 3600
            if hours_before_end >= 6:
                enddate_rule = "sports_early"

    resolved.append({
        "id": mid,
        "question": question[:80],
        "category": category,
        "max_price": max_price,
        "entry_price": entry_price,
        "won": won,
        "volume": volume,
        "resolve_hours": resolve_hours,
        "days_until_end": days_until_end,
        "enddate_rule": enddate_rule,
        "end_date_str": m.get("end_date", ""),
        "first_seen_str": m.get("first_seen", "")[:19],
    })

print(f"Markets passing base filters (no end_date): {len(resolved)}")

# =====================================================
# Analyze end_date impact
# =====================================================

# Which markets are affected by the DEFAULT rule change (7→3)?
# Only markets where enddate_rule == "default"
# Politics always stays at 7 days, sports_early always at 3 days

default_rule_markets = [m for m in resolved if m["enddate_rule"] == "default"]
politics_markets = [m for m in resolved if m["enddate_rule"] == "politics"]
sports_early_markets = [m for m in resolved if m["enddate_rule"] == "sports_early"]

print(f"\nEnd-date rule breakdown:")
print(f"  Default rule (affected by change): {len(default_rule_markets)}")
print(f"  Politics rule (always 7d): {len(politics_markets)}")
print(f"  Sports early rule (always 3d): {len(sports_early_markets)}")

# For default-rule markets, bucket by days_until_end
print(f"\n{'='*80}")
print("DEFAULT-RULE MARKETS: days_until_end distribution")
print(f"{'='*80}")

buckets = {
    "past (stuck)": lambda d: d is not None and d < -3,
    "-3 to 0 days (just ended)": lambda d: d is not None and -3 <= d < 0,
    "0 to 1 day": lambda d: d is not None and 0 <= d < 1,
    "1 to 3 days": lambda d: d is not None and 1 <= d < 3,
    "3 to 7 days": lambda d: d is not None and 3 <= d < 7,
    "7 to 14 days": lambda d: d is not None and 7 <= d < 14,
    "14+ days": lambda d: d is not None and d >= 14,
    "no end_date": lambda d: d is None,
}

for bucket_name, condition in buckets.items():
    in_bucket = [m for m in default_rule_markets if condition(m["days_until_end"])]
    wins = sum(1 for m in in_bucket if m["won"])
    losses = sum(1 for m in in_bucket if not m["won"])
    resolve_times = [m["resolve_hours"] for m in in_bucket if m["resolve_hours"] is not None]
    median_rh = sorted(resolve_times)[len(resolve_times)//2] if resolve_times else 0
    avg_rh = sum(resolve_times)/len(resolve_times) if resolve_times else 0

    cats = defaultdict(int)
    for m in in_bucket:
        cats[m["category"]] += 1

    print(f"\n  {bucket_name}: {len(in_bucket)} markets ({wins}W / {losses}L)")
    if resolve_times:
        print(f"    Resolve time: median {median_rh:.1f}h, avg {avg_rh:.1f}h")
    print(f"    Categories: {dict(cats)}")
    if losses > 0:
        for m in in_bucket:
            if not m["won"]:
                print(f"    LOSS: {m['category']} price={m['max_price']:.3f} | {m['question']}")

# =====================================================
# Simulate 3 configs: 7 days, 3 days, 1 day
# =====================================================
print(f"\n{'='*80}")
print("COMPARISON: end_date default threshold")
print(f"{'='*80}")

configs = [7, 3, 1]
data_days = 3.7

for max_days in configs:
    passed = []
    blocked = []

    for m in resolved:
        d = m["days_until_end"]
        rule = m["enddate_rule"]

        # Stuck market filter (always 3 days past)
        if d is not None and d < -3:
            blocked.append(m)
            continue

        if rule == "politics":
            # Always 7 days for politics
            if d is not None and d > 7:
                blocked.append(m)
                continue
        elif rule == "sports_early":
            # Always 3 days for sports
            if d is not None and d > 3:
                blocked.append(m)
                continue
        else:
            # Default rule - variable
            if d is not None and d > max_days:
                blocked.append(m)
                continue
            # Also block if no end_date
            if d is None:
                blocked.append(m)
                continue

        passed.append(m)

    wins = sum(1 for m in passed if m["won"])
    losses = sum(1 for m in passed if not m["won"])
    resolve_times = sorted([m["resolve_hours"] for m in passed if m["resolve_hours"] is not None])
    median_rh = resolve_times[len(resolve_times)//2] if resolve_times else 0
    avg_rh = sum(resolve_times)/len(resolve_times) if resolve_times else 0
    p90_rh = resolve_times[int(len(resolve_times)*0.9)] if resolve_times else 0

    # Profit calculation
    profits = [(1.0 - m["entry_price"]) * BET_SIZE for m in passed]
    avg_profit = sum(profits)/len(profits) if profits else 0
    total_profit = sum(profits)

    markets_per_day = len(passed) / data_days
    monthly_bets = markets_per_day * 30
    monthly_gross = monthly_bets * avg_profit
    monthly_losses = (losses / data_days) * 30 * BET_SIZE
    monthly_net = monthly_gross - monthly_losses

    # Capital turnover: how many times $10 turns over per day
    slots = 57  # $574 / $10
    if median_rh > 0:
        turns_per_slot_per_day = 24 / median_rh
        capital_limited_bets = slots * turns_per_slot_per_day
    else:
        capital_limited_bets = 999

    effective_bets_per_day = min(markets_per_day, capital_limited_bets)

    # Category breakdown
    cats = defaultdict(lambda: {"w": 0, "l": 0})
    for m in passed:
        if m["won"]:
            cats[m["category"]]["w"] += 1
        else:
            cats[m["category"]]["l"] += 1

    # What gets blocked vs 7-day
    blocked_default = [m for m in blocked if m["enddate_rule"] == "default"]
    blocked_default_wins = sum(1 for m in blocked_default if m["won"])
    blocked_default_losses = sum(1 for m in blocked_default if not m["won"])

    print(f"\n--- Default max = {max_days} day(s) ---")
    print(f"  Total passed: {len(passed)} ({wins}W / {losses}L), win rate: {wins/len(passed)*100:.2f}%" if passed else "  Total passed: 0")
    print(f"  Blocked total: {len(blocked)} (by end_date default: {len(blocked_default)}, {blocked_default_wins}W/{blocked_default_losses}L)")
    print(f"  Resolve time: median {median_rh:.1f}h, avg {avg_rh:.1f}h, P90 {p90_rh:.1f}h")
    print(f"  Markets/day: {markets_per_day:.1f}")
    print(f"  Capital-limited bets/day (57 slots × 24/{median_rh:.1f}h): {capital_limited_bets:.1f}")
    print(f"  Effective bets/day: {effective_bets_per_day:.1f}")
    print(f"  Avg profit/bet: ${avg_profit:.4f}")
    print(f"  Est. monthly bets: {monthly_bets:.0f}")
    print(f"  Est. monthly gross: ${monthly_gross:.2f}")
    print(f"  Est. monthly net: ${monthly_net:.2f}")
    cat_str = {k: f"{v['w']}W/{v['l']}L" for k, v in sorted(cats.items())}
    print(f"  Categories: {cat_str}")

    if max_days < 7 and blocked_default:
        lost_profit = sum((1.0 - m["entry_price"]) * BET_SIZE for m in blocked_default if m["won"])
        avoided_loss = sum(BET_SIZE for m in blocked_default if not m["won"])
        print(f"  Lost profit from blocked wins: ${lost_profit:.2f} (over {data_days}d)")
        print(f"  Avoided loss from blocked losses: ${avoided_loss:.2f}")
        print(f"  Monthly lost profit: ${lost_profit/data_days*30:.2f}")
        print(f"  Monthly avoided loss: ${avoided_loss/data_days*30:.2f}")
        if blocked_default:
            print(f"  Blocked default-rule markets:")
            for m in blocked_default[:15]:
                won_str = "WIN" if m["won"] else "LOSS"
                d = m["days_until_end"]
                rh = f"{m['resolve_hours']:.1f}h" if m["resolve_hours"] else "?"
                print(f"    [{won_str}] {m['category']:15s} end_in={d:.1f}d resolve={rh:>8s} | {m['question']}")

# =====================================================
# Save results
# =====================================================
output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "data_source": "97_scanner/scanner_data.json",
    "total_passed_base_filters": len(resolved),
    "data_period_days": data_days,
    "default_rule_markets": len(default_rule_markets),
    "politics_rule_markets": len(politics_markets),
    "sports_early_rule_markets": len(sports_early_markets),
}

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False, default=str)

print(f"\nResults saved to {OUTPUT_FILE}")
