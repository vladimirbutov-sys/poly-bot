"""Main entry point for 98_sure_bot — high-probability outcome trader."""
import sys
import os
import time
import logging
import threading
from datetime import datetime, timezone

# === Encoding fix for Windows console ===
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')
sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')

from config import (
    SCAN_INTERVAL, BET_SIZE, BET_SIZE_REGULAR, BET_SIZE_NEG_RISK, BET_SIZE_SUB_MATCH,
    BET_SIZE_WEATHER, BET_SIZE_SLOW, BET_SIZE_TEST_LOW,
    PRICE_THRESHOLD, MAX_PRICE, BOT_DIR, LOG_FILE,
    MAX_TOTAL_FROZEN,
)
import scanner
import filters
import executor
import tracker
import redeemer
import telegram_notify as tg


# === Logging setup ===
def setup_logging():
    """Configure logging to both file and console."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)


logger = logging.getLogger("main")


import re

_SUB_MATCH_PATTERNS = [
    # Esports: maps, games, sets
    r'\bgame\s*\d+\b', r'\bmap\s*\d+\b', r'\bset\s*\d+\b',
    r'\bround\s*\d+\b', r'\bperiod\s*\d+\b', r'\bhalf\s*[12]\b',
    r'\b(1st|2nd|3rd|4th|5th)\s*(game|map|set|round|period|half)\b',
    # Fighting: method of victory (not match outcome)
    r'\bwin\s+by\s+(KO|TKO|submission|decision|split|unanimous|majority)\b',
    r'\b(KO|TKO)\b',
    r'\bend in a draw\b',
    r'\bgo the distance\b',
    r'\b(over|under)\s+\d+\.?\d*\s+rounds?\b',
    r'\bmethod of victory\b',
    # Sports: props, not match outcome
    r'\btotal (goals|points|runs|corners|cards)\b',
    r'\b(over|under)\s+\d+\.?\d*\s+(goals|points|runs)\b',
    r'\bfirst (goal|point|score|blood)\b',
    r'\bboth teams (to )?score\b',
    r'\bclean sheet\b',
    r'\bexact score\b',
]

_ELECTION_PATTERNS = [
    r'\b(election|mayoral|gubernatorial)\b',
    r'\bleadership\s+(election|race|contest|vote)\b',
    r'\bnext\s+(prime\s+minister|president|chancellor|governor|mayor|PM)\b',
    r'\bnext\s+L.gma.ur\b',
    r'\bpart\s+of\s+the\s+next\s+(government|coalition|cabinet)\b',
    r'\bwin\s+(the\s+most\s+|)\d+\+?\s*seats\b',
    r'\bwin\s+the\s+\d{4}\b.*\b(mayoral|gubernat)',
]

def _is_election(title: str) -> bool:
    """Detect election/political appointment markets (slow resolution)."""
    return any(re.search(p, title, re.IGNORECASE) for p in _ELECTION_PATTERNS)


# === Strike markets: military action / strike markets bet only on the day of event ===
_STRIKE_PATTERNS = [
    r'\bstrike\b',
    r'\bmilitary\s+action\b',
    r'\battack\b',
    r'\bmissile\b',
    r'\bairstrike\b',
]

# Pattern to extract the event date from strike market titles
# Examples:
#   "Will Israel take military action in Gaza on April 2, 2026?"
#   "Israel strike on Yemen by April 30, 2026?"
#   "Iran strike UAE again in March?"
_STRIKE_DATE_PATTERN = re.compile(
    r'on\s+(january|february|march|april|may|june|july|august|september|october|november|december)'
    r'\s+(\d{1,2})(?:,?\s*(\d{4}))?',
    re.IGNORECASE,
)


def _is_strike_market(title: str) -> bool:
    """Detect strike/military action markets."""
    return any(re.search(p, title, re.IGNORECASE) for p in _STRIKE_PATTERNS)


def _extract_strike_date(title: str):
    """Extract the event date from a strike market title. Returns datetime or None."""
    m = _STRIKE_DATE_PATTERN.search(title)
    if not m:
        return None
    month_str, day_str, year_str = m.groups()
    year = int(year_str) if year_str else datetime.now(timezone.utc).year
    try:
        dt = datetime.strptime(f"{month_str} {day_str} {year}", "%B %d %Y")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _strike_is_today(title: str) -> bool:
    """Check if strike market's event date is today (UTC)."""
    dt = _extract_strike_date(title)
    if dt is None:
        return False
    today = datetime.now(timezone.utc).date()
    return dt.date() == today


