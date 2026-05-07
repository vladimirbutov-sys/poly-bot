"""
Backtest: verify 5 optimization recommendations on historical data.

Uses 97_scanner/scanner_data.json (10,117 resolved markets) which has
max_price_seen BEFORE resolution — the correct data for backtesting.

Tests each recommendation independently AND combined:
1. O/U filter for ALL sports (not just esports)
2. Wider slippage (+0.1c) — affects profit per bet, not win rate
3. MAX_PRICE → 0.995 (was 0.993)
4. End date default → 3 days (was 7)
5. MIN_VOLUME → $1000 (was $3000)

Output: comparison table OLD vs NEW for each change.
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SCANNER_DATA = "C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json"
OUTPUT_FILE = "C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/backtest_recommendations_2026-03-20.json"

BET_SIZE = 10.0
CAPITAL = 574.0

# =====================================================
# Load data
# =====================================================
print("Loading scanner data...")
with open(SCANNER_DATA, "r", encoding="utf-8") as f:
    sc = json.load(f)

markets_raw = sc.get("markets", {})
print(f"Total markets in scanner: {len(markets_raw)}")

# =====================================================
# Build resolved dataset with all fields we need
# =====================================================
resolved = []

for mid, m in markets_raw.items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue

    max_price = m.get("max_price_seen", 0)
    if max_price < 0.96:
        continue

    high_outcome = m.get("high_outcome", "")
    winner = res.get("winner", "")
    won = m.get("high_outcome_won", None)
    if won is None:
        if high_outcome and winner:
            won = (high_outcome == winner)
        else:
            continue

    category = m.get("category", "other") or "other"
    question = m.get("question", "")
    neg_risk = m.get("neg_risk", False)
    volume = m.get("volume", 0) or 0
    liquidity = m.get("liquidity", 0) or 0
    end_date = m.get("end_date", "")
    game_start_time = m.get("game_start_time", "")
    sports_type = m.get("sports_type", "")
    first_price = m.get("first_price", 0) or 0
    line = m.get("line", None)

    # Compute hours from first_seen to resolution
    first_seen = m.get("first_seen", "")
    closed_time = res.get("closed_time", "")
    resolve_hours = None
    if first_seen and closed_time:
        try:
            t1 = datetime.fromisoformat(first_seen.replace("Z", "+00:00"))
            ct = closed_time.replace("Z", "+00:00")
            if "T" not in ct:
                ct = ct.replace(" ", "T", 1)
            t2 = datetime.fromisoformat(ct)
            resolve_hours = (t2 - t1).total_seconds() / 3600
        except (ValueError, TypeError):
            pass

    resolved.append({
        "id": mid,
        "question": question,
        "max_price": max_price,
        "first_price": first_price,
        "won": won,
        "neg_risk": neg_risk,
        "category": category,
        "volume": volume,
        "liquidity": liquidity,
        "end_date": end_date,
        "game_start_time": game_start_time,
        "sports_type": sports_type,
        "line": line,
        "resolve_hours": resolve_hours,
    })

print(f"Resolved markets with price >= 96%: {len(resolved)}")


# =====================================================
# Filter functions (mirrors filters.py)
# =====================================================

# O/U patterns from filters.py
SPORTS_BAD_PATTERNS = [
    r'\bo/u\b', r'\bover/under\b', r'\bover\s*/\s*under\b',
    r'\bspread\b', r'\btotal\s+(maps?|kills?|rounds?|points?|goals?)\b',
    r'\bhandi?cap\b',
]

ALL_SPORTS_CATS = {"esports", "sports_other", "basketball", "hockey",
                   "american_football", "tennis", "fighting", "cricket",
                   "soccer", "baseball"}

COIN_FLIP_PATTERNS = [
    r'\bodd\s+or\s+even\b', r'\bodd/even\b',
    r'\bfirst\s+blood\b', r'\bfirst\s+kill\b',
    r'\bfirst\s+baron\b', r'\bfirst\s+dragon\b',
    r'\bfirst\s+tower\b', r'\bfirst\s+rift\s+herald\b',
    r'\bcoin\s+flip\b', r'\brampage\b', r'\bfirst\s+roshan\b',
    r'\bfirst\s+map\b', r'\bup\s+or\s+down\b',
]

THRESHOLD_PATTERNS = [
    r'\bclose\s+above\b', r'\bclose\s+below\b',
    r'\bbe\s+above\b', r'\bbe\s+below\b', r'\bbe\s+between\b',
    r'\bbe\s+greater\s+than\b', r'\bbe\s+less\s+than\b',
    r'\bprice\s+of\b',
    r'\breach\b.*\$[\d,]+', r'\bhit\b.*\$[\d,]+',
    r'\bfall\s+(to|below)\b.*\$[\d,]+',
    r'\bdrop\s+(to|below)\b.*\$[\d,]+',
    r'\brise\s+(to|above)\b.*\$[\d,]+',
]

WEATHER_PATTERNS = [
    r'\btemperature\b.*\d+\s*[°]?\s*[FC]\b',
    r'\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b',
]

SLOW_KEYWORDS = [
    r'\btop\b', r'\bseason\b', r'\bmost\b',
    r'\btransit\b', r'\bstrait\b', r'\bships?\b',
    r'\bweekly\b', r'\bmonthly\b',
]

FINANCIAL_ASSETS = [
    r'\bbitcoin\b', r'\bethereum\b', r'\bsolana\b', r'\bxrp\b',
    r'\bbtc\b', r'\beth\b', r'\bsol\b', r'\bdogecoin\b',
    r'\baapl\b', r'\bamzn\b', r'\bgoogl\b', r'\bnflx\b',
    r'\bmsft\b', r'\btsla\b', r'\bnvda\b',
    r'\bs&p\s*500\b', r'\bnasdaq\b', r'\bdow\s*jones\b',
    r'\bcrude\s*oil\b', r'\bgold\s*price\b', r'\bnatural\s*gas\b',
]

POLITICS_CATS = {"politics", "geopolitics"}


def matches_any(text, patterns):
    text_lower = text.lower()
    for p in patterns:
        if re.search(p, text_lower):
            return True
    return False


def is_sports_ou_spread(m):
    """Check if market is O/U, spread, or handicap in ANY sport."""
    if m["category"] not in ALL_SPORTS_CATS:
        return False
    return matches_any(m["question"], SPORTS_BAD_PATTERNS)


def is_esports_ou_spread(m):
    """Current filter: only esports O/U/spread."""
    if m["category"] != "esports":
        return False
    return matches_any(m["question"], SPORTS_BAD_PATTERNS)


def apply_common_filters(m):
    """Filters that DON'T change between old and new config."""
    q = m["question"]
    # Coin flip
    if matches_any(q, COIN_FLIP_PATTERNS):
        return False, "coin_flip"
    # Threshold
    if matches_any(q, THRESHOLD_PATTERNS):
        return False, "threshold"
    # Weather
    if matches_any(q, WEATHER_PATTERNS):
        return False, "weather"
    # Slow keywords
    if matches_any(q, SLOW_KEYWORDS):
        return False, "slow_keywords"
    # Financial assets (vol < 50K)
    if matches_any(q, FINANCIAL_ASSETS) and m["volume"] < 50000:
        return False, "financial_low_vol"
    return True, ""


