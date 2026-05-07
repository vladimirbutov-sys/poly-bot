"""
One-time script: sell 5 of 6 old NO positions (from duplicate bug).
Keep position #6 (cheapest entry 0.187) + 2 new gradient positions.
"""
import sys
import time
import executor
import tracker
from config import NO_TOKEN_ID

# These are the 5 old positions to sell (all except the 0.187 entry)
POSITIONS_TO_SELL = [
    "0x50a49a9eaa476892033dcfde3cdaa2859fba86f9906e7e167ef59d4b38c5c2b0",
    "0x2b73e385a5e0cf38f3a8db73b3b63591cb47fb8768d966499e829e5758894855",
    "0x8d9ce08334b5de9c2d72c96897e8b3fa757f67791fe3778244855c070629e80d",
    "0x5446f85294983f535aeba4738a95717f4724e4b71461d9dfa21a2d8d3744f0e3",
    "0x36b2e7f79a42fd1db526b59e4284b92ee85f5d4e5e468e16a505e7826c1bece6",
]

def main():
    # Get current NO bid
    prices = executor.get_orderbook_prices(NO_TOKEN_ID)
    if not prices:
        print("ERROR: Cannot get NO orderbook")
        sys.exit(1)

    bid = prices[0]
    print(f"Current NO bid: ${bid:.3f}")

    data = tracker.load()
    total_revenue = 0
    total_cost = 0
    sold_count = 0

    for pos_key in POSITIONS_TO_SELL:
        pos = data["positions"].get(pos_key)
        if not pos or pos.get("status") != "open":
            print(f"SKIP {pos_key[:16]}... (not open)")
            continue

        shares = pos.get("size_shares", 0)
        cost = pos.get("cost_usd", 0)
        entry = pos.get("entry_price", 0)

        print(f"\nSelling {pos_key[:16]}...")
        print(f"  Entry: {entry:.3f} | Shares: {shares:.2f} | Cost: ${cost:.2f}")
        print(f"  Sell at: ${bid:.3f} | Revenue: ~${shares * bid:.2f} | P&L: ~${shares * bid - cost:+.2f}")

        result = executor.place_limit_sell(NO_TOKEN_ID, bid, shares)
        if not result:
            # Retry 2 cents lower
            retry_price = round(bid - 0.02, 3)
            print(f"  Failed, retrying at ${retry_price:.3f}...")
            result = executor.place_limit_sell(NO_TOKEN_ID, retry_price, shares)
            if result:
                bid_used = retry_price
            else:
                print(f"  FAILED completely, skipping")
                continue
        else:
            bid_used = bid

        # Wait for fill (max 2 min)
        status = executor.wait_for_fill(result["order_id"], timeout=120)
        if status == "MATCHED":
            revenue = shares * bid_used
            total_revenue += revenue
            total_cost += cost

            # Record in tracker
            data = tracker.load()
            tracker.record_sell(data, pos_key, bid_used, shares, revenue, "manual_sell_old_no")
            sold_count += 1
            print(f"  SOLD! Revenue: ${revenue:.2f} | P&L: ${revenue - cost:+.2f}")
        else:
            print(f"  Not filled: {status}")

        # Small pause between orders
        time.sleep(2)

    print(f"\n{'='*50}")
    print(f"Sold: {sold_count}/{len(POSITIONS_TO_SELL)} positions")
    print(f"Total revenue: ${total_revenue:.2f}")
    print(f"Total cost: ${total_cost:.2f}")
    print(f"Total P&L: ${total_revenue - total_cost:+.2f}")

    # Show remaining positions
    data = tracker.load()
    remaining = tracker.get_open_positions(data, "NO")
    print(f"\nRemaining NO positions: {len(remaining)}")
    for key, pos in remaining:
        print(f"  {key[:16]}... entry {pos['entry_price']:.3f}, "
              f"{pos['size_shares']:.1f} shares, ${pos['cost_usd']:.2f}")


if __name__ == "__main__":
    main()
