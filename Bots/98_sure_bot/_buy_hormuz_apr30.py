"""Manual BUY: Strait of Hormuz traffic returns to normal by end of April.
YES, $25 at best ask. Одноразовый скрипт 2026-04-20.

НЕ добавляется в copybot tracker (это отдельная ручная ставка).
"""
import sys, os, json, time, math

sys.path.insert(0, r'c:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot')
os.chdir(r'c:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot')

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from web3 import Web3
from config import CLOB_HOST, CHAIN_ID, OUR_PRIVATE_KEY, OUR_WALLET, POLYGON_RPC

# ── Параметры сделки ─────────────────────────────────
TITLE = "Strait of Hormuz traffic returns to normal by end of April?"
TOKEN_ID = "77893140510362582253172593084218413010407941075415081594586195705930819989216"  # YES
CONDITION_ID = "0x924a2942747dd75703321a7c8d809c68f6a514c3b0f2a2e64274e02310634669"
BUDGET = 25.00  # USD

# ── Контракты ────────────────────────────────────────
CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
ctf = w3.eth.contract(
    address=Web3.to_checksum_address(CTF),
    abi=[{"constant": True, "inputs": [{"name": "a", "type": "address"}, {"name": "id", "type": "uint256"}],
          "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}],
          "type": "function", "stateMutability": "view"}],
)
usdc_c = w3.eth.contract(
    address=Web3.to_checksum_address(USDC),
    abi=[{"constant": True, "inputs": [{"name": "a", "type": "address"}], "name": "balanceOf",
          "outputs": [{"name": "", "type": "uint256"}], "type": "function", "stateMutability": "view"}],
)

# ── CLOB клиент ──────────────────────────────────────
c = ClobClient(CLOB_HOST, key=OUR_PRIVATE_KEY, chain_id=CHAIN_ID,
               signature_type=0, funder=OUR_WALLET)
c.set_api_creds(c.create_or_derive_api_creds())

# ── Баланс ───────────────────────────────────────────
cash = usdc_c.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET)).call() / 1e6
print(f"USDC balance: ${cash:.2f}")
if cash < BUDGET:
    print(f"ERROR: недостаточно USDC для покупки на ${BUDGET}")
    sys.exit(1)

print(f"\n{'='*60}")
print(f"{TITLE}")
print(f"YES за ${BUDGET}")
print(f"{'='*60}")

# ── Лучший ask + нужная глубина ──────────────────────
book = c.get_order_book(TOKEN_ID)
asks = sorted(
    [(float(a.price), float(a.size)) for a in (book.asks if hasattr(book, 'asks') else [])],
    key=lambda x: x[0],
)
if not asks:
    print("ERROR: нет asks в стакане")
    sys.exit(1)

# Цена с достаточной глубиной
cum = 0
limit_price = asks[0][0]
for p, s in asks:
    cum += p * s
    if cum >= BUDGET:
        limit_price = p
        break
limit_price = round(limit_price, 3)

shares = math.floor((BUDGET / limit_price) * 100) / 100
cost = round(shares * limit_price, 4)
while cost > BUDGET:
    shares = round(shares - 0.01, 2)
    cost = round(shares * limit_price, 4)

pre_bal = ctf.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET), int(TOKEN_ID)).call() / 1e6

print(f"  best ask:  ${asks[0][0]}")
print(f"  limit:     ${limit_price}")
print(f"  shares:    {shares}")
print(f"  cost:      ${cost:.2f}")
print(f"  pre_bal:   {pre_bal:.2f} sh")

# ── Отправка ордера ──────────────────────────────────
args = OrderArgs(token_id=TOKEN_ID, price=limit_price, size=shares, side="BUY")
signed = c.create_order(args)
resp = c.post_order(signed, OrderType.GTC)
if not (resp and resp.get("success")):
    print(f"REJECTED: {resp}")
    sys.exit(1)

oid = resp.get("orderID", "")
print(f"\norder submitted: {oid[:30]}...")

# ── Ждём исполнения ──────────────────────────────────
start = time.time()
filled = 0
while time.time() - start < 180:
    cur = ctf.functions.balanceOf(Web3.to_checksum_address(OUR_WALLET), int(TOKEN_ID)).call() / 1e6
    filled = cur - pre_bal
    if filled >= shares - 0.5:
        break
    print(f"  filled: {filled:.2f}/{shares} sh ({int(time.time()-start)}s)")
    time.sleep(10)

try:
    c.cancel(oid)
except Exception:
    pass

print(f"\n{'='*60}")
if filled < 0.5:
    print("NOTHING FILLED (кэнсл)")
    sys.exit(1)

actual_cost = round(filled * limit_price, 4)
print(f"FILLED: {filled:.2f} sh @ {limit_price} = ${actual_cost:.2f}")
print(f"{'='*60}")
print(f"Market: {TITLE}")
print(f"Order:  {oid}")
