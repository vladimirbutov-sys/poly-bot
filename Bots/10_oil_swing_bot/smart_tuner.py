"""
Smart Tuner — Quant Advisor for Oil Swing Bot.

Analyzes WTI ↔ Polymarket relationship, volatility, price distributions,
trade history, and orderbook depth. Produces a JSON report with specific
parameter recommendations and confidence ratings.

Auto-applies recommendations to config.py every hour via calibrate_loop.
"""
import os
import json
import math
import logging
import requests
from datetime import datetime, timezone, timedelta

import yfinance as yf

from config import (
    YES_TOKEN_ID, NO_TOKEN_ID,
    YES_ENTRY_STEPS, YES_EXIT_STEPS, NO_ENTRY_STEPS,
    YES_PROFIT_TARGET, MAX_YES_ENTRY_PRICE, MAX_NO_ENTRY_PRICE,
    DIVERGENCE_RATIO_NORMAL, WTI_SELL_NO_BELOW,
    STOP_CEASEFIRE_WTI, STOP_NO_WTI,
    STOP_THETA_DAYS, STOP_THETA_WTI_MOVE,
    POSITIONS_FILE, BANKROLL,
)

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_FILE = os.path.join(BOT_DIR, "tuner_report.json")
CALIBRATION_FILE = os.path.join(BOT_DIR, "theta_calibration.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [TUNER] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("smart_tuner")


# ═══════════════════════════════════════════
#  DATA FETCHING (reuse from calibrate.py)
# ═══════════════════════════════════════════

def fetch_price_history(token_id: str) -> list:
    """Fetch hourly price history from Polymarket CLOB."""
    url = "https://clob.polymarket.com/prices-history"
    params = {"market": token_id, "interval": "max", "fidelity": "60"}
    try:
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "history" in data:
                return [(int(p["t"]), float(p["p"])) for p in data["history"]]
            elif isinstance(data, list):
                return [(int(p["t"]), float(p["p"])) for p in data]
    except Exception as e:
        log.error(f"Fetch price history failed: {e}")
    return []


def fetch_wti_history() -> list:
    """Fetch WTI hourly history for last 30 days."""
    try:
        ticker = yf.Ticker("CL=F")
        hist = ticker.history(period="1mo", interval="1h")
        return [(int(t.timestamp()), float(row["Close"])) for t, row in hist.iterrows()]
    except Exception as e:
        log.error(f"WTI history error: {e}")
        return []


def fetch_orderbook(token_id: str) -> dict | None:
    """Fetch full orderbook for a token."""
    try:
        resp = requests.get(
            "https://clob.polymarket.com/book",
            params={"token_id": token_id},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        log.error(f"Orderbook fetch failed: {e}")
    return None


def get_wti_current() -> float | None:
    """Get current WTI price."""
    try:
        ticker = yf.Ticker("CL=F")
        data = ticker.fast_info
        return float(data.get("lastPrice") or data.get("last_price") or 0) or None
    except Exception:
        return None


# ═══════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════

def to_hourly(data: list) -> dict:
    """Convert [(ts, price)] to {hour_key: price}."""
    result = {}
    for ts, price in data:
        result[ts // 3600] = price
    return result


def pearson(xs, ys):
    """Pearson correlation. Returns None if < 5 points."""
    n = len(xs)
    if n < 5:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n)
    sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n)
    if sx == 0 or sy == 0:
        return None
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / n
    return cov / (sx * sy)


def ols_slope(xs, ys):
    """OLS regression slope (y on x). Returns None if < 5 points."""
    n = len(xs)
    if n < 5:
        return None
    mx = sum(xs) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    my = sum(ys) / n
    numer = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    return numer / denom


def percentile(values: list, pct: float) -> float:
    """Simple percentile (0-100)."""
    if not values:
        return 0
    s = sorted(values)
    idx = int(len(s) * pct / 100)
    return s[min(idx, len(s) - 1)]


def trading_days_remaining() -> int:
    """Trading days until March 31."""
    today = datetime.now(timezone.utc).date()
    deadline = datetime(2026, 3, 31).date()
    days = 0
    current = today
    while current <= deadline:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days


# ═══════════════════════════════════════════
#  ANALYSIS 1: REGIME DETECTION
# ═══════════════════════════════════════════

def analyze_regime(wti_hourly: dict, yes_hourly: dict) -> dict:
    """Detect WTI ↔ YES correlation regime."""
    now_hour = int(datetime.now(timezone.utc).timestamp()) // 3600
    common = sorted(set(wti_hourly.keys()) & set(yes_hourly.keys()))

    windows = {"24h": 24, "3d": 72, "7d": 168, "all": 999999}
    correlations = {}
    slopes = {}
    sample_sizes = {}

    for name, hours_back in windows.items():
        min_hour = now_hour - hours_back
        hrs = [h for h in common if h >= min_hour]
        if len(hrs) < 6:
            correlations[name] = None
            slopes[name] = None
            sample_sizes[name] = len(hrs)
            continue

        wti_ch, yes_ch = [], []
        for i in range(1, len(hrs)):
            if hrs[i] - hrs[i - 1] > 3:
                continue
            wti_ch.append(wti_hourly[hrs[i]] - wti_hourly[hrs[i - 1]])
            yes_ch.append((yes_hourly[hrs[i]] - yes_hourly[hrs[i - 1]]) * 100)  # to pp

        correlations[name] = round(pearson(wti_ch, yes_ch), 3) if pearson(wti_ch, yes_ch) is not None else None
        slopes[name] = round(ols_slope(wti_ch, yes_ch), 3) if ols_slope(wti_ch, yes_ch) is not None else None
        sample_sizes[name] = len(wti_ch)

    # Classify regime
    r_24h = correlations.get("24h") or 0
    r_3d = correlations.get("3d") or 0

    if r_24h > 0.5:
        classification = "strong"
    elif r_24h > 0.2:
        classification = "weak"
    elif r_24h > -0.2:
        classification = "decorrelated"
    else:
        classification = "inverted"

    # Regime shift detection
    regime_shift = abs(r_24h - r_3d) > 0.3

    # Structural break: split 7d data in half, compare slopes
    min_7d = now_hour - 168
    hrs_7d = [h for h in common if h >= min_7d]
    structural_break = False
    slope_first = None
    slope_second = None

    if len(hrs_7d) >= 20:
        mid = len(hrs_7d) // 2
        first_half = hrs_7d[:mid]
        second_half = hrs_7d[mid:]

        def half_slope(hrs_subset):
            wc, yc = [], []
            for i in range(1, len(hrs_subset)):
                if hrs_subset[i] - hrs_subset[i - 1] > 3:
                    continue
                wc.append(wti_hourly[hrs_subset[i]] - wti_hourly[hrs_subset[i - 1]])
                yc.append((yes_hourly[hrs_subset[i]] - yes_hourly[hrs_subset[i - 1]]) * 100)
            return ols_slope(wc, yc)

        slope_first = half_slope(first_half)
        slope_second = half_slope(second_half)
        if slope_first is not None and slope_second is not None and slope_first != 0:
            if abs(slope_second - slope_first) / max(abs(slope_first), 0.01) > 0.5:
                structural_break = True

    # Summary
    summaries = {
        "strong": "WTI и YES двигаются синхронно. Стратегия работает штатно.",
        "weak": "Связь WTI↔YES ослабла. Рекомендуется уменьшить ставки.",
        "decorrelated": "WTI и YES двигаются независимо. WTI-триггеры ненадёжны, уменьшить позиции.",
        "inverted": "WTI и YES двигаются в противофазе. Рекомендуется приостановить WTI-входы.",
    }

    return {
        "classification": classification,
        "correlations": correlations,
        "slopes": slopes,
        "sample_sizes": sample_sizes,
        "regime_shift": regime_shift,
        "structural_break": structural_break,
        "slope_first_half": round(slope_first, 3) if slope_first else None,
        "slope_second_half": round(slope_second, 3) if slope_second else None,
        "summary": summaries[classification],
    }


# ═══════════════════════════════════════════
#  ANALYSIS 2: VOLATILITY
# ═══════════════════════════════════════════

def analyze_volatility(wti_hourly: dict) -> dict:
    """WTI volatility and range analysis."""
    now_hour = int(datetime.now(timezone.utc).timestamp()) // 3600
    hours_sorted = sorted(wti_hourly.keys())

    def window_stats(hours_back):
        min_h = now_hour - hours_back
        hrs = [h for h in hours_sorted if h >= min_h and h in wti_hourly]
        if len(hrs) < 3:
            return {"vol": None, "min": None, "max": None, "mean": None, "count": 0}

        prices = [wti_hourly[h] for h in hrs]
        log_returns = []
        for i in range(1, len(hrs)):
            if hrs[i] - hrs[i - 1] <= 3 and wti_hourly[hrs[i - 1]] > 0:
                log_returns.append(math.log(wti_hourly[hrs[i]] / wti_hourly[hrs[i - 1]]))

        vol = None
        if len(log_returns) >= 3:
            mean_r = sum(log_returns) / len(log_returns)
            var = sum((r - mean_r) ** 2 for r in log_returns) / len(log_returns)
            vol = round(math.sqrt(var) * math.sqrt(24 * 252) * 100, 1)  # annualized %

        return {
            "vol": vol,
            "min": round(min(prices), 2),
            "max": round(max(prices), 2),
            "mean": round(sum(prices) / len(prices), 2),
            "count": len(prices),
        }

    w24h = window_stats(24)
    w3d = window_stats(72)
    w7d = window_stats(168)

    vol_ratio = None
    if w24h["vol"] and w7d["vol"] and w7d["vol"] > 0:
        vol_ratio = round(w24h["vol"] / w7d["vol"], 2)

    if vol_ratio and vol_ratio > 1.5:
        classification = "high"
    elif vol_ratio and vol_ratio < 0.5:
        classification = "low"
    else:
        classification = "normal"

    return {
        "realized_24h": w24h["vol"],
        "realized_3d": w3d["vol"],
        "realized_7d": w7d["vol"],
        "volatility_ratio": vol_ratio,
        "classification": classification,
        "wti_range_24h": {"min": w24h["min"], "max": w24h["max"]},
        "wti_range_3d": {"min": w3d["min"], "max": w3d["max"]},
        "wti_range_7d": {"min": w7d["min"], "max": w7d["max"]},
        "current_mean_24h": w24h["mean"],
    }


# ═══════════════════════════════════════════
#  ANALYSIS 3: SENSITIVITY (pp per $1 WTI)
# ═══════════════════════════════════════════

def analyze_sensitivity(wti_hourly: dict, yes_hourly: dict) -> dict:
    """How many pp YES moves per $1 WTI change."""
    now_hour = int(datetime.now(timezone.utc).timestamp()) // 3600
    common = sorted(set(wti_hourly.keys()) & set(yes_hourly.keys()))

    def calc_for_window(hours_back):
        min_h = now_hour - hours_back
        hrs = [h for h in common if h >= min_h]
        wti_ch, yes_ch = [], []
        for i in range(1, len(hrs)):
            if hrs[i] - hrs[i - 1] > 3:
                continue
            wti_ch.append(wti_hourly[hrs[i]] - wti_hourly[hrs[i - 1]])
            yes_ch.append((yes_hourly[hrs[i]] - yes_hourly[hrs[i - 1]]) * 100)
        return wti_ch, yes_ch

    results = {}
    for name, hours in [("24h", 24), ("3d", 72), ("7d", 168)]:
        wti_ch, yes_ch = calc_for_window(hours)
        s = ols_slope(wti_ch, yes_ch)
        results[name] = round(s, 3) if s is not None else None

    # Asymmetry: separate slopes for WTI up vs down
    wti_ch_3d, yes_ch_3d = calc_for_window(72)
    up_wti, up_yes = [], []
    down_wti, down_yes = [], []
    for w, y in zip(wti_ch_3d, yes_ch_3d):
        if w > 0:
            up_wti.append(w)
            up_yes.append(y)
        elif w < 0:
            down_wti.append(w)
            down_yes.append(y)

    up_slope = ols_slope(up_wti, up_yes) if len(up_wti) >= 5 else None
    down_slope = ols_slope(down_wti, down_yes) if len(down_wti) >= 5 else None

    # Best estimate: use 3d slope (enough data, recent enough)
    recommended = results.get("3d") or results.get("7d") or DIVERGENCE_RATIO_NORMAL
    sample_size = len(wti_ch_3d)

    confidence = "high" if sample_size >= 50 else "medium" if sample_size >= 20 else "low"

    return {
        "pp_per_dollar_24h": results.get("24h"),
        "pp_per_dollar_3d": results.get("3d"),
        "pp_per_dollar_7d": results.get("7d"),
        "current_hardcoded": DIVERGENCE_RATIO_NORMAL,
        "recommended": round(recommended, 2),
        "asymmetry": {
            "up_slope": round(up_slope, 3) if up_slope else None,
            "down_slope": round(down_slope, 3) if down_slope else None,
        },
        "confidence": confidence,
        "sample_size": sample_size,
    }


# ═══════════════════════════════════════════
#  ANALYSIS 4: PRICE DISTRIBUTION
# ═══════════════════════════════════════════

def analyze_price_distribution(yes_hourly: dict, no_hourly: dict) -> dict:
    """YES/NO price stats and achievable swings."""
    now_hour = int(datetime.now(timezone.utc).timestamp()) // 3600

    def stats_for(hourly, hours_back):
        min_h = now_hour - hours_back
        prices = [p for h, p in sorted(hourly.items()) if h >= min_h]
        if not prices:
            return None

        # Max achievable swing (buy low, sell high within window)
        min_p = min(prices)
        max_after_min = 0
        found_min = False
        for p in prices:
            if p == min_p:
                found_min = True
            if found_min and p > max_after_min:
                max_after_min = p
        max_swing = max_after_min - min_p if found_min and max_after_min > min_p else 0
        max_gain_pct = (max_swing / min_p * 100) if min_p > 0 else 0

        return {
            "current": round(prices[-1], 4),
            "min": round(min(prices), 4),
            "max": round(max(prices), 4),
            "p25": round(percentile(prices, 25), 4),
            "p50": round(percentile(prices, 50), 4),
            "p75": round(percentile(prices, 75), 4),
            "max_swing": round(max_swing, 4),
            "max_gain_pct": round(max_gain_pct, 1),
            "count": len(prices),
        }

    return {
        "yes_3d": stats_for(yes_hourly, 72),
        "yes_7d": stats_for(yes_hourly, 168),
        "no_3d": stats_for(no_hourly, 72),
        "no_7d": stats_for(no_hourly, 168),
    }


# ═══════════════════════════════════════════
#  ANALYSIS 5: THETA DECAY
# ═══════════════════════════════════════════

def analyze_theta() -> dict:
    """Read theta calibration and check decay rate."""
    days = trading_days_remaining()
    try:
        with open(CALIBRATION_FILE, "r") as f:
            cal = json.load(f)
    except Exception:
        return {"current_day": days, "profit_mult": None, "price_mult": None,
                "decay_rate": None, "accelerating": False}

    days_data = cal.get("days", {})
    current = days_data.get(str(days), {})
    prev = days_data.get(str(days + 1), {})

    pm = current.get("profit_mult")
    prm = current.get("price_mult")
    prev_pm = prev.get("profit_mult")

    decay_rate = round(prev_pm - pm, 3) if pm is not None and prev_pm is not None else None
    accelerating = decay_rate is not None and decay_rate > 0.1

    return {
        "current_day": days,
        "profit_mult": pm,
        "price_mult": prm,
        "decay_rate": decay_rate,
        "accelerating": accelerating,
    }


# ═══════════════════════════════════════════
#  ANALYSIS 6: TRADE HISTORY
# ═══════════════════════════════════════════

def analyze_trade_history() -> dict:
    """Analyze closed trades from positions.json."""
    try:
        with open(POSITIONS_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return {"total_trades": 0, "note": "Cannot read positions.json"}

    history = data.get("history", [])
    positions = data.get("positions", {})
    if not history:
        return {"total_trades": 0, "note": "No trade history"}

    pnls = [h.get("pnl", 0) for h in history]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p <= 0)

    # Which entry steps were triggered?
    yes_steps = set()
    no_steps = set()
    for pos in positions.values():
        step = pos.get("entry_step", -1)
        side = pos.get("side", "")
        if step >= 0:
            if side == "YES":
                yes_steps.add(step)
            elif side == "NO":
                no_steps.add(step)

    # Exit reasons
    reasons = {}
    for h in history:
        r = h.get("reason", "unknown")
        # Simplify reason
        if "profit" in r:
            key = "profit_target"
        elif "manual" in r:
            key = "manual"
        elif "exit" in r or "wti" in r:
            key = "wti_exit"
        else:
            key = r
        reasons[key] = reasons.get(key, 0) + 1

    primary_exit = max(reasons, key=reasons.get) if reasons else "unknown"

    # Holding periods
    hold_hours = []
    for pos in positions.values():
        opened = pos.get("opened_at", "")
        closed = pos.get("closed_at", "")
        if opened and closed:
            try:
                o = datetime.fromisoformat(opened)
                c = datetime.fromisoformat(closed)
                hold_hours.append((c - o).total_seconds() / 3600)
            except Exception:
                pass

    avg_hold = round(sum(hold_hours) / len(hold_hours), 1) if hold_hours else None

    return {
        "total_trades": len(history),
        "wins": wins,
        "losses": losses,
        "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else 0,
        "total_pnl": round(sum(pnls), 2),
        "avg_hold_hours": avg_hold,
        "yes_steps_triggered": sorted(yes_steps),
        "no_steps_triggered": sorted(no_steps),
        "exit_reasons": reasons,
        "primary_exit_reason": primary_exit,
    }


# ═══════════════════════════════════════════
#  ANALYSIS 7: ORDERBOOK DEPTH
# ═══════════════════════════════════════════

def analyze_orderbook() -> dict:
    """Check orderbook depth and spreads."""
    result = {}
    for name, token_id in [("yes", YES_TOKEN_ID), ("no", NO_TOKEN_ID)]:
        book = fetch_orderbook(token_id)
        if not book:
            result[name] = {"spread": None, "bid_depth": None, "ask_depth": None}
            continue

        bids = book.get("bids", [])
        asks = book.get("asks", [])
        best_bid = max(float(b["price"]) for b in bids) if bids else 0
        best_ask = min(float(a["price"]) for a in asks) if asks else 1
        spread = round(best_ask - best_bid, 4)

        # Depth within 5% of best bid/ask
        bid_depth = sum(
            float(b["size"]) * float(b["price"])
            for b in bids if float(b["price"]) >= best_bid * 0.95
        ) if bids else 0

        ask_depth = sum(
            float(a["size"]) * float(a["price"])
            for a in asks if float(a["price"]) <= best_ask * 1.05
        ) if asks else 0

        result[name] = {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread": spread,
            "bid_depth_usd": round(bid_depth, 2),
            "ask_depth_usd": round(ask_depth, 2),
        }

    return result


# ═══════════════════════════════════════════
#  RECOMMENDATIONS ENGINE
# ═══════════════════════════════════════════

def generate_recommendations(regime, volatility, sensitivity, prices, theta, trades, orderbook) -> tuple:
    """Generate specific parameter recommendations. Returns (recommendations, warnings)."""
    recommendations = []
    warnings = []
    days = trading_days_remaining()

    # Regime multiplier for bet sizes
    regime_mult = {"strong": 1.0, "weak": 0.7, "decorrelated": 0.4, "inverted": 0.2}
    r_mult = regime_mult.get(regime["classification"], 0.5)

    # Volatility multiplier
    vr = volatility.get("volatility_ratio") or 1.0
    if vr > 1.5:
        v_mult = 0.8
    elif vr < 0.5:
        v_mult = 1.2
    else:
        v_mult = 1.0

    # Theta multiplier from calibration
    t_mult = theta.get("profit_mult") or 1.0

    # Current WTI stats
    wti_3d = volatility.get("wti_range_3d", {})
    wti_7d = volatility.get("wti_range_7d", {})
    wti_mean = volatility.get("current_mean_24h") or 95.0
    wti_3d_min = wti_3d.get("min") or 91.0
    wti_3d_max = wti_3d.get("max") or 99.0
    wti_7d_min = wti_7d.get("min") or 90.0
    wti_7d_max = wti_7d.get("max") or 100.0

    # Sensitivity
    sens = sensitivity.get("recommended") or DIVERGENCE_RATIO_NORMAL

    # YES price stats
    yes_3d = prices.get("yes_3d") or {}
    no_3d = prices.get("no_3d") or {}

    # ── YES ENTRY STEPS ──
    # Logic: space steps between current WTI and reachable floor
    reachable_floor = min(wti_3d_min, wti_mean - (wti_7d_max - wti_7d_min))
    reachable_floor = max(reachable_floor, 85.0)  # sanity floor
    range_down = wti_mean - reachable_floor

    if range_down > 1:
        step1_trigger = round(wti_mean - range_down * 0.33, 0)
        step2_trigger = round(wti_mean - range_down * 0.55, 0)
        step3_trigger = round(wti_mean - range_down * 0.80, 0)
        # Deduplicate: each step must be at least $1 apart (descending)
        if step2_trigger >= step1_trigger:
            step2_trigger = step1_trigger - 1
        if step3_trigger >= step2_trigger:
            step3_trigger = step2_trigger - 1
    else:
        step1_trigger, step2_trigger, step3_trigger = 93, 91, 89

    # Bet sizes: percentage of bankroll × regime × vol
    combined_mult = r_mult * v_mult
    # YES is historically unprofitable — use conservative base sizes (1.5%, 1.5%, 5% of bankroll)
    base_yes = [round(BANKROLL * 0.015), round(BANKROLL * 0.015), round(BANKROLL * 0.05)]
    rec_yes_sizes = [max(5, round(b * combined_mult / 5) * 5) for b in base_yes]

    # Check if steps were triggered in history
    yes_triggered = set(trades.get("yes_steps_triggered", []))
    untriggered_yes = []
    for i in range(3):
        if i not in yes_triggered and i > 0:
            untriggered_yes.append(i)

    rec_yes_entry = [
        (step1_trigger, rec_yes_sizes[0]),
        (step2_trigger, rec_yes_sizes[1]),
        (step3_trigger, rec_yes_sizes[2]),
    ]

    # Confidence based on data
    n_wti = volatility.get("wti_range_7d", {})
    entry_confidence = "high" if (wti_7d.get("min") and wti_7d.get("max")) else "low"
    entry_sample = sensitivity.get("sample_size", 0)

    recommendations.append({
        "parameter": "YES_ENTRY_STEPS",
        "current": [(t, s) for t, s in YES_ENTRY_STEPS],
        "recommended": rec_yes_entry,
        "rationale": (
            f"WTI 3d диапазон: ${wti_3d_min}–${wti_3d_max}. "
            f"Режим: {regime['classification']} → ставки ×{combined_mult:.1f}. "
            + (f"Шаги {untriggered_yes} никогда не срабатывали. " if untriggered_yes else "")
            + f"Достижимый минимум: ~${reachable_floor:.0f}."
        ),
        "confidence": entry_confidence,
        "sample_size": entry_sample,
    })

    # ── YES EXIT STEPS ──
    # Based on sensitivity: what WTI level gives enough YES gain
    yes_current = yes_3d.get("current") or 0.65
    yes_target_gain = YES_PROFIT_TARGET * t_mult
    required_pp = yes_target_gain * 100 * yes_current  # pp needed
    required_wti_move = required_pp / max(abs(sens), 0.1) if sens else 3.0

    # Cap required_wti_move: if sensitivity is too low, don't let exits go above $100
    max_wti_move = 100.0 - wti_mean
    if required_wti_move > max_wti_move:
        required_wti_move = max_wti_move

    exit1 = round(wti_mean + required_wti_move * 0.4, 0)
    exit2 = round(wti_mean + required_wti_move * 0.7, 0)
    exit3 = round(wti_mean + required_wti_move * 1.0, 0)

    # Sanity: exits must stay within WTI range [current+0.5, 100]
    exit1 = max(exit1, wti_mean + 0.5)
    exit1 = min(exit1, 99.0)
    exit2 = min(exit2, 99.5)
    exit3 = min(exit3, 100.0)

    recommendations.append({
        "parameter": "YES_EXIT_STEPS",
        "current": [(t, p) for t, p in YES_EXIT_STEPS],
        "recommended": [(exit1, 0.30), (exit2, 0.50), (exit3, 1.00)],
        "rationale": (
            f"Чувствительность {sens:.1f} pp/$1. При YES={yes_current:.2f} и target {yes_target_gain:.0%}, "
            f"нужно движение WTI +${required_wti_move:.1f}. "
            f"Шаги распределены на 40%/70%/100% от требуемого движения."
        ),
        "confidence": sensitivity.get("confidence", "medium"),
        "sample_size": sensitivity.get("sample_size", 0),
    })

    # ── NO ENTRY STEPS ──
    reachable_ceiling = max(wti_3d_max, wti_mean + (wti_7d_max - wti_7d_min) * 0.5)
    reachable_ceiling = min(reachable_ceiling, 101.0)
    range_up = reachable_ceiling - wti_mean

    if range_up > 1:
        no_step1 = round(wti_mean + range_up * 0.40, 0)
        no_step2 = round(wti_mean + range_up * 0.65, 0)
        no_step3 = round(wti_mean + range_up * 0.85, 0)
        # Deduplicate: each step must be at least $1 apart
        if no_step2 <= no_step1:
            no_step2 = no_step1 + 1
        if no_step3 <= no_step2:
            no_step3 = no_step2 + 1
    else:
        no_step1, no_step2, no_step3 = 97, 98, 99

    # NO base sizes: 1.5%, 1.5%, 3% of bankroll
    base_no = [round(BANKROLL * 0.015), round(BANKROLL * 0.015), round(BANKROLL * 0.03)]
    rec_no_sizes = [max(5, round(b * combined_mult / 5) * 5) for b in base_no]

    # NO profit targets: keep fixed (backtest shows higher targets = more profit)
    # Theta should scale bet SIZE, not profit targets
    base_no_targets = [0.35, 0.69, 1.04]
    rec_no_targets = base_no_targets  # don't scale by theta

    recommendations.append({
        "parameter": "NO_ENTRY_STEPS",
        "current": [(t, s, pt) for t, s, pt in NO_ENTRY_STEPS],
        "recommended": [
            (no_step1, rec_no_sizes[0], rec_no_targets[0]),
            (no_step2, rec_no_sizes[1], rec_no_targets[1]),
            (no_step3, rec_no_sizes[2], rec_no_targets[2]),
        ],
        "rationale": (
            f"WTI 3d потолок: ${wti_3d_max}. "
            f"Режим: {regime['classification']} → ставки ×{combined_mult:.1f}. "
            f"Profit targets ×{t_mult:.2f} (theta). "
            f"Достижимый потолок: ~${reachable_ceiling:.0f}."
        ),
        "confidence": entry_confidence,
        "sample_size": entry_sample,
    })

    # ── YES PROFIT TARGET ──
    max_gain_yes = yes_3d.get("max_gain_pct", 0) if yes_3d else 0
    p75_target = max_gain_yes * 0.75 / 100 if max_gain_yes > 0 else YES_PROFIT_TARGET
    rec_target = round(min(max(p75_target * t_mult, 0.05), 0.30), 2)

    target_confidence = "high" if (yes_3d and yes_3d.get("count", 0) >= 50) else "medium"

    recommendations.append({
        "parameter": "YES_PROFIT_TARGET",
        "current": YES_PROFIT_TARGET,
        "recommended": rec_target,
        "rationale": (
            f"Макс. свинг YES за 3 дня: {max_gain_yes:.1f}%. "
            f"P75 от свинга = {p75_target:.1%}. "
            f"С theta ×{t_mult:.2f} → {rec_target:.0%}."
            + (" Не хватает данных для точной оценки." if target_confidence == "low" else "")
        ),
        "confidence": target_confidence,
        "sample_size": yes_3d.get("count", 0) if yes_3d else 0,
    })

    # ── MAX ENTRY PRICES ──
    yes_median = yes_3d.get("p50", 0.65) if yes_3d else 0.65
    no_median = no_3d.get("p50", 0.20) if no_3d else 0.20
    theta_prm = theta.get("price_mult") or 1.0

    rec_max_yes = round(min(yes_median + 0.03, MAX_YES_ENTRY_PRICE) * theta_prm, 2)
    rec_max_no = round(min(no_median + 0.05, MAX_NO_ENTRY_PRICE) * theta_prm, 2)

    recommendations.append({
        "parameter": "MAX_YES_ENTRY_PRICE",
        "current": MAX_YES_ENTRY_PRICE,
        "recommended": rec_max_yes,
        "rationale": f"Медиана YES за 3d: {yes_median:.2f}. С буфером +3¢ и theta ×{theta_prm:.2f} → {rec_max_yes:.2f}.",
        "confidence": "high" if yes_3d else "low",
        "sample_size": yes_3d.get("count", 0) if yes_3d else 0,
    })

    recommendations.append({
        "parameter": "MAX_NO_ENTRY_PRICE",
        "current": MAX_NO_ENTRY_PRICE,
        "recommended": rec_max_no,
        "rationale": f"Медиана NO за 3d: {no_median:.2f}. С буфером +5¢ и theta ×{theta_prm:.2f} → {rec_max_no:.2f}.",
        "confidence": "high" if no_3d else "low",
        "sample_size": no_3d.get("count", 0) if no_3d else 0,
    })

    # ── DIVERGENCE RATIO ──
    recommendations.append({
        "parameter": "DIVERGENCE_RATIO_NORMAL",
        "current": DIVERGENCE_RATIO_NORMAL,
        "recommended": sensitivity.get("recommended", DIVERGENCE_RATIO_NORMAL),
        "rationale": (
            f"Измеренная чувствительность 3d: {sensitivity.get('pp_per_dollar_3d')} pp/$1 "
            f"(текущая: {DIVERGENCE_RATIO_NORMAL}). "
            + (f"Асимметрия: вверх {sensitivity['asymmetry'].get('up_slope')}, "
               f"вниз {sensitivity['asymmetry'].get('down_slope')}."
               if sensitivity.get("asymmetry", {}).get("up_slope") else "")
        ),
        "confidence": sensitivity.get("confidence", "medium"),
        "sample_size": sensitivity.get("sample_size", 0),
    })

    # ── STOP-LOSSES ──
    # Ceasefire: tighten if WTI hasn't been anywhere near current level
    rec_ceasefire = max(round(wti_7d_min - 5, 0), 80.0)
    recommendations.append({
        "parameter": "STOP_CEASEFIRE_WTI",
        "current": STOP_CEASEFIRE_WTI,
        "recommended": rec_ceasefire,
        "rationale": f"WTI min за 7d: ${wti_7d_min}. Стоп на ${rec_ceasefire} ($5 ниже минимума).",
        "confidence": "medium",
        "sample_size": volatility.get("wti_range_7d", {}).get("min", 0),
    })

    # WTI_SELL_NO_BELOW: keep near current or tighten
    rec_sell_no = round(max(wti_3d_min - 1, 90.0), 0)
    recommendations.append({
        "parameter": "WTI_SELL_NO_BELOW",
        "current": WTI_SELL_NO_BELOW,
        "recommended": rec_sell_no,
        "rationale": f"WTI 3d min: ${wti_3d_min}. Продажа NO при WTI < ${rec_sell_no}.",
        "confidence": "medium",
        "sample_size": entry_sample,
    })

    # ── WARNINGS ──
    if regime["classification"] in ("decorrelated", "inverted"):
        warnings.append({
            "type": "regime_breakdown",
            "severity": "high",
            "message": (
                f"Корреляция WTI↔YES разрушена (24h: {regime['correlations'].get('24h')}). "
                f"WTI-триггеры могут не приводить к ожидаемому движению цен YES/NO."
            ),
        })

    if regime.get("structural_break"):
        warnings.append({
            "type": "structural_break",
            "severity": "high",
            "message": (
                f"Структурный перелом: наклон первой половины 7d = {regime.get('slope_first_half')}, "
                f"второй = {regime.get('slope_second_half')}. Рынок поменял поведение."
            ),
        })

    if untriggered_yes:
        warnings.append({
            "type": "untriggered_steps",
            "severity": "medium",
            "message": f"YES entry шаги {[s+1 for s in untriggered_yes]} никогда не срабатывали. Уровни возможно нереалистичны.",
        })

    if theta.get("accelerating"):
        warnings.append({
            "type": "theta_accelerating",
            "severity": "medium",
            "message": f"Theta ускоряется: profit_mult упал на {theta.get('decay_rate')} за день.",
        })

    if days <= 3:
        warnings.append({
            "type": "deadline_close",
            "severity": "high",
            "message": f"Осталось {days} торговых дней. Рекомендуется не открывать новые позиции.",
        })

    if rec_target < 0.06:
        warnings.append({
            "type": "low_upside",
            "severity": "medium",
            "message": f"Рекомендуемый profit target {rec_target:.0%} — очень низкий. Возможно не стоит входить.",
        })

    # Liquidity warning
    ob_yes = orderbook.get("yes", {})
    ob_no = orderbook.get("no", {})
    max_bet = max(rec_yes_sizes)
    if ob_yes.get("ask_depth_usd") and ob_yes["ask_depth_usd"] < max_bet * 2:
        warnings.append({
            "type": "liquidity_yes",
            "severity": "low",
            "message": f"Ликвидность YES ask: ${ob_yes['ask_depth_usd']:.0f} — может не хватить для ставки ${max_bet}.",
        })

    return recommendations, warnings


# ═══════════════════════════════════════════
#  MAIN: RUN TUNER
# ═══════════════════════════════════════════

def run_tuner() -> dict:
    """Run all analyses and generate report."""
    log.info("Starting Smart Tuner analysis...")

    # Fetch data
    log.info("Fetching data...")
    yes_data = fetch_price_history(YES_TOKEN_ID)
    no_data = fetch_price_history(NO_TOKEN_ID)
    wti_data = fetch_wti_history()

    if not yes_data or not wti_data:
        log.error("Insufficient data for analysis")
        return {"error": "Insufficient data", "generated_at": datetime.now(timezone.utc).isoformat()}

    log.info(f"Data: YES={len(yes_data)} pts, NO={len(no_data)} pts, WTI={len(wti_data)} pts")

    # Build hourly lookups
    wti_hourly = to_hourly(wti_data)
    yes_hourly = to_hourly(yes_data)
    no_hourly = to_hourly(no_data)

    # Run analyses
    log.info("Analyzing regime...")
    regime = analyze_regime(wti_hourly, yes_hourly)
    log.info(f"  Regime: {regime['classification']} | 24h corr: {regime['correlations'].get('24h')}")

    log.info("Analyzing volatility...")
    volatility = analyze_volatility(wti_hourly)
    log.info(f"  Vol ratio: {volatility.get('volatility_ratio')} | Class: {volatility['classification']}")

    log.info("Analyzing sensitivity...")
    sensitivity = analyze_sensitivity(wti_hourly, yes_hourly)
    log.info(f"  Sensitivity 3d: {sensitivity.get('pp_per_dollar_3d')} pp/$1 (hardcoded: {DIVERGENCE_RATIO_NORMAL})")

    log.info("Analyzing price distributions...")
    price_dist = analyze_price_distribution(yes_hourly, no_hourly)

    log.info("Analyzing theta...")
    theta = analyze_theta()
    log.info(f"  Day {theta['current_day']}: profit_mult={theta.get('profit_mult')}, accelerating={theta.get('accelerating')}")

    log.info("Analyzing trade history...")
    trades = analyze_trade_history()
    log.info(f"  Trades: {trades.get('total_trades')}, PnL: ${trades.get('total_pnl', 0):.2f}")

    log.info("Analyzing orderbook...")
    orderbook = analyze_orderbook()

    # Generate recommendations
    log.info("Generating recommendations...")
    recs, warnings = generate_recommendations(
        regime, volatility, sensitivity, price_dist, theta, trades, orderbook,
    )

    # Build summary
    changes_summary = []
    for r in recs:
        if r["current"] != r["recommended"]:
            changes_summary.append(f"{r['parameter']}: {r['current']} → {r['recommended']}")

    summary = (
        f"Режим: {regime['classification'].upper()} | "
        f"{theta['current_day']} дней | "
        f"Корр. 24h: {regime['correlations'].get('24h')} | "
        f"{len(warnings)} предупреждений | "
        f"{len(changes_summary)} изменений"
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "days_remaining": trading_days_remaining(),
        "regime": regime,
        "volatility": volatility,
        "sensitivity": sensitivity,
        "price_distribution": price_dist,
        "theta": theta,
        "trade_history": trades,
        "orderbook": orderbook,
        "recommendations": recs,
        "warnings": warnings,
        "summary": summary,
    }

    log.info(f"Done. {summary}")

    # Auto-apply recommendations to config.py
    apply_result = apply_recommendations(report)
    report["auto_applied"] = apply_result
    if apply_result["applied"]:
        log.info(f"Auto-applied {len(apply_result['applied'])} changes to config.py")
        for a in apply_result["applied"]:
            log.info(f"  {a['parameter']}: {a['old']} → {a['new']}")
    else:
        log.info("No config changes needed")

    return report


def save_report(report: dict):
    """Save report to JSON file."""
    tmp = REPORT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    os.replace(tmp, REPORT_FILE)
    log.info(f"Report saved: {REPORT_FILE}")


def format_telegram_summary(report: dict) -> str:
    """Format short Telegram message."""
    regime = report.get("regime", {})
    theta = report.get("theta", {})
    warnings = report.get("warnings", [])
    recs = report.get("recommendations", [])

    lines = [
        f"<b>SMART TUNER</b> | {report.get('days_remaining', '?')} дней | "
        f"Режим: {regime.get('classification', '?').upper()}",
        f"Корр. 24h: {regime.get('correlations', {}).get('24h')} | "
        f"3d: {regime.get('correlations', {}).get('3d')}",
    ]

    if warnings:
        lines.append("")
        for w in warnings[:3]:
            sev = {"high": "!!!", "medium": "!", "low": "~"}.get(w.get("severity"), "")
            lines.append(f"{sev} {w['message'][:80]}")

    changes = [r for r in recs if r["current"] != r["recommended"]]
    if changes:
        lines.append("")
        lines.append(f"Рекомендаций: {len(changes)}")
        for r in changes[:4]:
            lines.append(f"  {r['parameter']}: {r['current']} → {r['recommended']}")

    return "\n".join(lines)


# ═══════════════════════════════════════════
#  AUTO-APPLY: Write recommendations to config.py
# ═══════════════════════════════════════════

CONFIG_FILE = os.path.join(BOT_DIR, "config.py")


def _kelly_check(recs, report) -> list:
    """Check that total recommended bet sizes don't exceed Kelly criterion."""
    warnings = []
    trades = report.get("trade_history", {})
    win_rate = trades.get("wins", 0) / max(trades.get("total_trades", 1), 1)
    avg_pnl_pct = trades.get("avg_pnl", 0) / max(BANKROLL, 1)

    # Estimate Kelly fraction: use win_rate and avg gain
    # Kelly = W - (1-W)/R where W=win_rate, R=avg_win/avg_loss
    # Simplified: use 8% of bankroll as floor (conservative but not crippling)
    kelly_frac = max(avg_pnl_pct, 0.08)
    kelly_bet = BANKROLL * kelly_frac

    # Sum all recommended bet sizes
    total_bets = 0
    for r in recs:
        if r["parameter"] in ("YES_ENTRY_STEPS", "NO_ENTRY_STEPS"):
            recommended = r.get("recommended", [])
            for step in recommended:
                total_bets += float(step[1])  # bet_usd

    if total_bets > kelly_bet * 2:
        warnings.append(
            f"Total bets ${total_bets:.0f} exceed 2x Kelly ${kelly_bet:.0f}. "
            f"Reducing bet sizes proportionally."
        )
        # Scale down all bets proportionally
        scale = kelly_bet * 2 / total_bets
        for r in recs:
            if r["parameter"] in ("YES_ENTRY_STEPS", "NO_ENTRY_STEPS"):
                new_steps = []
                for step in r["recommended"]:
                    new_size = max(5, round(float(step[1]) * scale / 5) * 5)
                    new_steps.append(tuple([step[0], new_size] + list(step[2:])))
                r["recommended"] = new_steps

    return warnings


def apply_recommendations(report: dict) -> dict:
    """
    Apply tuner recommendations directly to config.py.
    Returns {applied: [...], skipped: [...], errors: [...]}.
    """
    recs = report.get("recommendations", [])
    if not recs:
        return {"applied": [], "skipped": [], "errors": ["No recommendations"]}

    # Kelly criterion check — scale down if bets too large
    kelly_warnings = _kelly_check(recs, report)
    for w in kelly_warnings:
        log.warning(f"[KELLY] {w}")

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config_text = f.read()
    except Exception as e:
        return {"applied": [], "skipped": [], "errors": [f"Cannot read config.py: {e}"]}

    original_text = config_text
    applied = []
    skipped = []
    errors = []

    # Protected parameters — backtest proved original values are optimal
    # Smart Tuner must NOT change these (see _analytics/2026-03-20_backtest-results.md)
    PROTECTED_PARAMS = {
        "YES_ENTRY_STEPS",      # original $5/$5/$15 minimizes ceasefire losses
        "YES_EXIT_STEPS",       # original step2=$99 gives better NO entry price
        "NO_ENTRY_STEPS",       # original $5/$5/$10 + targets 35%/69%/104% best by backtest
        "YES_PROFIT_TARGET",    # original 0.21 — lower cuts winners, higher misses exits
        "STOP_CEASEFIRE_WTI",   # manually set to $80 — prevents false stops during escalation crashes
    }

    for rec in recs:
        param = rec["parameter"]
        current = rec["current"]
        recommended = rec["recommended"]

        # Skip protected parameters
        if param in PROTECTED_PARAMS:
            skipped.append({"parameter": param, "reason": "PROTECTED (backtest-verified)"})
            continue

        # Skip if no change needed
        if current == recommended:
            skipped.append({"parameter": param, "reason": "no change"})
            continue

        # Skip low-confidence recommendations
        if rec.get("confidence") == "low":
            skipped.append({"parameter": param, "reason": "low confidence"})
            continue

        # Skip tiny changes for scalar params (avoid micro-adjustments every hour)
        if isinstance(current, (int, float)) and isinstance(recommended, (int, float)):
            if current != 0 and abs(recommended - current) / abs(current) < 0.05:
                skipped.append({"parameter": param, "reason": f"change <5% ({current} → {recommended})"})
                continue

        try:
            config_text = _replace_param(config_text, param, recommended)
            applied.append({
                "parameter": param,
                "old": current,
                "new": recommended,
                "confidence": rec.get("confidence", "?"),
            })
        except ValueError as e:
            errors.append(f"{param}: {e}")

    if not applied:
        log.info("No changes to apply")
        return {"applied": applied, "skipped": skipped, "errors": errors}

    # Write config with backup
    if config_text != original_text:
        backup = CONFIG_FILE + ".bak"
        try:
            with open(backup, "w", encoding="utf-8") as f:
                f.write(original_text)
        except Exception:
            pass  # backup is best-effort

        tmp = CONFIG_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(config_text)
        os.replace(tmp, CONFIG_FILE)
        log.info(f"Config updated: {len(applied)} parameters changed, backup saved")

    return {"applied": applied, "skipped": skipped, "errors": errors}


def _replace_param(text: str, param: str, value) -> str:
    """Replace a parameter value in config.py text using regex."""
    import re

    if param == "YES_ENTRY_STEPS":
        return _replace_steps_block(text, "YES_ENTRY_STEPS", value,
                                    template="    ({trigger}, {size}),{comment}\n",
                                    fmt_fn=_fmt_yes_entry)
    elif param == "YES_EXIT_STEPS":
        return _replace_steps_block(text, "YES_EXIT_STEPS", value,
                                    template="    ({trigger}, {pct}),{comment}\n",
                                    fmt_fn=_fmt_yes_exit)
    elif param == "NO_ENTRY_STEPS":
        return _replace_steps_block(text, "NO_ENTRY_STEPS", value,
                                    template="    ({trigger}, {size}, {target}),{comment}\n",
                                    fmt_fn=_fmt_no_entry)
    else:
        # Simple scalar parameter
        pattern = rf'^({param}\s*=\s*)([^\n#]+)(#.*)?$'
        match = re.search(pattern, text, re.MULTILINE)
        if not match:
            raise ValueError(f"Parameter {param} not found in config.py")

        if isinstance(value, float):
            val_str = f"{value}"
        elif isinstance(value, int):
            val_str = f"{value}"
        else:
            val_str = repr(value)

        # Pad value to align comment
        comment = match.group(3) or ""
        new_line = f"{match.group(1)}{val_str}  {comment}".rstrip()
        text = text[:match.start()] + new_line + text[match.end():]
        return text


def _replace_steps_block(text: str, param_name: str, steps: list,
                         template: str, fmt_fn) -> str:
    """Replace a multi-line list block like YES_ENTRY_STEPS = [...]."""
    import re
    # Find the block: from "PARAM = [" to the closing "]"
    pattern = rf'({param_name}\s*=\s*\[)[^\]]*(\])'
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError(f"Block {param_name} not found in config.py")

    lines = "\n"
    header_comment = _get_step_header(param_name)
    if header_comment:
        lines += f"    # {header_comment}\n"
    for i, step in enumerate(steps):
        lines += fmt_fn(i, step)

    new_block = f"{match.group(1)}{lines}{match.group(2)}"
    return text[:match.start()] + new_block + text[match.end():]


def _get_step_header(param: str) -> str:
    headers = {
        "YES_ENTRY_STEPS": "(wti_trigger, bet_usd)",
        "YES_EXIT_STEPS": "(wti_trigger, pct_of_position)",
        "NO_ENTRY_STEPS": "(wti_trigger, bet_usd, profit_target)",
    }
    return headers.get(param, "")


def _fmt_yes_entry(i: int, step) -> str:
    trigger, size = float(step[0]), float(step[1])
    labels = ["разведка", "подтверждение", "основная позиция"]
    label = labels[i] if i < len(labels) else ""
    comment = f"   # Step {i+1}: WTI <= ${trigger:.0f} -> ${size:.0f} ({label})" if label else f"   # Step {i+1}"
    return f"    ({trigger}, {size}),{comment}\n"


def _fmt_yes_exit(i: int, step) -> str:
    trigger, pct = float(step[0]), float(step[1])
    pct_label = f"{pct:.0%}" if pct == 1.0 else f"{pct:.0%}"
    return f"    ({trigger}, {pct}),   # Step {i+1}: WTI >= ${trigger:.0f} -> sell {pct_label}\n"


def _fmt_no_entry(i: int, step) -> str:
    trigger, size, target = float(step[0]), float(step[1]), float(step[2])
    return f"    ({trigger}, {size}, {target}),   # Step {i+1}: WTI >= ${trigger:.0f} -> ${size:.0f}, sell at +{target:.0%}\n"


if __name__ == "__main__":
    report = run_tuner()
    save_report(report)

    # Show what was auto-applied
    result = report.get("auto_applied", {})
    if result.get("applied"):
        print(f"\n{'='*60}")
        print(f"AUTO-APPLIED {len(result['applied'])} changes:")
        print(f"{'='*60}")
        for a in result["applied"]:
            print(f"  {a['parameter']}: {a['old']} → {a['new']} [{a['confidence']}]")
    if result.get("skipped"):
        print(f"\nSkipped {len(result['skipped'])}:")
        for s in result["skipped"]:
            print(f"  {s['parameter']}: {s['reason']}")

    print("\n" + "=" * 60)
    print("TELEGRAM SUMMARY:")
    print("=" * 60)
    print(format_telegram_summary(report))
