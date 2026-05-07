"""Check neg_risk capital freeze — the actual bottleneck."""
import json
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))

with open('positions.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

open_p = [p for p in data['positions'].values() if p.get('status') == 'open']
neg_risk_open = [p for p in open_p if p.get('neg_risk', False)]
non_neg_risk = [p for p in open_p if not p.get('neg_risk', False)]

neg_frozen = sum(p.get('cost_usd', 0) for p in neg_risk_open)
non_neg_invested = sum(p.get('cost_usd', 0) for p in non_neg_risk)

print("=" * 70)
print("NEG_RISK CAPITAL ANALYSIS")
print("=" * 70)
print(f"Open positions: {len(open_p)}")
print(f"  neg_risk: {len(neg_risk_open)} positions, ${neg_frozen:.2f} frozen")
print(f"  regular:  {len(non_neg_risk)} positions, ${non_neg_invested:.2f}")
print()
print(f"Neg_risk limit: $300")
print(f"Current frozen: ${neg_frozen:.2f}")
if neg_frozen >= 300:
    print(f"LIMIT EXCEEDED by ${neg_frozen - 300:.2f}")
    print("ALL neg_risk candidates are BLOCKED!")
else:
    print(f"Room left: ${300 - neg_frozen:.2f}")
print()

# How many candidates are neg_risk?
import scanner
candidates = scanner.scan()
nr_candidates = sum(1 for c in candidates if c.get('neg_risk', False))
non_nr_candidates = len(candidates) - nr_candidates
print(f"Current candidates: {len(candidates)}")
print(f"  neg_risk: {nr_candidates} ({nr_candidates*100//len(candidates)}%)")
print(f"  regular:  {non_nr_candidates} ({non_nr_candidates*100//len(candidates)}%)")

# Show neg_risk positions
print()
print(f"Open neg_risk positions ({len(neg_risk_open)}):")
for p in sorted(neg_risk_open, key=lambda x: x.get('timestamp', '')):
    title = p.get('title', '')[:55]
    cost = p.get('cost_usd', 0)
    ts = p.get('timestamp', '')[:10]
    print(f"  {ts} | ${cost:.2f} | {title}")

# What % of candidates would be unblocked if we raise neg_risk limit?
print()
print("WHAT-IF: raise neg_risk limit")
import filters
import tracker

tdata = tracker.load()
open_cids = tracker.get_open_condition_ids(tdata)

orig_limit = filters.MAX_NEG_RISK_FROZEN
from config import MAX_NEG_RISK_FROZEN

for new_limit in [300, 400, 500, 600, 1000]:
    # Monkey-patch
    import config
    old_val = config.MAX_NEG_RISK_FROZEN
    config.MAX_NEG_RISK_FROZEN = new_limit
    # Need to reload the constant in filters module too
    filters_orig = filters.MAX_NEG_RISK_FROZEN if hasattr(filters, 'MAX_NEG_RISK_FROZEN') else None

    # Actually filters imports it at top level, so we need to patch filters module directly
    # Let's just simulate
    passed = 0
    for c in candidates:
        # Simulate: would this pass if neg_risk limit = new_limit?
        neg_risk = c.get('neg_risk', False)
        if neg_risk and neg_frozen >= new_limit:
            continue  # still blocked

        p, r = filters.run_all_filters(c, open_cids, tdata)
        if p:
            passed += 1
        elif "Neg_risk cap" in r and neg_frozen < new_limit:
            # Would pass with higher limit
            passed += 1

    config.MAX_NEG_RISK_FROZEN = old_val
    print(f"  Limit ${new_limit}: ~{passed} candidates pass")
