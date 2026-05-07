"""Place two GTC limit sells — 50% each — and do NOT wait/cancel.
Orders stay live on the book.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker

ORDERS = [
    # (key_prefix, limit_price, label)
    ("0xbebc9542979584198224fb090c7d877c",
     0.58, "End enrichment Jun 30"),
    ("0x34268ab1f5eb173b3603289606f7e963",
     0.45, "Surrender stockpile Jun 30"),
]

data = tracker.load()

for key_prefix, limit_price, label in ORDERS:
    full_key = None
    pos = None
    for k, p in data["positions"].items():
        if k.startswith(key_prefix):
            full_key, pos = k, p
            break
    if not pos or pos.get("status") != "open":
        print(f"[{label}] not found or not open — SKIP\n")
        continue

    shares = round(float(pos.get("size_shares", 0)) * 0.5, 2)
    token = pos.get("token_id", "")

    print(f"=== {label} ===")
    print(f"  Selling 50% : {shares} sh @ limit ${limit_price} (GTC)")

    result = executor.place_limit_sell(token_id=token, price=limit_price, shares=shares)

    if isinstance(result, dict) and result.get("error") == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
        print(f"  SKIP: onchain balance too low ({result.get('onchain')})\n")
        continue
    if not result:
        print("  place_limit_sell returned None — FAIL\n")
        continue

    print(f"  ✓ LIVE on book  order_id: {result.get('order_id')}")
    print(f"    size_shares    : {result.get('size_shares')}")
    print(f"    price          : {result.get('price')}")
    print(f"    expected rev   : ${float(result.get('size_shares')) * limit_price:.2f}")
    avg = float(pos.get("avg_entry", 0) or 0)
    expected_pnl = (float(result.get('size_shares')) * limit_price) - (float(result.get('size_shares')) * avg)
    print(f"    expected PnL   : ${expected_pnl:+.2f}")
    print()
