"""3-part entry strategy.

Part 1: 60% immediately when signal fires
Part 2: 25% after 2-4 hours if price didn't jump >15%
Part 3: 15% only if price dipped 10%+ from part 1

Pending parts are stored in signals.json and checked periodically.
"""
import json
import os
import time
from datetime import datetime, timezone
import executor
import tracker
import filters
import telegram_notify as tg
from config import (
    SIGNALS_FILE,
    ENTRY_PART1_PCT, ENTRY_PART2_PCT, ENTRY_PART3_PCT,
    ENTRY_PART2_DELAY_H, ENTRY_PART2_MAX_DELAY_H, ENTRY_PART2_MAX_RISE,
    ENTRY_PART3_DIP_PCT, ENTRY_PART3_EXPIRY_DAYS,
)


def _load_signals():
    if os.path.exists(SIGNALS_FILE):
        try:
            with open(SIGNALS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"pending": []}


def _save_signals(data):
    tmp = SIGNALS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, SIGNALS_FILE)


def calculate_total_bet(tier: str, available_balance: float, bankroll: float,
                        player_invested: float = 0, conviction_tiers=None,
                        min_bet_usd=None) -> float:
    """Calculate total bet size based on Car's conviction level."""
    if conviction_tiers is None:
        from config import CONVICTION_TIERS
        conviction_tiers = CONVICTION_TIERS
    if min_bet_usd is None:
        from config import MIN_BET_USD
        min_bet_usd = MIN_BET_USD

    pct = 0.02  # default fallback (smaller than crock95's 0.05)
    for min_inv, max_inv, tier_pct, tier_name in conviction_tiers:
        if min_inv <= player_invested < max_inv:
            pct = tier_pct
            break

    bet = bankroll * pct
    bet = min(bet, available_balance)

    if bet < min_bet_usd:
        return 0

    return bet


def execute_part1(token_id: str, price: float, total_bet: float,
                  condition_id: str, title: str, outcome: str,
                  event_slug: str, tier: str, signal_player: str = "") -> bool:
    """Execute part 1: 60% of total bet immediately."""
    part1_usd = total_bet * ENTRY_PART1_PCT

    if part1_usd < 1.0:
        print(f"[ENTRY] Part 1 too small: ${part1_usd:.2f}")
        return False

    # Get current best ask
    prices = filters.get_orderbook_prices(token_id)
    order_price = price
    if prices:
        order_price = prices[1]  # best ask
        if order_price <= 0 or order_price >= 1:
            order_price = price

    from config import DRY_RUN
    if False:  # DRY_RUN killed
        print(f"[DRY-RUN] Would BUY Part 1 [{signal_player}]: {title[:50]} | ${part1_usd:.2f} @ {order_price:.3f}")
        return False

    print(f"[ENTRY] Part 1 [{signal_player}]: {title[:50]} | ${part1_usd:.2f} @ {order_price:.3f}")
    result = executor.place_limit_buy(token_id, order_price, part1_usd)

    if not result:
        tg.error(f"Part 1 failed: {title[:40]}")
        return False

    # Record position (with signal_player)
    data = tracker.load()
    tracker.record_position(
        data, result["order_id"], condition_id, token_id,
        title, outcome, event_slug,
        order_price, result["size_shares"], result["cost_usd"],
        tier, part=1, signal_player=signal_player,
    )

    tg.buy_placed(title, 1, order_price, result["cost_usd"])

    # Schedule parts 2 and 3
    signal_data = _load_signals()
    signal_data["pending"].append({
        "token_id": token_id,
        "condition_id": condition_id,
        "title": title,
        "outcome": outcome,
        "event_slug": event_slug,
        "tier": tier,
        "total_bet": total_bet,
        "part1_price": order_price,
        "part1_time": datetime.now(timezone.utc).isoformat(),
        "part2_done": False,
        "part3_done": False,
        "signal_player": signal_player,
    })
    _save_signals(signal_data)

    # Wait for fill in background — use detailed variant to catch partial fills
    fill_info = executor.wait_for_fill_with_details(result["order_id"])
    status = fill_info.get("status", "UNKNOWN")
    size_matched = fill_info.get("size_matched", 0)
    size_original = fill_info.get("size_original", result["size_shares"])

    if status == "MATCHED":
        tg.buy_filled(title, 1, order_price, result["cost_usd"])
        print(f"[ENTRY] Part 1 FILLED: {title[:50]}")
        try:
            import limit_tracker
            limit_tracker.log_entry(token_id, title, order_price, result["size_shares"], result["cost_usd"])
        except Exception:
            pass
        return True

    if status == "PARTIAL":
        # Partial fill — keep the filled portion in tracker, shrink the record
        actual_cost = round(size_matched * order_price, 2)
        print(f"[ENTRY] Part 1 PARTIAL: {title[:50]} — filled {size_matched:.2f}/{size_original:.2f} sh, "
              f"kept ${actual_cost:.2f} in tracker")
        data = tracker.load()
        pos = data["positions"].get(result["order_id"])
        if pos:
            refund = pos["cost_usd"] - actual_cost
            if refund > 0:
                data["stats"]["current_balance"] += refund
            pos["size_shares"] = round(size_matched, 2)
            pos["cost_usd"] = actual_cost
            pos["_partial_fill_note"] = (
                f"Partial fill recovered: {size_matched:.2f}/{size_original:.2f} sh filled before timeout"
            )
            tracker.save(data)
            tg.buy_filled(f"{title} (PARTIAL {size_matched:.0f}/{size_original:.0f})",
                          1, order_price, actual_cost)
        try:
            import limit_tracker
            limit_tracker.log_entry(token_id, title, order_price, size_matched, actual_cost)
        except Exception:
            pass
        return True

    # Nothing filled — revert fully
    print(f"[ENTRY] Part 1 not filled ({status}): {title[:50]}")
    data = tracker.load()
    pos = data["positions"].get(result["order_id"])
    if pos:
        data["stats"]["current_balance"] += pos["cost_usd"]
        data["stats"]["total_bets"] -= 1
        del data["positions"][result["order_id"]]
        tracker.save(data)
    return False


