"""
Trading strategy: full rule set for oil swing bot.

Entry YES: 3-step gradient as WTI drops below $93/$91/$89
Exit YES:  3-step gradient as WTI rises above $96/$98/$99
Entry NO:  single step when WTI > $97
Exit NO:   single step when WTI < $93

Stop-losses: ceasefire ($84), NO risk ($105), theta (3 days), portfolio ($200)
Time rules:  dead zone 12-16 ET, buy after 16 ET, sell before 12 ET
Deadline:    close all by March 26
"""
import os
import time
from datetime import datetime, timezone, timedelta
from config import (
    YES_ENTRY_STEPS, YES_EXIT_STEPS,
    NO_ENTRY_STEPS, WTI_SELL_NO_BELOW,
    MIN_BET_USD,
    STOP_CEASEFIRE_WTI, STOP_NO_WTI,
    STOP_THETA_DAYS, STOP_THETA_WTI_MOVE, STOP_PORTFOLIO_FLOOR,
    DEAD_ZONE_START_ET, DEAD_ZONE_END_ET,
    DEADLINE_DATE, SETTLEMENT_TRIGGER,
    DIVERGENCE_RATIO_NORMAL, DIVERGENCE_ALERT_MULT,
    DIVERGENCE_WINDOW_HOURS, DIVERGENCE_REDUCE_PCT,
    THETA_SCALING,
    MOMENTUM_BLOCK, MOMENTUM_WINDOW,
    WEEKEND_BLOCK, FRIDAY_CLOSE_HOUR_ET,
)

# --- Divergence state ---
_price_history = []
_divergence_active = False
_divergence_until = 0

# --- Momentum tracking ---
_wti_buffer = []


# =====================================================
# TIME HELPERS
# =====================================================

def get_et_hour() -> int:
    """Current hour in US Eastern Time (EDT = UTC-4 in March)."""
    now_utc = datetime.now(timezone.utc)
    return (now_utc.hour - 4) % 24


def is_dead_zone() -> tuple:
    """12:00-16:00 ET: no new positions."""
    h = get_et_hour()
    if DEAD_ZONE_START_ET <= h < DEAD_ZONE_END_ET:
        return True, f"Dead zone {h}:00 ET"
    return False, ""


def is_buy_window() -> bool:
    """Buy only after 16:00 ET (theta already priced in)."""
    return get_et_hour() >= DEAD_ZONE_END_ET or get_et_hour() < DEAD_ZONE_START_ET


def is_sell_window() -> bool:
    """Sell preferably before 12:00 ET (hope premium still in price)."""
    return get_et_hour() < DEAD_ZONE_START_ET


def is_past_deadline() -> bool:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return today >= DEADLINE_DATE


# =====================================================
# MOMENTUM & WEEKEND FILTERS
# =====================================================

def track_wti(wti: float):
    """Record WTI price for momentum calculation. Call every cycle."""
    _wti_buffer.append(wti)
    if len(_wti_buffer) > MOMENTUM_WINDOW * 2:
        _wti_buffer.pop(0)


def check_momentum_block() -> tuple:
    """
    Block NO entry if WTI rose more than MOMENTUM_BLOCK in last MOMENTUM_WINDOW points.
    Returns (is_blocked, reason).
    """
    if len(_wti_buffer) < 2:
        return False, ""

    window = min(MOMENTUM_WINDOW, len(_wti_buffer))
    old_wti = _wti_buffer[-window]
    current_wti = _wti_buffer[-1]
    change = current_wti - old_wti

    if change > MOMENTUM_BLOCK:
        return True, "Momentum block: WTI +$%.2f in %d cycles (limit $%.1f)" % (
            change, window, MOMENTUM_BLOCK)
    return False, ""


def is_weekend_blocked() -> bool:
    """
    Friday 20:00 ET to Monday 06:00 ET: no new positions.
    Protects from weekend gaps (March 8 gap: -65%).
    06 ET chosen via backtest: best P&L on realistic Mondays.
    """
    if not WEEKEND_BLOCK:
        return False

    dt = datetime.now(timezone.utc)
    weekday = dt.weekday()  # 0=Mon, 6=Sun
    hour_et = (dt.hour - 4) % 24

    if weekday == 4 and hour_et >= 20:  # Friday evening
        return True
    if weekday in (5, 6):  # Saturday, Sunday
        return True
    if weekday == 0 and hour_et < 6:  # Monday before 06:00 ET
        return True
    return False


def is_friday_close_time() -> bool:
    """Returns True if it's Friday at or after FRIDAY_CLOSE_HOUR_ET."""
    dt = datetime.now(timezone.utc)
    weekday = dt.weekday()
    hour_et = (dt.hour - 4) % 24
    return weekday == 4 and hour_et >= FRIDAY_CLOSE_HOUR_ET


