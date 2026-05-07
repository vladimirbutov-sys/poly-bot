"""Backtest of the event-based rebuy trigger branch for copy-bot v2.

Purpose
-------
When the state-based tier-upgrade increment returns < MIN_UPGRADE_USD because
denizz has net-sold and then bought back (reversal), we miss the signal.
This script simulates the proposed rebuy branch on the full denizz history
and compares to a control run without the rebuy branch.

Methodology
-----------
1. Walk denizz BUY+SELL activity chronologically.
2. Maintain per (cid, token) state:
     denizz_size, denizz_cost_basis (net)
     our_cost, our_shares
     last_rebuy_ts (for throttle)
3. On each BUY:
     a. Update denizz cost basis via running net invested.
     b. Compute state-based target = formula(denizz_cost_basis) * PR * topup_mult
        inc = target - our_cost
        If inc >= MIN_UPGRADE_USD -> normal tier-upgrade (our_cost += inc)
     c. Else check rebuy trigger:
          our_cost > 0 and new_buy_usd >= MIN_PLAYER_INVESTED and not throttled
          rebuy = formula(new_buy_usd) * PR
          rebuy = min(rebuy, MAX_POSITION_USD - our_cost)
          if rebuy >= MIN_BET_USD_LIVE: record rebuy event & add to our_cost
4. On each SELL of denizz we proportionally reduce our shares/cost.
5. Settle with closed_positions_raw (realizedPnl/totalBought ROI) or
   denizz_resolutions (winner/loser → +50%/-100%). Unresolved = 95% recovery.

Outputs (all absolute paths):
  rebuy_events.json   — every triggered rebuy
  rebuy_summary.json  — summary metrics for report
  rebuy_control.json  — same harness with trigger OFF (control)
"""
from __future__ import annotations
import io
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data"
ACT = os.path.join(BASE, "denizz_activity_ALL.json")
RES = os.path.join(BASE, "denizz_resolutions.json")
CLOSED = os.path.join(BASE, "denizz_closed_positions_raw.json")

OUT_EVENTS = os.path.join(BASE, "rebuy_events.json")
OUT_SUMMARY = os.path.join(BASE, "rebuy_summary.json")
OUT_CONTROL = os.path.join(BASE, "rebuy_control.json")

# --- Parameters (V9) ---
BET_FORMULA_A = 31.75
BET_FORMULA_B = -177.0
MIN_BET_FORMULA = 15.0
MAX_BET_USD = 250.0
MAX_POSITION_USD = 300.0
MIN_UPGRADE_USD = 5.0
MIN_BET_USD_LIVE = 10.0
MIN_PLAYER_INVESTED_DENIZZ = 500.0
BANKROLL = 4000.0
RESERVE = 300.0
REBUY_THROTTLE_SEC = 300
MIN_USD_SIZE_ACT = 30.0   # ignore dust BUYs (same filter as earlier scripts)

PRICE_RISK_TIERS = [
    (0.00, 0.15, 0.40),
    (0.15, 0.30, 0.70),
    (0.30, 0.70, 1.00),
    (0.70, 0.85, 0.90),
    (0.85, 0.99, 0.80),
]

TOPUP_RATIO_TIERS = [
    (0.00, 0.03, 0.0),
    (0.03, 0.10, 0.5),
    (0.10, 0.30, 0.75),
    (0.30, 999.0, 1.0),
]

PRICE_RISK_BUCKET_LABELS = [
    "0.00-0.15",
    "0.15-0.30",
    "0.30-0.70",
    "0.70-0.85",
    "0.85-0.99",
    "other",
]


def lookup_mult(x: float, tiers) -> float:
    for lo, hi, m in tiers:
        if lo <= x < hi:
            return m
    return 0.0 if x < 0 else 1.0


def price_bucket(price: float) -> str:
    for lo, hi, _ in PRICE_RISK_TIERS:
        if lo <= price < hi:
            return f"{lo:.2f}-{hi:.2f}"
    return "other"


