"""Filters to exclude bad markets. Each filter returns (passed: bool, reason: str)."""
import re
import logging
from datetime import datetime, timezone, timedelta

from config import (
    MIN_LIQUIDITY, MIN_VOLUME,
    PRICE_THRESHOLD_DEFAULT, PRICE_THRESHOLD_POLITICS,
    MAX_NEG_RISK_FROZEN,
    MAX_END_DATE_REGULAR, MAX_END_DATE_NEG_RISK,
)

logger = logging.getLogger("filters")

# --- Politics categories ---
POLITICS_CATEGORIES = {"politics", "geopolitics"}

# --- All sports categories (for cancellation filter) ---
ALL_SPORTS_CATEGORIES = {"esports", "sports_other", "basketball", "hockey",
                         "american_football", "tennis", "fighting", "cricket", "soccer"}

# --- How long after game_start to consider match possibly cancelled ---
GAME_STARTED_MAX_HOURS = 6  # if game started 6+ hours ago and not resolved, likely cancelled

# --- Coin-flip keywords (case-insensitive) ---
COIN_FLIP_PATTERNS = [
    r'\bodd\s+or\s+even\b',
    r'\bodd/even\b',
    r'\bfirst\s+blood\b',
    r'\bfirst\s+kill\b',
    r'\bfirst\s+baron\b',
    r'\bfirst\s+dragon\b',
    r'\bfirst\s+tower\b',
    r'\bfirst\s+rift\s+herald\b',
    r'\bcoin\s+flip\b',
    r'\brampage\b',
    r'\bfirst\s+roshan\b',
    r'\bfirst\s+map\b',
    r'\bup\s+or\s+down\b',
]

# --- Threshold market keywords ---
THRESHOLD_PATTERNS = [
    r'\bclose\s+above\b',
    r'\bclose\s+below\b',
    r'\bbe\s+above\b',
    r'\bbe\s+below\b',
    r'\bbe\s+between\b',
    r'\bbe\s+greater\s+than\b',
    r'\bbe\s+less\s+than\b',
    r'\bprice\s+of\b',
    r'\breach\b.*\$[\d,]+',
    r'\bhit\b.*\$[\d,]+',
    r'\bfall\s+(to|below)\b.*\$[\d,]+',
    r'\bdrop\s+(to|below)\b.*\$[\d,]+',
    r'\brise\s+(to|above)\b.*\$[\d,]+',
    r'\bdip\s+(to|below)\b',  # "Will BTC dip to $69K" — same risk as threshold
    r'\bpump\s+(to|above)\b',
]

# --- Weather patterns ---
WEATHER_PATTERNS = [
    r'\btemperature\b.*\d+\s*[°]?\s*[FC]\b',
    r'\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b',
    r'\d+\s*[°]?\s*[FC]\b.*\btemperature\b',
    r'\d+\s*[°]?\s*[FC]\b.*\bhighest\s+temp\b',
]

# --- Toxic market keywords (guaranteed losers at 97%+) ---
# Earthquakes: bracket markets "exactly N earthquakes" — count is unpredictable,
#   price crashes when actual count diverges from bracket. Lost $8+ on one position.
# Tweet/post brackets: "X will post 420-439 tweets" — count drifts unpredictably,
#   6 CRITICAL positions in portfolio from these markets.
TOXIC_KEYWORDS = [
    # Earthquakes: bracket counting markets, unpredictable (0 resolved in scanner)
    r'\bearthquake', r'\bseismic\b', r'\bmagnitude\s+\d',
    # Tornadoes: bracket counting markets, same blind spot as earthquakes (0 resolved)
    r'\btornado', r'\btornadoes\b',
    # Tweet/post brackets: UNBLOCKED 2026-04-07 — real data shows 47/47 win rate.
    # Max 2 bets per event enforced in main.py instead.
    # YouTube/social media counting brackets — kept blocked (no data yet)
    r'\bviews\b.*\b(million|day\s*1|first\s*day)\b',
    r'\bsubscribers\b',
]

# --- Slow-resolving keywords ---
# "top/season/most" = long-running markets
# "transit/strait/ships" = shipping data markets (IMF Portwatch, up to 14 days for resolution)
# "how many.*week" = weekly counting markets dependent on external data
SLOW_KEYWORDS = [
    r'\btop\b', r'\bseason\b', r'\bmost\b',
    r'\btransit\b', r'\bstrait\b', r'\bships?\b',
    r'\bweekly\b', r'\bmonthly\b',
]

