"""Passive limit SELL 100% Hamas disarm YES @ $0.30 GTC."""
import sys, io
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

TOKEN = "63234707295320507667894309258849048700632767113302157839265845777836046390818"
TITLE = "Will Hamas agree to disarm by June 30?"
KEY   = "0xsync_64ca77326caf39f557a7b4e2d290325e"
SHARES_TO_SELL = 150.0
LIMIT_PRICE = 0.30

bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"YES bid/ask: ${bid:.4f}/${ask:.4f}  limit ${LIMIT_PRICE} (passive, above ask)")
print(f"SELL: {TITLE}  {SHARES_TO_SELL} sh")

result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=SHARES_TO_SELL)
if not result or not result.get("order_id"):
    print("place_limit_sell failed"); sys.exit(1)
oid = result["order_id"]
print(f"Order LIVE: {oid[:24]}...  size={result.get('size_shares')}")
print(f"Sitting on book @ ${LIMIT_PRICE} GTC — fills when buyers step up.")
print(f"At fill: revenue ~${SHARES_TO_SELL * LIMIT_PRICE:.2f}  cost $27.00  PnL +${SHARES_TO_SELL * LIMIT_PRICE - 27:.2f}")