def formula_bet(invested_usd: float) -> float:
    if invested_usd <= 1.0:
        return 0.0
    raw = BET_FORMULA_A * math.log(invested_usd) + BET_FORMULA_B
    return max(MIN_BET_FORMULA, min(MAX_BET_USD, raw))


def build_resolution_map() -> Dict[Tuple[str, str], Tuple[bool, Optional[float]]]:
    """(cid, asset_id) -> (is_winner, denizz_roi_or_None)

    First source: closed_positions (realizedPnl/totalBought).
    Second source: resolutions dict (winner bool only).
    """
    with open(CLOSED, "r", encoding="utf-8") as f:
        closed = json.load(f)
    with open(RES, "r", encoding="utf-8") as f:
        resolutions = json.load(f)

    out: Dict[Tuple[str, str], Tuple[bool, Optional[float]]] = {}
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
        out[(c.get("conditionId"), str(c.get("asset")))] = (is_winner, roi)
    # resolutions dict
    for cid, r in resolutions.items():
        if not r.get("resolved"):
            continue
        for tok in r.get("tokens", []):
            key = (cid, str(tok.get("token_id")))
            if key in out:
                continue
            out[key] = (bool(tok.get("winner")), None)
    return out


def run_backtest(activity: List[dict],
                 res_map: Dict[Tuple[str, str], Tuple[bool, Optional[float]]],
                 *,
                 enable_rebuy: bool) -> Dict:
    """Simulate entire history. Returns results dict."""
    events = [a for a in activity
              if a.get("type") == "TRADE" and a.get("side") in ("BUY", "SELL")]
    events.sort(key=lambda a: a.get("timestamp") or 0)

    # per (cid, token)
    denizz_size: Dict[Tuple[str, str], float] = defaultdict(float)
    denizz_cost: Dict[Tuple[str, str], float] = defaultdict(float)
    our_cost: Dict[Tuple[str, str], float] = defaultdict(float)
    our_shares: Dict[Tuple[str, str], float] = defaultdict(float)
    our_first_price: Dict[Tuple[str, str], Optional[float]] = defaultdict(lambda: None)
    last_rebuy_ts: Dict[Tuple[str, str], float] = defaultdict(float)
    had_rebuy: Dict[Tuple[str, str], bool] = defaultdict(bool)
    leg_titles: Dict[Tuple[str, str], str] = {}

    bankroll = BANKROLL
    history_br: List[float] = [bankroll]

    trades_upgrade = 0
    trades_first_entry = 0
    rebuy_events: List[Dict] = []
    skipped_rebuy_throttle = 0
    skipped_rebuy_smallbuy = 0
    skipped_rebuy_mincost = 0
    skipped_rebuy_bankroll = 0
    skipped_rebuy_capreached = 0
    skipped_rebuy_lowsize = 0

    for a in events:
        cid = a.get("conditionId")
        asset = str(a.get("asset") or "")
        key = (cid, asset)
        ts = float(a.get("timestamp") or 0)
        price = float(a.get("price") or 0)
        usd = float(a.get("usdcSize") or 0)
        size = float(a.get("size") or 0)
        title = a.get("title") or ""
        if title and key not in leg_titles:
            leg_titles[key] = title
        side = a.get("side")

        if side == "BUY":
            if usd < MIN_USD_SIZE_ACT:
                continue
            # update denizz running cost
            prev_size = denizz_size[key]
            prev_cost = denizz_cost[key]
            denizz_size[key] = prev_size + size
            denizz_cost[key] = prev_cost + usd
            cur_cost_basis = denizz_cost[key]

            if price < 0.05 or price >= 0.99:
                continue

            # Top-up ratio and state-based target
            topup_m = 1.0
            if prev_cost > 0:
                ratio = usd / (prev_cost + usd) if (prev_cost + usd) > 0 else 1.0
                topup_m = lookup_mult(ratio, TOPUP_RATIO_TIERS)
            pr = lookup_mult(price, PRICE_RISK_TIERS)
            formula_target = formula_bet(cur_cost_basis) * topup_m * pr
            inc = formula_target - our_cost[key]

            if inc >= MIN_UPGRADE_USD:
                # normal tier-upgrade
                leftover = max(0.0, MAX_POSITION_USD - our_cost[key])
                bet = min(inc, leftover, MAX_BET_USD)
                if bet < MIN_BET_USD_LIVE:
                    continue
                if bankroll - bet < RESERVE:
                    continue
                bankroll -= bet
                shares = bet / price if price > 0 else 0.0
                if our_first_price[key] is None:
                    our_first_price[key] = price
                    trades_first_entry += 1
                else:
                    trades_upgrade += 1
                our_cost[key] += bet
                our_shares[key] += shares
                history_br.append(bankroll + sum(our_cost.values()))
                continue

            # rebuy trigger
            if not enable_rebuy:
                continue
            if our_cost[key] <= 0:
                skipped_rebuy_mincost += 1
                continue
            if usd < MIN_PLAYER_INVESTED_DENIZZ:
                skipped_rebuy_smallbuy += 1
                continue
            if ts - last_rebuy_ts[key] < REBUY_THROTTLE_SEC:
                skipped_rebuy_throttle += 1
                continue
            rebuy = formula_bet(usd) * pr
            leftover = max(0.0, MAX_POSITION_USD - our_cost[key])
            if leftover <= 0:
                skipped_rebuy_capreached += 1
                continue
            rebuy = min(rebuy, leftover, MAX_BET_USD)
            if rebuy < MIN_BET_USD_LIVE:
                skipped_rebuy_lowsize += 1
                continue
            if bankroll - rebuy < RESERVE:
                skipped_rebuy_bankroll += 1
                continue
            # commit rebuy
            shares = rebuy / price if price > 0 else 0.0
            bankroll -= rebuy
            if our_first_price[key] is None:
                our_first_price[key] = price
            our_cost[key] += rebuy
            our_shares[key] += shares
            last_rebuy_ts[key] = ts
            had_rebuy[key] = True
            rebuy_events.append({
                "ts": int(ts),
                "iso": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else "",
                "cid": cid,
                "token": asset,
                "title": title,
                "price": round(price, 4),
                "price_bucket": price_bucket(price),
                "pr_mult": pr,
                "denizz_new_buy_usd": round(usd, 2),
                "denizz_cost_basis_after": round(cur_cost_basis, 2),
                "our_cost_before": round(our_cost[key] - rebuy, 2),
                "our_cost_after": round(our_cost[key], 2),
                "rebuy_usd": round(rebuy, 2),
            })
            history_br.append(bankroll + sum(our_cost.values()))

        elif side == "SELL":
            # proportional follow-sell (based on denizz's sell ratio)
            prev_size = denizz_size[key]
            if prev_size <= 0 or our_shares[key] <= 0:
                # still update denizz state though
                denizz_size[key] = max(0.0, prev_size - size)
                # cost basis reduces proportionally
                if prev_size > 0:
                    denizz_cost[key] = max(0.0,
                                           denizz_cost[key] * (denizz_size[key] / prev_size))
                continue
            sell_ratio = min(1.0, size / prev_size)
            our_sell_shares = our_shares[key] * sell_ratio
            # our cost basis reduced proportionally; realize pnl relative to avg entry
            avg_entry = (our_cost[key] / our_shares[key]) if our_shares[key] > 0 else 0.0
            cost_out = avg_entry * our_sell_shares
            proceeds = our_sell_shares * price
            bankroll += proceeds
            our_shares[key] -= our_sell_shares
            our_cost[key] = max(0.0, our_cost[key] - cost_out)
            # update denizz
            denizz_size[key] = max(0.0, prev_size - size)
            if prev_size > 0:
                denizz_cost[key] = max(0.0,
                                       denizz_cost[key] * (denizz_size[key] / prev_size))
            history_br.append(bankroll + sum(our_cost.values()))

    # Settle all open legs
    wins = losses = 0
    resolved_pnl = 0.0
    roi_list: List[float] = []
    unresolved_count = 0
    rebuy_wins = rebuy_losses = 0
    rebuy_pnl = 0.0
    rebuy_roi_list: List[float] = []

    # map key -> per-leg invested in rebuys (for attribution)
    rebuy_invested_per_key: Dict[Tuple[str, str], float] = defaultdict(float)
    for ev in rebuy_events:
        rebuy_invested_per_key[(ev["cid"], ev["token"])] += ev["rebuy_usd"]

    leg_outcomes: Dict[Tuple[str, str], Dict] = {}

    for key, cost in our_cost.items():
        if cost <= 0.01 and our_shares[key] <= 1e-4:
            continue
        info = res_map.get(key)
        invested = cost
        if info is None:
            unresolved_count += 1
            payout = invested * 0.95
            pnl = payout - invested
            roi = pnl / invested if invested > 0 else 0
            bankroll += payout
            # don't count unresolved in WR
            leg_outcomes[key] = {"status": "unresolved", "pnl": pnl, "roi": roi,
                                 "invested": invested}
            continue
        is_winner, denizz_roi = info
        if denizz_roi is not None:
            payout = invested * (1.0 + denizz_roi)
        elif is_winner:
            payout = our_shares[key] * 1.0
        else:
            payout = 0.0
        pnl = payout - invested
        roi = pnl / invested if invested > 0 else 0
        bankroll += payout
        resolved_pnl += pnl
        roi_list.append(roi)
        if pnl > 0:
            wins += 1
        else:
            losses += 1
        leg_outcomes[key] = {"status": "resolved", "pnl": pnl, "roi": roi,
                             "invested": invested, "is_winner": is_winner,
                             "denizz_roi": denizz_roi}

    # Attribute rebuy-specific PnL proportionally per leg
    # For a leg with rebuy_invested=R and total invested=T → rebuy pnl = leg_pnl * (R/T)
    rebuy_resolved_wins = 0
    rebuy_resolved_losses = 0
    rebuy_resolved_pnl = 0.0
    rebuy_resolved_invested = 0.0
    rebuy_resolved_roi_usd_weighted = 0.0
    rebuy_unresolved = 0
    rebuy_unresolved_pnl = 0.0
    rebuy_unresolved_invested = 0.0
    rebuy_leg_rois = []
    for key, rebuy_inv in rebuy_invested_per_key.items():
        lo = leg_outcomes.get(key)
        total_cost = our_cost.get(key, 0.0)
        # If leg was fully sold before resolution, we still want attribution
        # For legs fully liquidated by follow-sell, our_cost[key]=0 and lo missing.
        if lo is None:
            # fully liquidated by follow-sell → approximate pnl=0 on the rebuy
            # (all proceeds already hit bankroll during simulation).
            continue
        if total_cost <= 0:
            continue
        share = min(1.0, rebuy_inv / total_cost) if total_cost > 0 else 0.0
        leg_pnl = lo["pnl"]
        attributed_pnl = leg_pnl * share
        attributed_inv = rebuy_inv
        attributed_roi = attributed_pnl / attributed_inv if attributed_inv > 0 else 0
        if lo["status"] == "resolved":
            if attributed_pnl > 0:
                rebuy_resolved_wins += 1
            else:
                rebuy_resolved_losses += 1
            rebuy_resolved_pnl += attributed_pnl
            rebuy_resolved_invested += attributed_inv
            rebuy_leg_rois.append(attributed_roi)
        else:
            rebuy_unresolved += 1
            rebuy_unresolved_pnl += attributed_pnl
            rebuy_unresolved_invested += attributed_inv

    # Drawdown on history_br
    dd = 0.0
    rp = history_br[0] if history_br else BANKROLL
    for v in history_br:
        if v > rp:
            rp = v
        cur = (rp - v) / rp if rp > 0 else 0.0
        if cur > dd:
            dd = cur

    # Bucket breakdown of rebuy events by price
    buckets = defaultdict(lambda: {"n": 0, "usd": 0.0})
    for ev in rebuy_events:
        b = ev["price_bucket"]
        buckets[b]["n"] += 1
        buckets[b]["usd"] += ev["rebuy_usd"]

    summary = {
        "config": {
            "enable_rebuy": enable_rebuy,
            "BET_FORMULA_A": BET_FORMULA_A,
            "BET_FORMULA_B": BET_FORMULA_B,
            "MIN_BET_FORMULA": MIN_BET_FORMULA,
            "MAX_BET_USD": MAX_BET_USD,
            "MAX_POSITION_USD": MAX_POSITION_USD,
            "MIN_UPGRADE_USD": MIN_UPGRADE_USD,
            "MIN_BET_USD_LIVE": MIN_BET_USD_LIVE,
            "MIN_PLAYER_INVESTED_DENIZZ": MIN_PLAYER_INVESTED_DENIZZ,
            "BANKROLL": BANKROLL,
            "RESERVE": RESERVE,
            "REBUY_THROTTLE_SEC": REBUY_THROTTLE_SEC,
            "PRICE_RISK_TIERS": PRICE_RISK_TIERS,
            "TOPUP_RATIO_TIERS": TOPUP_RATIO_TIERS,
        },
        "final_bankroll": round(bankroll, 2),
        "return_pct": round((bankroll - BANKROLL) / BANKROLL, 4),
        "max_drawdown_pct": round(dd, 4),
        "history_br_len": len(history_br),
        "trades_first_entry": trades_first_entry,
        "trades_upgrade": trades_upgrade,
        "rebuy_events_count": len(rebuy_events),
        "rebuy_unique_legs": len(rebuy_invested_per_key),
        "rebuy_usd_total": round(sum(r["rebuy_usd"] for r in rebuy_events), 2),
        "rebuy_skipped": {
            "throttle": skipped_rebuy_throttle,
            "smallbuy": skipped_rebuy_smallbuy,
            "mincost": skipped_rebuy_mincost,
            "bankroll": skipped_rebuy_bankroll,
            "cap_reached": skipped_rebuy_capreached,
            "below_min_live": skipped_rebuy_lowsize,
        },
        "rebuy_resolved": {
            "n": rebuy_resolved_wins + rebuy_resolved_losses,
            "wins": rebuy_resolved_wins,
            "losses": rebuy_resolved_losses,
            "wr": (rebuy_resolved_wins / (rebuy_resolved_wins + rebuy_resolved_losses)
                   if (rebuy_resolved_wins + rebuy_resolved_losses) else 0.0),
            "mean_roi": statistics.mean(rebuy_leg_rois) if rebuy_leg_rois else 0.0,
            "median_roi": statistics.median(rebuy_leg_rois) if rebuy_leg_rois else 0.0,
            "invested_usd": round(rebuy_resolved_invested, 2),
            "pnl_usd": round(rebuy_resolved_pnl, 2),
            "ev_per_dollar": (rebuy_resolved_pnl / rebuy_resolved_invested
                              if rebuy_resolved_invested > 0 else 0.0),
        },
        "rebuy_unresolved": {
            "n": rebuy_unresolved,
            "invested_usd": round(rebuy_unresolved_invested, 2),
            "pnl_usd_estimate": round(rebuy_unresolved_pnl, 2),
        },
        "total_resolved_legs": wins + losses,
        "total_wins": wins,
        "total_losses": losses,
        "total_unresolved_legs": unresolved_count,
        "total_mean_roi": statistics.mean(roi_list) if roi_list else 0.0,
        "total_resolved_pnl": round(resolved_pnl, 2),
        "price_bucket_breakdown": {k: v for k, v in buckets.items()},
    }
    return {"summary": summary, "events": rebuy_events}


