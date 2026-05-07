"""Manual BUY: Israel x Hezbollah ceasefire by April 30, 2026? — $75 at best_ask.
Outcome: NO (matches denizz). signal_player=denizz.
Aggregate into existing copybot tracker (will create new record if no open one).
"""
import sys, json, time, math
from datetime import datetime, timezone
import requests

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from web3 import Web3
from config import CLOB_HOST, CHAIN_ID, OUR_PRIVATE_KEY, OUR_WALLET

COPYBOT = r"c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/positions.json"
BUFFERS = r"c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/buy_buffers.json"
BUDGET = 75.00

# NO token of Hezbollah April 30 — verified from denizz position earlier
TOK = "38902668316823899581329108924389881286009857048696806385615295625967267371713"
COND = "0xc7140ddb5ae5dc94d4553fb05d4600816f33ff024844cebe8326f4c41c4a1a47"
TITLE = "Israel x Hezbollah ceasefire by April 30, 2026?"
OUTCOME = "No"

CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
w3 = Web3(Web3.HTTPProvider("https://polygon.gateway.tenderly.co"))
ctf = w3.eth.contract(
    address=Web3.to_checksum_address(CTF),
    abi=[{"constant": True, "inputs": [{"name": "a", "type": "address"}, {"name": "id", "type": "uint256"}],
          "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}],
          "type": "function", "stateMutability": "view"}],
)
usdc = w3.eth.contract(
    address=Web3.to_checksum_address(USDC),
    abi=[{"constant": True, "inputs": [{"name": "a", "type": "address"}], "name": "balanceOf",
          "outputs": [{"name": "", "type": "uint256"}], "type": "function", "stateMutability": "view"}],
)

# Cash check
cash = usdc.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call() / 1e6
print(f"USDC: ${cash:.2f}  budget ${BUDGET}")
if cash < BUDGET + 5:
    print("NOT ENOUGH CASH"); sys.exit(1)

# CLOB
c = ClobClient(CLOB_HOST, key=OUR_PRIVATE_KEY, chain_id=CHAIN_ID,
               signature_type=0, funder=OUR_WALLET)
c.set_api_creds(c.create_or_derive_api_creds())

book = c.get_order_book(TOK)
asks = book.asks if hasattr(book, "asks") else []
bids = book.bids if hasattr(book, "bids") else []
if not asks:
    print("NO ASKS"); sys.exit(1)
best_ask = min(float(a.price) for a in asks)
best_bid = max(float(b.price) for b in bids) if bids else 0
print(f"\nbest_bid {best_bid:.4f}  best_ask {best_ask:.4f}")
print("ask depth top 5:")
asks_sorted = sorted(asks, key=lambda x: float(x.price))
cum = 0.0
for a in asks_sorted[:5]:
    cum += float(a.price) * float(a.size)
    print(f"  {float(a.price):.4f} x {float(a.size):.2f}  cum=${cum:.2f}")

# Choose price with enough depth
chosen = best_ask
cum = 0.0
for a in asks_sorted:
    p = float(a.price); s = float(a.size)
    cum += p * s
    if cum >= BUDGET:
        chosen = p
        break
limit_price = round(chosen, 3)

raw_shares = BUDGET / limit_price
shares = math.floor(raw_shares * 100) / 100
cost = round(shares * limit_price, 4)
while cost > BUDGET:
    shares = round(shares - 0.01, 2)
    cost = round(shares * limit_price, 4)
print(f"\nPLAN: BUY {shares} sh @ {limit_price} = ${cost:.4f}")

pre_bal = ctf.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET), int(TOK)).call() / 1e6
print(f"pre-buy on-chain: {pre_bal:.4f} sh")

print("\nplacing order...")
args = OrderArgs(token_id=TOK, price=limit_price, size=shares, side="BUY")
signed = c.create_order(args)
resp = c.post_order(signed, OrderType.GTC)
print(f"resp: {resp}")
if not (resp and resp.get("success")):
    print("REJECTED"); sys.exit(1)
oid = resp.get("orderID", "")

start = time.time()
filled = 0.0
while time.time() - start < 180:
    cur = ctf.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET), int(TOK)).call() / 1e6
    filled = cur - pre_bal
    print(f"  t={int(time.time()-start):3}s  bal={cur:.4f}  filled={filled:.4f}/{shares}")
    if filled >= shares - 0.5:
        break
    time.sleep(5)