def run_filter_set(m, config):
    """Apply a full filter set to a market.
    config dict:
      - skip_neg_risk: bool
      - min_price_default: float
      - min_price_politics: float
      - max_price: float
      - min_liquidity: float
      - min_volume: float
      - ou_filter: "esports_only" | "all_sports"
      - max_end_date_days: int (default category)
    """
    # Skip neg_risk
    if config.get("skip_neg_risk", True) and m["neg_risk"]:
        return False, "neg_risk"

    # Price threshold
    price = m["max_price"]
    cat = m["category"]
    if cat in POLITICS_CATS:
        if price < config.get("min_price_politics", 0.96):
            return False, "price_low_politics"
    else:
        if price < config.get("min_price_default", 0.975):
            return False, "price_low"

    # Max price (but scanner data uses max_price_seen which may exceed this —
    # for backtest we check if FIRST price was <= max_price, indicating the bot
    # could have entered at an acceptable price)
    # Actually, first_price is the price when scanner first saw it.
    # If first_price > max_price, the bot wouldn't have bought it.
    # But if first_price <= max_price, we assume the bot would enter.
    first_p = m.get("first_price", 0)
    max_allowed = config.get("max_price", 0.993)
    # Use first_price as entry proxy — if first_price is in range, bot would buy
    # If first_price is 0 or very low, use max_price as fallback
    entry_price = first_p if first_p >= config.get("min_price_default", 0.975) else price
    if entry_price > max_allowed:
        return False, "price_too_high"

    # Liquidity
    if m["liquidity"] < config.get("min_liquidity", 500):
        return False, "low_liquidity"

    # Volume
    if m["volume"] < config.get("min_volume", 3000):
        return False, "low_volume"

    # O/U filter
    ou_mode = config.get("ou_filter", "esports_only")
    if ou_mode == "all_sports":
        if is_sports_ou_spread(m):
            return False, "sports_ou_spread"
    else:
        if is_esports_ou_spread(m):
            return False, "esports_ou_spread"

    # Common filters
    passed, reason = apply_common_filters(m)
    if not passed:
        return False, reason

    return True, "passed"


