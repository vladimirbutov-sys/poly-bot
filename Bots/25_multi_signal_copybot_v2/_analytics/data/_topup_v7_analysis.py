"""Part 1+2 combined analysis for 2026-04-17 report.

PART 1 — Top-up ratio relaxation
  Walk denizz BUY activity. Classify each as first-entry or top-up.
  For each top-up: bucket by ratio = buy_usd / (prev_invested + buy_usd)
  Tie each bucket to the final resolution of the leg → WR, meanROI, EV/$.

PART 2 — V7 vs V3 vs V1 backtest (and V8 if needed)
  Re-run the same variant harness as _price_risk_backtest.py but include
  V7 (keeps aggressive formula coefficients A=31.75, B=-177.0) and V8
  (aggressive formula + strict PRICE_RISK_TIERS in the expensive zone).

Also runs T1/T2/T3 TOPUP_RATIO_TIERS variants on the V3 baseline to measure
how much PnL we leave on the table with the 3% cutoff.
"""
from __future__ import annotations
import io
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data"
ACT = os.path.join(BASE, "denizz_activity_ALL.json")
RES = os.path.join(BASE, "denizz_resolutions.json")
CLOSED = os.path.join(BASE, "denizz_closed_positions_raw.json")

OUT_TOPUP_BUCKETS = os.path.join(BASE, "topup_v7_ratio_buckets.json")
OUT_TOPUP_BT = os.path.join(BASE, "topup_v7_topup_backtest.json")
OUT_V7_BT = os.path.join(BASE, "topup_v7_formula_backtest.json")

STARTING_BANKROLL = 4000.0
RESERVE = 300.0


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def topup_mult(tiers: List[Tuple[float, float, float]], ratio: float) -> float:
    for lo, hi, m in tiers:
        if lo <= ratio < hi:
            return m
    return 1.0


def price_risk_mult(tiers: List[Tuple[float, float, float]], price: float) -> float:
    if not tiers:
        return 1.0
    for lo, hi, m in tiers:
        if lo <= price < hi:
            return m
    return 1.0


def formula_bet(invested_usd: float, A: float, B: float, MIN: float, MAX: float) -> float:
    if invested_usd <= 1.0:
        return 0.0
    raw = A * math.log(invested_usd) + B
    raw = max(MIN, min(MAX, raw))
    return raw


def build_denizz_resolutions_map() -> Dict[Tuple[str, str], Tuple[bool, float, Optional[float]]]:
    """(cid, asset_id) -> (is_winner, avg_entry_denizz, denizz_roi_or_None)"""
    with open(CLOSED, "r", encoding="utf-8") as f:
        closed = json.load(f)
    with open(RES, "r", encoding="utf-8") as f:
        resolutions = json.load(f)

    out: Dict[Tuple[str, str], Tuple[bool, float, Optional[float]]] = {}
    for c in closed:
        cp = c.get("curPrice")
        if cp not in (0.0, 1.0, 0, 1):
            continue
        invested = float(c.get("totalBought") or 0.0)
        if invested < 1.0:
            continue
        pnl = float(c.get("realizedPnl") or 0.0)
        roi = pnl / invested
        is_winner = cp in (1.0, 1)
        out[(c.get("conditionId"), str(c.get("asset")))] = (
            is_winner, float(c.get("avgPrice") or 0.0), roi)
    for cid, r in resolutions.items():
        if not r.get("resolved"):
            continue
        for tok in r.get("tokens", []):
            key = (cid, str(tok.get("token_id")))
            if key in out:
                continue
            out[key] = (bool(tok.get("winner")), 0.0, None)
    return out


# -----------------------------------------------------------------------------
# PART 1 — top-up ratio bucket statistics
# -----------------------------------------------------------------------------

RATIO_BUCKETS = [
    (0.000, 0.010, "0-1%"),
    (0.010, 0.020, "1-2%"),
    (0.020, 0.030, "2-3%"),
    (0.030, 0.050, "3-5%"),
    (0.050, 0.100, "5-10%"),
    (0.100, 0.200, "10-20%"),
    (0.200, 0.300, "20-30%"),
    (0.300, 9999.0, "30%+"),
]


