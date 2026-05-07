"""
Oil Swing Trading Bot — Full Rule Set
======================================
Buy YES gradually as WTI drops ($93/$91/$89), sell as WTI rises ($96/$98/$99).
Buy NO at WTI $97+, sell at WTI $93-.
Stop-losses: ceasefire $84, NO $105, theta 3 days, portfolio $200.
Dead zone 12-16 ET. Deadline March 26.
"""
import sys
import io
import os
import time
import logging
from datetime import datetime, timezone

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
except Exception:
    pass

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BOT_DIR, "bot.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("oil_bot")

import wti_monitor
import executor
import tracker
import strategy
import telegram_notify as tg
from config import (
    BANKROLL, SCAN_INTERVAL, YES_TOKEN_ID, NO_TOKEN_ID,
    YES_ENTRY_STEPS, YES_EXIT_STEPS, NO_ENTRY_STEPS,
    YES_PROFIT_TARGET, MAX_YES_ENTRY_PRICE, MAX_NO_ENTRY_PRICE,
    STEP_COOLDOWN,
)

# News Sentinel
sys.path.insert(0, os.path.normpath(os.path.join(BOT_DIR, "..", "shared_oil")))
try:
    from news_sentinel import NewsSentinel
    _sentinel = NewsSentinel(cache_minutes=15)
except ImportError:
    _sentinel = None
_last_news_level = "GREEN"


def log(msg: str):
    logger.info(msg)


def get_market_prices() -> dict:
    yes_prices = executor.get_orderbook_prices(YES_TOKEN_ID)
    no_prices = executor.get_orderbook_prices(NO_TOKEN_ID)
    return {
        "yes_bid": yes_prices[0] if yes_prices else 0,
        "yes_ask": yes_prices[1] if yes_prices else 1,
        "no_bid": no_prices[0] if no_prices else 0,
        "no_ask": no_prices[1] if no_prices else 1,
    }


def do_buy(side: str, price: float, size_usd: float, wti: float, step: int = -1) -> bool:
    """Execute a buy order."""
    token_id = YES_TOKEN_ID if side == "YES" else NO_TOKEN_ID
    log(f"BUY {side}: ${size_usd:.2f} @ {price:.3f} | WTI ${wti:.2f} | step {step}")

    result = executor.place_limit_buy(token_id, price, size_usd)
    if not result:
        log(f"BUY {side} FAILED")
        tg.error(f"BUY {side} failed at {price:.3f}")
        return False

    status = executor.wait_for_fill(result["order_id"])
    if status == "MATCHED":
        data = tracker.load()
        tracker.record_buy(
            data, result["order_id"], side, price,
            result["size_shares"], result["cost_usd"], wti, step,
        )
        tg.buy(side, price, result["cost_usd"], wti)
        log(f"BUY {side} FILLED: {result['size_shares']:.1f} shares @ {price:.3f} = ${result['cost_usd']:.2f}")
        return True
    else:
        log(f"BUY {side} not filled: {status}")
        return False


def do_sell(side: str, shares: float, price: float, wti: float, reason: str) -> bool:
    """Execute a sell order for given shares."""
    token_id = YES_TOKEN_ID if side == "YES" else NO_TOKEN_ID
    log(f"SELL {side}: {shares:.1f} shares @ {price:.3f} | reason: {reason}")

    result = executor.place_limit_sell(token_id, price, shares)
    if not result:
        # Retry at 3% lower price
        retry_price = round(price * 0.97, 3)
        log(f"SELL {side} failed, retry at {retry_price:.3f}")
        result = executor.place_limit_sell(token_id, retry_price, shares)
        if not result:
            log(f"SELL {side} FAILED completely")
            tg.error(f"SELL {side} failed")
            return False
        price = retry_price

    status = executor.wait_for_fill(result["order_id"], timeout=300)
    if status == "MATCHED":
        revenue = shares * price
        data = tracker.load()
        # Find matching position to record sell
        open_pos = tracker.get_open_positions(data, side)
        if open_pos:
            key, pos = open_pos[0]
            pnl = revenue - (pos["cost_usd"] * (shares / pos["size_shares"])
                             if pos["size_shares"] > 0 else 0)
            tracker.record_sell(data, key, price, shares, revenue, reason)
            tg.sell(side, price, revenue, pnl, reason, wti)
            log(f"SELL {side} FILLED: ${revenue:.2f} | P&L: ${pnl:+.2f}")
        return True
    else:
        log(f"SELL {side} not filled: {status}")
        return False


