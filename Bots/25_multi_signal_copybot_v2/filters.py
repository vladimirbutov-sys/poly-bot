"""Signal detection and filtering for Multi-Signal Copy-Bot.

Any of 3 players can be the signal source (Car, aenews2, denizz).
Opposition check: none of the OTHER 2 players may have $500+ on opposite side.
Price range: per-player (Car/aenews2: 10-82c, denizz: 15-82c).
"""
import requests
from datetime import datetime, timezone, timedelta
from config import (
    PLAYERS, GAMMA_API, CLOB_HOST, DATA_API,
    CATEGORY_KEYWORDS, EXCLUDED_KEYWORDS, PRICE_FILTER,
    MIN_PLAYER_INVESTED, MAX_SLIPPAGE_TIERS, OPPOSITION_MIN_USD,
    OPPOSITION_IGNORE,
    BET_FORMULA_A, BET_FORMULA_B, MAX_BET_USD,
    PRICE_BET_MULTIPLIERS, BET_SCALE,
)

def get_max_slippage(price: float) -> float:
    """Return max allowed slippage based on entry price tier."""
    for min_p, max_p, max_slip in MAX_SLIPPAGE_TIERS:
        if min_p <= price < max_p:
            return max_slip
    return 0.015  # fallback


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def get_market_info(token_id: str) -> dict | None:
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"clob_token_ids": token_id},
            timeout=10,
        )
        if resp.status_code == 200:
            markets = resp.json()
            if markets:
                return markets[0]
    except Exception as e:
        print(f"[FILTER] Gamma API error: {e}")
    return None


def get_orderbook_prices(token_id: str) -> tuple | None:
    try:
        resp = requests.get(
            f"{CLOB_HOST}/book",
            params={"token_id": token_id},
            timeout=10,
        )
        if resp.status_code == 200:
            book = resp.json()
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            best_bid = max(float(b["price"]) for b in bids) if bids else 0.0
            best_ask = min(float(a["price"]) for a in asks) if asks else 1.0
            return best_bid, best_ask
    except Exception as e:
        print(f"[FILTER] Orderbook error: {e}")
    return None


def get_event_tags(event_slug: str) -> list:
    if not event_slug:
        return []
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"slug": event_slug},
            timeout=10,
        )
        if resp.status_code == 200:
            events = resp.json()
            if events:
                tags = events[0].get("tags", [])
                return [t.get("label", "") for t in tags if t.get("label")]
    except Exception as e:
        print(f"[FILTER] Events API error: {e}")
    return []