def bucket_of(ratio: float) -> str:
    for lo, hi, name in RATIO_BUCKETS:
        if lo <= ratio < hi:
            return name
    return "30%+"


def topup_bucket_stats(activity: List[dict], res_map) -> Dict:
    """Aggregate per-bucket statistics of denizz top-ups."""
    events = [a for a in activity if a.get("type") == "TRADE" and a.get("side") == "BUY"]
    events.sort(key=lambda a: a.get("timestamp") or 0)
    leg_running: Dict[Tuple[str, str], float] = defaultdict(float)
    # for each leg, sum USD by bucket, and count top-up events
    leg_bucket_usd: Dict[Tuple[str, str, str], float] = defaultdict(float)
    leg_bucket_count: Dict[Tuple[str, str, str], int] = defaultdict(int)

    topup_events_total = 0
    topup_usd_total = 0.0
    first_entries = 0

    for a in events:
        cid = a.get("conditionId")
        asset = str(a.get("asset") or "")
        key = (cid, asset)
        buy_usd = float(a.get("usdcSize") or 0.0)
        if buy_usd < 30.0:
            # do not count dust in ratio calcs or bucket stats, but DO NOT
            # update running for it either (preserves denizz's meaningful
            # cumulative cost basis).
            continue
        prev = leg_running[key]
        new_total = prev + buy_usd
        if prev <= 0:
            leg_running[key] = new_total
            first_entries += 1
            continue
        ratio = buy_usd / new_total if new_total > 0 else 1.0
        b = bucket_of(ratio)
        leg_bucket_usd[(cid, asset, b)] += buy_usd
        leg_bucket_count[(cid, asset, b)] += 1
        topup_events_total += 1
        topup_usd_total += buy_usd
        leg_running[key] = new_total

    # per-bucket aggregations
    bucket_events = defaultdict(int)
    bucket_usd = defaultdict(float)
    bucket_legs = defaultdict(set)
    bucket_resolved_wins = defaultdict(int)
    bucket_resolved_losses = defaultdict(int)
    bucket_resolved_rois: Dict[str, List[float]] = defaultdict(list)
    bucket_resolved_usd_weighted_pnl = defaultdict(float)
    bucket_resolved_usd = defaultdict(float)

    for (cid, asset, b), usd in leg_bucket_usd.items():
        key = (cid, asset)
        bucket_events[b] += leg_bucket_count[(cid, asset, b)]
        bucket_usd[b] += usd
        bucket_legs[b].add(key)
        info = res_map.get(key)
        if info is None:
            continue
        is_winner, _avg, denizz_roi = info
        # Consider ROI only if we have realizedPnl; otherwise map winner→+1, loser→-1
        if denizz_roi is not None:
            roi = denizz_roi
        else:
            roi = 1.0 if is_winner else -1.0
        bucket_resolved_rois[b].append(roi)
        if roi > 0:
            bucket_resolved_wins[b] += 1
        else:
            bucket_resolved_losses[b] += 1
        # EV weighted by what we actually risked in this bucket for this leg
        bucket_resolved_usd_weighted_pnl[b] += usd * roi
        bucket_resolved_usd[b] += usd

    rows = []
    for lo, hi, name in RATIO_BUCKETS:
        n_ev = bucket_events[name]
        n_legs = len(bucket_legs[name])
        wins = bucket_resolved_wins[name]
        losses = bucket_resolved_losses[name]
        wr = wins / (wins + losses) if (wins + losses) else 0.0
        rois = bucket_resolved_rois[name]
        mean_roi = statistics.mean(rois) if rois else 0.0
        median_roi = statistics.median(rois) if rois else 0.0
        ev_per_usd = (bucket_resolved_usd_weighted_pnl[name] / bucket_resolved_usd[name]
                      if bucket_resolved_usd[name] > 0 else 0.0)
        rows.append({
            "bucket": name, "lo": lo, "hi": hi,
            "n_topup_events": n_ev,
            "n_unique_legs": n_legs,
            "usd_total": bucket_usd[name],
            "resolved_legs": wins + losses,
            "wins": wins, "losses": losses,
            "win_rate": wr,
            "mean_roi_resolved": mean_roi,
            "median_roi_resolved": median_roi,
            "ev_per_dollar_resolved": ev_per_usd,
            "usd_resolved": bucket_resolved_usd[name],
        })

    summary = {
        "buckets": rows,
        "first_entries": first_entries,
        "topup_events_total": topup_events_total,
        "topup_usd_total": topup_usd_total,
    }
    return summary