def get_days_remaining() -> int:
    """Trading days remaining until March 31."""
    today = datetime.now(timezone.utc).date()
    deadline = datetime(2026, 3, 31).date()
    days = 0
    current = today
    while current <= deadline:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days


def get_theta_multiplier() -> float:
    """No scaling — full size always. Block entry at 0-2 days (returns 0)."""
    days = get_days_remaining()
    if days <= 2:
        return 0.0
    return 1.0


_calibration_cache = None
_calibration_loaded_at = 0


def _load_calibration() -> dict | None:
    """Load calibration from file, cache for 10 min."""
    global _calibration_cache, _calibration_loaded_at
    import json

    now = time.time()
    if _calibration_cache and (now - _calibration_loaded_at) < 600:
        return _calibration_cache

    cal_path = os.path.join(os.path.dirname(__file__), "theta_calibration.json")
    try:
        if os.path.exists(cal_path):
            with open(cal_path, "r") as f:
                _calibration_cache = json.load(f)
            _calibration_loaded_at = now
            return _calibration_cache
    except Exception:
        pass
    return None


def get_theta_adjustments() -> dict:
    """
    Get theta adjustments — from calibration file if available,
    otherwise fallback to theoretical formula.

    Calibration file is produced by calibrate.py (runs 3x/day)
    from actual Polymarket price data.
    """
    days = get_days_remaining()

    if days <= 0:
        return {"profit_mult": 0.0, "price_mult": 0.0, "days": 0, "source": "zero"}

    # Try calibrated values first
    cal = _load_calibration()
    if cal and "days" in cal:
        day_key = str(days)
        if day_key in cal["days"]:
            entry = cal["days"][day_key]
            return {
                "profit_mult": entry.get("profit_mult", 1.0),
                "price_mult": entry.get("price_mult", 1.0),
                "days": days,
                "source": "calibrated",
            }
        # If exact day not in calibration, find nearest lower
        for d in range(days, 0, -1):
            if str(d) in cal["days"]:
                entry = cal["days"][str(d)]
                return {
                    "profit_mult": entry.get("profit_mult", 1.0),
                    "price_mult": entry.get("price_mult", 1.0),
                    "days": days,
                    "source": f"calibrated_nearest_{d}",
                }

    # Fallback: theoretical formula
    ref = 7.0
    if days >= ref:
        return {"profit_mult": 1.0, "price_mult": 1.0, "days": days, "source": "theoretical_flat"}

    ratio = days / ref
    profit_mult = ratio ** 0.5
    price_mult = ratio ** 0.3

    return {
        "profit_mult": round(profit_mult, 3),
        "price_mult": round(price_mult, 3),
        "days": days,
        "source": "theoretical_fallback",
    }


# =====================================================
# POSITION SIZING
# =====================================================

def calculate_bet_size(fixed_usd: float, free_balance: float) -> float:
    """
    Calculate bet size from fixed USD amount.
    Scaled down by theta multiplier and divergence.
    Capped at available free balance.
    """
    bet = fixed_usd

    # Theta scaling
    theta_mult = get_theta_multiplier()
    bet *= theta_mult

    # Divergence scaling
    if _divergence_active and time.time() < _divergence_until:
        bet *= DIVERGENCE_REDUCE_PCT

    # Floor
    if bet < MIN_BET_USD:
        return 0.0

    # Don't bet more than free balance
    if bet > free_balance:
        return 0.0

    return round(bet, 2)


# =====================================================
# STOP-LOSS CHECKS
# =====================================================

def _hours_to_settlement() -> int:
    """Hours until next CME settlement (~14:30 ET)."""
    et_hour = get_et_hour()
    if et_hour < 14:
        return 14 - et_hour
    else:
        return (24 - et_hour) + 14


def _get_no_stop_level() -> float:
    """Graduated NO stop: tighter near settlement, looser far away.
    Settlement = only price that matters for resolution."""
    h = _hours_to_settlement()
    if h <= 1:
        return 101.0   # <1h: intraday ≈ settlement
    elif h <= 4:
        return 103.0   # 1-4h: US session, reliable
    elif h <= 8:
        return 105.0   # 4-8h: Europe, stabilizing
    else:
        return 108.0   # >8h: night noise, loose


def _get_ceasefire_stop_level() -> float:
    """Graduated YES ceasefire: tighter near settlement, looser far away."""
    h = _hours_to_settlement()
    if h <= 1:
        return 88.0    # <1h: tight
    elif h <= 4:
        return 86.0    # 1-4h: medium
    elif h <= 8:
        return 84.0    # 4-8h: loose
    else:
        return 82.0    # >8h: very loose


def check_stop_ceasefire(wti: float) -> bool:
    """Graduated ceasefire stop + panic at $75."""
    level = _get_ceasefire_stop_level()
    return wti < level or wti < 75.0


def check_stop_no(wti: float) -> bool:
    """Graduated NO stop + panic at $115."""
    level = _get_no_stop_level()
    return wti > level or wti > 115.0


