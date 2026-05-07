"""Backtest bet-sizing formulas on denizz's historical BUY stream.

For each BUY event by denizz:
  - skip dust (usdcSize < $30) and merge/arb events (requires identifying
    same-timestamp Yes+No pairs — we approximate with a simple filter).
  - build running per-leg denizz_invested USDC tally
  - compute bet = formula(denizz_invested_total_on_leg) * topup_ratio_mult(ratio)
      * price_risk_mult(price)  (capped by MIN/MAX)
  - aggregate our virtual position: running invested, shares, avg entry
  - on resolution (resolved) determine final ROI and update bankroll

Tracks metrics per variant: final_bankroll, max_drawdown, trades, wr, roi.
Reads same data files as the stats script, plus reuses topup ratio logic
from config.
"""
from __future__ import annotations
import json
import math
import os
import statistics
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

BASE = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data"
ACT = os.path.join(BASE, "denizz_activity_ALL.json")
RES = os.path.join(BASE, "denizz_resolutions.json")
CLOSED = os.path.join(BASE, "denizz_closed_positions_raw.json")
OUT = os.path.join(BASE, "price_risk_backtest_results.json")

TOPUP_RATIO_TIERS = [
    (0.00, 0.03, 0.0),
    (0.03, 0.10, 0.5),
    (0.10, 0.30, 0.75),
    (0.30, 999.0, 1.0),
]

STARTING_BANKROLL = 4000.0


def topup_mult(ratio: float) -> float:
    for lo, hi, m in TOPUP_RATIO_TIERS:
        if lo <= ratio < hi:
            return m
    return 1.0


def price_risk_mult(price: float, tiers: List[Tuple[float, float, float]]) -> float:
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


def build_denizz_resolutions_map() -> Dict[Tuple[str, str], Tuple[bool, float, float]]:
    """Return {(cid, asset_id): (is_winner, denizz_avg_entry, denizz_roi)}
    Using closed_positions_raw first (high quality, has realizedPnl)."""
    with open(CLOSED, "r", encoding="utf-8") as f:
        closed = json.load(f)
    with open(RES, "r", encoding="utf-8") as f:
        resolutions = json.load(f)

    out: Dict[Tuple[str, str], Tuple[bool, float, float]] = {}
    # from closed
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
        out[(c.get("conditionId"), str(c.get("asset")))] = (is_winner, float(c.get("avgPrice") or 0.0), roi)
    # from resolutions: only is_winner flag (no pnl)
    # we'll use denizz_activity-derived invested + payout as roi proxy
    for cid, r in resolutions.items():
        if not r.get("resolved"):
            continue
        for tok in r.get("tokens", []):
            key = (cid, str(tok.get("token_id")))
            if key in out:
                continue
            out[key] = (bool(tok.get("winner")), 0.0, None)  # roi unknown
    return out


