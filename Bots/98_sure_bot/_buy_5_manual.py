"""Buy 5 positions manually at best ask. Register in copybot tracker
with signal_player=denizz so standard exit logic applies.
"""
import sys, os, json, time, math
from datetime import datetime, timezone

sys.path.insert(0, r'c:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot')
os.chdir(r'c:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot')

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from web3 import Web3
from config import CLOB_HOST, CHAIN_ID, OUR_PRIVATE_KEY, OUR_WALLET, POLYGON_RPC

COPYBOT_POS = r"c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/positions.json"
COPYBOT_BUF = r"c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/buy_buffers.json"

CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
ctf = w3.eth.contract(address=Web3.to_checksum_address(CTF),
    abi=[{"constant": True, "inputs": [{"name": "a", "type": "address"}, {"name": "id", "type": "uint256"}],
          "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}],
          "type": "function", "stateMutability": "view"}])
usdc_c = w3.eth.contract(address=Web3.to_checksum_address(USDC),
    abi=[{"constant": True, "inputs": [{"name": "a", "type": "address"}], "name": "balanceOf",
          "outputs": [{"name": "", "type": "uint256"}], "type": "function", "stateMutability": "view"}])

c = ClobClient(CLOB_HOST, key=OUR_PRIVATE_KEY, chain_id=CHAIN_ID, signature_type=0, funder=OUR_WALLET)
c.set_api_creds(c.create_or_derive_api_creds())

# Load buy plan
plan = json.load(open('/tmp/buy_plan.json', 'r'))
print(f"Buy plan: {len(plan)} markets, total ${sum(p['budget'] for p in plan)}")
cash = usdc_c.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call() / 1e6
print(f"USDC: ${cash:.2f}\n")

results = []
for item in plan:
    title = item['title']
    outcome = item['outcome']
    tok = item['token']
    cid = item['cid']
    budget = item['budget']

    print(f"{'='*60}")
    print(f"{title} [{outcome}] ${budget}")

    # Fresh best ask
    book = c.get_order_book(tok)
    asks = sorted([(float(a.price), float(a.size)) for a in (book.asks if hasattr(book, 'asks') else [])], key=lambda x: x[0])
    if not asks:
        print(f"  NO ASKS — skip")
        continue
    # Find price with enough cumulative depth
    cum = 0
    limit_price = asks[0][0]
    for p, s in asks:
        cum += p * s
        if cum >= budget:
            limit_price = p
            break
    limit_price = round(limit_price, 3)

    shares = math.floor((budget / limit_price) * 100) / 100
    cost = round(shares * limit_price, 4)
    while cost > budget:
        shares = round(shares - 0.01, 2)
        cost = round(shares * limit_price, 4)

    pre_bal = ctf.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET), int(tok)).call() / 1e6
    print(f"  price={limit_price}  shares={shares}  cost=${cost:.2f}  pre_bal={pre_bal:.2f}")

    args = OrderArgs(token_id=tok, price=limit_price, size=shares, side="BUY")
    signed = c.create_order(args)
    resp = c.post_order(signed, OrderType.GTC)
    if not (resp and resp.get("success")):
        print(f"  REJECTED: {resp}")
        continue
    oid = resp.get("orderID", "")
    print(f"  order: {oid[:25]}...")

    # Poll balance
    start = time.time()
    filled = 0
    while time.time() - start < 120:
        cur = ctf.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET), int(tok)).call() / 1e6
        filled = cur - pre_bal
        if filled >= shares - 0.5:
            break
        time.sleep(5)

    try:
        c.cancel(oid)
    except Exception:
        pass

    if filled < 0.5:
        print(f"  NOTHING FILLED")
        continue

    actual_cost = round(filled * limit_price, 4)
    print(f"  FILLED: {filled:.2f} sh @ {limit_price} = ${actual_cost:.2f}")

    results.append({
        'title': title,
        'outcome': outcome,
        'token': tok,
        'cid': cid,
        'shares': filled,
        'price': limit_price,
        'cost': actual_cost,
        'order_id': oid,
    })