# -----------------------------------------------------------------------------
# PART 1b — TOP-UP variant backtest (T1 / T2 / T3)
# -----------------------------------------------------------------------------

def run_variant_bt(name: str, *, A, B, MIN, MAX, price_risk_tiers, topup_tiers,
                   activity, res_map, max_position_usd=400.0,
                   min_upgrade_usd=5.0, min_bet_live=10.0,
                   reserve=RESERVE, starting_br=STARTING_BANKROLL,
                   scale=1.0) -> Dict:
    events = [a for a in activity if a.get("type") == "TRADE" and a.get("side") == "BUY"]
    events.sort(key=lambda a: a.get("timestamp") or 0)

    leg_invested_denizz: Dict[Tuple[str, str], float] = defaultdict(float)
    our_pos: Dict[Tuple[str, str], Dict] = defaultdict(
        lambda: {"invested": 0.0, "shares": 0.0, "first_price": None})
    hits_max_bet = 0
    hits_max_bet_pnl = 0.0
    trades_at_max_bet_usd = 0.0

    bankroll = starting_br
    trades_taken = 0
    trades_skipped_filter = 0
    trades_skipped_bankroll = 0
    trades_skipped_min_upgrade = 0
    history_br: List[float] = [bankroll]

    for a in events:
        cid = a.get("conditionId")
        asset = str(a.get("asset") or "")
        key = (cid, asset)
        price = float(a.get("price") or 0.0)
        buy_usd = float(a.get("usdcSize") or 0.0)
        if buy_usd < 30.0:
            continue
        prev = leg_invested_denizz[key]
        leg_invested_denizz[key] = prev + buy_usd
        if price < 0.05 or price > 0.99:
            trades_skipped_filter += 1
            continue
        raw = formula_bet(leg_invested_denizz[key], A, B, MIN, MAX)
        if prev > 0:
            ratio = buy_usd / (prev + buy_usd) if (prev + buy_usd) > 0 else 1.0
            tm = topup_mult(topup_tiers, ratio)
        else:
            tm = 1.0
        pr = price_risk_mult(price_risk_tiers, price)
        bet = raw * tm * pr * scale

        already_in = our_pos[key]["invested"]
        leftover = max(0.0, max_position_usd - already_in)
        bet = min(bet, leftover)
        # MIN_UPGRADE_USD: if this is a top-up (we already have a position) and
        # computed bet is tiny, skip
        if already_in > 0 and bet < min_upgrade_usd:
            trades_skipped_min_upgrade += 1
            continue
        if bet < min_bet_live:
            trades_skipped_filter += 1
            continue
        available = bankroll - reserve
        if bet > available:
            trades_skipped_bankroll += 1
            continue
        # Did we hit MAX_BET cap? (raw unclamped formula > MAX)
        unclamped = A * math.log(max(leg_invested_denizz[key], 1.0001)) + B
        if unclamped > MAX:
            hits_max_bet += 1
            trades_at_max_bet_usd += bet
        shares = bet / price
        bankroll -= bet
        if our_pos[key]["first_price"] is None:
            our_pos[key]["first_price"] = price
        our_pos[key]["invested"] += bet
        our_pos[key]["shares"] += shares
        # remember whether this leg had at least one MAX_BET hit
        if unclamped > MAX:
            our_pos[key]["had_max_bet"] = True
        trades_taken += 1
        equity = bankroll + sum(p["invested"] for p in our_pos.values())
        history_br.append(equity)

    # settle
    resolved_pnl = 0.0
    wins = 0
    losses = 0
    roi_list: List[float] = []
    unresolved_count = 0
    open_invested_total = sum(p["invested"] for p in our_pos.values())
    max_bet_leg_pnl = 0.0
    for key, pos in our_pos.items():
        if pos["invested"] <= 0.01:
            continue
        info = res_map.get(key)
        if info is None:
            unresolved_count += 1
            payout = pos["invested"] * 0.95
            bankroll += payout
            open_invested_total -= pos["invested"]
            continue
        is_winner, _avg, denizz_roi = info
        if denizz_roi is not None:
            payout = pos["invested"] * (1.0 + denizz_roi)
        elif is_winner:
            payout = pos["shares"] * 1.0
        else:
            payout = 0.0
        pnl = payout - pos["invested"]
        roi = pnl / pos["invested"] if pos["invested"] > 0 else 0.0
        resolved_pnl += pnl
        bankroll += payout
        open_invested_total -= pos["invested"]
        if pnl > 0:
            wins += 1
        else:
            losses += 1
        roi_list.append(roi)
        if pos.get("had_max_bet"):
            max_bet_leg_pnl += pnl
        history_br.append(bankroll + open_invested_total)

    dd = 0.0
    rp = history_br[0]
    for v in history_br:
        if v > rp:
            rp = v
        cur = (rp - v) / rp if rp > 0 else 0.0
        if cur > dd:
            dd = cur

    mean_roi = statistics.mean(roi_list) if roi_list else 0.0
    std_roi = statistics.stdev(roi_list) if len(roi_list) > 1 else 0.0
    sharpe = (mean_roi / std_roi) if std_roi else None
    wr = wins / (wins + losses) if (wins + losses) else 0.0

    return {
        "name": name,
        "final_bankroll": round(bankroll, 2),
        "starting_bankroll": starting_br,
        "return_pct": (bankroll - starting_br) / starting_br,
        "max_drawdown_pct": dd,
        "trades_taken": trades_taken,
        "trades_skipped_filter": trades_skipped_filter,
        "trades_skipped_bankroll": trades_skipped_bankroll,
        "trades_skipped_min_upgrade": trades_skipped_min_upgrade,
        "resolved_trades": wins + losses,
        "wins": wins, "losses": losses,
        "win_rate": wr,
        "mean_roi": mean_roi, "std_roi": std_roi,
        "sharpe": sharpe,
        "total_resolved_pnl": resolved_pnl,
        "unresolved_legs": unresolved_count,
        "hits_max_bet": hits_max_bet,
        "trades_at_max_bet_usd": round(trades_at_max_bet_usd, 2),
        "max_bet_leg_pnl": round(max_bet_leg_pnl, 2),
        "config": {
            "A": A, "B": B, "MIN": MIN, "MAX": MAX,
            "price_risk_tiers": price_risk_tiers,
            "topup_tiers": topup_tiers,
            "max_position_usd": max_position_usd,
            "min_upgrade_usd": min_upgrade_usd,
        },
    }