def run_variant(name: str,
                A: float, B: float, MIN: float, MAX: float,
                price_risk_tiers: List[Tuple[float, float, float]],
                activity: List[dict],
                resolutions_map: Dict[Tuple[str, str], Tuple[bool, float, float]],
                max_position_usd: float = 300.0,
                scale: float = 1.0) -> Dict:
    """Simulate trading on denizz activity stream."""
    # Build per-leg (cid, asset) denizz's invested-running totals and BUY events
    # sorted by timestamp
    events = [a for a in activity if a.get("type") == "TRADE" and a.get("side") == "BUY"]
    events.sort(key=lambda a: a.get("timestamp") or 0)

    # running denizz invested per leg
    leg_invested: Dict[Tuple[str, str], float] = defaultdict(float)
    # our virtual positions: (cid,asset) -> {invested, shares}
    our_pos: Dict[Tuple[str, str], Dict] = defaultdict(lambda: {"invested": 0.0, "shares": 0.0, "first_price": None})

    bankroll = STARTING_BANKROLL
    peak = bankroll
    min_bankroll = bankroll
    trades_taken = 0
    trades_skipped_filter = 0
    trades_skipped_bankroll = 0
    # simulate cashflow: we deduct our bet at buy, then when a leg resolves we
    # add payout. We need to know the order of resolutions — there is no
    # timestamp in resolutions.json, so we approximate: as soon as we finish
    # walking all BUYs, we settle every resolved leg in one pass and compute
    # metrics. This drops intra-history drawdown fidelity but keeps final BR
    # accurate.
    history_br: List[float] = [bankroll]

    for a in events:
        cid = a.get("conditionId")
        asset = str(a.get("asset") or "")
        key = (cid, asset)
        price = float(a.get("price") or 0.0)
        buy_usd = float(a.get("usdcSize") or 0.0)
        if buy_usd < 30.0:
            continue  # dust / arb
        # update running denizz invested
        prev = leg_invested[key]
        leg_invested[key] = prev + buy_usd
        # price gate (same as bot config for denizz: 0.05..0.99)
        if price < 0.05 or price > 0.99:
            trades_skipped_filter += 1
            continue
        # formula bet based on denizz's total invested on this leg
        raw = formula_bet(leg_invested[key], A, B, MIN, MAX)
        # topup multiplier if already position
        if prev > 0:
            ratio = buy_usd / (prev + buy_usd) if (prev + buy_usd) > 0 else 1.0
            tm = topup_mult(ratio)
        else:
            tm = 1.0
        # price-risk multiplier
        pr = price_risk_mult(price, price_risk_tiers)
        bet = raw * tm * pr * scale
        # cap to max_position_usd (leftover capacity in this leg)
        already_in = our_pos[key]["invested"]
        leftover = max(0.0, max_position_usd - already_in)
        bet = min(bet, leftover)
        if bet < 10.0:  # below MIN_BET_USD_LIVE
            trades_skipped_filter += 1
            continue
        # bankroll check: don't spend below RESERVE_USD $200
        RESERVE = 200.0
        available = bankroll - RESERVE
        if bet > available:
            trades_skipped_bankroll += 1
            continue
        # execute buy: shares = bet / price (ignoring slippage for simplicity)
        shares = bet / price
        bankroll -= bet
        if our_pos[key]["first_price"] is None:
            our_pos[key]["first_price"] = price
        our_pos[key]["invested"] += bet
        our_pos[key]["shares"] += shares
        trades_taken += 1
        # total equity = cash bankroll + sum(invested in open positions at cost)
        equity = bankroll + sum(p["invested"] for p in our_pos.values())
        history_br.append(equity)

    # settle resolved positions
    resolved_pnl = 0.0
    wins = 0
    losses = 0
    roi_list: List[float] = []
    pos_detail = []
    unresolved_count = 0
    open_invested_total = sum(p["invested"] for p in our_pos.values())
    for key, pos in our_pos.items():
        if pos["invested"] <= 0.01:
            continue
        info = resolutions_map.get(key)
        if info is None:
            # unresolved in our data — assume MARKET-NEUTRAL outcome: recover
            # invested at 95% (approximating we'd at worst have to dump at
            # last price). This prevents the model from treating unresolved
            # legs as sunk losses, which otherwise biases all variants
            # negatively.
            unresolved_count += 1
            payout = pos["invested"] * 0.95
            bankroll += payout
            open_invested_total -= pos["invested"]
            equity = bankroll + open_invested_total
            history_br.append(equity)
            continue
        is_winner, _avg_entry, denizz_roi = info
        # If we know denizz's ROI for this leg (from closed_raw), use it as
        # proxy for our ROI (we follow his exit). Otherwise fall back to
        # binary winner/loser resolution.
        if denizz_roi is not None:
            # our payout = invested * (1 + denizz_roi)
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
        pos_detail.append({"key": list(key), "invested": pos["invested"],
                           "shares": pos["shares"], "entry_price": pos["first_price"],
                           "pnl": pnl, "roi": roi, "is_winner": is_winner})
        equity = bankroll + open_invested_total
        if equity > peak:
            peak = equity
        if equity < min_bankroll:
            min_bankroll = equity
        history_br.append(equity)

    # Max drawdown from peak (using history of equity = cash + invested)
    # During the BUY-streaming phase equity stays roughly flat (we just move
    # cash into open positions at cost). Only at settlement does equity
    # change due to PnL realizations. That isolates real losses.
    dd = 0.0
    running_peak = history_br[0]
    for v in history_br:
        if v > running_peak:
            running_peak = v
        cur_dd = (running_peak - v) / running_peak if running_peak > 0 else 0.0
        if cur_dd > dd:
            dd = cur_dd

    mean_roi = statistics.mean(roi_list) if roi_list else 0.0
    median_roi = statistics.median(roi_list) if roi_list else 0.0
    std_roi = statistics.stdev(roi_list) if len(roi_list) > 1 else 0.0
    sharpe = (mean_roi / std_roi) if std_roi else None
    wr = wins / (wins + losses) if (wins + losses) else 0.0

    return {
        "name": name,
        "A": A, "B": B, "MIN": MIN, "MAX": MAX,
        "price_risk_tiers": price_risk_tiers,
        "scale": scale,
        "final_bankroll": bankroll,
        "starting_bankroll": STARTING_BANKROLL,
        "return_pct": (bankroll - STARTING_BANKROLL) / STARTING_BANKROLL,
        "max_drawdown_pct": dd,
        "trades_taken": trades_taken,
        "trades_skipped_filter": trades_skipped_filter,
        "trades_skipped_bankroll": trades_skipped_bankroll,
        "resolved_trades": wins + losses,
        "wins": wins, "losses": losses,
        "win_rate": wr,
        "mean_roi": mean_roi, "median_roi": median_roi,
        "std_roi": std_roi, "sharpe": sharpe,
        "total_resolved_pnl": resolved_pnl,
        "unresolved_legs": unresolved_count,
    }


