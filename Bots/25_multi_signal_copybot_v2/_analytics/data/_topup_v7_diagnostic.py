"""Diagnostic: isolate why V3-in-this-harness ($4169) differs from original
price_risk_backtest V3 ($4851). Then produce a clean isolated comparison
holding everything fixed except the parameter under test.

Also produces a more targeted T2 variant with higher 2-3% multiplier, since
bucket EV/$ for 2-3% is positive (+0.228) on 7 resolved legs.
"""
from __future__ import annotations
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _topup_v7_analysis import (
    run_variant_bt, build_denizz_resolutions_map, ACT, formula_bet,
)

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import json as _json

with open(ACT, "r", encoding="utf-8") as f:
    activity = _json.load(f)
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
    (0.000, 0.020, 0.0),
    (0.020, 0.030, 0.3),
    (0.030, 0.100, 0.5),
    (0.100, 0.300, 0.75),
    (0.300, 999.0, 1.0),
]
T2b = [  # stronger mult in the 2-3% bucket (bucket EV/$ is +0.228)
    (0.000, 0.020, 0.0),
    (0.020, 0.030, 0.5),
    (0.030, 0.100, 0.5),
    (0.100, 0.300, 0.75),
    (0.300, 999.0, 1.0),
]
T3 = [
    (0.000, 0.015, 0.0),
    (0.015, 0.030, 0.35),
    (0.030, 0.100, 0.6),
    (0.100, 0.300, 0.85),
    (0.300, 999.0, 1.0),
]


def show(rows, hdr):
    print(f"\n=== {hdr} ===")
    print(f"{'name':<32} {'final':>8} {'ret':>7} {'DD':>6} {'trades':>6} "
          f"{'sk_min':>6} {'sk_BR':>6} {'W':>3} {'L':>3} {'WR':>6}")
    for r in rows:
        print(f"{r['name']:<32} ${r['final_bankroll']:>7.0f} "
              f"{r['return_pct']:>+6.1%} {r['max_drawdown_pct']:>5.1%} "
              f"{r['trades_taken']:>6} {r['trades_skipped_min_upgrade']:>6} "
              f"{r['trades_skipped_bankroll']:>6} {r['wins']:>3} {r['losses']:>3} "
              f"{r['win_rate']:>5.1%}")


# Step A: isolate each change from original V3 config to our new V3 config
# Original V3 (price_risk_backtest.py): RESERVE=200, MAX_POSITION=300, MIN_UPGRADE not enforced, BR=4000, topup=T1
# New V3 we evaluate: RESERVE=300, MAX_POSITION=400, MIN_UPGRADE_USD=5 enforced
step_a_variants = [
    ("V3_orig_style_res200_pos300", 200.0, 300.0, 1.0),  # closest to original paper result
    ("V3_res300_pos300",            300.0, 300.0, 5.0),
    ("V3_res300_pos400",            300.0, 400.0, 5.0),  # == current V3 default
    ("V3_res200_pos400",            200.0, 400.0, 5.0),
]
rows = []
for name, res, maxpos, minup in step_a_variants:
    r = run_variant_bt(
        name=name, A=30.0, B=-167.0, MIN=15.0, MAX=250.0,
        price_risk_tiers=PR_V3, topup_tiers=T1,
        activity=activity, res_map=res_map,
        max_position_usd=maxpos, min_upgrade_usd=minup,
        reserve=res,
    )
    rows.append(r)
show(rows, "STEP A — isolate RESERVE and MAX_POSITION impact on V3")

# Step B: top-up variants with tight reserve/max_position held (fair test)
step_b_variants = [
    ("T1_baseline",      T1, 300.0, 5.0),
    ("T2_soft_2-3_0.3",  T2, 300.0, 5.0),
    ("T2b_soft_2-3_0.5", T2b, 300.0, 5.0),
    ("T3_aggressive",    T3, 300.0, 3.0),
]
rows = []
for name, tu, maxpos, minup in step_b_variants:
    r = run_variant_bt(
        name=name, A=30.0, B=-167.0, MIN=15.0, MAX=250.0,
        price_risk_tiers=PR_V3, topup_tiers=tu,
        activity=activity, res_map=res_map,
        max_position_usd=maxpos, min_upgrade_usd=minup,
        reserve=300.0,
    )
    rows.append(r)
