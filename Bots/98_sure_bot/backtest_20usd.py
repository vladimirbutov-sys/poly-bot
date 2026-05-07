"""Backtest: $20 fixed bet + nr off + ed 7d — bankroll and risk analysis."""
import json
import sys
import os
import re
import random
from datetime import datetime, timezone, timedelta
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join("..", "97_scanner", "scanner_data.json"), "r", encoding="utf-8") as f:
    sc = json.load(f)

with open("positions.json", "r", encoding="utf-8") as f:
    bot = json.load(f)

markets = sc["markets"]

# ========== Filter logic (same as backtest_changes.py) ==========
MIN_LIQUIDITY = 500
MIN_VOLUME = 3000
PRICE_THRESHOLD_DEFAULT = 0.975
PRICE_THRESHOLD_POLITICS = 0.96
MAX_PRICE = 0.993
POLITICS_CATEGORIES = {"politics", "geopolitics"}
EARLY_SPORTS_CATEGORIES = {"esports", "sports_other", "basketball", "hockey",
                           "american_football", "tennis", "fighting", "cricket"}

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

def categorize(question):
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
        "soccer": ["soccer", "premier league", "la liga", "bundesliga", "serie a",
                    "champions league", "uefa", "fifa"],
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

def passes_filters(m):
    """Returns True if market passes our NEW filters (nr off, ed 7d)."""
    question = m.get("question", "")
    q_lower = question.lower()
    category = categorize(question)
    liquidity = m.get("liquidity", 0) or 0
    volume = m.get("volume", 0) or 0
    max_price = m.get("max_price_seen", 0)
    end_date_str = m.get("end_date", "")

    # Price threshold
    if category in POLITICS_CATEGORIES:
        if max_price < PRICE_THRESHOLD_POLITICS:
            return False
    else:
        if max_price < PRICE_THRESHOLD_DEFAULT:
            return False

    if liquidity < MIN_LIQUIDITY:
        return False
    if volume < MIN_VOLUME:
        return False

    # End date: max 7 days (using first_seen as reference time)
    if end_date_str:
        try:
            ed = end_date_str.replace("Z", "+00:00")
            if "T" in ed:
                end_dt = datetime.fromisoformat(ed)
            else:
                end_dt = datetime.strptime(ed, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            if end_dt.tzinfo is None:
                end_dt = end_dt.replace(tzinfo=timezone.utc)

            fs = m.get("first_seen", "")
            if fs:
                now = datetime.fromisoformat(fs.replace("Z", "+00:00"))
                if now.tzinfo is None:
                    now = now.replace(tzinfo=timezone.utc)
            else:
                now = datetime.now(timezone.utc)

            days_ahead = (end_dt - now).total_seconds() / 86400

            if category in POLITICS_CATEGORIES:
                if days_ahead > 7:
                    return False
            elif category in EARLY_SPORTS_CATEGORIES:
                gst = m.get("game_start_time", "")
                if gst:
                    try:
                        gst_dt = datetime.fromisoformat(gst.replace("Z", "+00:00"))
                        if gst_dt.tzinfo is None:
                            gst_dt = gst_dt.replace(tzinfo=timezone.utc)
                        if (end_dt - gst_dt).total_seconds() / 3600 >= 6:
                            if days_ahead > 3:
                                return False
                        elif days_ahead > 7:
                            return False
                    except Exception:
                        if days_ahead > 7:
                            return False
                elif days_ahead > 7:
                    return False
            else:
                if days_ahead > 7:
                    return False

            if days_ahead < -3:
                return False
        except Exception:
            return False

    if matches_any(q_lower, COIN_FLIP_PATTERNS):
        return False
    if matches_any(q_lower, THRESHOLD_PATTERNS):
        return False
    if matches_any(question, WEATHER_PATTERNS):
        return False
    if matches_any(q_lower, FINANCIAL_ASSETS):
        if (m.get("volume", 0) or 0) < 50000:
            return False
    if matches_any(q_lower, SLOW_KEYWORDS):
        return False
    if categorize(question) == "esports":
        if matches_any(q_lower, ESPORTS_BAD_PATTERNS):
            return False
    return True


# ========== PART 1: Historical backtest on 6800+ resolved markets ==========
resolved = {mid: m for mid, m in markets.items()
            if m.get("resolution") and isinstance(m["resolution"], dict)
            and m["resolution"].get("closed")}

BET = 20.0

print("=" * 85)
print(f"BACKTEST: ${BET:.0f} FIXED BET + NR OFF + ED 7D")
print(f"Data: {len(resolved)} resolved markets from scanner")
print("=" * 85)

wins = 0
losses = 0
total_profit = 0.0
loss_details = []
categories = Counter()

for mid, m in resolved.items():
    if not passes_filters(m):
        continue

    res = m["resolution"]
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
    categories[category] += 1

    max_p = m.get("max_price_seen", 0.985)
    entry = min(max_p, 0.99)
    if category in POLITICS_CATEGORIES:
        entry = max(entry, PRICE_THRESHOLD_POLITICS)
    else:
        entry = max(entry, PRICE_THRESHOLD_DEFAULT)

    shares = BET / entry
    if won:
        profit = shares * (1.0 - entry)
        wins += 1
    else:
        profit = -BET
        losses += 1
        loss_details.append({
            "q": m.get("question", "")[:70],
            "cat": category,
            "entry": entry,
            "liq": m.get("liquidity", 0),
        })
    total_profit += profit

total_bets = wins + losses
win_rate = wins / total_bets * 100 if total_bets else 0

print(f"\n  Bets placed: {total_bets}")
print(f"  Wins: {wins} | Losses: {losses}")
print(f"  Win rate: {win_rate:.3f}%")
print(f"  Total profit: ${total_profit:+,.2f}")
print(f"  Total invested: ${total_bets * BET:,.0f}")
print(f"  ROI: {total_profit / (total_bets * BET) * 100 if total_bets else 0:+.2f}%")

print(f"\n  By category:")
for cat, cnt in categories.most_common():
    print(f"    {cat:20s}: {cnt:5d}")

if loss_details:
    print(f"\n  LOSSES ({len(loss_details)}):")
    for ld in loss_details:
        print(f"    [{ld['cat']:12s}] entry {ld['entry']:.3f} | liq ${ld['liq']:,.0f} | {ld['q']}")
else:
    print(f"\n  LOSSES: 0 (perfect record)")


# ========== PART 2: Monte Carlo — bankroll requirement ==========
print()
print("=" * 85)
print("MONTE CARLO: BANKROLL REQUIREMENT ($20/bet, 10000 runs x 30 days)")
print("=" * 85)

random.seed(42)

# From scanner data
LOSS_RATE = 7 / 6717  # 0.104%
AVG_ENTRY = 0.9867
WIN_PROFIT = (1.0 - AVG_ENTRY) / AVG_ENTRY * BET  # per winning bet
MEDIAN_RESOLVE_H = 9.2
POOL_SIZE = 1000
REFRESH_RATE = 0.40
DAYS = 30
RUNS = 10000

print(f"\n  Parameters:")
print(f"    Bet size: ${BET:.0f}")
print(f"    Loss rate: {LOSS_RATE*100:.3f}% ({7} losses / {6717} resolved)")
print(f"    Win profit: ${WIN_PROFIT:.3f} per bet")
print(f"    Loss cost: ${BET:.0f} per bet")
print(f"    Median resolve: {MEDIAN_RESOLVE_H}h")
print(f"    Pool: ~{POOL_SIZE} candidates | Refresh: {REFRESH_RATE*100:.0f}%/day")

# Run simulation tracking: peak capital used, profit, max drawdown, losses
all_peaks = []
all_profits = []
all_drawdowns = []
all_losses = []
all_bets = []

for run in range(RUNS):
    open_positions = []  # list of (hours_remaining, bet_size)
    invested = 0.0
    peak_invested = 0.0
    profit = 0.0
    peak_profit = 0.0
    max_drawdown = 0.0
    n_bets = 0
    n_losses = 0

    for day in range(DAYS):
        # Resolve completed positions
        new_open = []
        for rem_h, bsz in open_positions:
            rem_h -= 24
            if rem_h <= 0:
                invested -= bsz
                if random.random() < LOSS_RATE:
                    profit -= bsz
                    n_losses += 1
                else:
                    profit += WIN_PROFIT
            else:
                new_open.append((rem_h, bsz))
        open_positions = new_open

        # Place new bets
        slots = max(0, int((1000 - invested) / BET))  # available slots from bankroll $1000
        daily_flow = int(POOL_SIZE * REFRESH_RATE)
        if day == 0:
            new_bets = min(slots, POOL_SIZE)
        else:
            new_bets = min(slots, daily_flow)

        for _ in range(new_bets):
            resolve_h = random.expovariate(1.0 / MEDIAN_RESOLVE_H)
            resolve_h = max(1, min(resolve_h, 168))
            open_positions.append((resolve_h, BET))
            invested += BET
            n_bets += 1
            if invested > peak_invested:
                peak_invested = invested

        # Track drawdown from profit peak
        if profit > peak_profit:
            peak_profit = profit
        dd = peak_profit - profit
        if dd > max_drawdown:
            max_drawdown = dd

    all_peaks.append(peak_invested)
    all_profits.append(profit)
    all_drawdowns.append(max_drawdown)
    all_losses.append(n_losses)
    all_bets.append(n_bets)

peaks = sorted(all_peaks)
profits = sorted(all_profits)
drawdowns = sorted(all_drawdowns)
losses_sorted = sorted(all_losses)

print(f"\n  Results ({RUNS} runs, {DAYS} days each):")
print(f"\n  Bets per month:")
print(f"    Median: {sorted(all_bets)[RUNS//2]}")
print(f"    Min:    {min(all_bets)}")

print(f"\n  Peak capital simultaneously invested:")
print(f"    Median:  ${peaks[RUNS//2]:>8.0f}")
print(f"    90th%:   ${peaks[int(RUNS*0.90)]:>8.0f}")
print(f"    95th%:   ${peaks[int(RUNS*0.95)]:>8.0f}")
print(f"    99th%:   ${peaks[int(RUNS*0.99)]:>8.0f}")
print(f"    Max:     ${peaks[-1]:>8.0f}")

print(f"\n  Monthly profit:")
print(f"    1st%:    ${profits[int(RUNS*0.01)]:>+8.2f}")
print(f"    5th%:    ${profits[int(RUNS*0.05)]:>+8.2f}")
print(f"    Median:  ${profits[RUNS//2]:>+8.2f}")
print(f"    95th%:   ${profits[int(RUNS*0.95)]:>+8.2f}")

print(f"\n  Max drawdown (from profit peak):")
print(f"    Median:  ${drawdowns[RUNS//2]:>8.2f}")
print(f"    95th%:   ${drawdowns[int(RUNS*0.95)]:>8.2f}")
print(f"    99th%:   ${drawdowns[int(RUNS*0.99)]:>8.2f}")
print(f"    Max:     ${drawdowns[-1]:>8.2f}")

print(f"\n  Losses per month:")
print(f"    Median:  {losses_sorted[RUNS//2]}")
print(f"    95th%:   {losses_sorted[int(RUNS*0.95)]}")
print(f"    Max:     {losses_sorted[-1]}")

loss_months = sum(1 for p in profits if p < 0)
print(f"\n  Losing months: {loss_months}/{RUNS} ({loss_months/RUNS*100:.2f}%)")


# ========== PART 3: Bankroll recommendations ==========
print()
print("=" * 85)
print("BANKROLL RECOMMENDATION ($20/bet)")
print("=" * 85)

p95_peak = peaks[int(RUNS * 0.95)]
p99_peak = peaks[int(RUNS * 0.99)]
p99_drawdown = drawdowns[int(RUNS * 0.99)]
median_profit = profits[RUNS // 2]
worst_profit = profits[int(RUNS * 0.01)]

print(f"\n  Peak capital 95th%:  ${p95_peak:.0f}")
print(f"  Peak capital 99th%:  ${p99_peak:.0f}")
print(f"  Max drawdown 99th%:  ${p99_drawdown:.0f}")
print()

for label, mult, buffer_mult in [
    ("Minimum (risky)",   1.0, 1.0),
    ("Comfortable",       1.2, 1.5),
    ("Conservative",      1.3, 2.0),
    ("Very safe",         1.5, 2.0),
]:
    bankroll = p95_peak * mult + p99_drawdown * buffer_mult
    roi = median_profit / bankroll * 100
    print(f"  {label:22s}: ${bankroll:>7.0f} | profit ${median_profit:>+7.2f}/mo | ROI {roi:>5.1f}%/mo")


# ========== PART 4: Stress test — what if loss rate is 2x worse? ==========
print()
print("=" * 85)
print("STRESS TEST: what if loss rate is 2x worse (0.21% instead of 0.10%)?")
print("=" * 85)

STRESS_LOSS_RATE = LOSS_RATE * 2
stress_profits = []
stress_drawdowns = []

for run in range(RUNS):
    open_positions = []
    invested = 0.0
    profit = 0.0
    peak_profit = 0.0
    max_dd = 0.0

    for day in range(DAYS):
        new_open = []
        for rem_h, bsz in open_positions:
            rem_h -= 24
            if rem_h <= 0:
                invested -= bsz
                if random.random() < STRESS_LOSS_RATE:
                    profit -= bsz
                else:
                    profit += WIN_PROFIT
            else:
                new_open.append((rem_h, bsz))
        open_positions = new_open

        slots = max(0, int((1000 - invested) / BET))
        daily_flow = int(POOL_SIZE * REFRESH_RATE)
        new_bets = min(slots, POOL_SIZE) if day == 0 else min(slots, daily_flow)

        for _ in range(new_bets):
            rh = max(1, min(random.expovariate(1.0 / MEDIAN_RESOLVE_H), 168))
            open_positions.append((rh, BET))
            invested += BET

        if profit > peak_profit:
            peak_profit = profit
        dd = peak_profit - profit
        if dd > max_dd:
            max_dd = dd

    stress_profits.append(profit)
    stress_drawdowns.append(max_dd)

sp = sorted(stress_profits)
sd = sorted(stress_drawdowns)
stress_loss_months = sum(1 for p in sp if p < 0)

print(f"\n  Loss rate: {STRESS_LOSS_RATE*100:.3f}% (2x actual)")
print(f"  Monthly profit:")
print(f"    1st%:    ${sp[int(RUNS*0.01)]:>+8.2f}")
print(f"    5th%:    ${sp[int(RUNS*0.05)]:>+8.2f}")
print(f"    Median:  ${sp[RUNS//2]:>+8.2f}")
print(f"  Max drawdown 99th%: ${sd[int(RUNS*0.99)]:>8.2f}")
print(f"  Losing months: {stress_loss_months}/{RUNS} ({stress_loss_months/RUNS*100:.2f}%)")


# ========== PART 5: Stress test — 5x worse ==========
print()
print("=" * 85)
print("STRESS TEST: what if loss rate is 5x worse (0.52%)?")
print("=" * 85)

STRESS5_LOSS_RATE = LOSS_RATE * 5
s5_profits = []
s5_drawdowns = []

for run in range(RUNS):
    open_positions = []
    invested = 0.0
    profit = 0.0
    peak_profit = 0.0
    max_dd = 0.0

    for day in range(DAYS):
        new_open = []
        for rem_h, bsz in open_positions:
            rem_h -= 24
            if rem_h <= 0:
                invested -= bsz
                if random.random() < STRESS5_LOSS_RATE:
                    profit -= bsz
                else:
                    profit += WIN_PROFIT
            else:
                new_open.append((rem_h, bsz))
        open_positions = new_open

        slots = max(0, int((1000 - invested) / BET))
        daily_flow = int(POOL_SIZE * REFRESH_RATE)
        new_bets = min(slots, POOL_SIZE) if day == 0 else min(slots, daily_flow)

        for _ in range(new_bets):
            rh = max(1, min(random.expovariate(1.0 / MEDIAN_RESOLVE_H), 168))
            open_positions.append((rh, BET))
            invested += BET

        if profit > peak_profit:
            peak_profit = profit
        dd = peak_profit - profit
        if dd > max_dd:
            max_dd = dd

    s5_profits.append(profit)
    s5_drawdowns.append(max_dd)

s5p = sorted(s5_profits)
s5d = sorted(s5_drawdowns)
s5_loss_months = sum(1 for p in s5p if p < 0)

print(f"\n  Loss rate: {STRESS5_LOSS_RATE*100:.3f}% (5x actual)")
print(f"  Monthly profit:")
print(f"    1st%:    ${s5p[int(RUNS*0.01)]:>+8.2f}")
print(f"    5th%:    ${s5p[int(RUNS*0.05)]:>+8.2f}")
print(f"    Median:  ${s5p[RUNS//2]:>+8.2f}")
print(f"  Max drawdown 99th%: ${s5d[int(RUNS*0.99)]:>8.2f}")
print(f"  Losing months: {s5_loss_months}/{RUNS} ({s5_loss_months/RUNS*100:.2f}%)")

# ========== SUMMARY ==========
print()
print("=" * 85)
print("SUMMARY")
print("=" * 85)
print(f"""
  Backtest ({total_bets} resolved markets):
    Win rate: {win_rate:.3f}% | Losses: {losses} | Profit: ${total_profit:+,.2f}

  Monte Carlo (10000 runs, 30 days):
    Median profit: ${median_profit:+.2f}/month
    Peak capital (95th%): ${p95_peak:.0f}
    Worst drawdown (99th%): ${p99_drawdown:.0f}
    Losing months: {loss_months/RUNS*100:.2f}%

  Stress test (2x loss rate):
    Still profitable: median ${sp[RUNS//2]:+.2f}/month
    Losing months: {stress_loss_months/RUNS*100:.2f}%

  Stress test (5x loss rate):
    Median ${s5p[RUNS//2]:+.2f}/month
    Losing months: {s5_loss_months/RUNS*100:.2f}%
""")
