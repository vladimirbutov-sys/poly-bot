"""Compute per-price-bucket performance stats for denizz resolved positions.

Sources:
  A) denizz_closed_positions_raw.json — 100 closed positions with
     avgPrice, totalBought (USDC invested), realizedPnl (dollar PnL),
     curPrice (1=winner, 0=loser, other=still trading).
  B) denizz_activity_ALL.json + denizz_resolutions.json — for markets
     not present in (A) but present in the activity file and resolved
     per resolutions.json. We reconstruct per-leg invested / payout from
     BUY/SELL events.

Outputs:
  _analytics/data/price_risk_positions_denizz.json   (merged per-position)
  _analytics/data/price_risk_bucket_stats_denizz.json (aggregated)
"""
from __future__ import annotations
import json
import math
import os
import statistics
from collections import defaultdict
from typing import Dict, List, Tuple

BASE = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data"
ACT = os.path.join(BASE, "denizz_activity_ALL.json")
RES = os.path.join(BASE, "denizz_resolutions.json")
CLOSED = os.path.join(BASE, "denizz_closed_positions_raw.json")
POS_OUT = os.path.join(BASE, "price_risk_positions_denizz.json")
STATS_OUT = os.path.join(BASE, "price_risk_bucket_stats_denizz.json")

BUCKETS: List[Tuple[float, float, str]] = [
    (0.02, 0.15, "02-15c"),
    (0.15, 0.30, "15-30c"),
    (0.30, 0.50, "30-50c"),
    (0.50, 0.70, "50-70c"),
    (0.70, 0.85, "70-85c"),
    (0.85, 0.98, "85-98c"),
]


def bucket_of(price: float) -> str | None:
    for lo, hi, name in BUCKETS:
        if lo <= price < hi:
            return name
    return None


def build_from_closed_raw() -> List[Dict]:
    """Closed positions with curPrice in {0,1} are definitive resolutions."""
    with open(CLOSED, "r", encoding="utf-8") as f:
        closed = json.load(f)
    out = []
    for c in closed:
        cp = c.get("curPrice")
        # intermediate curPrice -> not yet resolved (still tradeable)
        if cp not in (0.0, 1.0, 0, 1):
            continue
        invested = float(c.get("totalBought") or 0.0)
        if invested < 1.0:
            continue
        pnl = float(c.get("realizedPnl") or 0.0)
        roi = pnl / invested
        avg_entry = float(c.get("avgPrice") or 0.0)
        if avg_entry <= 0 or avg_entry >= 1:
            continue
        out.append({
            "source": "closed_raw",
            "cid": c.get("conditionId"),
            "asset": c.get("asset"),
            "outcome": c.get("outcome"),
            "title": c.get("title"),
            "avg_entry": avg_entry,
            "invested": invested,
            "pnl": pnl,
            "roi": roi,
            "is_winner": (cp in (1.0, 1)),
            "first_buy_ts": c.get("timestamp"),
        })
    return out


def build_from_activity(exclude_cids: set[str]) -> List[Dict]:
    with open(ACT, "r", encoding="utf-8") as f:
        acts = json.load(f)
    with open(RES, "r", encoding="utf-8") as f:
        resolutions = json.load(f)

    legs: Dict[Tuple[str, str], Dict] = defaultdict(lambda: {
        "conditionId": None, "asset": None, "outcome": None, "title": None,
        "buys": [], "sells": [], "merges": 0.0, "redeems": 0.0,
    })
    for a in acts:
        cid = a.get("conditionId")
        if cid in exclude_cids:
            continue
        t = a.get("type")
        if t not in ("TRADE", "MERGE", "REDEEM"):
            continue
        key = (cid, a.get("asset"))
        leg = legs[key]
        leg["conditionId"] = cid
        leg["asset"] = a.get("asset")
        leg["outcome"] = a.get("outcome")
        leg["title"] = a.get("title")
        if t == "MERGE":
            leg["merges"] += float(a.get("size") or 0.0)
            continue
        if t == "REDEEM":
            leg["redeems"] += float(a.get("size") or 0.0)
            continue
        # TRADE
        side = a.get("side")
        ts = a.get("timestamp", 0)
        price = float(a.get("price") or 0.0)
        shares = float(a.get("size") or 0.0)
        usdc = float(a.get("usdcSize") or 0.0)
        rec = (ts, price, shares, usdc)
        if side == "BUY":
            leg["buys"].append(rec)
        elif side == "SELL":
            leg["sells"].append(rec)

    out = []
    for (cid, asset), leg in legs.items():
        if not leg["buys"]:
            continue
        res = resolutions.get(cid)
        if not res or not res.get("resolved"):
            continue
        is_winner = False
        for tok in res.get("tokens", []):
            if str(tok.get("token_id")) == str(asset):
                is_winner = bool(tok.get("winner"))
                break
        invested = sum(b[3] for b in leg["buys"])
        shares_bought = sum(b[2] for b in leg["buys"])
        if invested < 1.0:
            continue
        avg_entry = sum(b[1] * b[2] for b in leg["buys"]) / shares_bought if shares_bought else 0.0
        sell_revenue = sum(s[3] for s in leg["sells"])
        shares_sold = sum(s[2] for s in leg["sells"])
        remaining = shares_bought - shares_sold - leg["merges"] - leg["redeems"]
        payout = 0.0
        if is_winner:
            payout += max(remaining, 0.0) * 1.0
            payout += leg["redeems"]
        pnl = (sell_revenue + payout) - invested
        roi = pnl / invested if invested > 0 else 0.0
        ts_first = min(b[0] for b in leg["buys"])
        out.append({
            "source": "activity",
            "cid": cid,
            "asset": asset,
            "outcome": leg.get("outcome"),
            "title": leg.get("title"),
            "avg_entry": avg_entry,
            "invested": invested,
            "pnl": pnl,
            "roi": roi,
            "is_winner": is_winner,
            "first_buy_ts": ts_first,
        })
    return out


