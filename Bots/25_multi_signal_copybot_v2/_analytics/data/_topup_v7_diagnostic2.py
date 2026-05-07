"""Second-pass diagnostic: find optimal combination given RESERVE=$300 (user's
recalibrated safety floor at $4000 BR). MAX_POSITION_USD is a dial we can
tune.
"""
from __future__ import annotations
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _topup_v7_analysis import run_variant_bt, build_denizz_resolutions_map, ACT

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open(ACT, "r", encoding="utf-8") as f:
    activity = json.load(f)
res_map = build_denizz_resolutions_map()

PR_V3 = [
    (0.00, 0.15, 0.40), (0.15, 0.30, 0.70), (0.30, 0.50, 1.00),
    (0.50, 0.70, 0.85), (0.70, 0.85, 0.75), (0.85, 0.99, 0.60),
]
PR_V8 = [
    (0.00, 0.15, 0.40), (0.15, 0.30, 0.70), (0.30, 0.50, 1.00),
    (0.50, 0.70, 0.85), (0.70, 0.85, 0.70), (0.85, 0.99, 0.50),
]
T1 = [(0.00, 0.03, 0.0), (0.03, 0.10, 0.5), (0.10, 0.30, 0.75), (0.30, 999.0, 1.0)]
T2 = [
    (0.000, 0.020, 0.0), (0.020, 0.030, 0.3),
    (0.030, 0.100, 0.5), (0.100, 0.300, 0.75), (0.300, 999.0, 1.0),
]
T2b = [
    (0.000, 0.020, 0.0), (0.020, 0.030, 0.5),
    (0.030, 0.100, 0.5), (0.100, 0.300, 0.75), (0.300, 999.0, 1.0),
]
T3 = [
    (0.000, 0.015, 0.0), (0.015, 0.030, 0.35),
    (0.030, 0.100, 0.6), (0.100, 0.300, 0.85), (0.300, 999.0, 1.0),
]


def run(name, A, B, Mn, Mx, pr, tu, maxpos, minup, res):
    return run_variant_bt(
        name=name, A=A, B=B, MIN=Mn, MAX=Mx,
        price_risk_tiers=pr, topup_tiers=tu,
        activity=activity, res_map=res_map,
        max_position_usd=maxpos, min_upgrade_usd=minup,
        reserve=res,
    )


def show(rows, hdr):
    print(f"\n=== {hdr} ===")
    print(f"{'name':<36} {'final':>8} {'ret':>7} {'DD':>6} {'trades':>6} "
          f"{'sk_min':>6} {'sk_BR':>6} {'W':>3} {'L':>3} {'WR':>6}")
    for r in rows:
        print(f"{r['name']:<36} ${r['final_bankroll']:>7.0f} "
              f"{r['return_pct']:>+6.1%} {r['max_drawdown_pct']:>5.1%} "
              f"{r['trades_taken']:>6} {r['trades_skipped_min_upgrade']:>6} "
              f"{r['trades_skipped_bankroll']:>6} {r['wins']:>3} {r['losses']:>3} "
              f"{r['win_rate']:>5.1%}")


# Grid 1: sweep MAX_POSITION at res=300 for each formula variant
print("\n### Grid 1: MAX_POSITION sweep at RESERVE=$300 ###")
for maxpos in (250.0, 275.0, 300.0, 325.0, 350.0, 400.0, 500.0):
    rows = []
    for fname, A, B, Mn, Mx, pr in [
        ("V1_noPR", 31.75, -177.0, 20.0, 200.0, []),
        ("V3",      30.0,  -167.0, 15.0, 250.0, PR_V3),
        ("V7",      31.75, -177.0, 15.0, 250.0, PR_V3),
        ("V8",      31.75, -177.0, 15.0, 250.0, PR_V8),
    ]:
        rows.append(run(f"{fname}_pos{int(maxpos)}", A, B, Mn, Mx, pr, T1, maxpos, 5.0, 300.0))
    show(rows, f"MAX_POSITION = ${maxpos}")

# Grid 2: top-up at the winning formula / pos combo with res=300
# (We'll pick pos value from Grid 1 winner)
print("\n### Grid 2: TOP-UP at V7/res=300/pos=300 (candidate) ###")
rows = []
for tname, tu in [("T1", T1), ("T2", T2), ("T2b", T2b), ("T3", T3)]:
    rows.append(run(f"V7_{tname}_pos300", 31.75, -177.0, 15.0, 250.0, PR_V3, tu, 300.0, 5.0, 300.0))
show(rows, "V7/res=300/pos=300, top-up sweep")

print("\n### Grid 2b: TOP-UP at V8/res=300/pos=300 ###")
rows = []
for tname, tu in [("T1", T1), ("T2", T2), ("T2b", T2b), ("T3", T3)]:
    rows.append(run(f"V8_{tname}_pos300", 31.75, -177.0, 15.0, 250.0, PR_V8, tu, 300.0, 5.0, 300.0))
show(rows, "V8/res=300/pos=300, top-up sweep")

print("\n### Grid 3: RESERVE sweep (V3/V7/V8 at pos=300, T1) ###")
for res in (150.0, 200.0, 250.0, 300.0, 350.0, 400.0):
    rows = []
    for fname, A, B, Mn, Mx, pr in [
        ("V3", 30.0,  -167.0, 15.0, 250.0, PR_V3),
        ("V7", 31.75, -177.0, 15.0, 250.0, PR_V3),
        ("V8", 31.75, -177.0, 15.0, 250.0, PR_V8),
    ]:
        rows.append(run(f"{fname}_res{int(res)}", A, B, Mn, Mx, pr, T1, 300.0, 5.0, res))
    show(rows, f"RESERVE = ${res}")

# Final champions
print("\n### FINAL CHAMPIONS ###")
rows = []
rows.append(run("V3_T1_r300p300",  30.0,  -167.0, 15.0, 250.0, PR_V3, T1, 300.0, 5.0, 300.0))
rows.append(run("V7_T1_r300p300",  31.75, -177.0, 15.0, 250.0, PR_V3, T1, 300.0, 5.0, 300.0))
rows.append(run("V8_T1_r300p300",  31.75, -177.0, 15.0, 250.0, PR_V8, T1, 300.0, 5.0, 300.0))
rows.append(run("V3_T2_r300p300",  30.0,  -167.0, 15.0, 250.0, PR_V3, T2, 300.0, 5.0, 300.0))
rows.append(run("V7_T2_r300p300",  31.75, -177.0, 15.0, 250.0, PR_V3, T2, 300.0, 5.0, 300.0))
rows.append(run("V8_T2_r300p300",  31.75, -177.0, 15.0, 250.0, PR_V8, T2, 300.0, 5.0, 300.0))
rows.append(run("V8_T1_r200p300",  31.75, -177.0, 15.0, 250.0, PR_V8, T1, 300.0, 5.0, 200.0))
rows.append(run("V8_T2_r200p300",  31.75, -177.0, 15.0, 250.0, PR_V8, T2, 300.0, 5.0, 200.0))
show(rows, "Champions")
with open(os.path.join(os.path.dirname(ACT), "topup_v7_champions.json"), "w", encoding="utf-8") as f:
    json.dump(rows, f, indent=2, default=str)
print("\nWrote topup_v7_champions.json")
