"""Sell all open positions at best bid price."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import executor
import filters
import tracker


def main():
    data = tracker.load()
    positions = tracker.get_open_positions(data)

    if not positions:
        print("No open positions to sell.")
        return

    print(f"=== Selling {len(positions)} positions at best bid ===\n")

    for key, pos in list(positions.items()):
        title = pos.get("title", "?")
        token_id = pos.get("token_id", "")
        shares = pos.get("size_shares", 0)
        entry = pos.get("avg_entry", pos.get("entry_price", 0))

        if shares < 0.5 or not token_id:
            print(f"SKIP {title[:50]} — no shares")
            continue

        # Get best bid
        prices = filters.get_orderbook_prices(token_id)
        if not prices:
            print(f"SKIP {title[:50]} — no orderbook")
            continue

        best_bid = prices[0]
        revenue = shares * best_bid
        pnl = revenue - pos.get("cost_usd", 0)

        print(f"{title[:55]}")
        print(f"  Entry: {entry:.3f} | Bid: {best_bid:.3f} | Shares: {shares:.2f}")
        print(f"  Revenue: ${revenue:.2f} | P&L: ${pnl:+.2f}")

        # Place sell at best bid
        result = executor.place_limit_sell(token_id, best_bid, shares)
        if result:
            order_id = result["order_id"]
            print(f"  SELL placed: {order_id[:20]}...")

            # Wait for fill (max 60 sec)
            status = executor.wait_for_fill(order_id, timeout=60)
            if status == "MATCHED":
                print(f"  ✓ SOLD @ {best_bid:.3f} — ${revenue:.2f}")
                data = tracker.load()
                tracker.record_sell(data, key, shares, best_bid, revenue, "manual_sell_all")
            else:
                print(f"  ✗ Not filled ({status}), retrying at bid - 1c...")
                retry_price = round(best_bid - 0.01, 2)
                if retry_price > 0.01:
                    result2 = executor.place_limit_sell(token_id, retry_price, shares)
                    if result2:
                        status2 = executor.wait_for_fill(result2["order_id"], timeout=60)
                        if status2 == "MATCHED":
                            revenue2 = shares * retry_price
                            print(f"  ✓ SOLD @ {retry_price:.3f} — ${revenue2:.2f}")
                            data = tracker.load()
                            tracker.record_sell(data, key, shares, retry_price, revenue2, "manual_sell_all_retry")
                        else:
                            print(f"  ✗ Retry also failed ({status2})")
        else:
            print(f"  ✗ Sell order failed")

        print()

    print("=== Done ===")


if __name__ == "__main__":
    main()