# --- Financial asset names (case-insensitive) ---
FINANCIAL_ASSETS = [
    # Crypto
    r'\bbitcoin\b', r'\bethereum\b', r'\bsolana\b', r'\bxrp\b',
    r'\bbtc\b', r'\beth\b', r'\bsol\b', r'\bdogecoin\b', r'\bcardano\b',
    r'\bpolygon\b', r'\bavalanch\b', r'\blitecoin\b', r'\bpolkadot\b',
    r'\bchainlink\b', r'\buniswap\b', r'\bshiba\b',
    # Stocks
    r'\baapl\b', r'\bamzn\b', r'\bgoogl\b', r'\bmeta\b', r'\bnflx\b',
    r'\bmsft\b', r'\btsla\b', r'\bnvda\b', r'\bapple\b', r'\bamazon\b',
    r'\bgoogle\b', r'\bnetflix\b', r'\bmicrosoft\b', r'\btesla\b',
    r'\bnvidia\b', r'\bopendoor\b',
    # Indices
    r'\bs&p\s*500\b', r'\bnasdaq\b', r'\bnyse\b', r'\bdow\s*jones\b',
    r'\bdjia\b', r'\bndx\b', r'\bspx\b', r'\bhang\s*seng\b', r'\bhsi\b',
    r'\brussell\b', r'\bnikkei\b', r'\bftse\b',
    # Commodities
    r'\bcrude\s*oil\b', r'\bgold\s*price\b', r'\bsilver\s*price\b',
    r'\bnatural\s*gas\b', r'\bwti\b', r'\bbrent\b',
    # Other financial
    r'\btreasury\s*yield\b', r'\bfed\s*rate\b', r'\bmicrostrategy\b',
]


def check_min_price(candidate: dict) -> tuple:
    """Filter 0: Category-specific minimum price.
    Politics/geopolitics: 96%+, everything else: 97.5%+.
    """
    price = candidate.get("price", 0)
    category = candidate.get("category", "").lower()
    if category in POLITICS_CATEGORIES:
        if price < PRICE_THRESHOLD_POLITICS:
            return False, f"Price {price:.3f} < {PRICE_THRESHOLD_POLITICS} (politics)"
    else:
        if price < PRICE_THRESHOLD_DEFAULT:
            return False, f"Price {price:.3f} < {PRICE_THRESHOLD_DEFAULT} (non-politics)"
    return True, ""




def check_liquidity(candidate: dict) -> tuple:
    """Filter 1: Minimum liquidity."""
    liq = candidate.get("liquidity", 0)
    if liq < MIN_LIQUIDITY:
        return False, f"Low liquidity: ${liq:.0f} < ${MIN_LIQUIDITY}"
    return True, ""


def check_coin_flip(candidate: dict) -> tuple:
    """Filter 2: Coin-flip / random-outcome markets."""
    question = candidate.get("question", "").lower()
    for pattern in COIN_FLIP_PATTERNS:
        if re.search(pattern, question):
            return False, f"Coin-flip market: matches '{pattern}'"
    return True, ""


def check_threshold_market(candidate: dict) -> tuple:
    """Filter 3: Threshold markets (price above/below X)."""
    question = candidate.get("question", "").lower()
    for pattern in THRESHOLD_PATTERNS:
        if re.search(pattern, question):
            return False, f"Threshold market: matches '{pattern}'"
    return True, ""


def check_weather(candidate: dict) -> tuple:
    """Filter 4: Weather markets with narrow temperature ranges."""
    question = candidate.get("question", "")
    for pattern in WEATHER_PATTERNS:
        if re.search(pattern, question, re.IGNORECASE):
            return False, f"Weather market: matches '{pattern}'"
    return True, ""


def check_stale(candidate: dict) -> tuple:
    """Filter 5: Minimum total volume."""
    vol = candidate.get("volume_total", 0) or 0
    if vol < MIN_VOLUME:
        return False, f"Low volume: ${vol:.0f} < ${MIN_VOLUME}"
    return True, ""


def check_already_bought(candidate: dict, open_condition_ids: set) -> tuple:
    """Filter 6: Already have an open position on this condition_id."""
    cid = candidate.get("condition_id", "")
    if cid in open_condition_ids:
        return False, "Already have open position on this market"
    return True, ""


