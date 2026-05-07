"""Enumerate top-10 rebuy events by size & per-leg ROI attribution.

Reads rebuy_events.json + resolution data and produces a ranked table for
inclusion in the human report.
"""
from __future__ import annotations
import io
import json
import os
import sys
from collections import defaultdict
from typing import Dict, Tuple, Optional

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BASE = r"C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2\_analytics\data"
EVENTS = os.path.join(BASE, "rebuy_events.json")
CLOSED = os.path.join(BASE, "denizz_closed_positions_raw.json")
RES = os.path.join(BASE, "denizz_resolutions.json")
OUT = os.path.join(BASE, "rebuy_top10.json")

with open(EVENTS, "r", encoding="utf-8") as f:
    events = json.load(f)
with open(CLOSED, "r", encoding="utf-8") as f:
    closed = json.load(f)
with open(RES, "r", encoding="utf-8") as f:
    resolutions = json.load(f)

# (cid, tok) -> ROI from closed positions
res_map: Dict[Tuple[str, str], Tuple[str, float]] = {}
for c in closed:
    cp = c.get("curPrice")
    if cp not in (0.0, 1.0, 0, 1):
        continue
    inv = float(c.get("totalBought") or 0)
    pnl = float(c.get("realizedPnl") or 0)
    if inv < 1:
        continue
    res_map[(c.get("conditionId"), str(c.get("asset")))] = ("resolved", pnl / inv)
for cid, r in resolutions.items():
    if not r.get("resolved"):
        continue
    for tok in r.get("tokens", []):
        key = (cid, str(tok.get("token_id")))
        if key in res_map:
            continue
        res_map[key] = ("resolved_win" if tok.get("winner") else "resolved_lose",
                        1.0 if tok.get("winner") else -1.0)

# Attach outcome to each event
annotated = []
for ev in events:
    key = (ev["cid"], ev["token"])
    info = res_map.get(key)
    if info is None:
        ev["outcome"] = "unresolved"
        ev["leg_roi"] = None
        ev["rebuy_pnl"] = None
    else:
        status, roi = info
        ev["outcome"] = status
        ev["leg_roi"] = round(roi, 4)
        ev["rebuy_pnl"] = round(ev["rebuy_usd"] * roi, 2)
    annotated.append(ev)

# Sort: resolved winners first by pnl, then by usd for unresolved
def sort_key(ev):
    if ev["rebuy_pnl"] is None:
        return (0, -ev["rebuy_usd"])  # unresolved: biggest size first, low priority
    return (1, -ev["rebuy_pnl"])

annotated.sort(key=lambda e: (e["rebuy_pnl"] if e["rebuy_pnl"] is not None else -999999),
               reverse=True)

top10 = annotated[:10]

print(f"{'date':<11} {'price':>6} {'rebuy$':>7} {'ROI':>7} {'pnl$':>7}  title")
for ev in top10:
    date = ev["iso"][:10]
    price = ev["price"]
    rebuy = ev["rebuy_usd"]
    roi = ev["leg_roi"]
    pnl = ev["rebuy_pnl"]
    title = ev["title"]
    print(f"{date:<11} {price:>6.3f} ${rebuy:>6.2f} "
          f"{'n/a' if roi is None else f'{roi:+.2%}':>7} "
          f"{'n/a' if pnl is None else f'${pnl:+.2f}':>7}  {title}")

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(top10, f, indent=2, default=str)
print(f"\nWrote {OUT}")

# summary counts
resolved_count = sum(1 for e in annotated if e["leg_roi"] is not None)
unresolved_count = sum(1 for e in annotated if e["leg_roi"] is None)
print(f"\nTotal rebuy events: {len(annotated)}")
print(f"  resolved: {resolved_count}")
print(f"  unresolved: {unresolved_count}")
# By outcome
wins_pos = sum(1 for e in annotated if e["leg_roi"] is not None and e["leg_roi"] > 0)
losses_pos = sum(1 for e in annotated if e["leg_roi"] is not None and e["leg_roi"] <= 0)
print(f"  resolved wins (ROI>0): {wins_pos}  resolved losses: {losses_pos}")