def _get_event_key(title: str) -> str:
    """Normalize title to an event key by stripping number ranges.
    'Will Elon Musk post 160-179 tweets from March 17...' -> 'will elon musk post N tweets from march N...'
    """
    t = title.lower()
    t = re.sub(r'\d+\s*-\s*\d+', 'N', t)       # 160-179 -> N
    t = re.sub(r'\d+\+', 'N', t)                # 200+ -> N
    t = re.sub(r'\b\d{1,3}\b', 'N', t)          # standalone numbers < 1000
    t = re.sub(r'\s+', ' ', t).strip()
    return t


_WEATHER_PATTERNS = [
    r'\btemperature\b.*\d+\s*[°]?\s*[FC]\b',
    r'\bhighest\s+temp\b.*\d+\s*[°]?\s*[FC]\b',
    r'\d+\s*[°]?\s*[FC]\b.*\btemperature\b',
    r'\d+\s*[°]?\s*[FC]\b.*\bhighest\s+temp\b',
]

def _is_sub_match(title: str) -> bool:
    """Detect game/map/set-specific markets (sub-match)."""
    t = title.lower()
    return any(re.search(p, t) for p in _SUB_MATCH_PATTERNS)


def _is_weather(title: str) -> bool:
    """Detect weather/temperature markets (test mode: $1 bets)."""
    for pattern in _WEATHER_PATTERNS:
        if re.search(pattern, title, re.IGNORECASE):
            return True
    return False


_SLOW_PATTERNS = [
    r'\btop\b', r'\bseason\b', r'\bmost\b',
    r'\btransit\b', r'\bstrait\b', r'\bships?\b',
    r'\bweekly\b', r'\bmonthly\b',
    # Entertainment ratings — unpredictable outcomes
    r'\b(rotten tomatoes|tomatometer|metacritic|imdb)\b',
    r'\bscore\s+(at least|over|above|under|below)\b',
    r'\b(box office|gross|opening weekend)\b',
]

def _is_slow(title: str) -> bool:
    """Detect slow-resolving markets (test mode: $1 bets)."""
    t = title.lower()
    return any(re.search(p, t) for p in _SLOW_PATTERNS)