def _parse_end_date(end_date_str: str) -> datetime:
    """Parse end_date string to datetime (UTC)."""
    end_date_str = end_date_str.replace("Z", "+00:00")
    if "T" in end_date_str:
        dt = datetime.fromisoformat(end_date_str)
    else:
        dt = datetime.strptime(end_date_str, "%Y-%m-%d")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_game_start(gst_str: str) -> datetime | None:
    """Parse game_start_time string to datetime (UTC)."""
    if not gst_str:
        return None
    try:
        gst_str = gst_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(gst_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


def check_end_date(candidate: dict) -> tuple:
    """Filter 8: Skip markets with bad end_date.

    Rules (checked in order):
    0. Resolution already proposed (uma_status="proposed") → skip end_date check,
       market will resolve in ~2 hours regardless of end_date
    1. Any category: end_date max 3 days in the past (stuck market)
    2. neg_risk markets: max MAX_END_DATE_NEG_RISK days (default 3)
    3. regular markets: max MAX_END_DATE_REGULAR days (default 2)
    """
    # Rule 0: resolution already proposed → end_date irrelevant
    uma_status = candidate.get("uma_status", "")
    if uma_status == "proposed":
        logger.info("UMA proposed, skipping end_date check: %s",
                     candidate.get("question", "")[:60])
        return True, ""

    end_date_str = candidate.get("end_date", "")
    if not end_date_str:
        return False, "No end_date — skip (unknown resolve time)"
    try:
        end_date = _parse_end_date(end_date_str)
    except (ValueError, TypeError):
        return False, "Bad end_date format"

    now = datetime.now(timezone.utc)
    neg_risk = candidate.get("neg_risk", False)

    # --- Past limit: 3 days for all categories ---
    if end_date < now - timedelta(days=3):
        return False, f"Stuck market, end_date passed: {end_date_str[:10]}"

    # --- Future limit: depends on market type ---
    days_ahead = (end_date - now).total_seconds() / 86400

    if neg_risk:
        max_days = MAX_END_DATE_NEG_RISK
        label = "neg_risk"
    else:
        max_days = MAX_END_DATE_REGULAR
        label = "regular"

    if days_ahead > max_days:
        return False, f"End date too far ({label}): {days_ahead:.1f}d > {max_days}d"

    return True, ""


def check_sports_cancelled(candidate: dict) -> tuple:
    """Filter 8b: Skip sports markets where match may have been cancelled.

    Polymarket rule: if a match is cancelled, resolution is 50/50.
    We buy at 97-99c, so a 50/50 payout = ~$2.50 loss per $5 bet.

    Rules:
    1. Sports market with game_start_time in the past by 6+ hours
       but market still open → match likely cancelled or postponed.
    2. Sports market where end_date is in the past but not resolved
       → stuck, possibly cancelled.
    """
    now = datetime.now(timezone.utc)

    # Rule 0: if game_start_time exists, it's a sports market regardless of category.
    # Gamma API returned stale prices for Leeds United FC (category="other")
    # 27h after the match ended — this rule catches that.
    gst = _parse_game_start(candidate.get("game_start_time", ""))
    if gst is not None:
        hours_since_start = (now - gst).total_seconds() / 3600
        if hours_since_start > GAME_STARTED_MAX_HOURS:
            return False, f"Game started {hours_since_start:.0f}h ago, possibly cancelled/stale"

    category = candidate.get("category", "").lower()
    if category not in ALL_SPORTS_CATEGORIES:
        return True, ""

    # Rule 2: end_date in the past → market should have resolved already
    end_date_str = candidate.get("end_date", "")
    if end_date_str:
        try:
            end_date = _parse_end_date(end_date_str)
            hours_overdue = (now - end_date).total_seconds() / 3600
            if hours_overdue > 6:
                return False, f"Sports: end_date passed {hours_overdue:.0f}h ago, possibly cancelled"
        except (ValueError, TypeError):
            pass

    return True, ""


def check_neg_risk(candidate: dict, tracker_data: dict = None) -> tuple:
    """Filter 9: cap total capital frozen in neg_risk positions.
    Non-neg_risk markets always pass. Neg_risk markets blocked
    when frozen neg_risk capital >= MAX_NEG_RISK_FROZEN ($300).
    """
    neg_risk = candidate.get("neg_risk", False)
    if not neg_risk:
        return True, ""

    if tracker_data is None:
        return True, ""

    frozen = sum(
        pos.get("cost_usd", 0)
        for pos in tracker_data.get("positions", {}).values()
        if pos.get("status") in ("open", "selling") and pos.get("neg_risk", False)
    )

    if frozen >= MAX_NEG_RISK_FROZEN:
        return False, f"Neg_risk cap: ${frozen:.0f} frozen >= ${MAX_NEG_RISK_FROZEN:.0f} limit"

    return True, ""


# --- Sports non-win patterns (O/U, Spread, Total — too random at 97%+) ---
# Extended from esports-only to ALL sports (2026-03-20: soccer O/U caused the only bot loss)
SPORTS_BAD_PATTERNS = [
    r'\bo/u\b', r'\bover/under\b', r'\bover\s*/\s*under\b',
    r'\bspread\b', r'\btotal\s+(maps?|kills?|rounds?|points?|goals?)\b',
    r'\bhandi?cap\b',
]


def check_sports_win_only(candidate: dict) -> tuple:
    """Filter 12: In ALL sports, only allow 'Will X win' markets.
    Blocks O/U, spread, handicap — these resolve unpredictably even at 97%+.
    """
    category = candidate.get("category", "").lower()
    if category not in ALL_SPORTS_CATEGORIES:
        return True, ""

    question = candidate.get("question", "").lower()
    for pattern in SPORTS_BAD_PATTERNS:
        if re.search(pattern, question):
            return False, f"Sports non-win market: {pattern}"
    return True, ""


def check_skip_neg_risk(candidate: dict) -> tuple:
    """Filter 13: Skip neg_risk markets (slow on-chain finalization, 3-5x longer redeem)."""
    if candidate.get("neg_risk", False):
        return False, "Skip neg_risk (slow finalization)"
    return True, ""


def check_toxic_keywords(candidate: dict) -> tuple:
    """Filter 14: Block earthquake and tweet/post bracket markets.
    These are counting/bracket markets where the count drifts unpredictably.
    Lost $8+ on earthquake brackets, 6 CRITICAL positions on tweet brackets."""
    question = candidate.get("question", "").lower()
    for pattern in TOXIC_KEYWORDS:
        if re.search(pattern, question):
            return False, f"Toxic market: {pattern}"
    return True, ""


def check_slow_keywords(candidate: dict) -> tuple:
    """Filter 10: Skip markets with slow-resolving keywords (top, season, most)."""
    question = candidate.get("question", "").lower()
    for pattern in SLOW_KEYWORDS:
        if re.search(pattern, question):
            return False, f"Slow keyword: {pattern}"
    return True, ""


MIN_VOLUME_FINANCIAL = 50000  # allow crypto/finance only at high volume

def check_financial_asset(candidate: dict) -> tuple:
    """Filter 11: Skip financial assets unless volume >= $50K."""
    question = candidate.get("question", "").lower()
    for pattern in FINANCIAL_ASSETS:
        if re.search(pattern, question):
            vol = candidate.get("volume_total", 0) or 0
            if vol >= MIN_VOLUME_FINANCIAL:
                return True, ""
            return False, f"Financial asset: {pattern} (vol ${vol:.0f} < ${MIN_VOLUME_FINANCIAL})"
    return True, ""


def check_delayed_resolution(candidate: dict) -> tuple:
    """Filter: Skip markets where resolution can drag far beyond end_date.

    Detects clauses like 'if not released by June 30' or 'officially cancelled'
    that allow resolution to freeze for weeks or months after the event ends.
    """
    desc = (candidate.get("description") or "").lower()
    if not desc:
        return True, ""

    end_date_str = candidate.get("end_date", "")
    end_dt = None
    if end_date_str:
        try:
            end_dt = _parse_end_date(end_date_str)
        except (ValueError, TypeError):
            pass

    # Patterns indicating possible delayed resolution
    delay_patterns = [
        r"not (?:released|aired|broadcast|published|available|known|confirmed|determined|finalized|announced) by",
        r"officially cancell?ed",
        r"postponed or cancell?ed",
        r"resolve to .{0,20}(?:december 31|june 30|september 30)",
    ]

    for pattern in delay_patterns:
        match = re.search(pattern, desc)
        if match:
            # Extract the fallback deadline date if present
            date_after = desc[match.end():match.end() + 80]
            month_match = re.search(
                r"(january|february|march|april|may|june|july|august|"
                r"september|october|november|december)\s+\d{1,2},?\s*\d{4}",
                date_after,
            )
            if month_match and end_dt:
                try:
                    fallback_dt = datetime.strptime(
                        month_match.group().replace(",", ""),
                        "%B %d %Y",
                    ).replace(tzinfo=timezone.utc)
                    gap_days = (fallback_dt - end_dt).days
                    if gap_days > 14:
                        return False, (
                            f"Delayed resolution: fallback {gap_days}d "
                            f"after end_date ({match.group()[:40]})"
                        )
                    return True, ""
                except ValueError:
                    pass
            # No parseable date but pattern matched → block if not sports
            cat = candidate.get("category", "")
            if not cat.startswith(("sports", "esports", "fighting",
                                   "basketball", "hockey", "baseball",
                                   "soccer", "tennis", "cricket",
                                   "american_football")):
                return False, f"Delayed resolution clause: {match.group()[:50]}"

    return True, ""


def check_title_date_vs_end_date(candidate: dict) -> tuple:
    """Filter: Skip markets where the title mentions a resolution date later than end_date.

    Example: title says "by April 30, 2026" but end_date is March 31.
    The real resolution can't happen until the title date, so end_date is misleading
    and money will be frozen much longer than expected.
    """
    question = candidate.get("question", "")
    if not question:
        return True, ""

    end_date_str = candidate.get("end_date", "")
    if not end_date_str:
        return True, ""

    try:
        end_dt = _parse_end_date(end_date_str)
    except (ValueError, TypeError):
        return True, ""

    # Match patterns like "by April 30, 2026", "before June 1, 2026", etc.
    months = (r"january|february|march|april|may|june|july|august|"
              r"september|october|november|december")
    patterns = [
        # "by April 30, 2026" / "before May 1, 2026" / "through June 30, 2026"
        rf"(?:by|before|until|through)\s+({months})\s+(\d{{1,2}}),?\s*(\d{{4}})",
        # "in Q2 2026" style — match quarter end
        # "by end of April 2026"
        rf"(?:by\s+)?end\s+of\s+({months}),?\s*(\d{{4}})",
    ]

    for pattern in patterns:
        match = re.search(pattern, question, re.IGNORECASE)
        if not match:
            continue

        groups = match.groups()
        try:
            if len(groups) == 3:
                # "April 30, 2026"
                month_str, day_str, year_str = groups
                title_dt = datetime.strptime(
                    f"{month_str} {day_str} {year_str}", "%B %d %Y"
                ).replace(tzinfo=timezone.utc)
            elif len(groups) == 2:
                # "end of April 2026" — use last day of month
                month_str, year_str = groups
                first_of_month = datetime.strptime(
                    f"{month_str} 1 {year_str}", "%B %d %Y"
                ).replace(tzinfo=timezone.utc)
                # Last day of month
                if first_of_month.month == 12:
                    title_dt = first_of_month.replace(year=first_of_month.year + 1, month=1, day=1) - timedelta(days=1)
                else:
                    title_dt = first_of_month.replace(month=first_of_month.month + 1, day=1) - timedelta(days=1)
            else:
                continue
        except ValueError:
            continue

        gap_days = (title_dt - end_dt).days
        if gap_days > 3:
            return False, (
                f"Title date {title_dt.strftime('%Y-%m-%d')} is {gap_days}d after "
                f"end_date {end_dt.strftime('%Y-%m-%d')}: '{match.group()}'"
            )

    # Also check description for dates after end_date (same logic)
    desc = candidate.get("description", "") or ""
    if desc:
        resolve_patterns = [
            rf"resolve[sd]?\s+(?:to\s+.{{0,20}})?(?:on|by|before|after)\s+({months})\s+(\d{{1,2}}),?\s*(\d{{4}})",
        ]
        for pattern in resolve_patterns:
            match = re.search(pattern, desc, re.IGNORECASE)
            if not match:
                continue
            try:
                month_str, day_str, year_str = match.groups()
                desc_dt = datetime.strptime(
                    f"{month_str} {day_str} {year_str}", "%B %d %Y"
                ).replace(tzinfo=timezone.utc)
                gap_days = (desc_dt - end_dt).days
                if gap_days > 3:
                    return False, (
                        f"Description resolve date {desc_dt.strftime('%Y-%m-%d')} is {gap_days}d "
                        f"after end_date: '{match.group()[:60]}'"
                    )
            except ValueError:
                continue

    return True, ""


def run_all_filters(candidate: dict, open_condition_ids: set,
                    tracker_data: dict = None) -> tuple:
    """
    Run all filters on a candidate.
    Returns (passed: bool, reason: str).
    """
    checks = [
        check_min_price(candidate),
        check_neg_risk(candidate, tracker_data),
        check_liquidity(candidate),
        check_end_date(candidate),
        check_sports_cancelled(candidate),
        check_financial_asset(candidate),
        check_toxic_keywords(candidate),
        check_delayed_resolution(candidate),
        check_title_date_vs_end_date(candidate),
        check_coin_flip(candidate),
        check_sports_win_only(candidate),
        check_threshold_market(candidate),
        # check_weather — disabled, testing with $1 bets (2026-03-25)
        # check_slow_keywords — disabled, testing with $1 bets (2026-03-25)
        check_stale(candidate),
        check_already_bought(candidate, open_condition_ids),
    ]

    for passed, reason in checks:
        if not passed:
            return False, reason

    return True, "All filters passed"
