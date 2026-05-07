"""
Oil Calibrator: WTI ↔ Polymarket correlation analysis + theta calibration.

Produces theta_calibration.json with:
1. Per-day theta multipliers (profit_mult, price_mult) — used by trading bot
2. WTI ↔ Polymarket correlation metrics (24h, 3d, all-time)
3. Chart data: WTI price + YES $100 + YES $105 time series
"""
import os
import json
import math
import requests
import logging
from datetime import datetime, timezone, timedelta

import yfinance as yf

from config import (
    YES_TOKEN_ID, NO_TOKEN_ID,
    YES_PROFIT_TARGET,
)

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
CALIBRATION_FILE = os.path.join(BOT_DIR, "theta_calibration.json")
LOG_FILE = os.path.join(BOT_DIR, "bot.log")

# $105 market YES token
YES_105_TOKEN_ID = "34523777569717412486079829083221613352783431812341266998118815593138999201307"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CALIB] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("calibrate")


def fetch_price_history(token_id: str) -> list:
    """Fetch full price history from Polymarket CLOB."""
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
        logger.error(f"Fetch failed: {e}")
    return []


def fetch_wti_history() -> list:
    """Fetch WTI hourly history for the last 30 days. Returns [(timestamp, price)]."""
    try:
        ticker = yf.Ticker("CL=F")
        hist = ticker.history(period="1mo", interval="1h")
        result = []
        for t, row in hist.iterrows():
            ts = int(t.timestamp())
            result.append((ts, float(row["Close"])))
        return result
    except Exception as e:
        logger.error(f"WTI history fetch error: {e}")
        return []


def _pearson(xs, ys):
    """Pearson correlation coefficient. Returns None if not enough data."""
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


def trading_days_until(dt, deadline):
    days = 0
    current = dt.date()
    end = deadline.date()
    while current <= end:
        if current.weekday() < 5:
            days += 1
        current += timedelta(days=1)
    return days