def process_candidate(candidate: dict, data: dict) -> bool:
    """
    Process a single candidate: check balance, calculate price, place order, track.
    Returns True if a bet was placed.
    """
    title = candidate["question"]
    token_id = candidate["token_id"]
    condition_id = candidate["condition_id"]
    market_price = candidate["price"]
    neg_risk = candidate.get("neg_risk", False)
    category = candidate.get("category", "")

    # --- Block sub-match markets (map/game/set) — only bet on full match outcomes ---
    if _is_sub_match(title):
        logger.info("SUB-MATCH SKIP: %s", title[:60])
        return False

    # --- Block election/appointment markets (slow resolution, freezes capital) ---
    if _is_election(title):
        logger.info("ELECTION SKIP: %s", title[:60])
        return False

    # --- Block slow-resolving markets (freeze capital too long) ---
    if _is_slow(title):
        logger.info("SLOW SKIP: %s", title[:60])
        return False

    # --- Limit positions per event ---
    # Default: 1 per event. Tweet/post bracket markets: allow 2 per event.
    event_key = _get_event_key(title)
    title_lower = title.lower()
    is_tweet_market = bool(re.search(r'\b(tweets?|posts?)\b', title_lower))
    max_per_event = 2 if is_tweet_market else 1

    open_positions = {k: v for k, v in data.get("positions", {}).items()
                      if v.get("status") == "open"}
    same_event_count = sum(
        1 for pos in open_positions.values()
        if _get_event_key(pos.get("title", "")) == event_key
    )
    if same_event_count >= max_per_event:
        logger.info("DUPLICATE EVENT SKIP (%d/%d): %s",
                    same_event_count, max_per_event, title[:60])
        return False

    # --- Choose bet size by market type ---
    # Live test: non-politics at 96.5-97.5% → $1 bets
    is_politics = category.lower() in ("politics", "geopolitics")
    if not is_politics and market_price < 0.975:
        target_bet = BET_SIZE_TEST_LOW
    elif _is_weather(title):
        target_bet = BET_SIZE_WEATHER
    elif neg_risk:
        target_bet = BET_SIZE_NEG_RISK
    else:
        target_bet = BET_SIZE_REGULAR

    # --- Check total frozen capital ---
    open_positions = {k: v for k, v in data.get("positions", {}).items()
                      if v.get("status") == "open"}
    total_frozen = sum(p.get("cost_usd", 0) for p in open_positions.values())
    if total_frozen + target_bet > MAX_TOTAL_FROZEN:
        logger.warning("Max frozen reached: $%.2f + $%.2f > $%.2f",
                        total_frozen, target_bet, MAX_TOTAL_FROZEN)
        return False

    # --- Filter 8: Check USDC balance ---
    usdc_balance = redeemer.get_usdc_balance_usd()
    if usdc_balance < target_bet:
        logger.warning("Insufficient USDC balance: $%.2f < $%.2f, skipping",
                        usdc_balance, target_bet)
        return False

    # --- Calculate limit price from Gamma + verify against CLOB ---
    limit_price = executor.get_limit_price(market_price)
    if limit_price is None:
        logger.debug("No valid limit price for %.3f, skipping: %s", market_price, title[:60])
        return False

    # Verify CLOB price (stale Gamma protection)
    price_ok, clob_price = executor.verify_price(token_id, market_price)
    if not price_ok:
        logger.warning("STALE PRICE SKIP: %s | Gamma=%.3f, CLOB=%.3f",
                        title[:60], market_price, clob_price)
        tg.send(f"Stale price skip: {title[:50]}\nGamma: {market_price:.3f} vs CLOB: {clob_price:.3f}")
        return False

    # --- Sports overround check (dynamic: ratio >= Sum(Yes) * 0.5) ---
    # On multi-outcome tournaments (golf, tennis, elections), the opposite side
    # (Yes) can be much higher than (1 - No_price), meaning No is overpriced.
    # Uses Sum(Yes) from all sub-markets of the same event (cached per scan cycle).
    # Skip if ratio >= S * 0.5 (safety margin for non-uniform overround).
    if neg_risk and candidate.get("event_id"):
        event_sum_yes = scanner.get_event_sum_yes().get(candidate["event_id"], 0)
        if event_sum_yes > 1.0:  # overround exists
            opposite_token = candidate.get("opposite_token_id", "")
            if opposite_token:
                opp_price = executor.get_clob_price(opposite_token)
                if opp_price is not None:
                    our_implied = 1 - market_price
                    if our_implied > 0:
                        ratio = opp_price / our_implied
                        threshold = max(event_sum_yes * 0.5, 1.0)
                        if ratio >= threshold:
                            logger.warning(
                                "OVERROUND SKIP: %s | No=%.3f, CLOB_Yes=%.3f, "
                                "ratio=%.1fx >= S*0.5=%.1f (S=%.1f%%)",
                                title[:60], market_price, opp_price,
                                ratio, threshold, event_sum_yes * 100)
                            return False

    logger.info("Placing: %s | gamma=%.3f limit=%.3f",
                 title[:60], market_price, limit_price)

    # --- Calculate bet size ---
    bet_size = executor.calculate_bet_size(limit_price, target_bet)
    if bet_size is None:
        logger.debug("Min 5 shares too expensive at %.3f, skipping: %s", limit_price, title[:60])
        return False

    # --- Check tracker balance ---
    if data["stats"]["current_balance"] < bet_size:
        logger.warning("Tracker balance too low: $%.2f < $%.2f",
                        data["stats"]["current_balance"], bet_size)
        return False

    # --- Check on-chain: do we already hold tokens? ---
    # Prevents silent accumulation from untracked partial fills
    # (Putnam $40 / Iran $75 bug: CLOB says "not filled" but shares land on-chain)
    onchain_balance = redeemer.check_token_balance(token_id)
    if onchain_balance > 0:
        onchain_shares = onchain_balance / 1e6
        logger.warning("ALREADY HOLD %.2f shares on-chain, SKIP: %s",
                        onchain_shares, title[:60])
        # Re-add to tracker if missing
        d = tracker.load()
        if condition_id not in tracker.get_open_condition_ids(d):
            logger.warning("Re-tracking on-chain position: %s", title[:60])
            real_cost = onchain_shares * market_price
            tracker.record_position(
                d, f"recovered_{condition_id[:16]}", condition_id, token_id, title,
                market_price, onchain_shares, real_cost,
                neg_risk=neg_risk, category=category,
                end_date=candidate.get("end_date", ""),
            )
        return False

    # --- Place order ---
    logger.info("Placing bet: %s | price %.3f -> limit %.3f | $%.2f",
                title[:60], market_price, limit_price, bet_size)

    result = executor.place_limit_buy(token_id, limit_price, bet_size)
    if not result:
        logger.warning("Order failed: %s", title[:60])
        tg.error(f"Order failed: {title}")
        return False

    order_id = result["order_id"]

    # --- Record position ---
    data = tracker.load()  # reload fresh
    tracker.record_position(
        data, order_id, condition_id, token_id, title,
        result["price"], result["size_shares"], result["cost_usd"],
        neg_risk=neg_risk, category=category,
        end_date=candidate.get("end_date", ""),
    )

    tg.new_bet(title, result["price"], result["cost_usd"], order_id)

    # --- Wait for fill in background thread ---
    def _wait_for_fill():
        fill_result = executor.wait_for_fill(order_id)
        final_status = fill_result["final_status"]
        filled_shares = fill_result["filled_shares"]
        original_shares = fill_result["original_shares"]

        if final_status == "MATCHED":
            logger.info("FILLED: %s", title[:60])
            tg.bet_filled(title, result["price"], filled_shares, filled_shares * result["price"])

        elif final_status == "PARTIAL":
            # Partial fill — update position with actual fill
            logger.info("PARTIAL: %s | %.2f / %.2f shares",
                        title[:60], filled_shares, original_shares)
            d = tracker.load()
            filled_cost = filled_shares * result["price"]
            tracker.update_position_fill(d, order_id, filled_shares, filled_cost)
            tg.bet_partial(title, filled_shares, original_shares)

        else:
            # CLOB says not filled — but check on-chain to be sure.
            # Partial fills can land on-chain before CLOB reports them.
            # Without this check, the position gets removed, the bot re-bets,
            # and shares silently accumulate (Putnam $40, Iran $75 bug).
            onchain_balance = redeemer.check_token_balance(token_id)
            onchain_shares = onchain_balance / 1e6 if onchain_balance > 0 else 0

            if onchain_shares >= 4.99:  # MIN_SHARES is 5
                # Shares exist on-chain — keep position, fix amount
                logger.warning("NOT FILLED per CLOB but %.2f shares ON-CHAIN: %s",
                               onchain_shares, title[:60])
                d = tracker.load()
                real_cost = onchain_shares * result["price"]
                tracker.update_position_fill(d, order_id, onchain_shares, real_cost)
            else:
                # Truly not filled — safe to remove
                logger.info("NOT FILLED (%s): %s", final_status, title[:60])
                d = tracker.load()
                tracker.remove_position(d, order_id)
                tg.bet_cancelled(title, f"Status: {final_status}")

    thread = threading.Thread(target=_wait_for_fill, daemon=True)
    thread.start()

    return True