def get_player_positions(condition_id: str, wallet: str) -> list:
    """Get positions for any wallet on this condition."""
    try:
        resp = requests.get(
            f"{DATA_API}/positions",
            params={"user": wallet, "market": condition_id},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[FILTER] Position API error ({wallet[:8]}): {e}")
    return []


def get_player_invested_on_token(condition_id: str, wallet: str, token_id: str) -> float:
    """Return player's CURRENT NET USD invested on a specific token.

    Net = current_size × avgPrice (what they hold RIGHT NOW × their cost basis).

    Changed 2026-04-09 from gross (totalBought × avgPrice) to net.
    Reason: gross persisted historical buys even after the player exited.
    Example: denizz buys $30k, sells half at profit, holds $15k. Gross still
    reports $30k → bot tier-classifies as S+ ($200 bet) when reality is S
    ($105). Bot was over-sizing every position where the player had partial-
    exited. Net reflects current conviction, not history.

    Edge case: if size=0 (fully exited), returns 0. main.py uses
    `max(buffer, api)` so a fresh BUY signal still gets through if the
    monitor saw it in the last 24h.

    Returns 0.0 on API failure or no matching position.
    """
    try:
        positions = get_player_positions(condition_id, wallet)
        for p in positions:
            p_token = p.get("asset", "") or p.get("tokenId", "")
            if p_token != token_id:
                continue
            ap = float(p.get("avgPrice", 0) or 0)
            size = float(p.get("size", 0) or 0)
            return size * ap
    except Exception as e:
        print(f"[FILTER] get_player_invested_on_token error: {e}")
    return 0.0


def get_player_avg_price(condition_id: str, wallet: str, token_id: str) -> float:
    """Return player's current avg buy price on this token. Used to detect
    'late entry' — when the current market price is much higher than the
    player's cost basis, we're copying at a bad moment and should size down."""
    try:
        positions = get_player_positions(condition_id, wallet)
        for p in positions:
            p_token = p.get("asset", "") or p.get("tokenId", "")
            if p_token != token_id:
                continue
            return float(p.get("avgPrice", 0) or 0)
    except Exception as e:
        print(f"[FILTER] get_player_avg_price error: {e}")
    return 0.0


def get_player_cost_basis(condition_id: str, wallet: str, token_id: str) -> float:
    """Return player's current weighted avg BUY price (cost basis) on this token.

    Strategy:
    1. Prefer data-api /positions → its `avgPrice` is the weighted average
       of REMAINING shares (accounts for sells correctly). This is what the
       player sees in the UI as their own cost basis. Use when position>0.
    2. Fallback (full exit): reconstruct cost basis with FIFO from /activity.
       When a sell happens, remove shares from the oldest buy lots first,
       then weighted-average what's left. This matches the "avgPrice at the
       moment of the last sell" concept.

    Used by exit_manager to decide whether the player's sell was in profit
    or loss relative to their own cost basis.

    Returns 0.0 on error / no buys found.
    """
    # 1. Fast path: data-api /positions
    try:
        existing_avg = get_player_avg_price(condition_id, wallet, token_id)
        if existing_avg > 0.0:
            return existing_avg
    except Exception:
        pass

    # 2. Full-exit fallback: FIFO reconstruction
    try:
        # Collect all TRADE events on this asset in chronological order
        trades = []
        offset = 0
        while offset < 2000:
            resp = requests.get(
                f"{DATA_API}/activity",
                params={
                    "user": wallet,
                    "market": condition_id,
                    "limit": 500,
                    "offset": offset,
                },
                timeout=15,
            )
            if not resp.ok:
                break
            batch = resp.json() or []
            if not batch:
                break
            for a in batch:
                if a.get("type") != "TRADE":
                    continue
                if str(a.get("asset", "")) != str(token_id):
                    continue
                trades.append(a)
            if len(batch) < 500:
                break
            offset += 500

        # Sort chronologically (data-api returns newest first by default)
        trades.sort(key=lambda x: x.get("timestamp", 0))

        # FIFO lot matching
        lots = []  # list of [remaining_size, price]
        last_avg_before_final_sell = 0.0
        for t in trades:
            side = t.get("side", "")
            size = float(t.get("size", 0) or 0)
            price = float(t.get("price", 0) or 0)
            if size <= 0 or price <= 0:
                continue
            if side == "BUY":
                lots.append([size, price])
            elif side == "SELL":
                # Snapshot avg right before this sell (for fallback return value)
                rem = sum(l[0] for l in lots)
                if rem > 0:
                    last_avg_before_final_sell = sum(l[0] * l[1] for l in lots) / rem
                # Consume FIFO from oldest lot
                to_remove = size
                while to_remove > 1e-6 and lots:
                    lot = lots[0]
                    if lot[0] <= to_remove + 1e-6:
                        to_remove -= lot[0]
                        lots.pop(0)
                    else:
                        lot[0] -= to_remove
                        to_remove = 0

        # Prefer remaining-shares avg, else last known avg before final sell
        rem = sum(l[0] for l in lots)
        if rem > 0:
            return sum(l[0] * l[1] for l in lots) / rem
        if last_avg_before_final_sell > 0:
            return last_avg_before_final_sell
    except Exception as e:
        print(f"[FILTER] get_player_cost_basis fallback error: {e}")
    return 0.0


def calculate_entry_size_multiplier(player_avg: float, current_ask: float) -> tuple:
    """Rule A+: penalize late entries relative to player's cost basis.

    Idea: if we're copying the player at a price 2× higher than their own
    average, our risk/reward is much worse than theirs. Scale our position
    size down proportionally — still participate, but with reduced exposure.

    Returns (multiplier, reason_string).
    """
    if player_avg <= 0 or current_ask <= 0:
        return 1.0, "no player history"
    mult = current_ask / player_avg
    if mult <= 1.2:
        return 1.0, f"on-time ({mult:.2f}x)"
    elif mult <= 1.5:
        return 0.75, f"late {mult:.2f}x - 75% size"
    elif mult <= 2.0:
        return 0.50, f"bad {mult:.2f}x - 50% size"
    elif mult <= 3.0:
        return 0.25, f"terrible {mult:.2f}x - 25% size"
    else:
        return 0.10, f"extreme {mult:.2f}x - 10% size"


def detect_merge_prep(condition_id: str, wallet: str, our_outcome: str) -> dict:
    """Detect if the player is buying our side *just to merge* (arbitrage
    exit) rather than opening a real directional position.

    Merge requires holding equal amounts of Yes + No. A player preparing to
    merge accumulates the side they're short on until it matches the side
    they already hold.

    Heuristic (ratio-based):
      skip as merge-prep when BOTH conditions hold:
        1. opposite_size >= 500 sh (floor, filters dust)
        2. opposite_size <= 5 × our_side_size
           (= opposite is within 5× of our side → sides are converging,
            player is in merge-accumulation phase)

    Cases:
      - 2589 No + 550 Yes → ratio 4.7, skip (merge-prep, Hezbollah case)
      - 2589 No + 2000 Yes → ratio 1.3, skip (merge-prep, April 7 case)
      - 100 No (dust) + 2000 Yes → floor fails, TAKE (real signal)
      - 10000 No + 500 Yes → ratio 20, TAKE (directional with small hedge)
      - 2589 No + 0 Yes → our_side=0 → undefined ratio, treat as merge-prep
        (player has ONLY opposite side → new buys almost certainly merge-prep)

    Returns:
      {
        'is_merge_prep': bool,
        'opposite_size': float,
        'our_side_size': float,
        'ratio': float,
        'reason': str,
      }
    """
    MIN_OPPOSITE_SIZE = 500.0      # floor to ignore dust
    MAX_RATIO = 5.0                # opposite / our_side <= 5 means merge-prep

    result = {
        'is_merge_prep': False,
        'opposite_size': 0.0,
        'our_side_size': 0.0,
        'opposite_outcome': '',
        'ratio': 0.0,
        'reason': '',
    }
    if not condition_id:
        return result

    our_side = (our_outcome or '').strip().capitalize()
    opposite = 'No' if our_side == 'Yes' else 'Yes'

    try:
        positions = get_player_positions(condition_id, wallet)
        opp_size = 0.0
        our_side_size = 0.0
        for p in positions:
            p_outcome = (p.get('outcome') or '').strip().capitalize()
            size = float(p.get('size', 0) or 0)
            if p_outcome == opposite:
                opp_size = size
            elif p_outcome == our_side:
                our_side_size = size
        result['opposite_size'] = opp_size
        result['our_side_size'] = our_side_size
        result['opposite_outcome'] = opposite

        if opp_size < MIN_OPPOSITE_SIZE:
            return result  # dust, not merge-prep

        if our_side_size <= 0:
            # Player has ONLY opposite side — any new buy on our side is
            # almost certainly merge-prep.
            result['is_merge_prep'] = True
            result['ratio'] = float('inf')
            result['reason'] = (
                f"player holds {opp_size:.0f} sh on {opposite} side and 0 on "
                f"{our_side} side — new {our_side} buys are merge-prep"
            )
            return result

        ratio = opp_size / our_side_size
        result['ratio'] = ratio
        if ratio <= MAX_RATIO:
            result['is_merge_prep'] = True
            result['reason'] = (
                f"player holds {opp_size:.0f} sh on {opposite} side vs "
                f"{our_side_size:.0f} sh on {our_side} side (ratio {ratio:.1f}× "
                f"≤ {MAX_RATIO:.0f}×) — merge-prep"
            )
    except Exception as e:
        print(f"[FILTER] detect_merge_prep error: {e}")

    return result


def get_player_trades(condition_id: str, wallet: str) -> list:
    try:
        resp = requests.get(
            f"{DATA_API}/trades",
            params={"user": wallet, "conditionId": condition_id, "limit": 50},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[FILTER] Trades API error: {e}")
    return []


# ---------------------------------------------------------------------------
# Core filter functions
# ---------------------------------------------------------------------------

def is_price_in_range(price: float, signal_player: str = "") -> bool:
    bounds = PRICE_FILTER.get(signal_player, PRICE_FILTER["_default"])
    return bounds["min"] <= price <= bounds["max"]


def get_price_multiplier(price: float) -> float:
    """Return bet size multiplier based on entry price. Only 82-99c is reduced."""
    for min_p, max_p, mult in PRICE_BET_MULTIPLIERS:
        if min_p <= price < max_p:
            return mult
    return 1.0


def is_excluded(title: str, slug: str) -> bool:
    text = (title + " " + slug).lower()
    return any(word.lower() in text for word in EXCLUDED_KEYWORDS)


def get_player_usd_on_outcome(condition_id: str, wallet: str, outcome: str) -> float:
    """Return CURRENT USD value of player's open position on a specific outcome.
    Uses Polymarket's currentValue (= remaining size × current price), NOT
    historical totalBought (which counts already-sold shares).
    """
    positions = get_player_positions(condition_id, wallet)
    target = outcome.strip().capitalize()
    total = 0.0
    for p in positions:
        p_outcome = p.get("outcome", "").strip().capitalize()
        if p_outcome != target:
            continue
        # Prefer Polymarket's currentValue (remaining size × current price)
        cv = float(p.get("currentValue", 0) or 0)
        if cv > 0:
            total += cv
            continue
        # Fallback: size × current price (or avg)
        size = float(p.get("size", 0) or 0)
        cur_p = float(p.get("curPrice", 0) or 0)
        ap = float(p.get("avgPrice", 0) or 0)
        usd = size * (cur_p if cur_p > 0 else ap)
        total += usd
    return total


def check_opposition(condition_id: str, our_outcome: str,
                     signal_player: str) -> dict:
    """Check if any of the OTHER 3 players has $500+ on the OPPOSITE side.

    signal_player: the player whose trade we're following.
    Checks the remaining 3 players for opposing positions.

    Returns:
      should_block: bool
      blockers: list of (player_name, usd_opposing)
      reason: str
    """
    result = {"should_block": False, "blockers": [], "reason": ""}

    if not condition_id:
        return result

    our_side = our_outcome.strip().capitalize()
    opposite = "No" if our_side == "Yes" else "Yes"

    # Players whose opposition is ignored for this signal player.
    ignore_list = OPPOSITION_IGNORE.get(signal_player, [])

    blockers = []
    for name, wallet in PLAYERS.items():
        if name == signal_player:
            continue
        if name in ignore_list:
            # Ignored counter-signal — log but don't block
            opp_usd = get_player_usd_on_outcome(condition_id, wallet, opposite)
            if opp_usd >= OPPOSITION_MIN_USD:
                print(f"[OPPOSITION] Ignoring {name}'s ${opp_usd:,.0f} on {opposite} "
                      f"vs {signal_player} signal (per OPPOSITION_IGNORE)")
            continue
        opp_usd = get_player_usd_on_outcome(condition_id, wallet, opposite)
        if opp_usd >= OPPOSITION_MIN_USD:
            blockers.append((name, opp_usd))

    if blockers:
        result["should_block"] = True
        result["blockers"] = blockers
        blocker_str = ", ".join(f"{n}:${u:,.0f}" for n, u in blockers)
        result["reason"] = (
            f"Opposition on {opposite}: {blocker_str} — BLOCKED"
        )
    else:
        result["reason"] = "No opposition found — ALLOWED"

    return result


def price_risk_mult(price: float) -> float:
    """V9 PRICE_RISK_TIERS multiplier. Cuts bet size on risky price buckets
    (longshot <30c, expensive >70c). Middle 30-70c is unchanged.
    Returns 1.0 if price outside all tiers (fallback to no cut)."""
    try:
        from config import PRICE_RISK_TIERS
    except ImportError:
        return 1.0
    for lo, hi, m in PRICE_RISK_TIERS:
        if lo <= price < hi:
            return m
    return 1.0


def calculate_bet_size(signal_player: str, player_invested: float,
                       price: float = 0.5) -> float:
    """Logarithmic bet sizing: our_bet = A * ln(invested) + B, capped at MAX_BET_USD.
    Price multipliers (PRICE_BET + PRICE_RISK) applied after cap.
    MIN_BET check happens in the caller."""
    import math
    if player_invested < 500:
        return 0
    raw = BET_FORMULA_A * math.log(player_invested) + BET_FORMULA_B
    raw = min(raw, MAX_BET_USD)  # cap BEFORE multipliers
    # Legacy price multiplier (slippage protection 82-99c)
    price_mult = get_price_multiplier(price)
    # V9: additional PRICE_RISK_TIERS multiplier (bucketed risk adjustment)
    risk_mult = price_risk_mult(price)
    raw = raw * price_mult * risk_mult * BET_SCALE
    # MIN_BET check happens AFTER all multipliers in the caller
    return round(raw, 2)


def calculate_bet_formula_only(usd_amount: float, price: float = 0.5) -> float:
    """Apply bet formula to an arbitrary USD amount (not player_invested).
    Used by rebuy trigger — formula is applied to denizz's NEW BUY size
    instead of his total net_invested.
    Includes PRICE_BET_MULTIPLIERS and PRICE_RISK_TIERS. No BET_SCALE."""
    import math
    if usd_amount < 1:
        return 0.0
    raw = BET_FORMULA_A * math.log(usd_amount) + BET_FORMULA_B
    raw = min(raw, MAX_BET_USD)
    price_mult = get_price_multiplier(price)
    risk_mult = price_risk_mult(price)
    raw = raw * price_mult * risk_mult
    return round(max(0.0, raw), 2)


# ---------------------------------------------------------------------------
# Category classification
# ---------------------------------------------------------------------------

ALLOWED_TAGS = {
    "politics":        ["Politics", "US Politics"],
    "geopolitics":     ["Geopolitics"],
    "entertainment":   ["Entertainment", "Sports"],
    "oil":             ["Oil", "Commodities"],
    "elections":       ["Elections"],
    "iran":            ["Iran", "Middle East", "Israel"],
    "russia_ukraine":  ["Russia", "Ukraine"],
    "tech":            ["Technology", "Tech"],
}


def classify_category(title: str, slug: str, event_slug: str = "") -> str | None:
    tags = get_event_tags(event_slug)
    if tags:
        tags_lower = [t.lower() for t in tags]
        for cat_name, allowed in ALLOWED_TAGS.items():
            for tag in allowed:
                if tag.lower() in tags_lower:
                    return cat_name

    text = (title + " " + slug + " " + event_slug).lower()
    for cat_name, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                return cat_name
    return None


# ---------------------------------------------------------------------------
# Timeseries hedge detection (cross-market umbrella events)
# ---------------------------------------------------------------------------

import re as _re

# Regex to strip dates, numbers, months, "by/before", surrounding punctuation
_TS_MONTHS = (
    r"january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)
_TS_DATE_RE = _re.compile(
    r"(?:by|before)?\s*"
    r"(?:" + _TS_MONTHS + r")?\s*"
    r"\d[\d,./\-]*(?:st|nd|rd|th)?\s*"
    r"(?:" + _TS_MONTHS + r")?\s*"
    r"(?:\d{4})?\s*"
    r"[?,.\-!]*",
    _re.IGNORECASE,
)
_TS_TRAILING_BY = _re.compile(r"\bby\b\s*$", _re.IGNORECASE)


def is_time_series_pair(title_a: str, title_b: str) -> bool:
    """Check if two market titles are the same question with different dates.

    Strips dates, numbers, months, 'by/before' and surrounding punctuation,
    then compares the remaining text (case-insensitive, whitespace-normalized).
    """
    def _normalize(t: str) -> str:
        t = _TS_DATE_RE.sub(" ", t)
        t = _TS_TRAILING_BY.sub("", t)
        # Remove standalone numbers left over
        t = _re.sub(r"\b\d+(?:st|nd|rd|th)?\b", "", t)
        # Collapse whitespace and strip
        t = _re.sub(r"\s+", " ", t).strip().lower()
        # Remove trailing punctuation
        t = t.rstrip("?,. ")
        return t

    a = _normalize(title_a)
    b = _normalize(title_b)
    return bool(a and b and a == b)


def detect_timeseries_hedge(event_slug: str, condition_id: str, outcome: str,
                            player_name: str, player_invested: float,
                            title: str) -> dict:
    """Detect cross-market hedge on time-series umbrella events.

    When denizz holds large NO positions across several date-variants of the
    same question ("Iran deal by Apr 30", "...by May 31") and then buys YES
    on a new date-variant, this is a hedge — not a directional signal.

    We replicate the hedge proportionally to our own primary positions.

    Returns dict with keys:
        is_hedge, should_buy, hedge_usd, denizz_primary_usd,
        our_primary_usd, reason
    """
    from config import MIN_HEDGE_USD

    NOT_HEDGE = {
        "is_hedge": False,
        "should_buy": False,
        "hedge_usd": 0.0,
        "denizz_primary_usd": 0.0,
        "our_primary_usd": 0.0,
        "reason": "not a timeseries hedge",
    }

    if not event_slug or not condition_id or player_invested <= 0:
        return NOT_HEDGE

    wallet = PLAYERS.get(player_name, "")
    if not wallet:
        return NOT_HEDGE

    outcome_cap = outcome.strip().capitalize()
    opposite = "No" if outcome_cap == "Yes" else "Yes"

    # === Fix 2026-04-21: directional overrides before hedge classification ===
    #
    # Two conditions treat the buy as a directional signal (not a hedge):
    #   1. Denizz already holds a substantial SAME-SIDE position on THIS cid
    #      → this buy is a top-up to his directional bet, not a hedge.
    #   2. The current buy event is very large in absolute $ terms
    #      → conviction signal, even if economically it looks like a hedge.
    #
    # Ref: _analytics/2026-04-21_hedge_detector_blocks_directional_topups.md
    SAME_SIDE_DIRECTIONAL_MIN_USD = 500.0
    HEDGE_OVERRIDE_BUY_USD = 1500.0

    try:
        denizz_same_side_usd = get_player_usd_on_outcome(
            condition_id, wallet, outcome_cap
        )
    except Exception:
        denizz_same_side_usd = 0.0

    if denizz_same_side_usd >= SAME_SIDE_DIRECTIONAL_MIN_USD:
        return {**NOT_HEDGE,
                "reason": f"same-cid same-side ${denizz_same_side_usd:.0f} — directional top-up"}

    if float(player_invested) >= HEDGE_OVERRIDE_BUY_USD:
        return {**NOT_HEDGE,
                "reason": f"large buy ${float(player_invested):.0f} — conviction override"}

    # Step 1: Fetch all markets in this event from Gamma API
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"slug": event_slug},
            timeout=10,
        )
        if resp.status_code != 200 or not resp.json():
            return NOT_HEDGE
        event_data = resp.json()[0]
        markets = event_data.get("markets", [])
        if not markets:
            return NOT_HEDGE
    except Exception as e:
        print(f"[FILTER] detect_timeseries_hedge gamma error: {e}")
        return NOT_HEDGE

    # Step 2: For each OTHER sub-market, check if it's a time-series pair
    # and if denizz holds the OPPOSITE outcome (= primary direction)
    denizz_primary_usd = 0.0
    for m in markets:
        sub_cid = m.get("conditionId") or m.get("condition_id") or ""
        if sub_cid == condition_id:
            continue  # skip current market
        sub_title = m.get("question") or m.get("title") or ""
        if not is_time_series_pair(title, sub_title):
            continue
        # This is a time-series sibling — check denizz's position on OPPOSITE
        sub_opp_usd = get_player_usd_on_outcome(sub_cid, wallet, opposite)
        if sub_opp_usd > 0:
            denizz_primary_usd += sub_opp_usd

    if denizz_primary_usd <= 0:
        return NOT_HEDGE

    # Dust check: if denizz's opposite-side position is < 3% of his current
    # buy, it's residual dust — not a real hedge. E.g. 15 shares NO ($10)
    # vs 88K shares YES ($30K) = 0.03% = dust.
    HEDGE_DUST_RATIO = 0.03
    if denizz_primary_usd < player_invested * HEDGE_DUST_RATIO:
        print(f"[FILTER] Timeseries hedge dust: denizz opposite ${denizz_primary_usd:.0f} "
              f"< {HEDGE_DUST_RATIO:.0%} of buy ${player_invested:.0f} — NOT hedge")
        return NOT_HEDGE

    # We confirmed: denizz has primary positions in opposite direction on
    # sibling time-series markets, and is now buying THIS outcome = hedge
    result = {
        "is_hedge": True,
        "should_buy": False,
        "hedge_usd": 0.0,
        "denizz_primary_usd": denizz_primary_usd,
        "our_primary_usd": 0.0,
        "reason": "",
    }

    # Step 2b: Check if denizz is buying the SAME side as primary → not a hedge
    # (e.g. he holds NO Apr30 and buys NO Apr21 → same side = not hedge)
    # Actually this is already correct: if outcome=YES and opposite=NO,
    # we checked denizz's NO positions above. If those exist, it IS a hedge.
    # If outcome=NO and opposite=YES, we checked YES positions.
    # But we need to confirm: denizz buying same side as primary is NOT a hedge.
    # That's handled naturally: if denizz buys NO (outcome=NO), opposite=YES,
    # and he holds YES on siblings → that means denizz is buying opposite of
    # his primary → IS a hedge. If he holds NO on siblings and buys NO →
    # we check YES positions → 0 → not a hedge. Correct.

    # Step 3: Check OUR positions on sibling time-series markets (same outcome as denizz primary)
    import tracker as _tracker
    try:
        data = _tracker.load()
    except Exception as e:
        result["reason"] = f"tracker error: {e}"
        return result

    our_primary_usd = 0.0
    for _k, _p in data.get("positions", {}).items():
        if _p.get("status") != "open":
            continue
        if _p.get("event_slug", "") != event_slug:
            continue
        if _p.get("condition_id", "") == condition_id:
            continue  # skip current market
        pos_outcome = (_p.get("outcome", "") or "").strip().capitalize()
        if pos_outcome == opposite:  # same direction as denizz's primary
            our_primary_usd += float(_p.get("cost_usd", 0) or 0)

    result["our_primary_usd"] = our_primary_usd

    if our_primary_usd <= 0:
        result["reason"] = "hedge detected but we have no primary position to hedge"
        return result

    # Step 4: Calculate proportional hedge size
    our_hedge = our_primary_usd * (player_invested / denizz_primary_usd)

    if our_hedge < MIN_HEDGE_USD:
        result["reason"] = (
            f"hedge ${our_hedge:.2f} < min ${MIN_HEDGE_USD:.0f} "
            f"(our primary ${our_primary_usd:.0f}, denizz primary ${denizz_primary_usd:.0f})"
        )
        return result

    result["should_buy"] = True
    result["hedge_usd"] = round(our_hedge, 2)
    result["reason"] = (
        f"timeseries hedge: our ${our_primary_usd:.0f} primary, "
        f"denizz ${denizz_primary_usd:.0f} primary, "
        f"proportional hedge ${our_hedge:.2f}"
    )
    return result


# ---------------------------------------------------------------------------
# Hedge detection (same-condition)
# ---------------------------------------------------------------------------

def detect_hedge_signal(condition_id: str, signal_player: str, our_outcome: str,
                        player_invested: float, event_slug: str = "") -> dict:
    """Detect if the incoming signal is a hedge by signal_player.

    A hedge = player buys a SMALL amount of our_outcome while holding a LARGE
    primary position in the OPPOSITE direction on the same event.

    Check order:
      1. Same condition_id (exact match — most reliable).
      2. Cross-market: sum player's opposite positions across all markets
         sharing the same event_slug (e.g. April 7/15 YES hedged by April 30 NO).

    Returns:
      is_hedge:       bool
      primary_usd:    float  — player's primary position value
      hedge_ratio:    float  — player_invested / primary_usd
      primary_source: str    — "same-condition" | "cross-market"
      reason:         str
    """
    from config import HEDGE_RATIO_MAX

    result = {
        "is_hedge": False,
        "primary_usd": 0.0,
        "hedge_ratio": 0.0,
        "primary_source": "",
        "reason": "not a hedge",
    }

    if player_invested <= 0:
        return result

    opposite = "No" if our_outcome.strip().capitalize() == "Yes" else "Yes"
    wallet = PLAYERS.get(signal_player, "")
    if not wallet:
        return result

    # 1. Same-condition check — 1 HTTP request
    primary_usd = get_player_usd_on_outcome(condition_id, wallet, opposite)
    primary_source = "same-condition"

    # 2. Cross-market check via OUR tracker (zero HTTP cost)
    # If player has no opposite position on same condition_id, check if WE have
    # an opposite position on the same event_slug. If we hold NO on "ceasefire
    # by April 30" and player buys YES on "ceasefire by April 15" — that's a hedge.
    # We use OUR position as a signal that this event has a directional bet,
    # and treat player's opposite-side buy as a hedge against it.
    if primary_usd <= 0 and event_slug:
        import tracker
        data = tracker.load()
        our_opposite_usd = 0.0
        for _k, _p in data.get("positions", {}).items():
            if _p.get("status") != "open":
                continue
            if _p.get("event_slug", "") != event_slug:
                continue
            if _p.get("condition_id", "") == condition_id:
                continue  # same condition — already checked above
            pos_outcome = (_p.get("outcome", "") or "").strip().capitalize()
            if pos_outcome == opposite:
                our_opposite_usd += float(_p.get("cost_usd", 0) or 0)
        if our_opposite_usd > 0:
            # We hold opposite on this event → player's buy is likely a hedge.
            # Use our_opposite_usd as primary for ratio check, but cap ratio
            # so that even a small our-position triggers hedge detection.
            # Logic: if we hold ANY opposite on this event, and player buys
            # the other side cheaply — it's a hedge regardless of sizes.
            primary_usd = max(our_opposite_usd, player_invested / HEDGE_RATIO_MAX)
            primary_source = "cross-market-tracker"
            print(f"[FILTER] Cross-market hedge: we hold ${our_opposite_usd:.0f} {opposite} "
                  f"on event {event_slug} (different condition_id)")

    if primary_usd <= 0:
        result["reason"] = f"player has no significant {opposite} positions on this event"
        return result

    ratio = player_invested / primary_usd
    result["primary_usd"] = primary_usd
    result["hedge_ratio"] = ratio
    result["primary_source"] = primary_source

    # EPSILON tolerance: in the cross-market branch above we compute
    #     primary_usd = max(our_opposite_usd, player_invested / HEDGE_RATIO_MAX)
    # so mathematically ratio == HEDGE_RATIO_MAX whenever the second arg wins.
    # In IEEE-754 float this identity fails ~17% of the time — player_invested /
    # (player_invested / 0.12) may yield 0.12000000000000001, which would slip
    # a real hedge through as a "directional trade". Incident 2026-04-15 was
    # exactly this case. Use a tiny epsilon to treat near-equality as equality.
    HEDGE_RATIO_EPSILON = 1e-9
    if ratio <= HEDGE_RATIO_MAX + HEDGE_RATIO_EPSILON:
        result["is_hedge"] = True
        result["reason"] = (
            f"player ${player_invested:.0f} on {our_outcome} vs "
            f"${primary_usd:,.0f} on {opposite} ({primary_source}) "
            f"→ ratio {ratio:.1%} ≤ {HEDGE_RATIO_MAX:.0%} = hedge"
        )
    else:
        result["reason"] = (
            f"ratio {ratio:.1%} > {HEDGE_RATIO_MAX:.0%} ({primary_source}) "
            f"— directional trade, not a hedge"
        )

    return result


def evaluate_hedge_profitability(our_outcome: str, condition_id: str,
                                 token_id: str, event_slug: str = "") -> dict:
    """Check if copying a hedge improves OUR portfolio.

    Finds our open primary position (opposite direction, same condition or
    event_slug). If our primary is ≥ HEDGE_MIN_GAIN_PCT above our entry price,
    the hedge locks in profit → copy. Otherwise → skip.

    If we have NO primary position at all, this hedge doesn't relate to our
    portfolio → treat as a standalone trade (should_copy=True, normal flow).

    Returns:
      should_copy:    bool
      our_entry:      float  — our avg entry price on primary
      current_price:  float  — current bid price of primary token
      gain_pct:       float  — (current - entry) / entry
      reason:         str
    """
    from config import HEDGE_MIN_GAIN_PCT
    import tracker as _tracker

    result = {
        "should_copy": False,
        "our_entry": 0.0,
        "current_price": 0.0,
        "gain_pct": 0.0,
        "reason": "",
    }

    opposite = "No" if our_outcome.strip().capitalize() == "Yes" else "Yes"

    try:
        data = _tracker.load()
        open_positions = _tracker.get_open_positions(data)
    except Exception as e:
        result["reason"] = f"tracker load error: {e}"
        result["should_copy"] = True  # can't evaluate → allow
        return result

    # Find our open primary position (opposite direction)
    # Prefer exact condition_id match; fall back to same event_slug.
    primary_pos = None
    for pos in open_positions.values():
        if pos.get("outcome", "").strip().capitalize() != opposite:
            continue
        if pos.get("condition_id") == condition_id:
            primary_pos = pos
            break
        if event_slug and pos.get("event_slug") == event_slug and primary_pos is None:
            primary_pos = pos  # keep searching for exact match

    if primary_pos is None:
        # We don't hold the primary → hedge is irrelevant to our portfolio.
        # Fall through to normal filters.
        result["should_copy"] = True
        result["reason"] = (
            f"we have no open {opposite} position on this event "
            f"— not our hedge, normal filters apply"
        )
        return result

    cost = float(primary_pos.get("cost_usd", 0))
    shares = float(primary_pos.get("size_shares", 0))
    if shares <= 0:
        result["reason"] = "primary position has zero shares — skip hedge"
        return result

    our_entry = cost / shares
    result["our_entry"] = our_entry

    # Current bid price of primary token (what we'd get if selling now)
    primary_token_id = primary_pos.get("token_id", "")
    current_price = our_entry  # fallback: assume no movement
    if primary_token_id:
        prices = get_orderbook_prices(primary_token_id)
        if prices:
            current_price = prices[0]  # best bid

    result["current_price"] = current_price
    gain_pct = (current_price - our_entry) / our_entry if our_entry > 0 else 0.0
    result["gain_pct"] = gain_pct

    # Max hedge size = unrealized gain on primary (in USD).
    # Spending more than this on the hedge guarantees a net loss regardless of outcome.
    unrealized_gain_usd = max(0.0, (current_price - our_entry) * shares)
    result["max_hedge_usd"] = unrealized_gain_usd

    if gain_pct >= HEDGE_MIN_GAIN_PCT:
        result["should_copy"] = True
        result["reason"] = (
            f"primary {opposite} entry={our_entry:.3f} now={current_price:.3f} "
            f"(+{gain_pct:.1%} ≥ {HEDGE_MIN_GAIN_PCT:.0%}) → COPY hedge"
        )
    else:
        result["should_copy"] = False
        result["reason"] = (
            f"primary {opposite} entry={our_entry:.3f} now={current_price:.3f} "
            f"({gain_pct:+.1%} < {HEDGE_MIN_GAIN_PCT:.0%}) → SKIP hedge"
        )

    return result


# ---------------------------------------------------------------------------
# Main signal check
# ---------------------------------------------------------------------------

def check_signal(token_id: str, entry_price: float, event: dict,
                 signal_player: str) -> tuple:
    """
    Check all conditions for a signal from signal_player.
    Returns (pass, bet_size, reason, info_dict).
    """
    market_info = get_market_info(token_id)
    if not market_info:
        return False, 0, "Market info not found", None

    condition_id = market_info.get("conditionId", "") or market_info.get("condition_id", "")
    question = market_info.get("question", "")
    slug = market_info.get("slug", "") or market_info.get("market_slug", "")
    event_slug = market_info.get("event_slug", "") or event.get("event_slug", "")
    our_outcome = event.get("outcome", "")

    # --- STEP 1: Excluded keywords ---
    if is_excluded(question, slug):
        return False, 0, f"Excluded: {question[:50]}", market_info

    # --- STEP 2: Category ---
    category = classify_category(question, slug, event_slug)
    if not category:
        return False, 0, f"Category not matched: {question[:50]}", market_info

    # --- STEP 3: Price filter (per-player range) ---
    prices = get_orderbook_prices(token_id)
    current_ask = prices[1] if prices else None
    if current_ask is not None:
        if not is_price_in_range(current_ask, signal_player):
            bounds = PRICE_FILTER.get(signal_player, PRICE_FILTER["_default"])
            return (False, 0,
                    f"Price {current_ask:.3f} out of [{bounds['min']}-{bounds['max']}] for {signal_player}",
                    market_info)

    # --- STEP 4: Player invested >= minimum for this player ---
    min_invested = MIN_PLAYER_INVESTED.get(signal_player, 500)
    signal_wallet = PLAYERS[signal_player]

    positions = get_player_positions(condition_id, signal_wallet)
    api_position_usd = 0.0
    for p in positions:
        ap = float(p.get("avgPrice", 0) or 0)
        size = float(p.get("size", 0) or 0)
        # NET invested (current holdings × avg price), not gross historical buys.
        # See get_player_invested_on_token() for full rationale.
        usd = size * ap
        p_token = p.get("asset", "") or p.get("tokenId", "")
        if p_token == token_id:
            api_position_usd = usd
            break

    buffer_total = float(event.get("_buffer_total_usd", 0) or 0)
    player_invested = max(api_position_usd, buffer_total)

    if player_invested < min_invested:
        return (False, 0,
                f"{signal_player} invested ${player_invested:.0f} < ${min_invested:.0f}",
                market_info)

    # --- STEP 4b-pre: HARD opposite-side rule ---
    # If we already hold an opposite-direction position on the same event
    # (different condition_id / expiration variant), NEVER enter the other side.
    # Rationale: these markets are correlated — holding both sides is net-neutral
    # and just ties up capital. Safer to just keep the existing thesis.
    if event_slug:
        import tracker as _tracker_hard
        _data = _tracker_hard.load()
        _opposite = "No" if our_outcome.strip().capitalize() == "Yes" else "Yes"
        _our_opp_usd = 0.0
        for _k, _p in _data.get("positions", {}).items():
            if _p.get("status") != "open":
                continue
            if _p.get("event_slug", "") != event_slug:
                continue
            _po = (_p.get("outcome", "") or "").strip().capitalize()
            if _po == _opposite:
                _our_opp_usd += float(_p.get("cost_usd", 0) or 0)
        if _our_opp_usd > 0:
            return (False, 0,
                    f"HARD opposite-side block: we hold ${_our_opp_usd:.0f} {_opposite} "
                    f"on event {event_slug} — refuse to buy {our_outcome}",
                    market_info)

    # --- STEP 4b: Hedge detection ---
    # If signal_player is buying a small position opposite to their large primary
    # position on the same event, this is a hedge — not a new directional bet.
    # We only copy if our corresponding primary position has unrealized gains
    # large enough to justify locking them in via the hedge.
    # If we have no matching primary position, treat as a standalone trade.
    _hedge_max_usd = None  # set below if this is a confirmed hedge
    hedge_info = detect_hedge_signal(
        condition_id=condition_id,
        signal_player=signal_player,
        our_outcome=our_outcome,
        player_invested=player_invested,
        event_slug=event_slug,
    )
    if hedge_info["is_hedge"]:
        print(f"[FILTER] Hedge detected: {hedge_info['reason']}")
        hedge_eval = evaluate_hedge_profitability(
            our_outcome=our_outcome,
            condition_id=condition_id,
            token_id=token_id,
            event_slug=event_slug,
        )
        print(f"[FILTER] Hedge eval: {hedge_eval['reason']}")
        if not hedge_eval["should_copy"]:
            return (False, 0,
                    f"Hedge skip: {hedge_eval['reason']}",
                    market_info)
        _hedge_max_usd = hedge_eval.get("max_hedge_usd")

    # --- STEP 4c: Top-up ratio filter ---
    # If player is adding a tiny % to a large existing position, it's noise.
    # Only applies when player already had a position before this buy.
    from config import TOPUP_RATIO_TIERS
    if api_position_usd > buffer_total and buffer_total > 0:
        topup_ratio = buffer_total / api_position_usd
        topup_mult = 1.0
        for lo, hi, mult in TOPUP_RATIO_TIERS:
            if lo <= topup_ratio < hi:
                topup_mult = mult
                break
        if topup_mult == 0.0:
            return (False, 0,
                    f"Top-up ratio {topup_ratio:.1%} < 3%: SKIP (noise, "
                    f"new ${buffer_total:.0f} / total ${api_position_usd:.0f})",
                    market_info)
        if topup_mult < 1.0:
            print(f"[FILTER] Top-up ratio {topup_ratio:.1%}: "
                  f"bet will be x{topup_mult} "
                  f"(new ${buffer_total:.0f} / total ${api_position_usd:.0f})")
    else:
        topup_mult = 1.0  # first entry or API glitch — full size

    # --- STEP 5: Opposition check (other 2 players) ---
    opposition = check_opposition(condition_id, our_outcome, signal_player)
    if opposition["should_block"]:
        return False, 0, f"Opposition: {opposition['reason']}", market_info
    if opposition["reason"]:
        print(f"[FILTER] Opposition check: {opposition['reason']}")

    # --- STEP 5b: Merge-prep detection — DISABLED ---
    # Backtest on 3500+ historical buys (Car + denizz) showed catastrophic
    # precision (~1-3%): the rule would block ~30% of all buys but <5% of
    # them are real merges. Players routinely hedge/rebalance without
    # merging, and the rule can't distinguish those cases.
    # Cost of removal: occasional false entry on merge-prep buys (~1% of
    # signals). Mitigation: when a real merge fires, handle_player_sell
    # already exits the position via the 'merge' source path.

    # --- STEP 6: Slippage (price-dependent limit) ---
    if current_ask is not None:
        slippage = current_ask - entry_price
        max_slip = get_max_slippage(entry_price)
        if slippage > max_slip + 0.0005:
            return False, 0, f"Slippage {slippage:.3f} > {max_slip:.3f} (price {entry_price:.2f})", market_info

    # --- STEP 7: Calculate bet size (with price multiplier) ---
    use_price = current_ask if current_ask is not None else entry_price
    bet_size = calculate_bet_size(signal_player, player_invested, use_price)

    # --- STEP 7a: Top-up ratio multiplier ---
    if topup_mult < 1.0:
        bet_size_before = bet_size
        bet_size = round(bet_size * topup_mult, 2)
        print(f"[FILTER] Top-up ratio: ${bet_size_before:.0f} -> ${bet_size:.0f}")

    # --- STEP 7b: Rule A+ — late-entry size gate ---
    # Scale our bet down if we're entering at a price much higher than the
    # player's average buy price. Rationale: our risk/reward is strictly
    # worse on late entries, so reduce exposure rather than full skip.
    player_avg = get_player_avg_price(condition_id, signal_wallet, token_id)
    size_mult, mult_reason = calculate_entry_size_multiplier(player_avg, use_price)
    if size_mult < 1.0:
        bet_size_before = bet_size
        bet_size = round(bet_size * size_mult, 2)
        print(f"[FILTER] Late-entry size gate: {mult_reason} | "
              f"${bet_size_before:.0f} -> ${bet_size:.0f} (player_avg ${player_avg:.3f})")

    # --- STEP 7c: Horizon size gate (graduated by days to end_date) ---
    # Multiplies on top of Rule A+ — both risks compose mathematically.
    end_date_str = ""
    if market_info:
        end_date_str = market_info.get("endDate") or market_info.get("end_date") or ""
    hz_mult, hz_reason = get_horizon_multiplier(end_date_str)
    if hz_mult == 0.0:
        return False, 0, f"Horizon blocked: {hz_reason}", market_info
    if hz_mult < 1.0:
        bet_size_before = bet_size
        bet_size = round(bet_size * hz_mult, 2)
        print(f"[FILTER] Horizon size gate: {hz_reason} | "
              f"${bet_size_before:.2f} -> ${bet_size:.2f}")

    # MIN_BET_FORMULA check — after ALL multipliers (price, late-entry, horizon)
    from config import MIN_BET_FORMULA
    if bet_size < MIN_BET_FORMULA:
        return False, 0, f"{signal_player} at ${player_invested:.0f} → bet ${bet_size:.0f} < min ${MIN_BET_FORMULA:.0f}", market_info

    info = {
        "category": category,
        "player_invested": player_invested,
        "condition_id": condition_id,
        "question": question,
        "event_slug": event_slug,
        "market_info": market_info,
        "opposition": opposition,
        "signal_player": signal_player,
    }

    tier = "B"
    if player_invested >= 10000:
        tier = "S+"
    elif player_invested >= 5000:
        tier = "S"
    elif player_invested >= 2000:
        tier = "A"

    return (True, bet_size,
            f"PASS ({tier}): {signal_player} ${player_invested:.0f}, bet ${bet_size:.0f}, {category}",
            info)


# ============================================================
# HIGH-PRICE OVERRIDE
# ============================================================

def _parse_end_date(s) -> datetime | None:
    """Parse end_date string to aware UTC datetime."""
    if not s:
        return None
    try:
        s = str(s).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s) if "T" in s else datetime.strptime(s, "%Y-%m-%d")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# === Horizon multiplier (graduated by days to end_date) ===

