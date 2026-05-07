"""Bucket stats for OUR closed positions (the bot's own trades)."""
from __future__ import annotations
import json
import os
import statistics
from collections import defaultdict
from typing import Dict, List, Tuple

BASE = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2"
POS_FILE = os.path.join(BASE, "positions.json")
OUT = os.path.join(BASE, "_analytics", "data", "price_risk_bucket_stats_ours.json")

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


def main() -> None:
    with open(POS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    positions = data["positions"]
    closed = [p for p in positions.values()
              if float(p.get("size_shares") or 0.0) == 0.0
              and p.get("status") in ("sold", "closed", "lost", "redeemed", "won")]
    # Our closed positions: may still be unresolved market — use final_pnl if available
    cleaned = []
    for p in closed:
        invested = float(p.get("cost_usd") or 0.0)
        if invested < 0.5:
            continue
        final_pnl = p.get("final_pnl")
        if final_pnl is None:
            # fall back to sum(sells.pnl)
            final_pnl = sum(float(s.get("pnl") or 0.0) for s in p.get("sells", []))
        roi = (final_pnl / invested) if invested > 0 else 0.0
        cleaned.append({
            "cid": p.get("condition_id"),
            "outcome": p.get("outcome"),
            "title": p.get("title"),
            "avg_entry": float(p.get("avg_entry") or p.get("entry_price") or 0.0),
            "invested": invested,
            "pnl": float(final_pnl),
            "roi": roi,
            "tier": p.get("tier"),
        })

    print(f"Total closed positions from positions.json: {len(closed)}")
    print(f"After cleaning (invested >= $0.50): {len(cleaned)}")

    bucket_positions: Dict[str, List[Dict]] = defaultdict(list)
    for p in cleaned:
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
            print(f"[{bname}] N=0")
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
            kelly = max(0.0, wr - (1.0 - wr) / (avg_win_roi / avg_loss_roi))
        else:
            kelly = None
        out[bname] = {
            "N": n, "wins": len(wins), "WR": wr, "mean_roi": mean_roi,
            "median_roi": median_roi, "ev_per_dollar": ev_per_dollar,
            "stddev_roi": stddev_roi, "sharpe_like": sharpe_like,
            "kelly_fraction": kelly, "avg_win_roi": avg_win_roi,
            "avg_loss_roi": avg_loss_roi,
            "total_invested": total_invested, "total_pnl": total_pnl,
        }
        sh = sharpe_like
        kf = kelly
        print(f"[{bname}] N={n:3d} wins={len(wins):3d} WR={wr:.1%}"
              f"  meanROI={mean_roi:+.3f}  medROI={median_roi:+.3f}"
              f"  EV/$={ev_per_dollar:+.3f}  stdROI={stddev_roi:.3f}"
              f"  Sharpe={'nan' if sh is None else f'{sh:+.3f}'}"
              f"  Kelly={'nan' if kf is None else f'{kf:.3f}'}")

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print("\nWrote", OUT)


if __name__ == "__main__":
    main()