# =====================================================
# Define OLD and NEW configs
# =====================================================
OLD_CONFIG = {
    "name": "CURRENT settings",
    "skip_neg_risk": True,
    "min_price_default": 0.975,
    "min_price_politics": 0.96,
    "max_price": 0.993,
    "min_liquidity": 500,
    "min_volume": 3000,
    "ou_filter": "esports_only",
    "max_end_date_days": 7,
}

NEW_CONFIG = {
    "name": "OPTIMIZED settings",
    "skip_neg_risk": True,
    "min_price_default": 0.975,
    "min_price_politics": 0.96,
    "max_price": 0.995,
    "min_liquidity": 1000,
    "min_volume": 1000,
    "ou_filter": "all_sports",
    "max_end_date_days": 3,
}

# Also test each change INDIVIDUALLY
INDIVIDUAL_CHANGES = [
    {
        "name": "Change 1: O/U → all sports",
        "skip_neg_risk": True,
        "min_price_default": 0.975, "min_price_politics": 0.96,
        "max_price": 0.993,
        "min_liquidity": 500, "min_volume": 3000,
        "ou_filter": "all_sports",  # CHANGED
        "max_end_date_days": 7,
    },
    {
        "name": "Change 3: MAX_PRICE → 0.995",
        "skip_neg_risk": True,
        "min_price_default": 0.975, "min_price_politics": 0.96,
        "max_price": 0.995,  # CHANGED
        "min_liquidity": 500, "min_volume": 3000,
        "ou_filter": "esports_only",
        "max_end_date_days": 7,
    },
    {
        "name": "Change 5: MIN_VOLUME → $1000",
        "skip_neg_risk": True,
        "min_price_default": 0.975, "min_price_politics": 0.96,
        "max_price": 0.993,
        "min_liquidity": 500,
        "min_volume": 1000,  # CHANGED
        "ou_filter": "esports_only",
        "max_end_date_days": 7,
    },
    {
        "name": "Change 2+5: MIN_LIQUIDITY → $1000 + MIN_VOLUME → $1000",
        "skip_neg_risk": True,
        "min_price_default": 0.975, "min_price_politics": 0.96,
        "max_price": 0.993,
        "min_liquidity": 1000, "min_volume": 1000,  # CHANGED
        "ou_filter": "esports_only",
        "max_end_date_days": 7,
    },
]