def compute_bucket_stats(positions: List[Dict]) -> Dict:
    bucket_positions: Dict[str, List[Dict]] = defaultdict(list)
    for p in positions:
        b = bucket_of(p["avg_entry"])
        if b is None:
            continue
        bucket_positions[b].append(p)

    out = {}
    for _, _, bname in BUCKETS:
        ps = bucket_positions.get(bname, [])
        n = len(ps)
        if n == 0:
            out[bname] = {"N": 0}
            continue
        rois = [p["roi"] for p in ps]
        wins = [p for p in ps if p["pnl"] > 0]
        losses = [p for p in ps if p["pnl"] <= 0]
        wr = len(wins) / n
        mean_roi = statistics.mean(rois)
        median_roi = statistics.median(rois)
        total_invested = sum(p["invested"] for p in ps)
        total_pnl = sum(p["pnl"] for p in ps)
        ev_per_dollar = (total_pnl / total_invested) if total_invested > 0 else None
        stddev_roi = statistics.stdev(rois) if n > 1 else 0.0
        sharpe_like = (mean_roi / stddev_roi) if stddev_roi else None
        avg_win_roi = statistics.mean([w["roi"] for w in wins]) if wins else 0.0
        avg_loss_roi = abs(statistics.mean([l["roi"] for l in losses])) if losses else 0.0
        if avg_win_roi > 0 and avg_loss_roi > 0 and wr:
            b_ratio = avg_win_roi / avg_loss_roi
            kelly = max(0.0, wr - (1.0 - wr) / b_ratio)
        else:
            kelly = None
        out[bname] = {
            "N": n, "wins": len(wins), "WR": wr,
            "mean_roi": mean_roi, "median_roi": median_roi,
            "ev_per_dollar": ev_per_dollar,
            "stddev_roi": stddev_roi, "sharpe_like": sharpe_like,
            "avg_win_roi": avg_win_roi, "avg_loss_roi": avg_loss_roi,
            "kelly_fraction": kelly,
            "total_invested": total_invested, "total_pnl": total_pnl,
        }
    return out


def main() -> None:
    closed_positions = build_from_closed_raw()
    closed_cids = set(p["cid"] for p in closed_positions)
    activity_positions = build_from_activity(exclude_cids=closed_cids)

    merged = closed_positions + activity_positions
    # de-dup by (cid, asset) in case of overlap
    seen = set()
    unique = []
    for p in merged:
        key = (p["cid"], str(p.get("asset") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)

    print(f"From closed_raw: {len(closed_positions)}")
    print(f"From activity+resolutions: {len(activity_positions)}")
    print(f"Merged unique: {len(unique)}")

    stats = compute_bucket_stats(unique)
    print()
    for lo, hi, bname in BUCKETS:
        s = stats[bname]
        if s.get("N", 0) == 0:
            print(f"[{bname}] N=0")
            continue
        sh = s.get("sharpe_like")
        kf = s.get("kelly_fraction")
        print(f"[{bname}] N={s['N']:3d} wins={s['wins']:3d} WR={s['WR']:.1%}"
              f"  meanROI={s['mean_roi']:+.3f}  medROI={s['median_roi']:+.3f}"
              f"  EV/$={s['ev_per_dollar']:+.3f}"
              f"  stdROI={s['stddev_roi']:.3f}"
              f"  Sharpe={'nan' if sh is None else f'{sh:+.3f}'}"
              f"  Kelly={'nan' if kf is None else f'{kf:.3f}'}")

    with open(POS_OUT, "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, default=str)
    with open(STATS_OUT, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, default=str)
    print("\nWrote", POS_OUT)
    print("Wrote", STATS_OUT)


if __name__ == "__main__":
    main()