try:
    c.cancel(oid)
except Exception:
    pass

if filled < 0.5:
    print("nothing filled"); sys.exit(1)

actual_cost = round(filled * limit_price, 4)
print(f"\n=== FILLED: {filled:.4f} sh @ {limit_price} = ${actual_cost:.4f} ===")

# Update tracker — find existing OPEN record on this token, or create new one
import tracker
sys.path.insert(0, r'c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot')

d = json.load(open(COPYBOT, "r", encoding="utf-8"))

# Find existing OPEN record on this (cid, token)
existing_key = None
for k, p in d.get("positions", {}).items():
    if (p.get("condition_id") == COND and str(p.get("token_id")) == TOK
            and p.get("status") == "open"):
        existing_key = k
        break

now_iso = datetime.now(timezone.utc).isoformat()

if existing_key:
    pos = d["positions"][existing_key]
    old_sh = float(pos.get("size_shares", 0))
    old_cost = float(pos.get("cost_usd", 0))
    new_sh = round(old_sh + filled, 6)
    new_cost = round(old_cost + actual_cost, 4)
    pos["size_shares"] = new_sh
    pos["cost_usd"] = new_cost
    pos["avg_entry"] = round(new_cost / new_sh, 6) if new_sh > 0 else limit_price
    pos["signal_player"] = "denizz"
    order_ids = pos.get("order_ids") or [existing_key]
    order_ids.append(oid)
    pos["order_ids"] = order_ids
    manual = pos.get("manual_additions", [])
    manual.append({
        "when": now_iso, "shares": filled, "price": limit_price,
        "cost": actual_cost, "order_id": oid,
        "note": "manual $75 buy Hezbollah Apr30 (user request)",
    })
    pos["manual_additions"] = manual
    pos["status"] = "open"
    print(f"\nAggregated into existing key {existing_key[:25]}...")
    print(f"  size_shares: {old_sh:.2f} -> {new_sh:.2f}")
    print(f"  cost_usd:    ${old_cost:.2f} -> ${new_cost:.2f}")
    print(f"  avg_entry:   {pos['avg_entry']:.4f}")
else:
    # No open record — create one
    new_key = oid
    d["positions"][new_key] = {
        "condition_id": COND,
        "token_id": TOK,
        "title": TITLE,
        "outcome": OUTCOME,
        "event_slug": "iran-x-israelus-conflict-ends-by",
        "entry_price": limit_price,
        "avg_entry": limit_price,
        "size_shares": filled,
        "cost_usd": actual_cost,
        "tier": "A",
        "strategy": "standard",
        "signal_player": "denizz",
        "parts_filled": 1,
        "parts_planned": 1,
        "order_ids": [oid],
        "timestamp": now_iso,
        "status": "open",
        "manual_additions": [{
            "when": now_iso, "shares": filled, "price": limit_price,
            "cost": actual_cost, "order_id": oid,
            "note": "manual $75 buy Hezbollah Apr30 (user request)",
        }],
    }
    print(f"\nCreated NEW position record key={new_key[:30]}...")
    print(f"  shares: {filled:.2f}  cost: ${actual_cost:.2f}  avg: {limit_price:.4f}")

with open(COPYBOT, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("tracker saved")

# buy_buffers — mark as signaled
try:
    bufs = json.load(open(BUFFERS, "r", encoding="utf-8"))
except Exception:
    bufs = {}
sk = bufs.get("signaled_keys") or {}
denizz_keys = sk.get("denizz") or {}
marker = f"{COND}_{TOK}"  # main.py uses _ separator
denizz_keys[marker] = now_iso
sk["denizz"] = denizz_keys
bufs["signaled_keys"] = sk
with open(BUFFERS, "w", encoding="utf-8") as f:
    json.dump(bufs, f, indent=2, ensure_ascii=False)
print(f"buy_buffers: signaled_keys[denizz] += {marker[:50]}...")

# Final
cash2 = usdc.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call() / 1e6
print(f"\nUSDC after: ${cash2:.2f}  delta {cash2-cash:+.2f}")
