"""Top-up Iran April 15 buy to reach $300 total."""
import sys, json, time, math
from datetime import datetime, timezone

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from web3 import Web3
from config import CLOB_HOST, CHAIN_ID, OUR_PRIVATE_KEY, OUR_WALLET

COPYBOT = r"c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/positions.json"
TOTAL_BUDGET = 300.00

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

# 1. Find primary open record (was updated by first script)
d = json.load(open(COPYBOT, "r", encoding="utf-8"))
primary_key, primary = None, None
for k, p in d.get("positions", {}).items():
    title = p.get("title", "") or ""
    outc = (p.get("outcome", "") or "").lower()
    if "Iran" in title and "April 15" in title and "Israel" in title and outc == "yes" and p.get("status") == "open":
        primary_key, primary = k, p
        break
if primary is None:
    print("no open record"); sys.exit(1)

TOK = str(primary.get("token_id"))
COND = primary.get("condition_id")
print(f"primary: {primary_key[:30]}...")
print(f"current size: {primary.get('size_shares')}  cost: ${primary.get('cost_usd')}  avg: {primary.get('avg_entry')}")

# 2. Calculate remaining budget from manual_additions so far
manual_spent = 0.0
for m in primary.get("manual_additions", []):
    manual_spent += float(m.get("cost", 0))
remaining = round(TOTAL_BUDGET - manual_spent, 4)
print(f"manual spent so far: ${manual_spent:.4f}")
print(f"remaining budget:    ${remaining:.4f}")
if remaining < 5:
    print("budget exhausted, done")
    sys.exit(0)

# 3. CLOB book
c = ClobClient(CLOB_HOST, key=OUR_PRIVATE_KEY, chain_id=CHAIN_ID,
               signature_type=0, funder=OUR_WALLET)
c.set_api_creds(c.create_or_derive_api_creds())

book = c.get_order_book(TOK)
asks = book.asks if hasattr(book, "asks") else []
if not asks:
    print("no asks"); sys.exit(1)

# Pick a price that has enough depth to fill the remaining budget
asks_sorted = sorted(asks, key=lambda x: float(x.price))
print("\nask depth:")
cum_cost = 0.0
chosen_price = None
for a in asks_sorted[:10]:
    p = float(a.price)
    s = float(a.size)
    lvl_cost = p * s
    cum_cost += lvl_cost
    print(f"  {p:.4f} x {s:9.2f}  cum_cost=${cum_cost:.2f}")
    if chosen_price is None and cum_cost >= remaining:
        chosen_price = p
print(f"\nchosen limit price: {chosen_price}")

if chosen_price is None:
    chosen_price = float(asks_sorted[-1].price)

limit_price = round(chosen_price, 3)
raw_shares = remaining / limit_price
shares = math.floor(raw_shares * 100) / 100
cost = round(shares * limit_price, 4)
while cost > remaining:
    shares = round(shares - 0.01, 2)
    cost = round(shares * limit_price, 4)
print(f"PLAN: BUY {shares} sh @ {limit_price} = ${cost:.4f}")

# 4. Pre-balance
pre_bal = ctf.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET), int(TOK)).call() / 1e6
print(f"pre-bal: {pre_bal:.4f}")

# 5. Order
args = OrderArgs(token_id=TOK, price=limit_price, size=shares, side="BUY")
signed = c.create_order(args)
resp = c.post_order(signed, OrderType.GTC)
print(f"resp: {resp}")
if not (resp and resp.get("success")):
    print("REJECTED"); sys.exit(1)
oid = resp.get("orderID", "")

# 6. Poll balance
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
    print("nothing filled")
    sys.exit(1)

actual_cost = round(filled * limit_price, 4)
print(f"\nFILLED: {filled:.4f} @ {limit_price} = ${actual_cost:.4f}")

# 7. Aggregate tracker
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
order_ids = pos.get("order_ids") or [primary_key]
order_ids.append(oid)
pos["order_ids"] = order_ids
manual = pos.get("manual_additions", [])
manual.append({
    "when": datetime.now(timezone.utc).isoformat(),
    "shares": filled,
    "price": limit_price,
    "cost": actual_cost,
    "order_id": oid,
    "note": "top-up to reach $300 total",
})
pos["manual_additions"] = manual
with open(COPYBOT, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

total_manual = sum(float(m.get("cost", 0)) for m in manual)
print(f"\nTracker:  {old_sh:.2f} -> {new_sh:.2f} sh  cost ${old_cost:.2f} -> ${new_cost:.2f}  avg {new_avg:.4f}")
print(f"Total manual spent on this position: ${total_manual:.2f} of ${TOTAL_BUDGET} budget")

cash = usdc.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call() / 1e6
print(f"USDC: ${cash:.2f}")
