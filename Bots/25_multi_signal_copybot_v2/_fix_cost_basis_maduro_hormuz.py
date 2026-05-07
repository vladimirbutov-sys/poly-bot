"""Correct cost_usd / avg_entry for Maduro + Hormuz positions.

- Maduro: queried via executor.get_actual_fill — single trade, real VWAP $0.495.
- Hormuz: trade history is too tangled (40 trades, multiple in/out cycles, merge
  operations) to recompute reliably. Use Polymarket UI's stated avg ($0.257)
  as ground truth — Polymarket's UI knows the real cost basis after all merges
  and partial sells. Source: user screenshot 2026-04-17, "25.7c" avg.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

CORRECTIONS = [
    {
        "label": "Maduro Venezuela end 2026",
        "key_prefix": "0xmanual_6cb16f62918b057ec41a845e4cedb468",
        "source": "real fill via get_trades",
        "new_avg": 0.495,           # VWAP from confirmed trade
        "size_for_cost": None,       # use existing size_shares
    },
    {
        "label": "Hormuz traffic returns to normal April",
        "key_prefix": "0xc230fd694650a0af08d5389b51814ea987234f32dd3eae6e208e5ff5cf2ee848",
        "source": "Polymarket UI (user screenshot 2026-04-17)",
        "new_avg": 0.257,
        "size_for_cost": None,
    },
]

data = tracker.load()
saved = []

for c in CORRECTIONS:
    full_key = None
    pos = None
    for k, p in data.get("positions", {}).items():
        if k.startswith(c["key_prefix"]):
            full_key = k; pos = p; break
    if not pos or pos.get("status") != "open":
        print(f"SKIP {c['label']}: not found or not open"); continue

    size = c["size_for_cost"] if c["size_for_cost"] is not None else float(pos.get("size_shares") or 0)
    new_avg = round(c["new_avg"], 6)
    new_cost = round(size * new_avg, 6)

    old_cost = float(pos.get("cost_usd") or 0)
    old_avg = float(pos.get("avg_entry") or 0)

    print(f"\n{c['label']}")
    print(f"  source: {c['source']}")
    print(f"  size  : {size:.4f} sh")
    print(f"  BEFORE: avg ${old_avg:.4f}  cost ${old_cost:.2f}")
    print(f"  AFTER : avg ${new_avg:.4f}  cost ${new_cost:.2f}   (delta ${new_cost-old_cost:+.2f})")

    pos["cost_usd"] = new_cost
    pos["avg_entry"] = new_avg
    pos.setdefault("dedup_history", []).append({
        "at_local": "2026-04-17_cost_basis_fix",
        "reason": f"manual-buy script recorded cost = matched*LIMIT_PRICE; corrected via {c['source']}",
        "old_cost_usd": old_cost,
        "old_avg_entry": old_avg,
        "new_cost_usd": new_cost,
        "new_avg_entry": new_avg,
    })
    saved.append((c["label"], old_cost, new_cost, old_avg, new_avg))

if saved:
    tracker.save(data)
    print("\n=== SAVED ===")
    for label, oc, nc, oa, na in saved:
        print(f"  {label}: cost ${oc:.2f}->${nc:.2f}  avg ${oa:.4f}->${na:.4f}")
else:
    print("\n(no changes)")
