"""Re-adopt Netanyahu-Aoun NO position into tracker.

Background: tracker.sync_with_onchain falsely closed this position at 14:58
when an RPC call returned balance=0 (transient failure). On-chain balance
is actually 58 sh — we still own the shares, but bot doesn't see them and
can't apply follow-sell or stop-loss.

This script:
  1. Queries true on-chain balance (sanity check).
  2. Restores the original tracker record (key 0xmanual_c6038565...) with
     status=open, real shares, and cost basis from the actual fill price
     ($0.80 — confirmed via get_actual_fill earlier today).
  3. Records the re-adoption in dedup_history for forensics.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import tracker, safe_sell
from config import OUR_WALLET

KEY = "0xmanual_c6038565caf48436e07bf30f0e9827f6"
TOKEN = "23330623927523224976798170032966383651796457473765550056022078478545665896004"
ORIGINAL_AVG = 0.80   # real VWAP from manual_buy fill earlier today

onchain = safe_sell.get_wallet_balance(OUR_WALLET, TOKEN)
print(f"On-chain Netanyahu-Aoun NO balance: {onchain} sh")
if not onchain or onchain < 1:
    print("On-chain balance < 1 — nothing to re-adopt. Exiting.")
    sys.exit(1)

# Floor to 2 decimals (CLOB precision in tracker)
import math
shares = math.floor(onchain * 100) / 100
cost = round(shares * ORIGINAL_AVG, 6)

data = tracker.load()
pos = data["positions"].get(KEY)
if not pos:
    print(f"Position {KEY[:20]} not found in tracker. Aborting.")
    sys.exit(2)

print(f"\nBefore re-adopt:")
print(f"  status: {pos.get('status')}  size: {pos.get('size_shares')}  cost: ${pos.get('cost_usd')}")

old_status = pos.get("status")
old_size = pos.get("size_shares")
old_cost = pos.get("cost_usd")

# Restore
pos["status"] = "open"
pos["size_shares"] = shares
pos["cost_usd"] = cost
pos["avg_entry"] = ORIGINAL_AVG
pos["entry_price"] = ORIGINAL_AVG
# Clear any stale sells that the false sync may have added
# (but keep the historical sells list untouched if it's empty/intact)
pos.setdefault("dedup_history", []).append({
    "at_local": "2026-04-17_re-adopt_after_false_sync_close",
    "reason": "tracker.sync_with_onchain falsely closed this position when an "
              "RPC call returned balance=0 (transient). On-chain still has "
              f"{onchain} sh. Restoring real state.",
    "old_status": old_status,
    "old_size": old_size,
    "old_cost": old_cost,
    "new_size": shares,
    "new_cost": cost,
    "new_avg": ORIGINAL_AVG,
})

tracker.save(data)
print(f"\nAfter re-adopt:")
print(f"  status: open  size: {shares} sh  cost: ${cost}  avg: ${ORIGINAL_AVG}")
print(f"\n✓ Position restored. Bot will pick it up on next check_exits cycle.")
print(f"  follow-sell + stop-loss now active again.")