def calibrate():
    logger.info("Starting calibration...")

    # === Fetch all data ===
    yes_data = fetch_price_history(YES_TOKEN_ID)
    no_data = fetch_price_history(NO_TOKEN_ID)
    yes_105_data = fetch_price_history(YES_105_TOKEN_ID)
    wti_data = fetch_wti_history()

    if not yes_data or not no_data:
        logger.error("No price data available")
        return False

    logger.info(f"YES $100: {len(yes_data)} pts, NO $100: {len(no_data)} pts, "
                f"YES $105: {len(yes_105_data)} pts, WTI: {len(wti_data)} pts")

    deadline = datetime(2026, 3, 31, tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)

    # ══════════════════════════════════════════
    #  PART 1: Correlation WTI ↔ Polymarket
    # ══════════════════════════════════════════

    # Build hourly lookups
    def to_hourly(data):
        result = {}
        for ts, price in data:
            hour_key = ts // 3600
            result[hour_key] = price
        return result

    wti_hourly = to_hourly(wti_data)
    yes100_hourly = to_hourly(yes_data)
    yes105_hourly = to_hourly(yes_105_data)

    # Find common hours between WTI and YES $100
    common_hours = sorted(set(wti_hourly.keys()) & set(yes100_hourly.keys()))

    # Calculate correlations for different windows
    now_hour = int(now.timestamp()) // 3600
    windows = {
        "24h": now_hour - 24,
        "3d": now_hour - 72,
        "7d": now_hour - 168,
        "all": 0,
    }

    correlation = {}
    for window_name, min_hour in windows.items():
        hours = [h for h in common_hours if h >= min_hour]
        if len(hours) < 5:
            correlation[window_name] = None
            continue

        # Correlation on price changes (not levels)
        wti_changes = []
        yes_changes = []
        for i in range(1, len(hours)):
            h_prev, h_cur = hours[i - 1], hours[i]
            if h_cur - h_prev > 3:  # skip gaps > 3 hours
                continue
            wti_changes.append(wti_hourly[h_cur] - wti_hourly[h_prev])
            yes_changes.append(yes100_hourly[h_cur] - yes100_hourly[h_prev])

        r = _pearson(wti_changes, yes_changes)
        correlation[window_name] = round(r, 3) if r is not None else None

    logger.info(f"Correlation WTI↔YES $100: "
                f"24h={correlation.get('24h')}, 3d={correlation.get('3d')}, "
                f"7d={correlation.get('7d')}, all={correlation.get('all')}")

    # ══════════════════════════════════════════
    #  PART 2: Chart data (WTI + YES $100 + YES $105)
    # ══════════════════════════════════════════

    # Build aligned hourly series for the chart
    # Use all hours where we have at least WTI or YES $100
    all_hours = sorted(set(wti_hourly.keys()) | set(yes100_hourly.keys()) | set(yes105_hourly.keys()))
    # Keep only last 30 days
    min_chart_hour = now_hour - 720  # ~30 days
    chart_hours = [h for h in all_hours if h >= min_chart_hour]

    chart_data = []
    for h in chart_hours:
        entry = {
            "t": h * 3600,  # back to unix timestamp
            "wti": round(wti_hourly[h], 2) if h in wti_hourly else None,
            "yes100": round(yes100_hourly[h], 4) if h in yes100_hourly else None,
            "yes105": round(yes105_hourly[h], 4) if h in yes105_hourly else None,
        }
        # Only include if at least one value present
        if any(v is not None for v in [entry["wti"], entry["yes100"], entry["yes105"]]):
            chart_data.append(entry)

    logger.info(f"Chart data: {len(chart_data)} hourly points")

    # ══════════════════════════════════════════
    #  PART 3: Theta calibration (original logic)
    # ══════════════════════════════════════════

    no_hourly = to_hourly(no_data)

    day_buckets = {}
    for ts, yes_price in yes_data:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        days = trading_days_until(dt, deadline)
        hour_key = ts // 3600
        no_price = no_hourly.get(hour_key)
        if no_price is None:
            continue
        if days not in day_buckets:
            day_buckets[days] = []
        day_buckets[days].append((yes_price, no_price))

    if not day_buckets:
        logger.error("No matched data for theta")
        return False

    ref_zone = (0.15, 0.35)
    yes_by_day = {}
    for days, pairs in day_buckets.items():
        filtered = [y for y, n in pairs if ref_zone[0] <= n <= ref_zone[1]]
        if filtered:
            yes_by_day[days] = sum(filtered) / len(filtered)

    gains_by_day = {}
    for days, pairs in day_buckets.items():
        prices = [y for y, n in pairs]
        if len(prices) < 3:
            continue
        all_gains = []
        for i in range(len(prices)):
            if prices[i] <= 0:
                continue
            for j in range(i + 1, len(prices)):
                gain = (prices[j] - prices[i]) / prices[i]
                all_gains.append(gain)
        if all_gains:
            all_gains.sort()
            n = len(all_gains)
            gains_by_day[days] = {
                "p50": all_gains[int(n * 0.5)],
                "p75": all_gains[int(n * 0.75)],
                "p90": all_gains[min(int(n * 0.9), n - 1)],
                "max": all_gains[-1],
                "count": len(prices),
            }

    all_days = sorted(day_buckets.keys(), reverse=True)
    base_target = YES_PROFIT_TARGET

    ref_yes = None
    for d in all_days:
        if d in yes_by_day and d >= 15:
            ref_yes = yes_by_day[d]
            break
    if ref_yes is None:
        for d in all_days:
            if d in yes_by_day:
                ref_yes = yes_by_day[d]
                break
    if ref_yes is None:
        ref_yes = 0.5

    ref_days = 7
    ref_p90 = base_target
    for d in all_days:
        if d in gains_by_day and d >= 7:
            ref_days = d
            ref_p90 = gains_by_day[d]["p90"]
            break

    logger.info(f"Theta: target={base_target:.0%}, ref_yes={ref_yes:.3f}, ref_days={ref_days}")

    days_dict = {}
    min_days_seen = min(day_buckets.keys())
    max_days_seen = max(day_buckets.keys())

    for days in range(0, max_days_seen + 1):
        if days <= 0:
            days_dict[str(days)] = {"profit_mult": 0.0, "price_mult": 0.0, "source": "zero"}
            continue
        if days >= ref_days:
            days_dict[str(days)] = {"profit_mult": 1.0, "price_mult": 1.0, "source": "above_ref"}
            continue

        if days in gains_by_day and base_target > 0:
            pm = max(0.0, min(1.0, gains_by_day[days]["p90"] / base_target))
            profit_source = "measured"
        else:
            pm = (days / 7.0) ** 0.5 if days < 7 else 1.0
            profit_source = "extrapolated"

        if days in yes_by_day and ref_yes > 0:
            prm = max(0.0, min(1.0, yes_by_day[days] / ref_yes))
            price_source = "measured"
        else:
            prm = (days / 7.0) ** 0.3 if days < 7 else 1.0
            price_source = "extrapolated"

        entry = {
            "profit_mult": round(pm, 4),
            "price_mult": round(prm, 4),
            "source": f"profit:{profit_source},price:{price_source}",
        }
        if days in gains_by_day:
            entry["p90_gain"] = round(gains_by_day[days]["p90"], 4)
        if days in yes_by_day:
            entry["avg_yes"] = round(yes_by_day[days], 4)
        days_dict[str(days)] = entry

    # Log theta summary
    logger.info("Theta results:")
    for d in sorted(days_dict.keys(), key=int, reverse=True):
        entry = days_dict[d]
        day_num = int(d)
        if day_num < min_days_seen - 2 or day_num > max_days_seen:
            continue
        extras = ""
        if "p90_gain" in entry:
            extras += f" p90={entry['p90_gain']:+.1%}"
        if "avg_yes" in entry:
            extras += f" YES={entry['avg_yes']:.3f}"
        logger.info(f"  Day {day_num:>3}: pm={entry['profit_mult']:.3f} prm={entry['price_mult']:.3f}{extras}")

    # ══════════════════════════════════════════
    #  SAVE
    # ══════════════════════════════════════════

    calibration = {
        "calibrated_at": now.isoformat(),
        "ref_days": ref_days,
        "ref_yes_price": round(ref_yes, 4),
        "ref_p90_gain": round(ref_p90, 4),
        "data_points": len(yes_data),
        "correlation": correlation,
        "chart": chart_data,
        "days": days_dict,
    }

    tmp = CALIBRATION_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(calibration, f, indent=2)
    os.replace(tmp, CALIBRATION_FILE)

    logger.info(f"Saved: correlation, {len(chart_data)} chart pts, {len(days_dict)} day entries")
    return True


if __name__ == "__main__":
    calibrate()