def sell_all(side: str, wti: float, reason: str):
    """Sell entire position of a side."""
    data = tracker.load()
    positions = tracker.get_open_positions(data, side)
    if not positions:
        return

    token_id = YES_TOKEN_ID if side == "YES" else NO_TOKEN_ID
    prices = executor.get_orderbook_prices(token_id)
    if not prices:
        log(f"SELL ALL {side}: no orderbook")
        return

    for key, pos in positions:
        shares = pos.get("size_shares", 0)
        if shares >= 0.5:
            do_sell(side, shares, prices[0], wti, reason)


def _check_step_cooldown(data: dict, steps_key: str, side: str) -> bool:
    """Check if enough time passed since last step entry (STEP_COOLDOWN seconds)."""
    done_steps = data.get(steps_key, [])
    if not done_steps:
        return True  # No previous steps, OK to proceed

    # Find the most recent position opened for this side
    latest_open = None
    for key, pos in data["positions"].items():
        if pos.get("side") == side and pos.get("status") == "open":
            opened_at = pos.get("opened_at", "")
            if opened_at:
                try:
                    dt = datetime.fromisoformat(opened_at)
                    if latest_open is None or dt > latest_open:
                        latest_open = dt
                except Exception:
                    pass

    if latest_open is None:
        return True

    if latest_open.tzinfo is None:
        latest_open = latest_open.replace(tzinfo=timezone.utc)

    elapsed = (datetime.now(timezone.utc) - latest_open).total_seconds()
    return elapsed >= STEP_COOLDOWN


_last_calibration = 0
CALIBRATION_INTERVAL = 8 * 3600  # 8 hours


def maybe_recalibrate():
    """Run calibration every 8 hours."""
    global _last_calibration
    now = time.time()
    if now - _last_calibration < CALIBRATION_INTERVAL:
        return
    try:
        import calibrate
        if calibrate.calibrate():
            log("Theta calibration updated")
        _last_calibration = now
    except Exception as e:
        log(f"Calibration failed: {e}")
        _last_calibration = now  # Don't retry immediately


