"""Market scanner — fetches all open markets and finds high-probability candidates."""
import json
import logging
import requests

from config import GAMMA_API, PRICE_THRESHOLD, MAX_PRICE

logger = logging.getLogger("scanner")

PAGE_SIZE = 500


def categorize(question: str) -> str:
    """Keyword-based market categorization (Gamma API has no category field)."""
    q = question.lower()

    # Sports
    if any(k in q for k in [
        "vs.", "vs ", "o/u ", "spread:", "map ", "game handicap",
        "nba", "nhl", "mlb", "nfl", "mls", "ufc", "atp", "wta",
        "counter-strike", "cs2", "valorant", "dota", "lol:",
        "tennis", "boxing", "cricket", "t20", "ipl",
    ]):
        if any(k in q for k in ["counter-strike", "cs2", "valorant", "dota", "lol:", "league of legends"]):
            return "esports"
        if any(k in q for k in ["ufc", "boxing", "mma"]):
            return "fighting"
        if any(k in q for k in ["nba", "basketball"]):
            return "basketball"
        if any(k in q for k in ["nhl", "hockey"]):
            return "hockey"
        if any(k in q for k in ["mlb", "baseball"]):
            return "baseball"
        if any(k in q for k in ["nfl", "football", "super bowl"]):
            return "american_football"
        if any(k in q for k in [
            "mls", "soccer", "premier league", "la liga", "serie a", "ucl",
            "fc ", "cf ", "united", "city fc",
        ]):
            return "soccer"
        if any(k in q for k in ["atp", "wta", "tennis", "open,", "miami open", "qualification:"]):
            return "tennis"
        if "cricket" in q:
            return "cricket"
        return "sports_other"

    if any(k in q for k in ["bitcoin", "btc", "ethereum", "eth", "crypto", "solana", "token"]):
        return "crypto"
    if any(k in q for k in [
        "president", "election", "trump", "biden", "congress", "senate",
        "governor", "democrat", "republican", "vote", "minister", "parliament",
    ]):
        return "politics"
    if any(k in q for k in [
        "war", "strike", "invasion", "military", "ceasefire", "nato",
        "ukraine", "russia", "iran", "israel", "sanction",
    ]):
        return "geopolitics"
    if any(k in q for k in [
        "s&p", "nasdaq", "stock", "gold", "oil", "crude", "fed ",
        "interest rate", "gdp", "inflation",
    ]):
        return "finance"
    if any(k in q for k in ["ai ", "openai", "chatgpt", "google", "apple", "meta ", "amazon"]):
        return "tech"

    return "other"


def fetch_all_open_markets() -> list:
    """
    Fetch all open markets from Gamma API with pagination.
    Returns list of raw market dicts.
    """
    all_markets = []
    offset = 0

    while True:
        try:
            resp = requests.get(
                f"{GAMMA_API}/markets",
                params={
                    "closed": "false",
                    "limit": PAGE_SIZE,
                    "offset": offset,
                },
                timeout=30,
            )
            resp.raise_for_status()
            batch = resp.json()
        except Exception as e:
            logger.error("Gamma API error at offset %d: %s", offset, e)
            break

        if not batch:
            break

        all_markets.extend(batch)
        logger.debug("Fetched %d markets (offset %d)", len(batch), offset)

        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return all_markets


def parse_candidates(markets: list) -> list:
    """
    From raw markets, find outcomes with price in [PRICE_THRESHOLD, MAX_PRICE].
    Returns list of candidate dicts ready for filtering.
    """
    candidates = []

    for market in markets:
        try:
            # outcomePrices is a JSON string like '["0.985", "0.015"]'
            raw_prices = market.get("outcomePrices")
            if not raw_prices:
                continue
            prices = json.loads(raw_prices)

            raw_outcomes = market.get("outcomes")
            if not raw_outcomes:
                continue
            outcomes = json.loads(raw_outcomes) if isinstance(raw_outcomes, str) else raw_outcomes

            raw_token_ids = market.get("clobTokenIds")
            if not raw_token_ids:
                continue
            token_ids = json.loads(raw_token_ids) if isinstance(raw_token_ids, str) else raw_token_ids

            if len(prices) != len(outcomes) or len(prices) != len(token_ids):
                continue

            for i, price_str in enumerate(prices):
                price = float(price_str)
                if PRICE_THRESHOLD <= price <= MAX_PRICE:
                    # Find opposite token (for 2-outcome markets)
                    opposite_token = ""
                    if len(token_ids) == 2:
                        opposite_token = token_ids[1 - i]

                    # Extract event_id for overround grouping
                    events_list = market.get("events", [])
                    event_id = str(events_list[0].get("id", "")) if events_list else ""

                    candidates.append({
                        "condition_id": market.get("conditionId", ""),
                        "question_id": market.get("questionId", ""),
                        "token_id": token_ids[i],
                        "opposite_token_id": opposite_token,
                        "outcome": outcomes[i],
                        "price": price,
                        "question": market.get("question", ""),
                        "description": market.get("description", ""),
                        "liquidity": float(market.get("liquidityNum", 0) or 0),
                        "volume_24h": float(market.get("volume24hr", 0) or 0),
                        "volume_total": float(market.get("volumeNum", 0) or 0),
                        "neg_risk": market.get("negRisk", False),
                        "game_start_time": market.get("gameStartTime", ""),
                        "end_date": market.get("endDate", ""),
                        "category": categorize(market.get("question", "")),
                        "uma_status": market.get("umaResolutionStatus", ""),
                        "event_id": event_id,
                    })

        except (json.JSONDecodeError, ValueError, TypeError, IndexError) as e:
            logger.debug("Skip market parse error: %s", e)
            continue

    return candidates


def build_event_sum_yes(markets: list) -> dict:
    """
    For neg_risk multi-outcome events, calculate Sum(Yes) per event.
    Uses Gamma API outcomePrices — fast, no extra API calls.
    Returns dict: event_id -> sum_of_yes_prices.
    """
    event_sums = {}  # event_id -> total Yes price

    for market in markets:
        if not market.get("negRisk"):
            continue

        events = market.get("events", [])
        if not events:
            continue
        event_id = str(events[0].get("id", ""))
        if not event_id:
            continue

        raw_prices = market.get("outcomePrices")
        if not raw_prices:
            continue
        try:
            prices = json.loads(raw_prices)
            if len(prices) == 2:
                # Yes is the smaller price (player wins), No is the bigger
                yes_price = min(float(p) for p in prices)
                event_sums[event_id] = event_sums.get(event_id, 0) + yes_price
        except (json.JSONDecodeError, ValueError):
            continue

    return event_sums


# Cache for current scan cycle
_event_sum_yes_cache = {}


def get_event_sum_yes() -> dict:
    """Return cached Sum(Yes) per event for current scan cycle."""
    return _event_sum_yes_cache


def scan() -> list:
    """
    Full scan: fetch markets, parse candidates.
    Returns list of candidate dicts (before filtering).
    """
    global _event_sum_yes_cache

    logger.info("Starting market scan...")
    markets = fetch_all_open_markets()
    logger.info("Fetched %d open markets", len(markets))

    # Build Sum(Yes) cache for overround check (no extra API calls)
    _event_sum_yes_cache = build_event_sum_yes(markets)
    logger.debug("Built Sum(Yes) for %d neg_risk events", len(_event_sum_yes_cache))

    candidates = parse_candidates(markets)
    logger.info("Found %d candidates with price in [%.3f, %.3f]",
                len(candidates), PRICE_THRESHOLD, MAX_PRICE)

    return candidates
