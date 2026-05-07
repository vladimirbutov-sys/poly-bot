"""Sell at market: Iran leadership change Jun 30 NO + Israel strike Yemen Apr 30 NO."""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters

POSITIONS = [
    {
        "key":   "0x5b6bdc406f77fd7ede4d8f10d4b0c19c85c7d3f28e7795f5b8774013a771ab52",
        "title": "Iran leadership change by June 30",
        "token": "114037086617269022315323137414379159845174084075275061115260986148267202915748",
        "shares": 111.58,
        "limit": 0.76,  # crosses best bid 0.77, fill at 0.77
    },
    {
        "key":   "0xmanual_6c3f24c0a5a32f16851875b9ec93b4af",
        "title": "Israel strike on Yemen by April 30",
        "token": "30561980169268678819735256982225694704116127378508623571936660192492766073388",
        "shares": 203.91,
        "limit": 0.94,  # crosses best bid 0.948, fill at 0.948
    },
]

for pos in POSITIONS:
    print(f"\n{'='*60}")
    print(f"SELL {pos['title']}")
    print(f"{'='*60}")
    bid, ask = filters.get_orderbook_prices(pos['token'])
    print(f"  live bid/ask: ${bid:.4f}/${ask:.4f}")
    print(f"  limit ${pos['limit']} on {pos['shares']} sh")

    result = executor.place_limit_sell(token_id=pos['token'], price=pos['limit'], shares=pos['shares'])
    if not result or not result.get("order_id"):
        print(f"  PLACE FAILED for {pos['title']}")
        continue
    oid = result["order_id"]
    print(f"  order: {oid[:24]}...")

    fill = executor.wait_for_fill_with_details(oid, timeout=90)
    matched = float(fill.get("size_matched") or 0)
    print(f"  status={fill.get('status')}  matched={matched:.2f}/{fill.get('size_original'):.2f}")
    if matched < 0.5:
        print(f"  Nothing filled, skipping tracker update")
        continue

    real = executor.get_actual_fill(oid)
    actual_price = real['vwap'] if (real and real['size'] > 0) else pos['limit']
    revenue = real['cost_usd'] if (real and real['size'] > 0) else matched * pos['limit']
    print(f"  VWAP ${actual_price:.4f}  revenue ${revenue:.2f}")

    # tracker update
    data = tracker.load()
    p = data.get("positions", {}).get(pos['key'])
    if p is None:
        print(f"  WARN: tracker key {pos['key']} not found")
        continue

    cur_sh = float(p.get("size_shares", 0))
    cost = float(p.get("cost_usd", 0))
    cost_sold = cost * (matched / cur_sh) if cur_sh > 0 else 0
    pnl = revenue - cost_sold
    new_sh = cur_sh - matched

    p["size_shares"] = round(new_sh, 4)
    p["cost_usd"] = round(cost - cost_sold, 4)
    p.setdefault("sells", []).append({
        "shares": round(matched, 4),
        "price": round(actual_price, 6),
        "revenue": round(revenue, 4),
        "pnl": round(pnl, 4),
        "reason": "manual_exit_market",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if new_sh < 0.5:
        p["status"] = "sold"
        p["final_pnl"] = round(pnl + sum(s.get('pnl',0) for s in p.get('sells',[])[:-1]), 4)

    tracker.save(data)
    print(f"  OK sold {matched:.2f} sh @ ${actual_price:.4f} = ${revenue:.2f}")
    print(f"     cost basis: ${cost_sold:.2f}  PnL ${pnl:+.2f}  status={p['status']}")
    time.sleep(2)
