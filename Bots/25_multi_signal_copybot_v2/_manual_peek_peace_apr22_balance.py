"""Peek on-chain balance + tracker shares for US x Iran peace Apr 22 YES."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import tracker, filters
from safe_sell import get_wallet_balance
from config import OUR_WALLET

TOKEN = "10355316169421062771540371697837923442956106006258739802114788264214901200573"
CID   = "0xbbc6689d0f6d57ea42168836712237c7308b3e0118c8914d31b6126d0f3254c5"

data = tracker.load()
total_tracker = 0.0
for k, p in (data.get("positions") or {}).items():
    if p.get("token_id") == TOKEN and p.get("status") == "open":
        sh = float(p.get("size_shares") or 0)
        print(f"  open {k[:24]}... size={sh} cost=${p.get('cost_usd')}")
        total_tracker += sh

onchain = get_wallet_balance(OUR_WALLET, TOKEN)
bid, ask = filters.get_orderbook_prices(TOKEN)
print(f"\nTotal tracker open shares : {total_tracker:.4f}")
print(f"On-chain balance          : {onchain:.4f}")
print(f"Live bid/ask              : ${bid:.3f} / ${ask:.3f}")
print(f"20% of on-chain           : {onchain * 0.20:.4f}")