def main() -> None:
    with open(ACT, "r", encoding="utf-8") as f:
        activity = json.load(f)
    res_map = build_denizz_resolutions_map()
    print(f"Resolutions mapped: {len(res_map)}")

    # Proposed PRICE_RISK_TIERS (derived from stats + conservative defaults
    # for small-sample buckets). See MD report for rationale.
    pr_tiers_proposed = [
        (0.00, 0.15, 0.40),   # very risky longshots
        (0.15, 0.30, 0.70),   # cheap but decent EV
        (0.30, 0.50, 1.00),   # sweet spot
        (0.50, 0.70, 0.85),   # good EV, lower upside
        (0.70, 0.85, 0.75),   # limited upside
        (0.85, 0.99, 0.60),   # very limited upside
    ]

    variants = [
        # V1 current (no price_risk)
        {"name": "V1_current",
         "A": 31.75, "B": -177.0, "MIN": 20.0, "MAX": 200.0,
         "price_risk_tiers": [], "scale": 1.0},
        # V2 current + price_risk
        {"name": "V2_current+PR",
         "A": 31.75, "B": -177.0, "MIN": 20.0, "MAX": 200.0,
         "price_risk_tiers": pr_tiers_proposed, "scale": 1.0},
        # V3 recalibrated bigger MAX, higher MIN retained
        # Solve: at invested=$1000 ln(1000)=6.907; bet=~$40 → A*6.907+B=40
        # At invested=$10000 ln=9.21; bet=~$100 → A*9.21+B=100 → A=(100-40)/(9.21-6.907)=26.05, B=40-26.05*6.907=-139.94
        # At invested=$50000 ln=10.82 → bet=A*10.82+B=26.05*10.82-139.94=141.87 (close to 180 target; pick A=30, B=-167 for steeper)
        {"name": "V3_recalib+PR",
         "A": 30.0, "B": -167.0, "MIN": 15.0, "MAX": 250.0,
         "price_risk_tiers": pr_tiers_proposed, "scale": 1.0},
        # V4 conservative
        {"name": "V4_conservative+PR",
         "A": 25.0, "B": -140.0, "MIN": 10.0, "MAX": 150.0,
         "price_risk_tiers": pr_tiers_proposed, "scale": 1.0},
        # V5 aggressive (higher MAX, no PR — sanity check)
        {"name": "V5_aggressive_noPR",
         "A": 35.0, "B": -195.0, "MIN": 25.0, "MAX": 300.0,
         "price_risk_tiers": [], "scale": 1.0},
        # V6 recalib + PR, but higher floor (avoid <10 cent regime entirely with mult=0)
        {"name": "V6_recalib+PR_strict",
         "A": 30.0, "B": -167.0, "MIN": 15.0, "MAX": 250.0,
         "price_risk_tiers": [
            (0.00, 0.15, 0.30),
            (0.15, 0.30, 0.60),
            (0.30, 0.50, 1.00),
            (0.50, 0.70, 0.90),
            (0.70, 0.85, 0.70),
            (0.85, 0.99, 0.50),
         ], "scale": 1.0},
    ]

    results = []
    for v in variants:
        r = run_variant(
            name=v["name"], A=v["A"], B=v["B"], MIN=v["MIN"], MAX=v["MAX"],
            price_risk_tiers=v["price_risk_tiers"], activity=activity,
            resolutions_map=res_map, scale=v["scale"],
        )
        results.append(r)
        print(f"\n== {r['name']} ==")
        print(f"  final_BR=${r['final_bankroll']:.0f}  ret={r['return_pct']:+.1%}  "
              f"DD={r['max_drawdown_pct']:.1%}")
        print(f"  trades={r['trades_taken']} skipped_filter={r['trades_skipped_filter']} "
              f"skipped_BR={r['trades_skipped_bankroll']}")
        print(f"  resolved={r['resolved_trades']} W={r['wins']} L={r['losses']} WR={r['win_rate']:.1%}")
        sh = r.get("sharpe")
        print(f"  meanROI={r['mean_roi']:+.3f} medROI={r['median_roi']:+.3f} "
              f"stdROI={r['std_roi']:.3f} Sharpe={'nan' if sh is None else f'{sh:+.3f}'}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    print("\nWrote", OUT)


if __name__ == "__main__":
    main()