def check_stop_theta(pos: dict, wti: float) -> bool:
    """
    YES held > 3 days and WTI didn't move $3+ from entry.
    """
    opened_at = pos.get("opened_at", "")
    if not opened_at:
        return False

    try:
        open_dt = datetime.fromisoformat(opened_at)
        if open_dt.tzinfo is None:
            open_dt = open_dt.replace(tzinfo=timezone.utc)
        days_held = (datetime.now(timezone.utc) - open_dt).total_seconds() / 86400

        if days_held < STOP_THETA_DAYS:
            return False

        # Check if WTI moved enough from entry
        entry_wti = pos.get("entry_wti", wti)
        wti_move = wti - entry_wti

        if wti_move < STOP_THETA_WTI_MOVE:
            return True  # didn't move enough, theta is eating profit

    except Exception:
        pass

    return False


def check_stop_portfolio(balance: float, invested: float) -> bool:
    """Portfolio (balance + invested) < $200 -> stop bot."""
    return (balance + invested) < STOP_PORTFOLIO_FLOOR


def check_settlement(wti: float) -> bool:
    """WTI >= $100 -> market may resolve YES."""
    return wti >= SETTLEMENT_TRIGGER


# =====================================================
# SIGNAL GENERATION
# =====================================================

def get_yes_entry_step(wti: float, completed_steps: set) -> tuple:
    """
    Check if WTI triggers a YES buy step.
    Returns (step_index, wti_trigger, bet_usd) or (None, None, None).
    """
    for i, (trigger, bet_usd) in enumerate(YES_ENTRY_STEPS):
        if i not in completed_steps and wti <= trigger:
            return i, trigger, bet_usd
    return None, None, None


def get_yes_exit_step(wti: float, completed_exits: set) -> tuple:
    """
    Check if WTI triggers a YES sell step.
    Returns (step_index, wti_trigger, pct_of_position) or (None, None, None).
    """
    for i, (trigger, pct) in enumerate(YES_EXIT_STEPS):
        if i not in completed_exits and wti >= trigger:
            return i, trigger, pct
    return None, None, None


def get_no_entry_step(wti: float, completed_steps: set) -> tuple:
    """
    Check if WTI triggers a NO buy step.
    Returns (step_index, wti_trigger, bet_usd) or (None, None, None).
    """
    for i, (trigger, bet_usd, _profit_target) in enumerate(NO_ENTRY_STEPS):
        if i not in completed_steps and wti >= trigger:
            return i, trigger, bet_usd
    return None, None, None


def get_no_profit_target(entry_step: int) -> float:
    """Get profit target for a NO position, adjusted for theta."""
    if 0 <= entry_step < len(NO_ENTRY_STEPS):
        base = NO_ENTRY_STEPS[entry_step][2]
    else:
        base = 0.50
    adj = get_theta_adjustments()
    return round(base * adj["profit_mult"], 3)


def should_sell_no(wti: float, has_no: bool) -> bool:
    """Sell NO when WTI <= $93."""
    return has_no and wti <= WTI_SELL_NO_BELOW


# =====================================================
# DIVERGENCE DETECTION
# =====================================================

def check_divergence(wti: float, yes_pct: float) -> dict | None:
    """
    Detect when YES moves disproportionately to WTI.
    Normal: $1 WTI ≈ 2.2pp YES.
    Alert if actual > 2x expected.
    """
    global _divergence_active, _divergence_until

    now = time.time()
    _price_history.append((now, wti, yes_pct))

    # Keep last 8 hours
    cutoff = now - 8 * 3600
    while _price_history and _price_history[0][0] < cutoff:
        _price_history.pop(0)

    # Need data from DIVERGENCE_WINDOW_HOURS ago
    window = DIVERGENCE_WINDOW_HOURS * 3600
    old_entries = [e for e in _price_history if e[0] <= now - window]
    if not old_entries:
        return None

    old_t, old_wti, old_yes = old_entries[-1]
    wti_change = wti - old_wti
    yes_change = yes_pct - old_yes
    expected = wti_change * DIVERGENCE_RATIO_NORMAL

    if abs(expected) < 2:
        return None  # WTI barely moved

    if abs(yes_change) > abs(expected) * DIVERGENCE_ALERT_MULT:
        _divergence_active = True
        _divergence_until = now + 2 * 3600  # 2 hours reduced mode

        return {
            "wti_change_usd": wti_change,
            "wti_change_pct": (wti_change / old_wti * 100) if old_wti else 0,
            "yes_change_pp": yes_change,
            "expected_pp": expected,
        }

    if _divergence_active and now >= _divergence_until:
        _divergence_active = False

    return None


def is_flash_crash(wti_change: float, yes_change_pp: float) -> bool:
    """
    Flash crash = YES dropped >15pp but WTI dropped <$2.
    Rule: DO NOT SELL during flash crash.
    """
    return yes_change_pp < -15 and abs(wti_change) < 2
