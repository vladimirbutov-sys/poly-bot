"""Manual BUY: Iran x Israel/US conflict ends by April 15, $300 at best_ask.
Aggregate into existing copybot record. signal_player=denizz."""
import sys, os, json, time, math
from datetime import datetime, timezone
import requests

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from web3 import Web3
from config import CLOB_HOST, CHAIN_ID, OUR_PRIVATE_KEY, OUR_WALLET

COPYBOT = r"c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/positions.json"
BUFFERS = r"c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/buy_buffers.json"
BUDGET = 300.00

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

# 1. Find existing record in copybot tracker
d = json.load(open(COPYBOT, "r", encoding="utf-8"))
matches = []
for k, p in d.get("positions", {}).items():
    title = p.get("title", "") or ""
    outc = (p.get("outcome", "") or "").lower()
    if "Iran" in title and "April 15" in title and "Israel" in title and outc == "yes":
        matches.append((k, p))

if not matches:
    print("ERROR: no existing April 15 Yes record in tracker — abort")
    sys.exit(1)

print(f"Found {len(matches)} matching records:")
for k, p in matches:
    print(f"  key={k[:22]}...  sh={p.get('size_shares',0):.2f}  "
          f"avg_entry={p.get('avg_entry',0):.4f}  status={p.get('status')}")

# Pick the OPEN record as primary
primary_key, primary = None, None
for k, p in matches:
    if p.get("status") == "open":
        primary_key, primary = k, p
        break
if primary is None:
    primary_key, primary = matches[0]

TOK = str(primary.get("token_id"))
COND = primary.get("condition_id")
print(f"\nprimary key: {primary_key[:30]}...")
print(f"token:     {TOK[:30]}...")
print(f"condition: {COND}")

# 2. data-api verification
r = requests.get(
    "https://data-api.polymarket.com/positions",
    params={"user": OUR_WALLET, "sizeThreshold": 0, "limit": 500},
    timeout=15,
)
for p in r.json():
    if str(p.get("asset", "")) == TOK:
        print(f"data-api: {p.get('title','?')[:55]}")
        print(f"  outcome={p.get('outcome')} size={p.get('size')} avg={p.get('avgPrice')}")
        break
else:
    print("(no data-api record for token)")

# 3. Cash check
cash = usdc.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call() / 1e6
print(f"\nUSDC: ${cash:.2f}  budget ${BUDGET}")
if cash < BUDGET + 5:
    print("NOT ENOUGH CASH — abort")
    sys.exit(1)

# 4. CLOB orderbook
c = ClobClient(CLOB_HOST, key=OUR_PRIVATE_KEY, chain_id=CHAIN_ID,
               signature_type=0, funder=OUR_WALLET)
c.set_api_creds(c.create_or_derive_api_creds())

book = c.get_order_book(TOK)
asks = book.asks if hasattr(book, "asks") else []
bids = book.bids if hasattr(book, "bids") else []
if not asks:
    print("NO ASKS — abort")
    sys.exit(1)

best_ask = min(float(a.price) for a in asks)
best_bid = max(float(b.price) for b in bids) if bids else 0
print(f"\nbest_bid {best_bid:.4f}  best_ask {best_ask:.4f}")
print("ask depth top 5:")
for a in sorted(asks, key=lambda x: float(x.price))[:5]:
    print(f"  {float(a.price):.4f} x {float(a.size):.2f}")

# 5. Compute shares strictly <= $300
limit_price = round(best_ask, 3)
raw_shares = BUDGET / limit_price
shares = math.floor(raw_shares * 100) / 100
cost = round(shares * limit_price, 4)
while cost > BUDGET:
    shares = round(shares - 0.01, 2)
    cost = round(shares * limit_price, 4)
print(f"\nPLAN: BUY {shares} sh @ {limit_price} = ${cost:.4f}")
assert cost <= BUDGET + 1e-6

# 6. Pre-balance
pre_bal = ctf.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET), int(TOK)).call() / 1e6
print(f"pre-buy on-chain: {pre_bal:.4f} sh")

# 7. Place limit BUY
print("\nplacing order...")
args = OrderArgs(token_id=TOK, price=limit_price, size=shares, side="BUY")
signed = c.create_order(args)
resp = c.post_order(signed, OrderType.GTC)
print(f"response: {resp}")
if not (resp and resp.get("success")):
    print("REJECTED — abort")
    sys.exit(1)

oid = resp.get("orderID", "")

# 8. Poll via actual balance delta
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
    print("\nNOTHING FILLED — abort tracker update")
    sys.exit(1)

actual_cost = round(filled * limit_price, 4)
print(f"\n=== FILLED: {filled:.4f} sh @ {limit_price} = ${actual_cost:.4f} ===")

# 9. Aggregate into primary tracker record
d = json.load(open(COPYBOT, "r", encoding="utf-8"))
pos = d["positions"][primary_key]
old_sh = float(pos.get("size_shares", 0))
old_cost = float(pos.get("cost_usd", 0))
new_sh = round(old_sh + filled, 6)
new_cost = round(old_cost + actual_cost, 4)
new_avg = round(new_cost / new_sh, 6) if new_sh > 0 else limit_price

pos["size_shares"] = new_sh
pos["cost_usd"] = new_cost
pos["avg_entry"] = new_avg
pos["signal_player"] = "denizz"
pos["parts_filled"] = int(pos.get("parts_filled", 1)) + 1
order_ids = pos.get("order_ids") or [primary_key]
order_ids.append(oid)
pos["order_ids"] = order_ids
pos["status"] = "open"

manual = pos.get("manual_additions", [])
manual.append({
    "when": datetime.now(timezone.utc).isoformat(),
    "shares": filled,
    "price": limit_price,
    "cost": actual_cost,
    "order_id": oid,
    "note": "manual $300 buy, user request",
})
pos["manual_additions"] = manual

with open(COPYBOT, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print(f"\nTracker updated:")
print(f"  size_shares: {old_sh:.2f} -> {new_sh:.2f}")
print(f"  cost_usd:    ${old_cost:.2f} -> ${new_cost:.2f}")
print(f"  avg_entry:   {new_avg:.4f}")
print(f"  signal_player: denizz")

# 10. buy_buffers.json — mark as already signaled so bot does not re-enter
try:
    bufs = json.load(open(BUFFERS, "r", encoding="utf-8"))
except Exception:
    bufs = {}
sk = bufs.get("signaled_keys") or {}
denizz_keys = sk.get("denizz") or {}
marker = f"{COND}:{TOK}"
denizz_keys[marker] = datetime.now(timezone.utc).isoformat()
sk["denizz"] = denizz_keys
bufs["signaled_keys"] = sk
with open(BUFFERS, "w", encoding="utf-8") as f:
    json.dump(bufs, f, indent=2, ensure_ascii=False)
print(f"buy_buffers.json: denizz signaled += {marker[:40]}...")

# 11. Final USDC
cash2 = usdc.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call() / 1e6
print(f"\nUSDC after: ${cash2:.2f}  (delta {cash2-cash:+.2f})")