def main():
    with open(ACT, "r", encoding="utf-8") as f:
        activity = json.load(f)
    print(f"Activity records: {len(activity)}")
    res_map = build_resolution_map()
    print(f"Resolutions mapped: {len(res_map)}")

    # ----- CONTROL run: rebuy OFF -----
    print("\n=== CONTROL (rebuy OFF) ===")
    control = run_backtest(activity, res_map, enable_rebuy=False)
    cs = control["summary"]
    print(f"Final BR: ${cs['final_bankroll']}  ret={cs['return_pct']*100:+.1f}%  DD={cs['max_drawdown_pct']*100:.1f}%")
    print(f"First entries: {cs['trades_first_entry']}  Upgrades: {cs['trades_upgrade']}")
    print(f"Resolved legs: {cs['total_resolved_legs']}  W/L: {cs['total_wins']}/{cs['total_losses']}  meanROI={cs['total_mean_roi']:+.3f}")

    with open(OUT_CONTROL, "w", encoding="utf-8") as f:
        json.dump(cs, f, indent=2, default=str)

    # ----- TREATMENT run: rebuy ON -----
    print("\n=== TREATMENT (rebuy ON) ===")
    treat = run_backtest(activity, res_map, enable_rebuy=True)
    ts = treat["summary"]
    print(f"Final BR: ${ts['final_bankroll']}  ret={ts['return_pct']*100:+.1f}%  DD={ts['max_drawdown_pct']*100:.1f}%")
    print(f"First entries: {ts['trades_first_entry']}  Upgrades: {ts['trades_upgrade']}")
    print(f"Rebuy events: {ts['rebuy_events_count']}  Unique legs: {ts['rebuy_unique_legs']}  USD: ${ts['rebuy_usd_total']}")
    print(f"Skipped breakdown: {ts['rebuy_skipped']}")
    rr = ts["rebuy_resolved"]
    print(f"Rebuy resolved: N={rr['n']} W/L={rr['wins']}/{rr['losses']} WR={rr['wr']*100:.1f}% meanROI={rr['mean_roi']:+.3f} EV/$={rr['ev_per_dollar']:+.3f} pnl=${rr['pnl_usd']}")
    print(f"Rebuy unresolved: N={ts['rebuy_unresolved']['n']} inv=${ts['rebuy_unresolved']['invested_usd']}")
    print(f"Total resolved: W/L={ts['total_wins']}/{ts['total_losses']}  meanROI={ts['total_mean_roi']:+.3f}")

    # Delta
    print("\n=== DELTA (treatment - control) ===")
    print(f"Final BR delta: ${ts['final_bankroll'] - cs['final_bankroll']:+.2f}")
    print(f"Return delta:   {(ts['return_pct']-cs['return_pct'])*100:+.2f}pp")
    print(f"Additional trades taken: {ts['trades_upgrade'] + ts['rebuy_events_count'] + ts['trades_first_entry'] - (cs['trades_upgrade'] + cs['trades_first_entry'])}")

    # Price-bucket table
    print("\n=== Rebuy events by price bucket ===")
    for b in PRICE_RISK_BUCKET_LABELS:
        for lo, hi, _ in PRICE_RISK_TIERS:
            label = f"{lo:.2f}-{hi:.2f}"
            if label == b:
                break
        row = ts["price_bucket_breakdown"].get(b, {"n": 0, "usd": 0})
        print(f"  {b:<15}  n={row['n']:>4}  usd=${row['usd']:>8.2f}")

    with open(OUT_SUMMARY, "w", encoding="utf-8") as f:
        json.dump(ts, f, indent=2, default=str)
    with open(OUT_EVENTS, "w", encoding="utf-8") as f:
        json.dump(treat["events"], f, indent=2, default=str)

    print(f"\nWrote {OUT_SUMMARY}\nWrote {OUT_EVENTS}\nWrote {OUT_CONTROL}")


if __name__ == "__main__":
    main()
