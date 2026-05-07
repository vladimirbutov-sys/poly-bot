"""Silent A/B logging: track whether limit orders would have been better.

After each real trade (buy or sell), spawns a background thread that monitors
the price for 10-15 minutes and records whether a hypothetical limit order
at 2% better price would have filled.

Results written to limit_ab_log.csv — no impact on trading logic.
"""
import csv
import os
import threading
import time
from datetime import datetime, timezone

import filters

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "limit_ab_log.csv")

CSV_HEADER = [
    "timestamp", "market", "direction", "our_price", "our_shares", "our_usd",
    "limit_price_2pct", "best_price_in_window", "would_fill", "fill_minute",
    "savings_per_share", "savings_total_usd", "window_minutes", "checks_done",
]


def _ensure_csv():
    """Create CSV with header if it doesn't exist yet."""
    if not os.path.exists(CSV_PATH):
        try:
            with open(CSV_PATH, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(CSV_HEADER)
        except Exception:
            pass


def _append_row(row: list):
    _ensure_csv()
    try:
        with open(CSV_PATH, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(row)
    except Exception:
        pass


def _track_buy(token_id, title, our_price, our_shares, our_cost_usd):
    """Background: monitor best ask for 10 min, check if 2%-limit would fill."""
    try:
        limit_price = round(our_price * 0.98, 4)
        best_in_window = None
        fill_minute = 0
        checks = 0

        for i in range(20):  # 20 checks x 30s = 10 min
            time.sleep(30)
            checks += 1
            try:
                prices = filters.get_orderbook_prices(token_id)
                if prices is None:
                    continue
                ask = prices[1]  # best ask
                if best_in_window is None or ask < best_in_window:
                    best_in_window = ask
                if fill_minute == 0 and ask <= limit_price:
                    fill_minute = (i + 1) * 0.5  # minutes
            except Exception:
                continue

        would_fill = best_in_window is not None and best_in_window <= limit_price
        if best_in_window is None:
            best_in_window = our_price  # fallback

        savings_per_share = round(our_price - best_in_window, 6)
        savings_total = round(savings_per_share * our_shares, 4)

        _append_row([
            datetime.now(timezone.utc).isoformat(), title[:80], "BUY",
            our_price, our_shares, our_cost_usd,
            limit_price, round(best_in_window, 4), would_fill, fill_minute,
            savings_per_share, savings_total, 10, checks,
        ])

        print(f"[LIMIT_AB] Result: {title[:40]} would_fill={would_fill} savings={savings_per_share:.3f}")
    except Exception as e:
        print(f"[LIMIT_AB] BUY tracker error: {e}")


def _track_sell(token_id, title, our_price, our_shares, our_revenue):
    """Background: monitor best bid for 15 min, check if 2%-limit would fill."""
    try:
        limit_price = round(our_price * 1.02, 4)
        best_in_window = None
        fill_minute = 0
        checks = 0

        for i in range(30):  # 30 checks x 30s = 15 min
            time.sleep(30)
            checks += 1
            try:
                prices = filters.get_orderbook_prices(token_id)
                if prices is None:
                    continue
                bid = prices[0]  # best bid
                if best_in_window is None or bid > best_in_window:
                    best_in_window = bid
                if fill_minute == 0 and bid >= limit_price:
                    fill_minute = (i + 1) * 0.5
            except Exception:
                continue

        would_fill = best_in_window is not None and best_in_window >= limit_price
        if best_in_window is None:
            best_in_window = our_price

        savings_per_share = round(best_in_window - our_price, 6)
        savings_total = round(savings_per_share * our_shares, 4)

        _append_row([
            datetime.now(timezone.utc).isoformat(), title[:80], "SELL",
            our_price, our_shares, our_revenue,
            limit_price, round(best_in_window, 4), would_fill, fill_minute,
            savings_per_share, savings_total, 15, checks,
        ])

        print(f"[LIMIT_AB] Result: {title[:40]} would_fill={would_fill} savings={savings_per_share:.3f}")
    except Exception as e:
        print(f"[LIMIT_AB] SELL tracker error: {e}")


def log_entry(token_id, title, our_price, our_shares, our_cost_usd):
    """Start background tracking after a BUY fill."""
    try:
        print(f"[LIMIT_AB] Started tracking BUY {title[:40]} @ {our_price}")
        t = threading.Thread(
            target=_track_buy,
            args=(token_id, title, our_price, our_shares, our_cost_usd),
            daemon=True,
        )
        t.start()
    except Exception:
        pass


def log_exit(token_id, title, our_price, our_shares, our_revenue):
    """Start background tracking after a SELL fill."""
    try:
        print(f"[LIMIT_AB] Started tracking SELL {title[:40]} @ {our_price}")
        t = threading.Thread(
            target=_track_sell,
            args=(token_id, title, our_price, our_shares, our_revenue),
            daemon=True,
        )
        t.start()
    except Exception:
        pass
