"""
Daily strategy auto-review (v2).

Analyzes accumulated data from 97_scanner and 98_sure_bot,
detects risks, applies protective adjustments, and generates
actionable recommendations with full transparency (assumptions, risks, pros/cons).

Run daily (or on demand): py -3.12 strategy_review.py

Blocks:
  1. Bot fact stats: P&L, breakdowns by category / type / end_date / price bucket
  2. Scanner market supply: filtered by bot conditions, resolve speed, capital efficiency
  3. Recommendations: bet_size, end_date, MAX_NEG_RISK_FROZEN, filters, sort
  4. Output: full report to _analytics/, summary to Telegram

Auto-actions (protective):
  - PAUSE bot if 5+ losses in 7 days or loss rate critical
  - ALERT on category win rate drops
"""
import json
import sys
import os
import re
import math
import logging
from datetime import datetime, timezone, timedelta
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# === Setup logging ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("strategy_review.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("strategy_review")

# === Load bot modules ===
import tracker
import telegram_notify as tg
import config

# === Paths ===
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
SCANNER_DIR = os.path.join(BOT_DIR, "..", "97_scanner")
SCANNER_DATA = os.path.join(SCANNER_DIR, "scanner_data.json")
REVIEW_FILE = os.path.join(BOT_DIR, "strategy_review.json")
PAUSE_FILE = os.path.join(BOT_DIR, "PAUSE")
ANALYTICS_DIR = os.path.join(BOT_DIR, "_analytics")

# === Thresholds ===
LOSS_RATE_WARN = 0.005
LOSS_RATE_CRITICAL = 0.010
CATEGORY_WIN_RATE_WARN = 0.99
CATEGORY_WIN_RATE_BLOCK = 0.97
MIN_CATEGORY_SAMPLE = 50
MAX_MEDIAN_RESOLVE_H = 48


# =====================================================================
# DATA LOADING
# =====================================================================
def load_scanner_data():
    """Load scanner_data.json."""
    logger.info("Loading scanner_data.json...")
    with open(SCANNER_DATA, "r", encoding="utf-8") as f:
        return json.load(f)