# execute_hp_bet removed in v2 — HP strategy deleted, unified system for 82-99c


def check_pending_parts():
    """Check and execute pending part 2 and part 3 orders."""
    signal_data = _load_signals()
    now = datetime.now(timezone.utc)
    changed = False

    for sig in signal_data["pending"]:
        token_id = sig["token_id"]
        title = sig["title"]
        part1_price = sig["part1_price"]
        total_bet = sig["total_bet"]

        try:
            part1_time = datetime.fromisoformat(sig["part1_time"])
            if part1_time.tzinfo is None:
                part1_time = part1_time.replace(tzinfo=timezone.utc)
        except Exception:
            continue

        hours_since = (now - part1_time).total_seconds() / 3600
        days_since = hours_since / 24

        # Get current price
        prices = filters.get_orderbook_prices(token_id)
        if not prices:
            continue
        current_ask = prices[1]

        # --- PART 2: after 2-4 hours, if price didn't jump >15% ---
        if not sig["part2_done"] and ENTRY_PART2_DELAY_H <= hours_since <= ENTRY_PART2_MAX_DELAY_H:
            price_rise = (current_ask - part1_price) / part1_price if part1_price > 0 else 0

            if price_rise > ENTRY_PART2_MAX_RISE:
                print(f"[ENTRY] Part 2 SKIP: price rose {price_rise:.1%} > {ENTRY_PART2_MAX_RISE:.0%} | {title[:50]}")
                sig["part2_done"] = True
                sig["part2_skipped"] = "price_rose"
                changed = True
                continue

            part2_usd = total_bet * ENTRY_PART2_PCT
            data = tracker.load()
            available = tracker.get_available_balance(data)
            part2_usd = min(part2_usd, available)

            if part2_usd >= 1.0:
                print(f"[ENTRY] Part 2: {title[:50]} | ${part2_usd:.2f} @ {current_ask:.3f}")
                result = executor.place_limit_buy(token_id, current_ask, part2_usd)
                if result:
                    data = tracker.load()
                    tracker.record_position(
                        data, result["order_id"], sig["condition_id"], token_id,
                        title, sig["outcome"], sig["event_slug"],
                        current_ask, result["size_shares"], result["cost_usd"],
                        sig["tier"], part=2,
                    )
                    tg.buy_placed(title, 2, current_ask, result["cost_usd"])

            sig["part2_done"] = True
            changed = True

        # Part 2 expired (past max delay)
        elif not sig["part2_done"] and hours_since > ENTRY_PART2_MAX_DELAY_H:
            sig["part2_done"] = True
            sig["part2_skipped"] = "expired"
            changed = True

        # --- PART 3: if price dipped 10%+ from part 1 ---
        if not sig["part3_done"] and days_since <= ENTRY_PART3_EXPIRY_DAYS:
            price_drop = (part1_price - current_ask) / part1_price if part1_price > 0 else 0

            if price_drop >= ENTRY_PART3_DIP_PCT:
                part3_usd = total_bet * ENTRY_PART3_PCT
                data = tracker.load()
                available = tracker.get_available_balance(data)
                part3_usd = min(part3_usd, available)

                if part3_usd >= 1.0:
                    print(f"[ENTRY] Part 3 (dip {price_drop:.1%}): {title[:50]} | ${part3_usd:.2f} @ {current_ask:.3f}")
                    result = executor.place_limit_buy(token_id, current_ask, part3_usd)
                    if result:
                        data = tracker.load()
                        tracker.record_position(
                            data, result["order_id"], sig["condition_id"], token_id,
                            title, sig["outcome"], sig["event_slug"],
                            current_ask, result["size_shares"], result["cost_usd"],
                            sig["tier"], part=3,
                        )
                        tg.buy_placed(title, 3, current_ask, result["cost_usd"])

                sig["part3_done"] = True
                changed = True

        # Part 3 expired
        elif not sig["part3_done"] and days_since > ENTRY_PART3_EXPIRY_DAYS:
            sig["part3_done"] = True
            sig["part3_skipped"] = "expired"
            changed = True

    # Clean up fully processed signals
    signal_data["pending"] = [
        s for s in signal_data["pending"]
        if not (s.get("part2_done") and s.get("part3_done"))
    ]

    if changed:
        _save_signals(signal_data)