def run_cycle():
    """One trading cycle — all rules applied."""
    maybe_recalibrate()

    # 1. Get WTI price
    wti = wti_monitor.get_wti_price()
    if not wti:
        log("WTI unavailable, skipping")
        return

    # Track WTI for momentum filter
    strategy.track_wti(wti)

    # === NEWS SENTINEL CHECK ===
    global _last_news_level
    if _sentinel:
        try:
            news_level = _sentinel.get_risk_level()
            # Alert on escalation to YELLOW/RED/BLACK
            if news_level in ("YELLOW", "RED", "BLACK") and news_level != _last_news_level:
                alert_text = _sentinel.format_alert_text()
                tg.news_alert(alert_text)
                log("NEWS: %s (was %s)" % (news_level, _last_news_level))
            _last_news_level = news_level
        except Exception as e:
            log("News sentinel error: %s" % e)

    # 2. Get market prices
    market = get_market_prices()
    yes_mid = (market["yes_bid"] + market["yes_ask"]) / 2 * 100

    # 3. Load state
    data = tracker.load()
    balance = tracker.get_balance(data)
    invested = tracker.get_invested(data)
    free = tracker.get_free_balance(data)
    portfolio = tracker.get_portfolio_value(data)
    has_yes = tracker.has_open(data, "YES")
    has_no = tracker.has_open(data, "NO")
    days_left = strategy.get_days_remaining()
    theta_mult = strategy.get_theta_multiplier()
    theta_adj = strategy.get_theta_adjustments()

    log(f"WTI: ${wti:.2f} | YES: {yes_mid:.1f}% | NO bid: {market['no_bid']:.4f} | Free: ${free:.2f} | "
        f"Invested: ${invested:.2f} | Days: {days_left} | Theta: {theta_mult:.0%} | "
        f"Profit×{theta_adj['profit_mult']:.2f} Price×{theta_adj['price_mult']:.2f}")

    # === STOP-LOSS CHECKS (always run, ignore dead zone) ===

    # Settlement check
    if strategy.check_settlement(wti):
        log(f"SETTLEMENT: WTI ${wti:.2f} >= $100!")
        tg.settlement_resolved(wti)
        return "RESOLVED"

    # Portfolio stop
    if strategy.check_stop_portfolio(balance, invested):
        log(f"PORTFOLIO STOP: ${portfolio:.2f} < $200")
        sell_all("YES", wti, "portfolio_stop")
        sell_all("NO", wti, "portfolio_stop")
        return "STOPPED"

    # Ceasefire stop — sell all YES
    if has_yes and strategy.check_stop_ceasefire(wti):
        log(f"CEASEFIRE STOP: WTI ${wti:.2f} < $84")
        sell_all("YES", wti, "ceasefire_stop")
        data = tracker.load()
        tracker.reset_yes_steps(data)
        return

    # NO stop — sell NO
    if has_no and strategy.check_stop_no(wti):
        log(f"NO STOP: WTI ${wti:.2f} > $105")
        sell_all("NO", wti, "no_stop_105")
        return

    # Theta stop — check each YES position
    if has_yes:
        for key, pos in tracker.get_open_positions(data, "YES"):
            if strategy.check_stop_theta(pos, wti):
                shares = pos.get("size_shares", 0)
                prices = executor.get_orderbook_prices(YES_TOKEN_ID)
                if prices and shares >= 0.5:
                    log(f"THETA STOP: YES held >3 days, WTI didn't move $3+")
                    do_sell("YES", shares, prices[0], wti, "theta_stop")

    # === DEADLINE CHECK ===
    if strategy.is_past_deadline():
        if has_yes or has_no:
            log("DEADLINE: closing all positions")
            sell_all("YES", wti, "deadline")
            sell_all("NO", wti, "deadline")
            data = tracker.load()
            tracker.reset_yes_steps(data)
        return

    # === DIVERGENCE CHECK ===
    div = strategy.check_divergence(wti, yes_mid)
    if div:
        log(f"DIVERGENCE: WTI {div['wti_change_pct']:+.1f}%, "
            f"YES {div['yes_change_pp']:+.1f}pp (expected {div['expected_pp']:+.1f}pp)")
        tg.divergence_alert(
            div["wti_change_pct"], div["yes_change_pp"],
            div["expected_pp"], wti, yes_mid,
        )
        # Flash crash — do NOT sell
        if strategy.is_flash_crash(div["wti_change_usd"], div["yes_change_pp"]):
            log("FLASH CRASH detected — NOT selling, waiting for recovery")
            return

    # === SELL SIGNALS (run even during dead zone) ===

    # --- Profit-based YES exit (OR condition, theta-adjusted) ---
    yes_target = YES_PROFIT_TARGET * theta_adj["profit_mult"]

    if has_yes:
        yes_sold_by_profit = False
        for key, pos in tracker.get_open_positions(data, "YES"):
            entry_price = pos.get("entry_price", 0)
            if entry_price > 0 and yes_target > 0 and market["yes_bid"] >= entry_price * (1 + yes_target):
                shares = pos.get("size_shares", 0)
                profit_pct = (market["yes_bid"] / entry_price - 1) * 100
                if shares >= 0.5:
                    log(f"SELL YES PROFIT: +{profit_pct:.0f}% (target +{yes_target:.1%}) "
                        f"(bought {entry_price:.3f}, now {market['yes_bid']:.3f})")
                    if do_sell("YES", shares, market["yes_bid"], wti,
                               f"profit_{profit_pct:.0f}pct"):
                        yes_sold_by_profit = True
        if yes_sold_by_profit:
            data = tracker.load()
            if not tracker.has_open(data, "YES"):
                tracker.reset_yes_steps(data)

    # --- Reset YES steps if positions were closed externally (dashboard, manual) ---
    data = tracker.load()
    if not tracker.has_open(data, "YES") and data.get("yes_entry_steps_done"):
        log("Resetting YES steps (positions closed externally)")
        tracker.reset_yes_steps(data)

    # --- WTI-based YES gradient exit ---
    data = tracker.load()
    has_yes = tracker.has_open(data, "YES")
    if has_yes:
        completed_exits = set(data.get("yes_exit_steps_done", []))
        step_i, trigger, pct = strategy.get_yes_exit_step(wti, completed_exits)

        if step_i is not None:
            total_shares = tracker.get_total_shares(data, "YES")
            sell_shares = total_shares * pct

            if sell_shares >= 0.5:
                log(f"SELL YES step {step_i+1}: WTI ${wti:.2f} >= ${trigger}, "
                    f"selling {pct:.0%} = {sell_shares:.1f} shares")

                if do_sell("YES", sell_shares, market["yes_bid"], wti,
                           f"exit_step_{step_i+1}_wti_{trigger}"):
                    data = tracker.load()
                    data["yes_exit_steps_done"].append(step_i)
                    tracker.save(data)

                    if pct >= 1.0:
                        data = tracker.load()
                        tracker.reset_yes_steps(data)

    # --- Profit-based NO exit (per-step targets) ---
    data = tracker.load()
    has_no = tracker.has_open(data, "NO")
    if has_no:
        for key, pos in tracker.get_open_positions(data, "NO"):
            entry_price = pos.get("entry_price", 0)
            entry_step = pos.get("entry_step", -1)
            profit_target = strategy.get_no_profit_target(entry_step)
            sell_at = entry_price * (1 + profit_target) if entry_price > 0 else 0
            log(f"NO step{entry_step}: entry={entry_price:.4f} target=+{profit_target:.0%} sell_at={sell_at:.4f} bid={market['no_bid']:.4f}")
            if entry_price > 0 and market["no_bid"] >= sell_at:
                shares = pos.get("size_shares", 0)
                profit_pct = (market["no_bid"] / entry_price - 1) * 100
                if shares >= 0.5:
                    log(f"SELL NO PROFIT: +{profit_pct:.0f}% (target +{profit_target:.0%}) "
                        f"(bought {entry_price:.3f} step {entry_step}, now {market['no_bid']:.3f})")
                    do_sell("NO", shares, market["no_bid"], wti,
                            f"profit_{profit_pct:.0f}pct_step{entry_step}")
        # Reset NO steps if all NO sold
        data = tracker.load()
        if not tracker.has_open(data, "NO"):
            tracker.reset_no_steps(data)

    # --- Reset NO steps if positions were closed externally (dashboard, manual) ---
    data = tracker.load()
    if not tracker.has_open(data, "NO") and data.get("no_entry_steps_done"):
        log("Resetting NO steps (positions closed externally)")
        tracker.reset_no_steps(data)

    # --- WTI-based NO exit ---
    data = tracker.load()
    has_no = tracker.has_open(data, "NO")
    if has_no and strategy.should_sell_no(wti, has_no):
        sell_all("NO", wti, f"exit_no_wti_{wti:.0f}")
        data = tracker.load()
        tracker.reset_no_steps(data)

    # === FRIDAY AUTO-CLOSE (close all before weekend gap) ===
    if strategy.is_friday_close_time():
        if has_yes or has_no:
            log("FRIDAY CLOSE: closing all positions before weekend")
            sell_all("YES", wti, "friday_weekend_close")
            sell_all("NO", wti, "friday_weekend_close")
            tg.send("<b>WEEKEND SHUTDOWN</b>\nAll positions closed.\nWTI: $%.2f" % wti)
            data = tracker.load()
            tracker.reset_yes_steps(data)
            tracker.reset_no_steps(data)
        return

    # === DEAD ZONE CHECK (block new buys only) ===
    dead, dead_reason = strategy.is_dead_zone()
    if dead:
        log(f"Dead zone: {dead_reason}")
        return

    # === WEEKEND BLOCK ===
    if strategy.is_weekend_blocked():
        log("Weekend block active, no new entries")
        return

    # === BUY SIGNALS (after 16:00 ET preferred) ===

    if not strategy.is_buy_window():
        return

    # Buy YES — gradient entry
    data = tracker.load()
    free = tracker.get_free_balance(data)
    completed_entries = set(data.get("yes_entry_steps_done", []))
    step_i, trigger, bet_usd = strategy.get_yes_entry_step(wti, completed_entries)
    yes_max_price = MAX_YES_ENTRY_PRICE * theta_adj["price_mult"]

    if step_i is not None:
        # Price guard: don't buy YES if too expensive (theta-adjusted)
        if market["yes_ask"] > yes_max_price:
            log(f"SKIP YES step {step_i+1}: ask {market['yes_ask']:.3f} > max {yes_max_price:.3f}")
        # Cooldown: wait 1h between steps
        elif not _check_step_cooldown(data, "yes_entry_steps_done", "YES"):
            log(f"SKIP YES step {step_i+1}: cooldown not elapsed")
        else:
            bet_size = strategy.calculate_bet_size(bet_usd, free)
            if bet_size > 0:
                log(f"BUY YES step {step_i+1}: WTI ${wti:.2f} <= ${trigger}, "
                    f"${bet_size:.2f} @ {market['yes_ask']:.3f}")

                if do_buy("YES", market["yes_ask"], bet_size, wti, step_i):
                    data = tracker.load()
                    data["yes_entry_steps_done"].append(step_i)
                    tracker.save(data)

    # Buy NO — gradient entry
    data = tracker.load()
    free = tracker.get_free_balance(data)
    completed_no = set(data.get("no_entry_steps_done", []))
    step_i, trigger, bet_usd = strategy.get_no_entry_step(wti, completed_no)
    no_max_price = MAX_NO_ENTRY_PRICE * theta_adj["price_mult"]

    # Momentum filter: don't buy NO if WTI rising fast
    momentum_blocked, momentum_reason = strategy.check_momentum_block()
    if momentum_blocked and step_i is not None:
        log(f"SKIP NO: {momentum_reason}")
        step_i = None

    if step_i is not None:
        # Price guard: don't buy NO if too expensive (theta-adjusted)
        if market["no_ask"] > no_max_price:
            log(f"SKIP NO step {step_i+1}: ask {market['no_ask']:.3f} > max {no_max_price:.3f}")
        # Cooldown: wait 1h between steps
        elif not _check_step_cooldown(data, "no_entry_steps_done", "NO"):
            log(f"SKIP NO step {step_i+1}: cooldown not elapsed")
        else:
            bet_size = strategy.calculate_bet_size(bet_usd, free)
            if bet_size > 0:
                log(f"BUY NO step {step_i+1}: WTI ${wti:.2f} >= ${trigger}, "
                    f"${bet_size:.2f} @ {market['no_ask']:.3f}")

                if do_buy("NO", market["no_ask"], bet_size, wti, step_i):
                    data = tracker.load()
                    data.setdefault("no_entry_steps_done", []).append(step_i)
                tracker.save(data)