# Update tracker
print(f"\n{'='*60}")
print(f"Updating tracker with {len(results)} positions")
d = json.load(open(COPYBOT_POS, 'r', encoding='utf-8'))
now_iso = datetime.now(timezone.utc).isoformat()

for r in results:
    # Check if open position already exists on this (cid, token)
    existing_key = None
    for k, p in d.get("positions", {}).items():
        if (p.get("condition_id") == r['cid']
                and str(p.get("token_id")) == str(r['token'])
                and p.get("status") == "open"):
            existing_key = k
            break

    if existing_key:
        # Aggregate
        pos = d["positions"][existing_key]
        old_sh = float(pos.get("size_shares", 0))
        old_cost = float(pos.get("cost_usd", 0))
        new_sh = round(old_sh + r['shares'], 6)
        new_cost = round(old_cost + r['cost'], 4)
        pos["size_shares"] = new_sh
        pos["cost_usd"] = new_cost
        pos["avg_entry"] = round(new_cost / new_sh, 6) if new_sh > 0 else r['price']
        pos["signal_player"] = "denizz"
        oids = pos.get("order_ids") or [existing_key]
        oids.append(r['order_id'])
        pos["order_ids"] = oids
        manual = pos.get("manual_additions", [])
        manual.append({
            "when": now_iso, "shares": r['shares'], "price": r['price'],
            "cost": r['cost'], "order_id": r['order_id'],
            "note": f"manual buy ${r['cost']:.2f}",
        })
        pos["manual_additions"] = manual
        print(f"  AGGREGATED: {r['title'][:40]} → {old_sh:.2f}+{r['shares']:.2f}={new_sh:.2f}")
    else:
        # New position
        d["positions"][r['order_id']] = {
            "condition_id": r['cid'],
            "token_id": r['token'],
            "title": r['title'],
            "outcome": r['outcome'],
            "event_slug": "",
            "entry_price": r['price'],
            "avg_entry": r['price'],
            "size_shares": r['shares'],
            "cost_usd": r['cost'],
            "tier": "A",
            "strategy": "standard",
            "signal_player": "denizz",
            "parts_filled": 1,
            "parts_planned": 1,
            "order_ids": [r['order_id']],
            "timestamp": now_iso,
            "status": "open",
            "manual_additions": [{
                "when": now_iso, "shares": r['shares'], "price": r['price'],
                "cost": r['cost'], "order_id": r['order_id'],
                "note": f"manual buy ${r['cost']:.2f}",
            }],
        }
        print(f"  NEW: {r['title'][:40]} → {r['shares']:.2f} sh")

with open(COPYBOT_POS, 'w', encoding='utf-8') as f:
    json.dump(d, f, indent=2, ensure_ascii=False)
print("tracker saved")

# Update buy_buffers — mark as signaled
try:
    b = json.load(open(COPYBOT_BUF, 'r', encoding='utf-8'))
except Exception:
    b = {}
sk = b.get("signaled_keys") or {}
denizz_sk = sk.get("denizz") or {}
for r in results:
    marker = f"{r['cid']}_{r['token']}"
    denizz_sk[marker] = now_iso
sk["denizz"] = denizz_sk
b["signaled_keys"] = sk
with open(COPYBOT_BUF, 'w', encoding='utf-8') as f:
    json.dump(b, f, indent=2, ensure_ascii=False)
print("buy_buffers updated")

# Final USDC
cash2 = usdc_c.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call() / 1e6
total_spent = sum(r['cost'] for r in results)
print(f"\nUSDC: ${cash2:.2f} (delta ${cash2-cash:+.2f}, spent ${total_spent:.2f})")
print(f"\nSummary:")
for r in results:
    print(f"  {r['shares']:8.2f} sh @ {r['price']:.3f} = ${r['cost']:7.2f}  {r['title'][:50]} [{r['outcome']}]")
