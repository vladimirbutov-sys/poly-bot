"""Re-adopt orphan on-chain position: Iran x Israel/US conflict ends by April 7 YES.

Background: 22.12 sh of YES sit on-chain after multiple buy-sell cycles, but
tracker has 8 sold entries for the same (cid, token). The reverse-scan in
tracker.sync_with_onchain blocks re-adoption because existing_keys includes
all statuses (a 2026-04-15 fix to prevent re-adopt loops). Result:
_watchdog._verify_sync alerts on Telegram every 10 min.

Market is past its end_date (Apr 7) but UMA hasn't resolved yet. Current
bid $0.90 implies ~90% YES resolution. Re-adopting under bot's care:
  - Telegram alert stops immediately
  - redeemer.py auto-claims $1/sh when UMA resolves
  - follow-sell available if denizz exits remaining
"""
import sys, io, hashlib, time
from datetime import datetime, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import tracker, safe_sell, requests
from config import OUR_WALLET

CID   = "0x8183a221622f2d5d2b46da86c80d55a61f43d3"
TOKEN = "21743669032210695168079601505378236205866986767926346409604806906483294819314"
TITLE = "Iran x Israel/US conflict ends by April 7?"
SLUG  = "iran-x-israelus-conflict-ends-by-april-7"
OUTCOME = "Yes"

# Verify on-chain shares before adopting
onchain = safe_sell.get_wallet_balance(OUR_WALLET, TOKEN)
print(f"On-chain balance: {onchain} sh")
if not onchain or onchain < 1:
    print("On-chain balance < 1 — nothing to adopt. Exiting.")
    sys.exit(1)

# Get avg price from data-api positions endpoint (real cost basis)
print("Fetching avg price from data-api...")
r = requests.get(
    "https://data-api.polymarket.com/positions",
    params={"user": OUR_WALLET.lower(), "limit": 500, "sizeThreshold": 0.5},
    timeout=15,
).json()
avg_price = 0.0
for p in r:
    if p.get("conditionId") == CID and p.get("asset") == TOKEN:
        avg_price = float(p.get("avgPrice", 0) or 0)
        break
print(f"  avg price from API: ${avg_price:.4f}")
if avg_price <= 0:
    print("  WARN: avg price not found, using 0.50 fallback")
    avg_price = 0.50

import math
shares = math.floor(onchain * 100) / 100
cost = round(shares * avg_price, 6)

# Make sure no other open entry exists already (defensive)
data = tracker.load()
for k, p in data.get("positions", {}).items():
    if (p.get("condition_id") == CID
        and str(p.get("token_id")) == TOKEN
        and p.get("status") == "open"):
        print(f"Already an open entry: {k[:30]} (size={p.get('size_shares')})")
        print("Aborting to avoid duplicates.")
        sys.exit(2)

# Adopt with new key prefix to avoid confusion with 8 existing sold entries
new_key = "0xreadopt_" + hashlib.md5(f"{CID}_{TOKEN}_{time.time()}".encode()).hexdigest()[:32]
data.setdefault("positions", {})[new_key] = {
    "condition_id": CID,
    "token_id": TOKEN,
    "title": TITLE,
    "outcome": OUTCOME,
    "event_slug": SLUG,
    "entry_price": round(avg_price, 6),
    "avg_entry": round(avg_price, 6),
    "size_shares": shares,
    "cost_usd": cost,
    "tier": "manual",
    "strategy": "manual",
    "signal_player": "manual",
    "parts_filled": 1,
    "parts_planned": 1,
    "order_ids": [],
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "status": "open",
    "sells": [],
    "final_pnl": 0,
    "_adopted_from": "manual_readopt_orphan_2026-04-17",
    "_readopt_reason": "8 sold entries blocked sync reverse-scan; on-chain 22 sh leftover, market awaiting UMA resolution",
}

tracker.save(data)
print(f"\n✓ Adopted as {new_key[:30]}")
print(f"  size: {shares} sh  cost: ${cost}  avg: ${avg_price}")
print(f"  Telegram SYNC MISMATCH alert should clear on next watchdog cycle.")
print(f"  redeemer.py will auto-claim $1/sh when market resolves.")