PAUSE_FILE = os.path.join(BOT_DIR, "PAUSE")


def run_scan_cycle():
    """Run one full scan-filter-buy cycle."""
    # Check pause flag — touch PAUSE file to stop new bets (redeem keeps running)
    if os.path.exists(PAUSE_FILE):
        logger.info("PAUSED: new bets paused (PAUSE file exists). Redeem still active.")
        return

    # Load tracker data
    data = tracker.load()
    open_cids = tracker.get_open_condition_ids(data)

    portfolio_value = tracker.get_portfolio_value(data)
    logger.info("Scan cycle started | Balance: $%.2f | Portfolio: $%.2f | Open: %d",
                data["stats"]["current_balance"], portfolio_value, len(open_cids))

    # Scan markets
    candidates = scanner.scan()
    if not candidates:
        logger.info("No candidates found this cycle")
        return

    # SHORT FIRST: sort by end_date ascending (fastest resolve first), then price ascending (highest ROI)
    candidates.sort(key=lambda c: (c.get("end_date") or "9999", c["price"]))

    # Deduplicate by condition_id (scanner pagination can return same market twice)
    seen_cids = set()
    unique = []
    for c in candidates:
        cid = c["condition_id"]
        if cid not in seen_cids:
            seen_cids.add(cid)
            unique.append(c)
    candidates = unique

    # PARTITION: strike markets first, rest after
    # For strike markets: only bet if today is the event day (no early/late bets)
    strike_candidates = []
    regular_candidates = []
    for c in candidates:
        title = c.get("question", "")
        if _is_strike_market(title):
            if _strike_is_today(title):
                strike_candidates.append(c)
            # else: skip strike markets that aren't for today
        else:
            regular_candidates.append(c)

    if strike_candidates:
        logger.info("Strike markets today: %d (processed first)", len(strike_candidates))

    ordered = strike_candidates + regular_candidates

    # Filter and process
    bets_placed = 0
    for candidate in ordered:
        # Run all filters (including duplicate check)
        passed, reason = filters.run_all_filters(candidate, open_cids, data)
        if not passed:
            logger.debug("SKIP: %s | %s", candidate["question"][:50], reason)
            continue

        # Try to place bet
        data = tracker.load()  # reload for up-to-date balance
        if process_candidate(candidate, data):
            bets_placed += 1
            # Add to open set so we don't buy same market twice in one cycle
            open_cids.add(candidate["condition_id"])

    logger.info("Scan cycle done: %d candidates, %d bets placed", len(candidates), bets_placed)