def main():
    logger.info("=" * 60)
    logger.info("  OIL SWING TRADING BOT v2")
    logger.info(f"  Bankroll: ${BANKROLL:.0f}")
    logger.info(f"  YES entry: WTI <= $93/$91/$89 (gradient)")
    logger.info(f"  YES exit:  WTI >= $96/$98/$99 (gradient)")
    logger.info(f"  NO entry:  WTI >= $97")
    logger.info(f"  NO exit:   WTI <= $93")
    logger.info(f"  Stop-loss: ceasefire $84 / NO $105 / theta 3d / portfolio $200")
    logger.info(f"  Dead zone: 12:00-16:00 ET")
    logger.info(f"  Deadline:  {strategy.DEADLINE_DATE}")
    logger.info(f"  Days left: {strategy.get_days_remaining()}")
    logger.info(f"  Max bet:   25% of free balance")
    logger.info(f"  Started:   {datetime.now(timezone.utc).isoformat()}")
    logger.info("=" * 60)

    data = tracker.load()
    tg.startup(data["stats"]["current_balance"])

    log(f"Balance: ${data['stats']['current_balance']:.2f} | "
        f"Invested: ${tracker.get_invested(data):.2f} | "
        f"Trades: {data['stats']['total_trades']} | "
        f"P&L: ${data['stats']['total_pnl']:+.2f}")

    while True:
        try:
            result = run_cycle()
            if result in ("RESOLVED", "STOPPED"):
                log(f"Bot stopping: {result}")
                tg.shutdown()
                break
        except KeyboardInterrupt:
            log("Shutting down...")
            tg.shutdown()
            break
        except Exception as e:
            log(f"ERROR: {e}")
            tg.error(str(e)[:200])

        time.sleep(SCAN_INTERVAL)


_lock_fh = None

def acquire_lock():
    """Prevent multiple bot instances via Windows file lock."""
    global _lock_fh
    import msvcrt
    lock_path = os.path.join(BOT_DIR, "bot.lock")
    try:
        _lock_fh = open(lock_path, "w")
        msvcrt.locking(_lock_fh.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
    except (IOError, OSError):
        logger.error("Another instance is already running. Exiting.")
        sys.exit(1)


if __name__ == "__main__":
    acquire_lock()
    main()