# -----------------------------------------------------------------------------
# MAIN
# -----------------------------------------------------------------------------

def main() -> None:
    with open(ACT, "r", encoding="utf-8") as f:
        activity = json.load(f)
    res_map = build_denizz_resolutions_map()
    print(f"Resolutions mapped: {len(res_map)}")
    print(f"Total activity records: {len(activity)}")

    # ---------- PART 1: ratio bucket stats ----------
    print("\n==== PART 1: TOP-UP RATIO BUCKETS (denizz history) ====")
    summary = topup_bucket_stats(activity, res_map)
    print(f"First entries: {summary['first_entries']}")
    print(f"Top-up events (≥$30): {summary['topup_events_total']}, "
          f"total USD: ${summary['topup_usd_total']:,.0f}")
    print(f"{'Bucket':<8} {'N_ev':>5} {'N_legs':>6} {'USD_total':>12} "
          f"{'Resolv':>6} {'W':>4} {'L':>4} {'WR':>6} "
          f"{'meanROI':>8} {'medROI':>7} {'EV/$':>7}")
    for r in summary["buckets"]:
        print(f"{r['bucket']:<8} {r['n_topup_events']:>5} {r['n_unique_legs']:>6} "
              f"${r['usd_total']:>11,.0f} {r['resolved_legs']:>6} "
              f"{r['wins']:>4} {r['losses']:>4} {r['win_rate']:>5.1%} "
              f"{r['mean_roi_resolved']:>+7.3f} {r['median_roi_resolved']:>+6.3f} "
              f"{r['ev_per_dollar_resolved']:>+6.3f}")

    with open(OUT_TOPUP_BUCKETS, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"\nWrote {OUT_TOPUP_BUCKETS}")

    # how many events sit below 3% threshold today (current T1)
    below_3 = sum(r["n_topup_events"] for r in summary["buckets"] if r["hi"] <= 0.030)
    below_3_usd = sum(r["usd_total"] for r in summary["buckets"] if r["hi"] <= 0.030)
    below_2 = sum(r["n_topup_events"] for r in summary["buckets"] if r["hi"] <= 0.020)
    below_2_usd = sum(r["usd_total"] for r in summary["buckets"] if r["hi"] <= 0.020)
    below_15 = sum(r["n_topup_events"] for r in summary["buckets"] if r["hi"] <= 0.020 or r["bucket"] == "1-2%")
    print(f"\nBelow 3% (current skip): {below_3} events, ${below_3_usd:,.0f} denizz USD")
    print(f"Below 2%:                 {below_2} events, ${below_2_usd:,.0f} denizz USD")

    # ---------- PART 1b: TOP-UP variant backtest ----------
    # V3 baseline config (per existing _price_risk_backtest.py)
    PR_V3 = [
        (0.00, 0.15, 0.40),
        (0.15, 0.30, 0.70),
        (0.30, 0.50, 1.00),
        (0.50, 0.70, 0.85),
        (0.70, 0.85, 0.75),
        (0.85, 0.99, 0.60),
    ]

    # T1 baseline (current)
    T1 = [
        (0.00, 0.03, 0.0),
        (0.03, 0.10, 0.5),
        (0.10, 0.30, 0.75),
        (0.30, 999.0, 1.0),
    ]
    # T2 soft
    T2 = [
        (0.000, 0.020, 0.0),
        (0.020, 0.030, 0.3),   # 2-3% slice: 30%
        (0.030, 0.100, 0.5),
        (0.100, 0.300, 0.75),
        (0.300, 999.0, 1.0),
    ]
    # T3 aggressive
    T3 = [
        (0.000, 0.015, 0.0),
        (0.015, 0.030, 0.35),
        (0.030, 0.100, 0.6),   # slightly higher mult
        (0.100, 0.300, 0.85),
        (0.300, 999.0, 1.0),
    ]

    print("\n==== PART 1b: TOP-UP T1 / T2 / T3 BACKTEST (V3 formula) ====")
    topup_variants = [
        ("T1_baseline_3pct",  T1, 400.0, 5.0),
        ("T2_soft_2pct_mini", T2, 400.0, 5.0),
        ("T3_aggressive_1.5", T3, 500.0, 3.0),
    ]
    topup_results = []
    for name, tiers, maxpos, minup in topup_variants:
        r = run_variant_bt(
            name=name, A=30.0, B=-167.0, MIN=15.0, MAX=250.0,
            price_risk_tiers=PR_V3, topup_tiers=tiers,
            activity=activity, res_map=res_map,
            max_position_usd=maxpos, min_upgrade_usd=minup,
        )
        topup_results.append(r)
        print(f"\n== {r['name']} ==")
        print(f"  final=${r['final_bankroll']} ret={r['return_pct']:+.1%} DD={r['max_drawdown_pct']:.1%}")
        print(f"  trades={r['trades_taken']} (skip_filter={r['trades_skipped_filter']}, "
              f"skip_min_upg={r['trades_skipped_min_upgrade']}, skip_br={r['trades_skipped_bankroll']})")
        print(f"  resolved={r['resolved_trades']} W={r['wins']} L={r['losses']} WR={r['win_rate']:.1%}")
        print(f"  hits_MAX_BET={r['hits_max_bet']} usd_at_MAX=${r['trades_at_max_bet_usd']} "
              f"pnl_on_MAX_legs=${r['max_bet_leg_pnl']}")

    with open(OUT_TOPUP_BT, "w", encoding="utf-8") as f:
        json.dump(topup_results, f, indent=2, default=str)
    print(f"\nWrote {OUT_TOPUP_BT}")

    # ---------- PART 2: V1 vs V3 vs V7 (± V8) FORMULA BACKTEST ----------
    print("\n==== PART 2: V1 / V3 / V7 (+V8 if needed) FORMULA BACKTEST ====")
    PR_V8 = [  # V8 — V7 formula but strict high-price multiplier
        (0.00, 0.15, 0.40),
        (0.15, 0.30, 0.70),
        (0.30, 0.50, 1.00),
        (0.50, 0.70, 0.85),
        (0.70, 0.85, 0.70),
        (0.85, 0.99, 0.50),
    ]

    formula_variants = [
        # V1 AS-IS reference (no PR, no new MAX_POSITION)
        ("V1_current_noPR",   31.75, -177.0, 20.0, 200.0, [],    T1, 300.0, 5.0),
        # V3 baseline (today's recommendation)
        ("V3_recalib_PR",     30.0,  -167.0, 15.0, 250.0, PR_V3, T1, 400.0, 5.0),
        # V7 — aggressive formula, V3 PR, V3 caps
        ("V7_aggressive_PR",  31.75, -177.0, 15.0, 250.0, PR_V3, T1, 400.0, 5.0),
        # V8 — V7 + strict PR at top
        ("V8_aggressive_PR_strict", 31.75, -177.0, 15.0, 250.0, PR_V8, T1, 400.0, 5.0),
    ]
    formula_results = []
    for name, A, B, Mn, Mx, pr, tu, maxpos, minup in formula_variants:
        r = run_variant_bt(
            name=name, A=A, B=B, MIN=Mn, MAX=Mx,
            price_risk_tiers=pr, topup_tiers=tu,
            activity=activity, res_map=res_map,
            max_position_usd=maxpos, min_upgrade_usd=minup,
        )
        formula_results.append(r)
        print(f"\n== {r['name']} ==")
        print(f"  final=${r['final_bankroll']} ret={r['return_pct']:+.1%} DD={r['max_drawdown_pct']:.1%}")
        print(f"  trades={r['trades_taken']} resolved={r['resolved_trades']} "
              f"W={r['wins']} L={r['losses']} WR={r['win_rate']:.1%}")
        sh = r.get('sharpe')
        print(f"  meanROI={r['mean_roi']:+.3f} stdROI={r['std_roi']:.3f} "
              f"Sharpe={'nan' if sh is None else f'{sh:+.3f}'}")
        print(f"  hits_MAX_BET={r['hits_max_bet']} usd_at_MAX=${r['trades_at_max_bet_usd']} "
              f"pnl_on_MAX_legs=${r['max_bet_leg_pnl']}")

    with open(OUT_V7_BT, "w", encoding="utf-8") as f:
        json.dump(formula_results, f, indent=2, default=str)
    print(f"\nWrote {OUT_V7_BT}")

    # ---------- Anchors table ----------
    print("\n==== FORMULA ANCHORS ====")
    anchors = [500, 1000, 5000, 10000, 30000, 100000]
    print(f"{'invested':>10}  {'V1':>7}  {'V3':>7}  {'V7':>7}")
    for inv in anchors:
        v1 = formula_bet(inv, 31.75, -177.0, 20.0, 200.0)
        v3 = formula_bet(inv, 30.0, -167.0, 15.0, 250.0)
        v7 = formula_bet(inv, 31.75, -177.0, 15.0, 250.0)
        print(f"  ${inv:>8}  ${v1:>5.1f}  ${v3:>5.1f}  ${v7:>5.1f}")


if __name__ == "__main__":
    main()