show(rows, "STEP B — TOP-UP VARIANTS at V3/res=300/pos=300")

# Step B': Same but at res=200/pos=300 (best-performing V3 above) to re-rank
rows2 = []
for name, tu, maxpos, minup in step_b_variants:
    r = run_variant_bt(
        name=name + "_r200p300", A=30.0, B=-167.0, MIN=15.0, MAX=250.0,
        price_risk_tiers=PR_V3, topup_tiers=tu,
        activity=activity, res_map=res_map,
        max_position_usd=maxpos, min_upgrade_usd=minup,
        reserve=200.0,
    )
    rows2.append(r)
show(rows2, "STEP B' — TOP-UP VARIANTS at V3/res=200/pos=300 (original-style)")

# Step C: Formula variants at res=300, pos=400 (real-world target config)
step_c_variants = [
    ("V1_noPR_res300p400",    31.75, -177.0, 20.0, 200.0, [],    T1),
    ("V3_res300p400",         30.0,  -167.0, 15.0, 250.0, PR_V3, T1),
    ("V7_res300p400",         31.75, -177.0, 15.0, 250.0, PR_V3, T1),
    ("V8_res300p400",         31.75, -177.0, 15.0, 250.0, PR_V8, T1),
]
rows = []
for name, A, B, Mn, Mx, pr, tu in step_c_variants:
    r = run_variant_bt(
        name=name, A=A, B=B, MIN=Mn, MAX=Mx,
        price_risk_tiers=pr, topup_tiers=tu,
        activity=activity, res_map=res_map,
        max_position_usd=400.0, min_upgrade_usd=5.0,
        reserve=300.0,
    )
    rows.append(r)
show(rows, "STEP C — FORMULA V1/V3/V7/V8 at res=300/pos=400")

# Step D: Same formula variants at res=200/pos=300 (closer to original backtest)
rows = []
for name, A, B, Mn, Mx, pr, tu in step_c_variants:
    r = run_variant_bt(
        name=name.replace("res300p400", "res200p300"),
        A=A, B=B, MIN=Mn, MAX=Mx,
        price_risk_tiers=pr, topup_tiers=tu,
        activity=activity, res_map=res_map,
        max_position_usd=300.0, min_upgrade_usd=5.0,
        reserve=200.0,
    )
    rows.append(r)
show(rows, "STEP D — FORMULA V1/V3/V7/V8 at res=200/pos=300 (original-style)")

# Step E: best T * best formula combined
# Pick winner from step B, combine with winner from step C
step_e_variants = [
    ("V7_T1_res300p400",  31.75, -177.0, 15.0, 250.0, PR_V3, T1, 400.0, 5.0, 300.0),
    ("V7_T2_res300p400",  31.75, -177.0, 15.0, 250.0, PR_V3, T2, 400.0, 5.0, 300.0),
    ("V7_T2b_res300p400", 31.75, -177.0, 15.0, 250.0, PR_V3, T2b, 400.0, 5.0, 300.0),
    ("V7_T2_res300p300",  31.75, -177.0, 15.0, 250.0, PR_V3, T2, 300.0, 5.0, 300.0),
    ("V3_T2_res300p300",  30.0,  -167.0, 15.0, 250.0, PR_V3, T2, 300.0, 5.0, 300.0),
    ("V3_T2b_res300p300", 30.0,  -167.0, 15.0, 250.0, PR_V3, T2b, 300.0, 5.0, 300.0),
]
rows = []
for name, A, B, Mn, Mx, pr, tu, maxpos, minup, res in step_e_variants:
    r = run_variant_bt(
        name=name, A=A, B=B, MIN=Mn, MAX=Mx,
        price_risk_tiers=pr, topup_tiers=tu,
        activity=activity, res_map=res_map,
        max_position_usd=maxpos, min_upgrade_usd=minup,
        reserve=res,
    )
    rows.append(r)
show(rows, "STEP E — combined V3/V7 × T1/T2/T2b")

# save all
all_rows = []
for step_label, vs in [("step_a", step_a_variants), ("step_c", step_c_variants)]:
    pass
# (Dump step-E only for brevity)
with open(os.path.join(os.path.dirname(ACT), "topup_v7_diagnostic_combined.json"), "w", encoding="utf-8") as f:
    json.dump(rows, f, indent=2, default=str)
print("\nWrote topup_v7_diagnostic_combined.json")