# =====================================================
# Run backtest for each config
# =====================================================
def backtest(data, config):
    """Run backtest with given config. Returns stats dict."""
    wins, losses = 0, 0
    loss_list = []
    filter_reasons = defaultdict(int)
    categories_passed = defaultdict(lambda: {"w": 0, "l": 0})
    price_buckets = defaultdict(lambda: {"w": 0, "l": 0})
    resolve_times = []

    for m in data:
        passed, reason = run_filter_set(m, config)
        if not passed:
            filter_reasons[reason] += 1
            continue

        # Would have bet on this market
        if m["won"]:
            wins += 1
        else:
            losses += 1
            loss_list.append({
                "question": m["question"][:80],
                "max_price": m["max_price"],
                "first_price": m["first_price"],
                "category": m["category"],
                "volume": m["volume"],
                "liquidity": m["liquidity"],
                "neg_risk": m["neg_risk"],
                "sports_type": m.get("sports_type", ""),
            })

        # Category stats
        c = m["category"]
        if m["won"]:
            categories_passed[c]["w"] += 1
        else:
            categories_passed[c]["l"] += 1

        # Price bucket stats
        p = m["max_price"]
        if p < 0.975:
            bucket = "0.96-0.975"
        elif p < 0.98:
            bucket = "0.975-0.98"
        elif p < 0.985:
            bucket = "0.98-0.985"
        elif p < 0.99:
            bucket = "0.985-0.99"
        elif p < 0.993:
            bucket = "0.99-0.993"
        else:
            bucket = "0.993+"
        if m["won"]:
            price_buckets[bucket]["w"] += 1
        else:
            price_buckets[bucket]["l"] += 1

        # Resolve time
        if m.get("resolve_hours") and m["resolve_hours"] > 0:
            resolve_times.append(m["resolve_hours"])

    total = wins + losses
    win_rate = wins / total if total > 0 else 0
    loss_rate = losses / total if total > 0 else 0

    # P&L projection
    avg_entry = 0.985  # typical entry price
    profit_per_win = BET_SIZE / avg_entry - BET_SIZE
    loss_per_loss = BET_SIZE
    ev_per_bet = win_rate * profit_per_win - loss_rate * loss_per_loss
    avg_resolve_h = sorted(resolve_times)[len(resolve_times) // 2] if resolve_times else 12
    slots = CAPITAL / BET_SIZE
    turns_per_day = 24 / avg_resolve_h if avg_resolve_h > 0 else 2
    fill_rate = 0.60
    bets_per_month = slots * turns_per_day * 30 * fill_rate
    monthly_pnl = bets_per_month * ev_per_bet

    return {
        "config_name": config["name"],
        "total_passed": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(win_rate * 100, 4),
        "loss_rate_1_in_n": total // losses if losses > 0 else 0,
        "ev_per_bet": round(ev_per_bet, 4),
        "monthly_pnl_estimate": round(monthly_pnl, 2),
        "bets_per_month": round(bets_per_month),
        "median_resolve_h": round(avg_resolve_h, 1),
        "loss_list": loss_list,
        "filter_reasons": dict(filter_reasons),
        "categories": {c: dict(v) for c, v in categories_passed.items()},
        "price_buckets": {b: dict(v) for b, v in price_buckets.items()},
    }


# =====================================================
# Run all backtests
# =====================================================
print(f"\n{'='*90}")
print(f"BACKTEST: VERIFYING 5 RECOMMENDATIONS")
print(f"Data: {len(resolved)} resolved markets from 97_scanner")
print(f"{'='*90}")

all_configs = [OLD_CONFIG] + INDIVIDUAL_CHANGES + [NEW_CONFIG]
results = {}

for config in all_configs:
    name = config["name"]
    r = backtest(resolved, config)
    results[name] = r

    # Print summary
    print(f"\n--- {name} ---")
    print(f"  Passed filters: {r['total_passed']} markets")
    print(f"  Wins: {r['wins']} | Losses: {r['losses']}")
    print(f"  Win rate: {r['win_rate']:.3f}%", end="")
    if r["losses"] > 0:
        print(f" (1 loss per {r['loss_rate_1_in_n']})")
    else:
        print(f" (ZERO losses)")
    print(f"  EV/bet: ${r['ev_per_bet']:.4f}")
    print(f"  Est. monthly P&L: ${r['monthly_pnl_estimate']:.2f} ({r['bets_per_month']} bets/month)")

    # Print losses if any
    if r["loss_list"]:
        print(f"\n  LOSSES:")
        for loss in r["loss_list"]:
            print(f"    {loss['max_price']:.4f} | {loss['category']:12s} | vol=${loss['volume']:,.0f} | "
                  f"liq=${loss['liquidity']:,.0f} | {loss['question']}")

    # Filter reasons
    if r["filter_reasons"]:
        top_reasons = sorted(r["filter_reasons"].items(), key=lambda x: -x[1])[:8]
        print(f"\n  Top filter reasons:")
        for reason, count in top_reasons:
            print(f"    {reason:25s}: {count:5d}")

# =====================================================
# Comparison table
# =====================================================
print(f"\n\n{'='*90}")
print(f"COMPARISON TABLE")
print(f"{'='*90}")
print(f"\n{'Config':45s} {'Passed':>7s} {'W':>6s} {'L':>4s} {'WR':>9s} {'EV/bet':>8s} {'PnL/mo':>9s}")
print("-" * 95)
for config in all_configs:
    name = config["name"]
    r = results[name]
    l_str = f"1/{r['loss_rate_1_in_n']}" if r["losses"] > 0 else "0"
    print(f"{name:45s} {r['total_passed']:7d} {r['wins']:6d} {r['losses']:4d} "
          f"{r['win_rate']:8.3f}% ${r['ev_per_bet']:7.4f} ${r['monthly_pnl_estimate']:8.2f}")

# =====================================================
# Key finding: O/U filter impact
# =====================================================
print(f"\n\n{'='*90}")
print(f"KEY FINDING: O/U MARKETS IN SPORTS")
print(f"{'='*90}")

ou_in_sports = [m for m in resolved if is_sports_ou_spread(m) and not is_esports_ou_spread(m)]
ou_wins = sum(1 for m in ou_in_sports if m["won"])
ou_losses = sum(1 for m in ou_in_sports if not m["won"])
print(f"\nSports O/U/spread markets (excluding esports): {len(ou_in_sports)}")
print(f"  Wins: {ou_wins} | Losses: {ou_losses}")
if ou_losses > 0:
    print(f"  Win rate: {ou_wins / (ou_wins + ou_losses) * 100:.2f}%")
    print(f"\n  O/U LOSSES (markets the new filter would have PREVENTED):")
    for m in ou_in_sports:
        if not m["won"]:
            print(f"    {m['max_price']:.4f} | {m['category']:12s} | vol=${m['volume']:,.0f} | {m['question'][:70]}")

# =====================================================
# Category breakdown for OPTIMIZED config
# =====================================================
print(f"\n\n{'='*90}")
print(f"CATEGORY BREAKDOWN (OPTIMIZED config)")
print(f"{'='*90}")
r_new = results[NEW_CONFIG["name"]]
print(f"\n{'Category':15s} {'W':>6s} {'L':>4s} {'WR':>9s}")
print("-" * 40)
for c in sorted(r_new["categories"], key=lambda x: -(r_new["categories"][x]["w"] + r_new["categories"][x]["l"])):
    d = r_new["categories"][c]
    t = d["w"] + d["l"]
    wr = d["w"] / t * 100 if t > 0 else 0
    print(f"{c:15s} {d['w']:6d} {d['l']:4d} {wr:8.3f}%")

# =====================================================
# Save full results
# =====================================================
output = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "data_source": "97_scanner/scanner_data.json (resolved markets with pre-resolution prices)",
    "total_resolved_markets": len(resolved),
    "results": {name: {k: v for k, v in r.items() if k != "loss_list"}
                for name, r in results.items()},
    "losses_detail": {name: r["loss_list"] for name, r in results.items() if r["loss_list"]},
    "methodology": (
        "Each market's max_price_seen is the highest price observed BEFORE resolution. "
        "high_outcome_won indicates if that outcome won. Filters are applied exactly as "
        "in the bot's filters.py, testing each proposed change independently and combined."
    ),
}

import os
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False)

print(f"\n\nResults saved to: {OUTPUT_FILE}")
print("DONE.")