def _cleanup_ghost_positions():
    """Remove 'open' positions that have 0 tokens on-chain (order was never filled).
    This happens when the bot restarts while a fill-checker thread was waiting.
    """
    data = tracker.load()
    open_positions = tracker.get_open_positions(data)
    if not open_positions:
        return

    removed = 0
    for key, pos in list(open_positions.items()):
        token_id = pos.get("token_id", "")
        if not token_id:
            continue

        balance = redeemer.check_token_balance(token_id)
        if balance < 0:
            logger.warning("RPC error checking %s, skipping cleanup", pos.get("title", "?")[:40])
            continue
        if balance == 0:
            title = pos.get("title", "?")
            logger.warning("Ghost position (0 on-chain): %s — removing", title[:60])
            data = tracker.load()
            tracker.remove_position(data, key)
            removed += 1
            tg.send(f"Ghost removed: {title} (0 shares on-chain)")
        elif balance > 0:
            # Check if actual shares differ from recorded
            recorded_shares = pos.get("size_shares", 0)
            real_shares = balance / 1e6
            if abs(real_shares - recorded_shares) > 0.01:
                logger.warning("Share mismatch: %s | recorded=%.2f, on-chain=%.2f — fixing",
                               pos.get("title", "?")[:60], recorded_shares, real_shares)
                data = tracker.load()
                real_cost = real_shares * pos.get("entry_price", 0)
                tracker.update_position_fill(data, key, real_shares, real_cost)

    if removed:
        logger.info("Cleaned up %d ghost positions", removed)
    else:
        logger.info("No ghost positions found")


def main():
    setup_logging()

    logger.info("=" * 50)
    logger.info("  98_sure_bot")
    logger.info("  Strategy: buy outcomes priced %.1f-%.1fc",
                PRICE_THRESHOLD * 100, MAX_PRICE * 100)
    logger.info("  Bet size: reg $%.2f / neg $%.2f | Scan interval: %ds",
                BET_SIZE_REGULAR, BET_SIZE_NEG_RISK, SCAN_INTERVAL)
    logger.info("  Started: %s", datetime.now(timezone.utc).isoformat())
    logger.info("=" * 50)

    # Show current stats
    data = tracker.load()
    stats = tracker.get_summary(data)
    open_positions = tracker.get_open_positions(data)
    logger.info("Balance: $%.2f | Bets: %d | W/L: %d/%d | PnL: $%+.2f | Open: %d",
                stats["current_balance"], stats["total_bets"],
                stats["wins"], stats["losses"], stats["total_pnl"],
                len(open_positions))

    # Cleanup ghost positions (orders recorded but never filled on-chain)
    _cleanup_ghost_positions()

    # Send startup notification
    tg.startup(stats["current_balance"], len(open_positions))

    # Start auto-redeem in background
    redeemer.start_background()

    # Report every 8 hours (28800 seconds)
    REPORT_INTERVAL = 28800
    last_report_time = time.time()

    # Strategy review every 24 hours
    REVIEW_INTERVAL = 86400
    last_review_time = time.time()

    # Main scan loop
    try:
        while True:
            try:
                run_scan_cycle()
            except Exception as e:
                logger.error("Scan cycle error: %s", e, exc_info=True)
                tg.error(f"Scan cycle error: {e}")

            # Daily strategy review
            if time.time() - last_review_time >= REVIEW_INTERVAL:
                try:
                    import strategy_review
                    strategy_review.run_review()
                    last_review_time = time.time()
                except Exception as e:
                    logger.error("Strategy review error: %s", e)

            # Check if it's time for a report
            if time.time() - last_report_time >= REPORT_INTERVAL:
                try:
                    data = tracker.load()
                    report_text = tracker.generate_report(data)
                    logger.info("8-hour report:\n%s", report_text)
                    tg.report(report_text)
                    last_report_time = time.time()
                except Exception as e:
                    logger.error("Report error: %s", e)

            # Sleep in 60-second chunks (Windows sleep/hibernate safe)
            remaining = SCAN_INTERVAL
            while remaining > 0:
                time.sleep(min(60, remaining))
                remaining -= 60

    except KeyboardInterrupt:
        logger.info("Shutting down...")
        tg.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