def load_previous_review():
    if os.path.exists(REVIEW_FILE):
        with open(REVIEW_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_review(review):
    with open(REVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(review, f, indent=2, ensure_ascii=False, default=str)


def _parse_dt(s):
    """Parse ISO datetime string to UTC datetime."""
    if not s:
        return None
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None


# =====================================================================
# BLOCK 1: BOT FACT STATS
# =====================================================================

def block1_bot_stats(bot_data):
    """Compute comprehensive bot statistics with breakdowns."""
    now = datetime.now(timezone.utc)
    positions = bot_data.get("positions", {})
    stats = bot_data.get("stats", {})

    # Classify positions
    open_p = []
    won_p = []
    lost_p = []
    selling_p = []
    all_resolved = []

    for key, p in positions.items():
        status = p.get("status", "")
        if status == "open":
            open_p.append(p)
        elif status == "won":
            won_p.append(p)
            all_resolved.append(p)
        elif status == "lost":
            lost_p.append(p)
            all_resolved.append(p)
        elif status in ("selling", "sold"):
            selling_p.append(p)

    # --- Overall stats ---
    total_resolved = len(won_p) + len(lost_p)
    win_rate = len(won_p) / total_resolved if total_resolved > 0 else 0
    total_pnl = stats.get("total_pnl", 0)
    balance = stats.get("current_balance", 0)
    open_cost = sum(p.get("cost_usd", 0) for p in open_p)
    selling_cost = sum(p.get("cost_usd", 0) for p in selling_p)
    capital = balance + open_cost + selling_cost

    # --- Unrealized P&L ---
    # Open positions: expected payout = shares * $1, cost = cost_usd
    # Unrealized = (shares - cost) for each open position
    unrealized_pnl = sum(
        p.get("size_shares", 0) - p.get("cost_usd", 0)
        for p in open_p
    )

    # --- 7-day / 30-day windows ---
    windows = {}
    for label, days in [("7d", 7), ("30d", 30), ("all", 9999)]:
        cutoff = now - timedelta(days=days)
        w_won = w_lost = 0
        w_pnl = 0.0
        w_cost = 0.0
        for p in all_resolved:
            ra = _parse_dt(p.get("resolved_at", ""))
            if ra and ra < cutoff:
                continue
            if p["status"] == "won":
                w_won += 1
            else:
                w_lost += 1
            w_pnl += p.get("pnl", 0)
            w_cost += p.get("cost_usd", 0)
        windows[label] = {
            "wins": w_won, "losses": w_lost, "total": w_won + w_lost,
            "loss_rate": w_lost / (w_won + w_lost) if (w_won + w_lost) > 0 else 0,
            "pnl": w_pnl, "cost": w_cost,
        }

    # --- Breakdown by neg_risk ---
    type_breakdown = {"regular": _empty_breakdown(), "neg_risk": _empty_breakdown()}
    for p in all_resolved:
        key = "neg_risk" if p.get("neg_risk") else "regular"
        type_breakdown[key]["total"] += 1
        type_breakdown[key]["cost"] += p.get("cost_usd", 0)
        type_breakdown[key]["pnl"] += p.get("pnl", 0)
        if p["status"] == "won":
            type_breakdown[key]["wins"] += 1
        else:
            type_breakdown[key]["losses"] += 1

    for key in type_breakdown:
        bd = type_breakdown[key]
        bd["win_rate"] = bd["wins"] / bd["total"] if bd["total"] > 0 else 0

    # --- Breakdown by neg_risk for open positions ---
    open_by_type = {"regular": {"count": 0, "cost": 0}, "neg_risk": {"count": 0, "cost": 0}}
    for p in open_p:
        key = "neg_risk" if p.get("neg_risk") else "regular"
        open_by_type[key]["count"] += 1
        open_by_type[key]["cost"] += p.get("cost_usd", 0)

    # --- Breakdown by category ---
    cat_breakdown = defaultdict(lambda: _empty_breakdown())
    for p in all_resolved:
        cat = p.get("category", "other") or "other"
        cat_breakdown[cat]["total"] += 1
        cat_breakdown[cat]["cost"] += p.get("cost_usd", 0)
        cat_breakdown[cat]["pnl"] += p.get("pnl", 0)
        if p["status"] == "won":
            cat_breakdown[cat]["wins"] += 1
        else:
            cat_breakdown[cat]["losses"] += 1
    for cat in cat_breakdown:
        bd = cat_breakdown[cat]
        bd["win_rate"] = bd["wins"] / bd["total"] if bd["total"] > 0 else 0

    # --- Resolve time breakdown by type ---
    resolve_by_type = {"regular": [], "neg_risk": []}
    for p in all_resolved:
        ts = _parse_dt(p.get("timestamp", ""))
        ra = _parse_dt(p.get("resolved_at", ""))
        if ts and ra:
            h = (ra - ts).total_seconds() / 3600
            if h > 0:
                key = "neg_risk" if p.get("neg_risk") else "regular"
                resolve_by_type[key].append(h)

    resolve_stats = {}
    for key, hours in resolve_by_type.items():
        if hours:
            hours.sort()
            n = len(hours)
            resolve_stats[key] = {
                "median_h": hours[n // 2],
                "avg_h": sum(hours) / n,
                "p90_h": hours[int(n * 0.9)] if n >= 10 else hours[-1],
                "count": n,
            }
        else:
            resolve_stats[key] = {"median_h": 0, "avg_h": 0, "p90_h": 0, "count": 0}

    # --- Open position age ---
    open_ages = []
    old_positions = []
    for p in open_p:
        ts = _parse_dt(p.get("timestamp", ""))
        if ts:
            age_h = (now - ts).total_seconds() / 3600
            open_ages.append(age_h)
            if age_h > 72:
                old_positions.append({
                    "title": p.get("title", "")[:60],
                    "age_h": age_h,
                    "cost": p.get("cost_usd", 0),
                    "neg_risk": p.get("neg_risk", False),
                })

    # --- Fill rate (approximate: positions that were removed = unfilled) ---
    # Total bets ever placed vs positions that exist
    total_bets_ever = stats.get("total_bets", 0)
    existing_positions = len(positions)
    # Removed positions = total_bets - existing (removed = unfilled/cancelled)
    # This is approximate since remove_position decrements total_bets
    # Better: count by status
    fill_rate = existing_positions / total_bets_ever if total_bets_ever > 0 else 1.0

    # --- Price bucket breakdown ---
    price_buckets = [
        ("96.0-97.5c", 0.960, 0.975),
        ("97.5-98.0c", 0.975, 0.980),
        ("98.0-98.5c", 0.980, 0.985),
        ("98.5-99.0c", 0.985, 0.990),
        ("99.0-99.5c", 0.990, 0.995),
    ]
    bucket_stats = {}
    for name, lo, hi in price_buckets:
        b_won = [p for p in won_p if lo <= p.get("entry_price", 0) < hi]
        b_lost = [p for p in lost_p if lo <= p.get("entry_price", 0) < hi]
        total = len(b_won) + len(b_lost)
        pnl = sum(p.get("pnl", 0) for p in b_won) + sum(p.get("pnl", 0) for p in b_lost)
        bucket_stats[name] = {
            "wins": len(b_won), "losses": len(b_lost), "total": total,
            "pnl": pnl,
            "win_rate": len(b_won) / total if total > 0 else 0,
        }

    return {
        "total_resolved": total_resolved,
        "win_rate": win_rate,
        "total_pnl": total_pnl,
        "unrealized_pnl": unrealized_pnl,
        "balance": balance,
        "open_cost": open_cost,
        "selling_cost": selling_cost,
        "capital": capital,
        "utilization": (open_cost + selling_cost) / capital if capital > 0 else 0,
        "windows": windows,
        "type_breakdown": type_breakdown,
        "open_by_type": open_by_type,
        "cat_breakdown": dict(cat_breakdown),
        "resolve_by_type": resolve_stats,
        "open_count": len(open_p),
        "selling_count": len(selling_p),
        "median_open_age_h": sorted(open_ages)[len(open_ages) // 2] if open_ages else 0,
        "old_positions_72h": old_positions,
        "fill_rate": fill_rate,
        "price_buckets": bucket_stats,
    }


def _empty_breakdown():
    return {"wins": 0, "losses": 0, "total": 0, "cost": 0.0, "pnl": 0.0, "win_rate": 0.0}


# =====================================================================
# BLOCK 2: SCANNER MARKET SUPPLY (filtered by bot conditions)
# =====================================================================

def block2_scanner_supply(sc_data):
    """Analyze resolved scanner markets filtered to match bot's actual conditions."""
    now = datetime.now(timezone.utc)
    markets = sc_data.get("markets", {})

    # All resolved markets
    resolved = {}
    for mid, m in markets.items():
        res = m.get("resolution")
        if not res or not isinstance(res, dict) or not res.get("closed"):
            continue
        resolved[mid] = m

    total_resolved = len(resolved)

    # Filter to bot-eligible: price >= 97.5% (or 96% politics)
    eligible = {}
    for mid, m in resolved.items():
        max_p = m.get("max_price_seen", 0) or 0
        cat = (m.get("category", "") or "").lower()
        if cat in ("politics", "geopolitics"):
            if max_p >= 0.96:
                eligible[mid] = m
        else:
            if max_p >= 0.975:
                eligible[mid] = m

    # Win/loss for eligible
    wins = losses = unknown = 0
    for m in eligible.values():
        ho = m.get("high_outcome", "")
        w = m.get("resolution", {}).get("winner", "")
        if ho and w:
            if ho == w:
                wins += 1
            else:
                losses += 1
        else:
            unknown += 1

    # --- By category ---
    cat_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "total": 0, "resolve_hours": []})
    for m in eligible.values():
        cat = (m.get("category", "other") or "other").lower()
        ho = m.get("high_outcome", "")
        w = m.get("resolution", {}).get("winner", "")
        cat_stats[cat]["total"] += 1
        if ho and w:
            if ho == w:
                cat_stats[cat]["wins"] += 1
            else:
                cat_stats[cat]["losses"] += 1
        rt = m.get("resolve_time_hours")
        if rt is not None:
            cat_stats[cat]["resolve_hours"].append(rt)

    cat_summary = {}
    for cat, s in cat_stats.items():
        rh = sorted(s["resolve_hours"])
        n = len(rh)
        cat_summary[cat] = {
            "wins": s["wins"], "losses": s["losses"], "total": s["total"],
            "win_rate": s["wins"] / s["total"] if s["total"] > 0 else 0,
            "loss_rate": s["losses"] / s["total"] if s["total"] > 0 else 0,
            "median_resolve_h": rh[n // 2] if n > 0 else 0,
            "avg_resolve_h": sum(rh) / n if n > 0 else 0,
        }

    # --- By neg_risk ---
    type_stats = {"regular": {"total": 0, "wins": 0, "losses": 0, "rh": []},
                  "neg_risk": {"total": 0, "wins": 0, "losses": 0, "rh": []}}
    for m in eligible.values():
        key = "neg_risk" if m.get("neg_risk") else "regular"
        type_stats[key]["total"] += 1
        ho = m.get("high_outcome", "")
        w = m.get("resolution", {}).get("winner", "")
        if ho and w:
            if ho == w:
                type_stats[key]["wins"] += 1
            else:
                type_stats[key]["losses"] += 1
        rt = m.get("resolve_time_hours")
        if rt is not None:
            type_stats[key]["rh"].append(rt)

    type_summary = {}
    for key, s in type_stats.items():
        rh = sorted(s["rh"])
        n = len(rh)
        type_summary[key] = {
            "total": s["total"], "wins": s["wins"], "losses": s["losses"],
            "win_rate": s["wins"] / s["total"] if s["total"] > 0 else 0,
            "median_resolve_h": rh[n // 2] if n > 0 else 0,
            "p90_resolve_h": rh[int(n * 0.9)] if n >= 10 else (rh[-1] if rh else 0),
        }

    # --- Resolve time by end_date bucket ---
    ed_buckets = {"0-1d": [], "1-2d": [], "2-3d": [], "3-5d": [], "5d+": [], "no_end_date": []}
    for m in eligible.values():
        rt = m.get("resolve_time_hours")
        if rt is None:
            continue
        ed = m.get("end_date", "")
        fs = m.get("first_seen", "")
        if not ed or not fs:
            ed_buckets["no_end_date"].append(rt)
            continue
        try:
            ed_dt = _parse_dt(ed)
            fs_dt = _parse_dt(fs)
            if ed_dt and fs_dt:
                days_to_end = (ed_dt - fs_dt).total_seconds() / 86400
                if days_to_end <= 1:
                    ed_buckets["0-1d"].append(rt)
                elif days_to_end <= 2:
                    ed_buckets["1-2d"].append(rt)
                elif days_to_end <= 3:
                    ed_buckets["2-3d"].append(rt)
                elif days_to_end <= 5:
                    ed_buckets["3-5d"].append(rt)
                else:
                    ed_buckets["5d+"].append(rt)
            else:
                ed_buckets["no_end_date"].append(rt)
        except Exception:
            ed_buckets["no_end_date"].append(rt)

    ed_summary = {}
    for bucket, hours in ed_buckets.items():
        if hours:
            hours.sort()
            n = len(hours)
            ed_summary[bucket] = {
                "count": n,
                "median_h": hours[n // 2],
                "avg_h": sum(hours) / n,
                "p90_h": hours[int(n * 0.9)] if n >= 10 else hours[-1],
            }
        else:
            ed_summary[bucket] = {"count": 0, "median_h": 0, "avg_h": 0, "p90_h": 0}

    # --- Weekly loss rate trend ---
    weekly = defaultdict(lambda: {"wins": 0, "losses": 0})
    for m in eligible.values():
        closed_time = m.get("resolution", {}).get("closed_time", "")
        ct = _parse_dt(closed_time)
        if not ct:
            continue
        week_key = ct.strftime("%Y-W%W")
        ho = m.get("high_outcome", "")
        w = m.get("resolution", {}).get("winner", "")
        if not ho or not w:
            continue
        if ho == w:
            weekly[week_key]["wins"] += 1
        else:
            weekly[week_key]["losses"] += 1

    loss_trend = []
    for week, s in sorted(weekly.items()):
        total = s["wins"] + s["losses"]
        if total < 10:
            continue
        loss_trend.append({
            "week": week, "wins": s["wins"], "losses": s["losses"],
            "total": total, "loss_rate": s["losses"] / total,
        })

    # --- Loss pattern keywords ---
    loss_words = Counter()
    loss_questions = []
    for m in eligible.values():
        ho = m.get("high_outcome", "")
        w = m.get("resolution", {}).get("winner", "")
        if not ho or not w or ho == w:
            continue
        q = m.get("question", "")
        loss_questions.append(q)
        stop = {"the", "will", "and", "for", "this", "that", "with", "from",
                "have", "been", "are", "was", "were", "not", "but", "what",
                "who", "how", "when", "where", "does", "win", "next"}
        for word in re.findall(r'\b[a-zA-Z]{3,}\b', q.lower()):
            if word not in stop:
                loss_words[word] += 1

    # --- Capital efficiency estimate ---
    # For each type, compute: profit per $1 invested per hour frozen
    # profit per bet = (1 - avg_price) * avg_shares
    # time frozen = median resolve hours
    # capital_efficiency = profit_per_dollar / time_frozen_hours
    # We approximate from scanner: avg ROI per bet * turns per day
    all_rh = [m.get("resolve_time_hours", 0) for m in eligible.values()
              if m.get("resolve_time_hours") is not None]
    overall_median_h = sorted(all_rh)[len(all_rh) // 2] if all_rh else 9.2

    return {
        "total_resolved": total_resolved,
        "eligible": len(eligible),
        "wins": wins,
        "losses": losses,
        "unknown": unknown,
        "win_rate": wins / (wins + losses) if (wins + losses) > 0 else 0,
        "loss_rate": losses / (wins + losses) if (wins + losses) > 0 else 0,
        "cat_summary": cat_summary,
        "type_summary": type_summary,
        "ed_summary": ed_summary,
        "loss_trend": loss_trend,
        "loss_questions": loss_questions[:20],
        "suspicious_keywords": dict(Counter({w: c for w, c in loss_words.items() if c >= 3}).most_common(15)),
        "overall_median_resolve_h": overall_median_h,
    }


# =====================================================================
# BLOCK 3: RECOMMENDATIONS
# =====================================================================

def block3_recommendations(bot_stats, scanner_stats, bot_data):
    """Generate specific parameter recommendations with assumptions and risks."""
    recs = []

    # Current config values
    bet_reg = config.BET_SIZE_REGULAR
    bet_neg = config.BET_SIZE_NEG_RISK
    max_ed_reg = config.MAX_END_DATE_REGULAR
    max_ed_neg = config.MAX_END_DATE_NEG_RISK
    max_neg_frozen = config.MAX_NEG_RISK_FROZEN
    capital = bot_stats["capital"]

    # --- 1. Bet size recommendation ---
    # Based on capital / diversification target
    # Optimal: enough slots for good throughput without over-concentrating
    reg_resolve_h = bot_stats["resolve_by_type"]["regular"]["median_h"] or 5.0
    neg_resolve_h = bot_stats["resolve_by_type"]["neg_risk"]["median_h"] or 15.0

    # Regular: how many bets can we run simultaneously?
    reg_slots = capital * 0.7 / bet_reg  # 70% of capital for regular
    reg_turns_day = 24 / reg_resolve_h
    reg_daily_throughput = reg_slots * reg_turns_day

    # Ideal: 40-60 slots at current capital for good diversification
    ideal_reg_bet = capital * 0.7 / 50
    ideal_reg_bet = max(5, round(ideal_reg_bet / 5) * 5)
    ideal_reg_bet = min(ideal_reg_bet, 50)

    if abs(ideal_reg_bet - bet_reg) >= 5:
        direction = "increase" if ideal_reg_bet > bet_reg else "decrease"
        recs.append({
            "param": "BET_SIZE_REGULAR",
            "current": bet_reg,
            "recommended": ideal_reg_bet,
            "reasoning": (
                f"Capital ${capital:.0f} with {reg_slots:.0f} reg slots. "
                f"Target 50 slots for diversification -> ${ideal_reg_bet:.0f}/bet."
            ),
            "assumption": "Capital stays near current level; resolve time stable",
            "risk": f"If capital drops, fewer bets = less diversification",
            "pros": f"Better {'throughput' if direction == 'decrease' else 'profit per bet'}",
            "cons": f"{'Lower profit per bet' if direction == 'decrease' else 'Less diversification'}",
        })

    # --- 2. End date limits ---
    # Compare capital efficiency for different end_date windows
    ed = scanner_stats.get("ed_summary", {})
    for label, param, current_max, market_type in [
        ("regular", "MAX_END_DATE_REGULAR", max_ed_reg, "regular"),
        ("neg_risk", "MAX_END_DATE_NEG_RISK", max_ed_neg, "neg_risk"),
    ]:
        # Check if tighter or looser would help
        # Efficiency = 1 / median_resolve_hours (higher = better turnover)
        tight_bucket = "0-1d"
        current_buckets = []
        for b in ["0-1d", "1-2d", "2-3d", "3-5d", "5d+"]:
            days = {"0-1d": 1, "1-2d": 2, "2-3d": 3, "3-5d": 5, "5d+": 7}[b]
            if days <= current_max:
                current_buckets.append(b)

        # No recommendation if current looks fine
        # But note if loosening would add supply
        next_bucket = None
        for b in ["0-1d", "1-2d", "2-3d", "3-5d", "5d+"]:
            days = {"0-1d": 1, "1-2d": 2, "2-3d": 3, "3-5d": 5, "5d+": 7}[b]
            if days == current_max + 1 or (current_max < 5 and days == 5 and current_max >= 3):
                next_bucket = b
                break

        if next_bucket and ed.get(next_bucket, {}).get("count", 0) > 20:
            next_med = ed[next_bucket]["median_h"]
            curr_med = ed.get(current_buckets[-1] if current_buckets else "0-1d", {}).get("median_h", 5)
            recs.append({
                "param": param,
                "current": current_max,
                "recommended": current_max,  # keep current (just inform)
                "reasoning": (
                    f"Loosening {label} to include {next_bucket} would add {ed[next_bucket]['count']} "
                    f"markets but median resolve {next_med:.1f}h vs {curr_med:.1f}h. "
                    f"Capital frozen {next_med/curr_med:.1f}x longer."
                ),
                "assumption": "Resolve times from scanner are representative",
                "risk": "Slower turnover = less capital for fast markets",
                "pros": f"More supply (+{ed[next_bucket]['count']} markets)",
                "cons": f"Slower resolve ({next_med:.1f}h median)",
            })

    # --- 3. MAX_NEG_RISK_FROZEN ---
    neg_open = bot_stats["open_by_type"]["neg_risk"]
    reg_open = bot_stats["open_by_type"]["regular"]
    neg_frozen = neg_open["cost"]
    neg_type = scanner_stats.get("type_summary", {}).get("neg_risk", {})
    neg_med_h = neg_type.get("median_resolve_h", 15)
    reg_type = scanner_stats.get("type_summary", {}).get("regular", {})
    reg_med_h = reg_type.get("median_resolve_h", 5)

    # neg_risk efficiency relative to regular
    if neg_med_h > 0 and reg_med_h > 0:
        neg_efficiency_ratio = reg_med_h / neg_med_h  # <1 means neg is slower
    else:
        neg_efficiency_ratio = 0.3

    # Optimal neg cap: proportion of capital matching efficiency ratio
    ideal_neg_cap = capital * neg_efficiency_ratio * 0.5  # halved because slower
    ideal_neg_cap = max(50, round(ideal_neg_cap / 25) * 25)
    ideal_neg_cap = min(ideal_neg_cap, capital * 0.5)

    if abs(ideal_neg_cap - max_neg_frozen) >= 25:
        recs.append({
            "param": "MAX_NEG_RISK_FROZEN",
            "current": max_neg_frozen,
            "recommended": ideal_neg_cap,
            "reasoning": (
                f"Neg_risk resolves {neg_med_h:.1f}h (vs reg {reg_med_h:.1f}h). "
                f"Efficiency ratio {neg_efficiency_ratio:.2f}. "
                f"Currently ${neg_frozen:.0f} frozen in {neg_open['count']} neg positions."
            ),
            "assumption": "Resolve speed difference stays consistent",
            "risk": "If neg_risk markets start resolving faster, cap is too tight",
            "pros": "More capital available for faster-resolving regular markets",
            "cons": "Fewer neg_risk bets = missed opportunities in that segment",
        })

    # --- 4. Sort/prioritization recommendation ---
    # Current: sort by end_date ASC, then price ASC (short first, cheapest first)
    # Check if capital efficiency differs significantly
    if reg_med_h > 0:
        reg_roi_per_h = (1 - 0.985) / reg_med_h  # ~1.5% avg ROI / hours
    else:
        reg_roi_per_h = 0
    if neg_med_h > 0:
        neg_roi_per_h = (1 - 0.985) / neg_med_h
    else:
        neg_roi_per_h = 0

    if reg_roi_per_h > 0 and neg_roi_per_h > 0:
        ratio = reg_roi_per_h / neg_roi_per_h
        if ratio > 2:
            recs.append({
                "param": "SORT_PRIORITY",
                "current": "end_date ASC, price ASC",
                "recommended": "end_date ASC, price ASC (keep current)",
                "reasoning": (
                    f"Regular markets are {ratio:.1f}x more capital-efficient. "
                    f"Current sort (shortest end_date first) naturally favors fast markets."
                ),
                "assumption": "end_date is a reliable proxy for resolve speed",
                "risk": "None — current sort is already optimal for capital efficiency",
                "pros": "Maximizes capital turnover",
                "cons": "May skip higher-ROI slow markets when capital is available",
            })

    # --- 5. Category-specific risks ---
    for cat, cs in scanner_stats.get("cat_summary", {}).items():
        if cs["total"] >= MIN_CATEGORY_SAMPLE and cs["loss_rate"] > 0.005:
            recs.append({
                "param": f"CATEGORY_{cat.upper()}",
                "current": "allowed",
                "recommended": "review" if cs["loss_rate"] < 0.02 else "consider blocking",
                "reasoning": (
                    f"{cat}: {cs['losses']} losses in {cs['total']} markets "
                    f"(loss rate {cs['loss_rate']*100:.2f}%). "
                    f"Median resolve: {cs['median_resolve_h']:.1f}h."
                ),
                "assumption": "Scanner loss rate reflects bot's actual risk",
                "risk": "Blocking may reduce supply without meaningful safety gain",
                "pros": f"Avoid ~{cs['loss_rate']*100:.2f}% loss rate in this category",
                "cons": f"Lose {cs['total']} market supply",
            })

    return recs


# =====================================================================
# PROTECTIVE ACTIONS (unchanged from v1)
# =====================================================================

def check_protective_actions(bot_stats):
    """Check for critical conditions and take automatic protective actions."""
    now = datetime.now(timezone.utc)
    alerts = []
    warnings = []
    auto_actions = []

    w7 = bot_stats["windows"]["7d"]
    lr_7d = w7["loss_rate"]
    lr_7d_losses = w7["losses"]
    lr_7d_total = w7["total"]

    # Critical: 5+ losses in 7 days
    if lr_7d_losses >= 5:
        alerts.append(
            f"HIGH LOSSES: {lr_7d_losses} losses in 7 days "
            f"({lr_7d_total} bets, {lr_7d*100:.2f}%)"
        )
        if not os.path.exists(PAUSE_FILE):
            with open(PAUSE_FILE, "w") as f:
                f.write(f"Auto-paused by strategy_review at {now.isoformat()}\n"
                        f"Reason: {lr_7d_losses} losses in 7 days\n")
            auto_actions.append("BOT PAUSED: too many losses")

    elif lr_7d_total >= 200 and lr_7d >= LOSS_RATE_CRITICAL:
        alerts.append(
            f"CRITICAL: 7-day loss rate {lr_7d*100:.2f}% "
            f"({lr_7d_losses} losses / {lr_7d_total} bets)"
        )
        if not os.path.exists(PAUSE_FILE):
            with open(PAUSE_FILE, "w") as f:
                f.write(f"Auto-paused by strategy_review at {now.isoformat()}\n"
                        f"Reason: 7-day loss rate {lr_7d*100:.2f}%\n")
            auto_actions.append("BOT PAUSED: loss rate critical")

    elif lr_7d_losses >= 3:
        warnings.append(
            f"3+ losses in 7 days: {lr_7d_losses} / {lr_7d_total} bets ({lr_7d*100:.2f}%)"
        )

    # Old positions
    if bot_stats["old_positions_72h"]:
        old_count = len(bot_stats["old_positions_72h"])
        old_cost = sum(p["cost"] for p in bot_stats["old_positions_72h"])
        warnings.append(f"{old_count} positions > 72h (${old_cost:.2f} frozen)")

    # Resolve time warning
    for t, rs in bot_stats["resolve_by_type"].items():
        if rs["count"] > 5 and rs["median_h"] > MAX_MEDIAN_RESOLVE_H:
            warnings.append(f"{t} median resolve {rs['median_h']:.0f}h > {MAX_MEDIAN_RESOLVE_H}h")

    return alerts, warnings, auto_actions


# =====================================================================
# BLOCK 4: OUTPUT — Report file + Telegram
# =====================================================================

def generate_full_report(bot_stats, scanner_stats, recs, alerts, warnings, auto_actions):
    """Generate full markdown report for _analytics/ folder."""
    now = datetime.now(timezone.utc)
    lines = []
    lines.append(f"# Daily Strategy Review — {now.strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")

    # --- Auto-actions ---
    if auto_actions:
        lines.append("## AUTO-ACTIONS TAKEN")
        for a in auto_actions:
            lines.append(f"- **{a}**")
        lines.append("")

    # --- Alerts ---
    if alerts:
        lines.append("## ALERTS")
        for a in alerts:
            lines.append(f"- {a}")
        lines.append("")

    # --- Warnings ---
    if warnings:
        lines.append("## WARNINGS")
        for w in warnings:
            lines.append(f"- {w}")
        lines.append("")

    # === BLOCK 1: Bot Stats ===
    lines.append("## 1. Bot Performance")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Balance | ${bot_stats['balance']:.2f} |")
    lines.append(f"| Open positions | {bot_stats['open_count']} (${bot_stats['open_cost']:.2f} frozen) |")
    lines.append(f"| Selling | {bot_stats['selling_count']} (${bot_stats['selling_cost']:.2f}) |")
    lines.append(f"| Capital (total) | ${bot_stats['capital']:.2f} |")
    lines.append(f"| Utilization | {bot_stats['utilization']*100:.0f}% |")
    lines.append(f"| Realized PnL | ${bot_stats['total_pnl']:+.2f} |")
    lines.append(f"| Unrealized PnL | ${bot_stats['unrealized_pnl']:+.2f} |")
    lines.append(f"| Resolved | {bot_stats['total_resolved']} (WR: {bot_stats['win_rate']*100:.1f}%) |")
    lines.append("")

    # Rolling windows
    lines.append("### Rolling Windows")
    lines.append("| Period | W/L | Loss Rate | PnL |")
    lines.append("|--------|-----|-----------|-----|")
    for label in ["7d", "30d", "all"]:
        w = bot_stats["windows"][label]
        lines.append(f"| {label} | {w['wins']}/{w['losses']} | {w['loss_rate']*100:.2f}% | ${w['pnl']:+.2f} |")
    lines.append("")

    # Type breakdown
    lines.append("### By Market Type (resolved)")
    lines.append("| Type | W/L | WR | PnL | Cost |")
    lines.append("|------|-----|----|-----|------|")
    for t in ["regular", "neg_risk"]:
        bd = bot_stats["type_breakdown"][t]
        lines.append(f"| {t} | {bd['wins']}/{bd['losses']} | {bd['win_rate']*100:.1f}% | ${bd['pnl']:+.2f} | ${bd['cost']:.2f} |")
    lines.append("")

    # Open by type
    lines.append("### Open Positions by Type")
    lines.append("| Type | Count | Frozen |")
    lines.append("|------|-------|--------|")
    for t in ["regular", "neg_risk"]:
        ot = bot_stats["open_by_type"][t]
        lines.append(f"| {t} | {ot['count']} | ${ot['cost']:.2f} |")
    lines.append("")

    # Resolve times by type
    lines.append("### Resolve Times (bot positions)")
    lines.append("| Type | Median | Avg | P90 | Count |")
    lines.append("|------|--------|-----|-----|-------|")
    for t in ["regular", "neg_risk"]:
        rs = bot_stats["resolve_by_type"][t]
        lines.append(f"| {t} | {rs['median_h']:.1f}h | {rs['avg_h']:.1f}h | {rs['p90_h']:.1f}h | {rs['count']} |")
    lines.append("")

    # Category breakdown (if data exists)
    if bot_stats["cat_breakdown"]:
        lines.append("### By Category (bot resolved)")
        lines.append("| Category | W/L | WR | PnL |")
        lines.append("|----------|-----|----|-----|")
        for cat, bd in sorted(bot_stats["cat_breakdown"].items(), key=lambda x: -x[1]["total"]):
            if bd["total"] > 0:
                lines.append(f"| {cat} | {bd['wins']}/{bd['losses']} | {bd['win_rate']*100:.1f}% | ${bd['pnl']:+.2f} |")
        lines.append("")

    # Price buckets
    lines.append("### By Price Bucket")
    lines.append("| Bucket | W/L | WR | PnL |")
    lines.append("|--------|-----|----|-----|")
    for name, bs in bot_stats["price_buckets"].items():
        if bs["total"] > 0:
            lines.append(f"| {name} | {bs['wins']}/{bs['losses']} | {bs['win_rate']*100:.1f}% | ${bs['pnl']:+.2f} |")
    lines.append("")

    # Old positions
    if bot_stats["old_positions_72h"]:
        lines.append("### Stuck Positions (>72h)")
        for p in bot_stats["old_positions_72h"]:
            lines.append(f"- {p['title']} | {p['age_h']:.0f}h | ${p['cost']:.2f} | neg={p['neg_risk']}")
        lines.append("")

    # === BLOCK 2: Scanner Supply ===
    lines.append("## 2. Scanner Market Supply")
    lines.append("")
    lines.append(f"Total resolved in scanner: {scanner_stats['total_resolved']}")
    lines.append(f"Bot-eligible (price threshold): {scanner_stats['eligible']}")
    lines.append(f"Win/Loss: {scanner_stats['wins']}/{scanner_stats['losses']} "
                 f"({scanner_stats['win_rate']*100:.2f}% WR)")
    lines.append(f"Overall median resolve: {scanner_stats['overall_median_resolve_h']:.1f}h")
    lines.append("")

    # By type
    lines.append("### By Market Type (scanner)")
    lines.append("| Type | Total | W/L | WR | Median Resolve | P90 |")
    lines.append("|------|-------|-----|----|----------------|-----|")
    for t in ["regular", "neg_risk"]:
        ts = scanner_stats["type_summary"].get(t, {})
        lines.append(
            f"| {t} | {ts.get('total', 0)} | {ts.get('wins', 0)}/{ts.get('losses', 0)} | "
            f"{ts.get('win_rate', 0)*100:.2f}% | {ts.get('median_resolve_h', 0):.1f}h | "
            f"{ts.get('p90_resolve_h', 0):.1f}h |")
    lines.append("")

    # By end_date bucket
    lines.append("### Resolve Time by End-Date Bucket (scanner)")
    lines.append("| Bucket | Count | Median | Avg | P90 |")
    lines.append("|--------|-------|--------|-----|-----|")
    for bucket in ["0-1d", "1-2d", "2-3d", "3-5d", "5d+", "no_end_date"]:
        es = scanner_stats["ed_summary"].get(bucket, {})
        if es.get("count", 0) > 0:
            lines.append(f"| {bucket} | {es['count']} | {es['median_h']:.1f}h | {es['avg_h']:.1f}h | {es['p90_h']:.1f}h |")
    lines.append("")

    # By category
    lines.append("### By Category (scanner, bot-eligible)")
    lines.append("| Category | Total | Losses | Loss Rate | Median Resolve |")
    lines.append("|----------|-------|--------|-----------|----------------|")
    for cat, cs in sorted(scanner_stats["cat_summary"].items(), key=lambda x: -x[1]["total"]):
        if cs["total"] >= 10:
            lines.append(
                f"| {cat} | {cs['total']} | {cs['losses']} | "
                f"{cs['loss_rate']*100:.2f}% | {cs['median_resolve_h']:.1f}h |")
    lines.append("")

    # Loss trend
    if scanner_stats["loss_trend"]:
        lines.append("### Weekly Loss Rate Trend")
        lines.append("| Week | W/L | Total | Loss Rate |")
        lines.append("|------|-----|-------|-----------|")
        for w in scanner_stats["loss_trend"][-8:]:
            lines.append(f"| {w['week']} | {w['wins']}/{w['losses']} | {w['total']} | {w['loss_rate']*100:.3f}% |")
        lines.append("")

    # Suspicious keywords
    if scanner_stats["suspicious_keywords"]:
        lines.append("### Suspicious Keywords (appear in 3+ losing markets)")
        for kw, count in scanner_stats["suspicious_keywords"].items():
            lines.append(f"- `{kw}`: {count} losses")
        lines.append("")

    # === BLOCK 3: Recommendations ===
    lines.append("## 3. Recommendations")
    lines.append("")
    if not recs:
        lines.append("No parameter changes recommended at this time.")
    else:
        for i, r in enumerate(recs, 1):
            lines.append(f"### {i}. {r['param']}")
            lines.append(f"- **Current**: {r['current']}")
            lines.append(f"- **Recommended**: {r['recommended']}")
            lines.append(f"- **Reasoning**: {r['reasoning']}")
            lines.append(f"- **Assumption**: {r['assumption']}")
            lines.append(f"- **Risk**: {r['risk']}")
            lines.append(f"- **Pros**: {r['pros']}")
            lines.append(f"- **Cons**: {r['cons']}")
            lines.append("")

    # === Config snapshot ===
    lines.append("## 4. Current Config Snapshot")
    lines.append(f"- BET_SIZE_REGULAR: ${config.BET_SIZE_REGULAR:.2f}")
    lines.append(f"- BET_SIZE_NEG_RISK: ${config.BET_SIZE_NEG_RISK:.2f}")
    lines.append(f"- MAX_END_DATE_REGULAR: {config.MAX_END_DATE_REGULAR}d")
    lines.append(f"- MAX_END_DATE_NEG_RISK: {config.MAX_END_DATE_NEG_RISK}d")
    lines.append(f"- MAX_NEG_RISK_FROZEN: ${config.MAX_NEG_RISK_FROZEN:.0f}")
    lines.append(f"- PRICE_THRESHOLD: {config.PRICE_THRESHOLD}")
    lines.append(f"- MAX_PRICE: {config.MAX_PRICE}")
    lines.append(f"- SCAN_INTERVAL: {config.SCAN_INTERVAL}s")
    lines.append("")

    return "\n".join(lines)


def generate_telegram_summary(bot_stats, scanner_stats, recs, alerts, warnings, auto_actions):
    """Generate concise Telegram message (HTML, max ~3500 chars)."""
    now = datetime.now(timezone.utc)
    lines = [f"<b>Strategy Review {now.strftime('%Y-%m-%d')}</b>"]

    # Auto-actions
    if auto_actions:
        for a in auto_actions:
            lines.append(f"⚠️ <b>{a}</b>")

    # Alerts
    if alerts:
        for a in alerts:
            lines.append(f"🔴 {a}")

    # Stats block
    w7 = bot_stats["windows"]["7d"]
    w30 = bot_stats["windows"]["30d"]
    lines.append("")
    lines.append(f"<b>Bot Stats</b>")
    lines.append(
        f"Capital: ${bot_stats['capital']:.0f} | "
        f"Balance: ${bot_stats['balance']:.0f} | "
        f"Util: {bot_stats['utilization']*100:.0f}%"
    )
    lines.append(
        f"PnL: ${bot_stats['total_pnl']:+.2f} (unreal: ${bot_stats['unrealized_pnl']:+.2f})"
    )
    lines.append(
        f"7d: {w7['wins']}W/{w7['losses']}L ${w7['pnl']:+.2f} | "
        f"30d: {w30['wins']}W/{w30['losses']}L ${w30['pnl']:+.2f}"
    )

    # Open positions summary
    reg_o = bot_stats["open_by_type"]["regular"]
    neg_o = bot_stats["open_by_type"]["neg_risk"]
    lines.append(
        f"Open: {bot_stats['open_count']} "
        f"(reg {reg_o['count']}/${reg_o['cost']:.0f} | "
        f"neg {neg_o['count']}/${neg_o['cost']:.0f})"
    )

    # Resolve times
    reg_rs = bot_stats["resolve_by_type"]["regular"]
    neg_rs = bot_stats["resolve_by_type"]["neg_risk"]
    if reg_rs["count"] > 0 or neg_rs["count"] > 0:
        lines.append(
            f"Resolve: reg {reg_rs['median_h']:.1f}h | neg {neg_rs['median_h']:.1f}h (median)"
        )

    # Warnings
    if warnings:
        lines.append("")
        for w in warnings[:3]:  # max 3 warnings in TG
            lines.append(f"🟡 {w}")

    # Top recommendations (max 2)
    if recs:
        lines.append("")
        lines.append("<b>Recommendations</b>")
        for r in recs[:2]:
            lines.append(f"💡 {r['param']}: {r['current']} → {r['recommended']}")
            lines.append(f"   {r['reasoning'][:120]}")

    if not alerts and not warnings and not auto_actions:
        lines.append("")
        lines.append("✅ All clear")

    # Trim to ~3500 chars for Telegram limit
    text = "\n".join(lines)
    if len(text) > 3500:
        text = text[:3500] + "\n..."

    return text


# =====================================================================
# MAIN: Run all analyses
# =====================================================================

def run_review():
    """Run full strategy review."""
    now = datetime.now(timezone.utc)
    logger.info("=" * 70)
    logger.info("STRATEGY REVIEW v2: %s", now.strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 70)

    # Load data
    sc_data = load_scanner_data()
    bot_data = tracker.load()

    # Block 1: Bot stats
    logger.info("Block 1: Computing bot stats...")
    bot_stats = block1_bot_stats(bot_data)

    # Block 2: Scanner supply
    logger.info("Block 2: Analyzing scanner supply...")
    scanner_stats = block2_scanner_supply(sc_data)

    # Block 3: Recommendations
    logger.info("Block 3: Generating recommendations...")
    recs = block3_recommendations(bot_stats, scanner_stats, bot_data)

    # Protective checks
    alerts, warnings, auto_actions = check_protective_actions(bot_stats)

    # Block 4: Output

    # --- Log summary ---
    logger.info("Capital: $%.2f | Balance: $%.2f | Open: %d | Util: %.0f%%",
                bot_stats["capital"], bot_stats["balance"],
                bot_stats["open_count"], bot_stats["utilization"] * 100)
    logger.info("PnL: $%+.2f (unrealized: $%+.2f)",
                bot_stats["total_pnl"], bot_stats["unrealized_pnl"])
    logger.info("7d: %dW/%dL | 30d: %dW/%dL",
                bot_stats["windows"]["7d"]["wins"], bot_stats["windows"]["7d"]["losses"],
                bot_stats["windows"]["30d"]["wins"], bot_stats["windows"]["30d"]["losses"])
    logger.info("Scanner eligible: %d (WR %.2f%%, loss rate %.3f%%)",
                scanner_stats["eligible"], scanner_stats["win_rate"] * 100,
                scanner_stats["loss_rate"] * 100)

    if alerts:
        for a in alerts:
            logger.warning("ALERT: %s", a)
    if auto_actions:
        for a in auto_actions:
            logger.warning("AUTO-ACTION: %s", a)
    if recs:
        for r in recs:
            logger.info("REC: %s: %s -> %s", r["param"], r["current"], r["recommended"])

    # --- Save review JSON ---
    review = {
        "timestamp": now.isoformat(),
        "bot_stats": {
            "capital": bot_stats["capital"],
            "balance": bot_stats["balance"],
            "total_pnl": bot_stats["total_pnl"],
            "unrealized_pnl": bot_stats["unrealized_pnl"],
            "open_count": bot_stats["open_count"],
            "utilization": bot_stats["utilization"],
            "win_rate": bot_stats["win_rate"],
            "windows": bot_stats["windows"],
        },
        "scanner_stats": {
            "eligible": scanner_stats["eligible"],
            "win_rate": scanner_stats["win_rate"],
            "loss_rate": scanner_stats["loss_rate"],
            "median_resolve_h": scanner_stats["overall_median_resolve_h"],
        },
        "alerts": alerts,
        "warnings": warnings,
        "recommendations": [{"param": r["param"], "current": r["current"],
                             "recommended": r["recommended"]} for r in recs],
        "auto_actions": auto_actions,
    }
    save_review(review)

    # --- Save full report to _analytics ---
    os.makedirs(ANALYTICS_DIR, exist_ok=True)
    report_filename = f"{now.strftime('%Y-%m-%d')}_daily-review.md"
    report_path = os.path.join(ANALYTICS_DIR, report_filename)
    full_report = generate_full_report(bot_stats, scanner_stats, recs, alerts, warnings, auto_actions)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(full_report)
    logger.info("Full report saved: %s", report_path)

    # --- Send Telegram ---
    tg_text = generate_telegram_summary(bot_stats, scanner_stats, recs, alerts, warnings, auto_actions)
    tg.send(tg_text)
    logger.info("Telegram summary sent")

    return review


if __name__ == "__main__":
    run_review()
