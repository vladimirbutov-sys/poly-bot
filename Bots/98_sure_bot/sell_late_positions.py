"""
Sell stuck positions (end_date <= cutoff) via limit sell orders.
Price = max(best_bid, entry_price) — never sell below what we paid.
Orders are GTC — they stay until filled.

Dry-run by default — pass --execute to actually place sell orders.

Usage:
    py -3.12 sell_late_positions.py           # dry run
    py -3.12 sell_late_positions.py --execute  # place sell orders
"""
import json
import sys
import time
import math
import logging
from datetime import datetime, timezone
from pathlib import Path

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

from config import CLOB_HOST, CHAIN_ID, OUR_PRIVATE_KEY, OUR_WALLET

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sell")

POSITIONS_FILE = Path(__file__).parent / "positions.json"
CUTOFF_DATE = "2026-03-26T23:59:59Z"  # sell positions with end_date <= this

DRY_RUN = "--execute" not in sys.argv

_client = None


def get_client() -> ClobClient:
    global _client
    if _client is None:
        _client = ClobClient(
            CLOB_HOST,
            key=OUR_PRIVATE_KEY,
            chain_id=CHAIN_ID,
            signature_type=0,
            funder=OUR_WALLET,
        )
        _client.set_api_creds(_client.create_or_derive_api_creds())
    return _client


def get_best_bid(token_id: str) -> float | None:
    """Get best (highest) bid price from CLOB orderbook."""
    try:
        client = get_client()
        book = client.get_order_book(token_id)
        if not book:
            return None
        bids = book.bids if hasattr(book, 'bids') else []
        if not bids:
            return None
        # Bids are sorted ascending — best (highest) bid is last
        return max(float(b.price) for b in bids)
    except Exception as e:
        log.warning("Orderbook error for %s: %s", token_id[:20], e)
        return None


def place_sell_order(token_id: str, price: float, shares: float) -> dict | None:
    """Place a GTC limit sell order."""
    try:
        client = get_client()

        # Round shares down to 2 decimals (can't sell more than we have)
        shares = math.floor(shares * 100) / 100
        # Round price to 3 decimals (CLOB precision)
        price = round(price, 3)

        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=shares,
            side="SELL",
        )

        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)

        if response and response.get("success"):
            order_id = response.get("orderID", "")
            log.info("SELL order placed: %s | %.2f shares @ %.3f = $%.2f",
                     order_id[:16], shares, price, shares * price)
            return {"order_id": order_id, "price": price, "shares": shares}
        else:
            error_msg = response.get("errorMsg", "Unknown") if response else "No response"
            log.warning("SELL rejected: %s", error_msg)
            return None

    except Exception as e:
        log.error("SELL failed: %s", e)
        return None


def main():
    if DRY_RUN:
        log.info("=== DRY RUN (pass --execute to actually sell) ===")
    else:
        log.info("=== EXECUTING SELL ORDERS ===")

    data = json.load(open(POSITIONS_FILE, "r", encoding="utf-8"))
    positions = data["positions"]

    # Find open positions with end_date <= cutoff
    candidates = []
    for order_id, pos in positions.items():
        if pos.get("status") != "open":
            continue
        end_date = pos.get("end_date", "")
        if not end_date or end_date > CUTOFF_DATE:
            continue
        candidates.append((order_id, pos))

    candidates.sort(key=lambda x: x[1].get("end_date", ""))
    log.info("Open positions with end_date <= 2026-03-26: %d", len(candidates))

    if not candidates:
        log.info("Nothing to sell.")
        return

    # Check orderbook and build sell plan
    to_sell = []

    for order_id, pos in candidates:
        token_id = pos["token_id"]
        entry_price = pos["entry_price"]
        shares = pos["size_shares"]
        title = pos.get("title", "")[:60]

        best_bid = get_best_bid(token_id)
        time.sleep(0.3)

        if best_bid is None:
            log.info("SKIP (no bids): %s", title)
            continue

        # Sell price = max(best_bid, entry_price) — never sell below entry
        sell_price = max(best_bid, entry_price)
        will_fill = "instant" if best_bid >= entry_price else "waiting"
        pnl = (sell_price - entry_price) * shares

        to_sell.append({
            "order_id": order_id,
            "token_id": token_id,
            "title": pos.get("title", ""),
            "entry_price": entry_price,
            "best_bid": best_bid,
            "sell_price": sell_price,
            "shares": shares,
            "cost_usd": pos["cost_usd"],
            "end_date": pos.get("end_date", "")[:10],
            "pnl": pnl,
            "will_fill": will_fill,
        })

    # Show table
    print()
    log.info("%-3s %-42s %6s %6s %6s %7s %6s %7s",
             "#", "Title", "Entry", "Bid", "Sell@", "Shares", "Fill?", "PnL")
    log.info("-" * 95)

    total_cost = 0
    total_pnl = 0

    for i, item in enumerate(to_sell, 1):
        log.info("%-3d %-42s %6.3f %6.3f %6.3f %7.2f %6s %+7.3f",
                 i,
                 item["title"][:42],
                 item["entry_price"],
                 item["best_bid"],
                 item["sell_price"],
                 item["shares"],
                 item["will_fill"],
                 item["pnl"])
        total_cost += item["cost_usd"]
        total_pnl += item["pnl"]

    print()
    instant = sum(1 for x in to_sell if x["will_fill"] == "instant")
    waiting = sum(1 for x in to_sell if x["will_fill"] == "waiting")
    log.info("Total: %d orders (%d instant fill, %d will wait GTC)", len(to_sell), instant, waiting)
    log.info("Total cost: $%.2f", total_cost)
    log.info("Total PnL (if all fill): $%+.3f", total_pnl)

    if DRY_RUN:
        print()
        log.info("DRY RUN — no orders placed. Run with --execute to sell.")
        return

    # Execute sells
    print()
    log.info("Placing sell orders...")
    sold = 0
    failed = 0

    for item in to_sell:
        result = place_sell_order(
            token_id=item["token_id"],
            price=item["sell_price"],
            shares=item["shares"],
        )

        if result:
            sold += 1
            pos = positions[item["order_id"]]
            pos["status"] = "sold"
            pos["sell_order_id"] = result["order_id"]
            pos["sell_price"] = result["price"]
            pos["pnl"] = round((result["price"] - pos["entry_price"]) * result["shares"], 6)
            pos["sold_at"] = datetime.now(timezone.utc).isoformat()
        else:
            failed += 1

        time.sleep(0.5)

    # Save updated positions
    with open(POSITIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print()
    log.info("Done! Placed: %d, Failed: %d", sold, failed)
    log.info("Orders are GTC — instant fills done, rest will wait for buyers.")


if __name__ == "__main__":
    main()