def get_horizon_multiplier(end_date_str):
    """Return (multiplier, reason) based on days until market end_date.

    0-30 days: 1.0 (full bet)
    30-60 days: 0.8
    60-90 days: 0.7
    90-120 days: 0.4
    120+ days: 0.0 (block entry)
    """
    from config import HORIZON_TIERS
    if not end_date_str:
        return 1.0, ""
    try:
        end = datetime.fromisoformat(str(end_date_str).replace('Z', '+00:00'))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        days = (end - datetime.now(timezone.utc)).days
        for min_d, max_d, mult in HORIZON_TIERS:
            if min_d <= days < max_d:
                if mult == 0.0:
                    return 0.0, f"horizon blocked ({days}d >= 120d)"
                return mult, f"horizon {days}d -> x{mult}"
    except Exception:
        pass
    return 1.0, ""


# HP strategy removed in v2 — entire 82-99c zone uses unified system


# ---------------------------------------------------------------------------
# Top-up detection (on-chain classification) — Bugfix #1 2026-04-15
# ---------------------------------------------------------------------------
def get_denizz_size_before_event(wallet: str, token_id: str,
                                 event_size: float = 0.0,
                                 cid: str = "",
                                 player_name: str = "denizz"):
    """Return (size_before_event, cache_hit) for a given player on a token.

    Used by main.handle_buy to classify a BUY event as 'new entry' vs 'top-up'
    based on the player's ACTUAL on-chain share balance BEFORE the event, not
    on our internal _signaled_keys state. This catches the case where denizz
    held a position for months before our bot ever saw it.

    Lookup strategy (L1 cache -> L2 RPC):
      1. Try exit_manager._player_size_cache via _cache_get(). The cache is
         populated at startup from data-api and refreshed on every sell event
         and on periodic refresh_cache_for_open_positions(). For tokens we
         already track, the cache is authoritative and saves an RPC hop.
      2. On cache miss, call exit_manager._get_player_size_onchain() which
         reads CTF.balanceOf directly from Polygon. Result is NOT written
         back to cache from here (caller may be inside _entry_lock; cache
         writes happen in exit_manager's own flow).

    Args:
        wallet: player wallet address (hex string).
        token_id: CTF ERC-1155 token id (stringified uint256).
        event_size: shares bought in THIS buy event. Subtracted from the
            returned size so the caller sees the balance BEFORE the event
            was applied on-chain. Pass 0 if unknown — caller then gets the
            AT-OR-AFTER balance which is a conservative over-estimate of
            pre-event size (so top-up classification stays correct; only
            edge case is a brand-new buy where event_size == balance ->
            size_before = 0 -> classified as new entry, which is right).
        cid: condition id, used for cache lookup key.
        player_name: name matching exit_manager._player_size_cache keys.

    Returns:
        (size_before, cache_hit):
          size_before: float shares, or None on RPC failure (caller SKIPs).
          cache_hit: True iff value came from L1 cache (no network call).
    """
    # L1 cache
    try:
        import exit_manager
        cached = exit_manager._cache_get(player_name, cid, str(token_id))
    except Exception:
        cached = None
    if cached is not None:
        size_before = max(0.0, float(cached) - float(event_size or 0.0))
        return size_before, True

    # L2 RPC
    try:
        import exit_manager
        onchain = exit_manager._get_player_size_onchain(wallet, str(token_id))
    except Exception as e:
        print(f"[FILTER] get_denizz_size_before_event RPC exception: {e}")
        return None, False
    if onchain is None:
        return None, False
    size_before = max(0.0, float(onchain) - float(event_size or 0.0))
    return size_before, False

