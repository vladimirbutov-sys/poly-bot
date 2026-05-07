"""Exit management: time stops, price targets, follow-Car exits.

Exit rules:
1. Car sells -> we sell (handled in main.py via on_sell)
2. Price reaches 95c+ AND we're in profit -> sell everything
3. Price dropped 75%+ from our entry -> forced sell (stop-loss)
4. Position held 20+ days and loss <= 20% -> close position
5. Market resolved -> redeem (handled by redeemer.py)

Note: No hedge re-check (hedge filter removed, replaced by Denizz check at entry).
"""
import time
import threading
import requests
from datetime import datetime, timezone, timedelta
import filters
import executor
import tracker
import monitor
import telegram_notify as tg
from config import (
    EXIT_SELL_AT_PRICE,
    PLAYERS, DRY_RUN,
)

def get_stop_loss_pct(entry_price):
    """Return stop-loss percentage based on entry price tier."""
    from config import STOP_LOSS_TIERS
    for min_p, max_p, pct in STOP_LOSS_TIERS:
        if min_p <= entry_price < max_p:
            return pct
    return 0.50  # fallback



# === Player size cache (on-chain truth) ===
# Stores the LAST KNOWN on-chain balance for each (player, cid, token).
# Populated at startup from data-api, then updated lazily on each sell event
# via a direct CTF.balanceOf RPC call. This is the ONLY source of truth for
# sold_pct calculation — we never trust event["old_size"] or event["sold_shares"]
# from the monitor, because the monitor can phantom-fire due to API pagination
# bugs (denizz has 450+ positions, data-api drops some on each call).
#
# Format: {(player, cid, token): {"size": float, "ts": int}}
_player_size_cache = {}

# === Player PEAK cache (approach C: peak from activity history) ===
# Stores the historical MAX position size ever reached by the player on each
# (cid, token). Populated at startup via _compute_player_peak() which walks
# the full data-api/activity history. Used as denominator for sold_pct
# so that "% sold from peak" reflects reality, not just "delta since last cache".
# Format: {(player, cid, token): float}
_player_peak_cache = {}


def _peak_get(player: str, cid: str, token: str) -> float | None:
    return _player_peak_cache.get((player, cid, token))


def _peak_set(player: str, cid: str, token: str, peak: float):
    _player_peak_cache[(player, cid, token)] = float(peak)


def _compute_player_peak(wallet: str, condition_id: str, token_id: str) -> float:
    """Walk full activity history for (wallet, condition_id), compute the
    running balance on the specific token_id, and return the MAXIMUM value ever
    reached. Falls back to current on-chain if history can't be fetched.

    Handles event types: TRADE (BUY/SELL), MERGE, SPLIT, REDEEM.
    """
    try:
        # Paginate through activity
        all_events = []
        offset = 0
        for _ in range(10):  # up to 5000 events
            r = requests.get(
                "https://data-api.polymarket.com/activity",
                params={
                    "user": wallet,
                    "market": condition_id,
                    "limit": 500,
                    "offset": offset,
                },
                timeout=15,
            )
            if not r.ok:
                break
            batch = r.json() or []
            if not batch:
                break
            all_events.extend(batch)
            if len(batch) < 500:
                break
            offset += 500

        # Filter to this specific token_id
        relevant = [e for e in all_events if str(e.get("asset", "")) == str(token_id)]
        if not relevant:
            # No history — use current on-chain as peak
            onchain = _get_player_size_onchain(wallet, token_id)
            return float(onchain or 0.0)

        # Sort chronologically (oldest first)
        relevant.sort(key=lambda x: x.get("timestamp", 0))

        running = 0.0
        peak = 0.0
        for e in relevant:
            ev_type = (e.get("type") or "").upper()
            side = (e.get("side") or "").upper()
            size = float(e.get("size", 0) or 0)
            if ev_type == "TRADE":
                if side == "BUY":
                    running += size
                elif side == "SELL":
                    running -= size
            elif ev_type == "MERGE":
                running -= size  # merging removes tokens
            elif ev_type == "SPLIT":
                running += size  # splitting creates tokens
            elif ev_type == "REDEEM":
                running = 0.0  # redemption zeros balance
            running = max(running, 0.0)
            peak = max(peak, running)

        # Sanity: peak should be >= current on-chain
        onchain = _get_player_size_onchain(wallet, token_id)
        if onchain is not None:
            peak = max(peak, float(onchain))
        return peak
    except Exception as e:
        print(f"[EXIT] _compute_player_peak error: {e}")
        onchain = _get_player_size_onchain(wallet, token_id)
        return float(onchain or 0.0)


def init_player_peaks():
    """At startup: load PEAK position size for each of our open positions.
    This is the 'approach C' implementation — one activity query per open
    position, in parallel batches. Called once by main.py at startup."""
    data = tracker.load()
    open_positions = tracker.get_open_positions(data)
    if not open_positions:
        print("[EXIT] init_player_peaks: no open positions")
        return

    loaded = 0
    for key, pos in open_positions.items():
        player = pos.get("signal_player", "")
        if not player:
            continue
        wallet = (PLAYERS.get(player) or "").lower()
        if not wallet:
            continue
        cid = pos.get("condition_id", "")
        tok = str(pos.get("token_id", ""))
        if not cid or not tok:
            continue
        peak = _compute_player_peak(wallet, cid, tok)
        if peak > 0:
            _peak_set(player, cid, tok, peak)
            loaded += 1
        time.sleep(0.1)  # gentle pacing

    print(f"[EXIT] init_player_peaks: loaded {loaded} peaks from activity history")


def _get_player_size_onchain(wallet: str, token_id: str) -> float | None:
    """Read player's REAL token balance from Polygon CTF.balanceOf.
    Returns shares (float) or None on RPC error."""
    try:
        from web3 import Web3
        from config import POLYGON_RPC
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC, request_kwargs={"timeout": 10}))
        ctf = w3.eth.contract(
            address=Web3.to_checksum_address("0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"),
            abi=[{"constant": True,
                  "inputs": [{"name": "a", "type": "address"}, {"name": "id", "type": "uint256"}],
                  "name": "balanceOf",
                  "outputs": [{"name": "", "type": "uint256"}],
                  "type": "function", "stateMutability": "view"}],
        )
        raw = ctf.functions.balanceOf(
            Web3.to_checksum_address(wallet), int(token_id)
        ).call()
        return raw / 1e6
    except Exception as e:
        print(f"[EXIT] on-chain RPC error: {e}")
        return None


def _cache_get(player: str, cid: str, token: str) -> float | None:
    """Get cached player size. Returns None if not cached."""
    entry = _player_size_cache.get((player, cid, token))
    if entry is None:
        return None
    return entry["size"]


def _cache_set(player: str, cid: str, token: str, size: float):
    """Update player size cache."""
    _player_size_cache[(player, cid, token)] = {
        "size": size,
        "ts": int(time.time()),
    }


def init_player_cache(player_name: str, wallet: str):
    """Populate cache from data-api at startup. Called once per player."""
    try:
        r = requests.get(
            "https://data-api.polymarket.com/positions",
            params={"user": wallet, "limit": 500, "sizeThreshold": 0},
            timeout=20,
        )
        if not r.ok:
            print(f"[EXIT] cache init failed for {player_name}: HTTP {r.status_code}")
            return
        count = 0
        for p in r.json():
            cid = p.get("conditionId", "")
            asset = str(p.get("asset", ""))
            size = float(p.get("size", 0) or 0)
            if cid and asset and size > 0:
                _cache_set(player_name, cid, asset, size)
                count += 1
        print(f"[EXIT] cache init: {player_name} → {count} positions cached")
    except Exception as e:
        print(f"[EXIT] cache init error: {e}")


def refresh_cache_for_open_positions():
    """Periodic refresh: update on-chain cache for tokens where WE have open
    positions. Called every ~60 seconds from periodic_checks in main.py.

    Only touches tokens we actually care about (from our tracker), so it's
    ~2-10 RPC calls per run — lightweight and reliable.
    """
    data = tracker.load()
    open_positions = tracker.get_open_positions(data)
    if not open_positions:
        return

    refreshed = 0
    for key, pos in open_positions.items():
        player = pos.get("signal_player", "")
        if not player:
            continue
        wallet = (PLAYERS.get(player) or "").lower()
        if not wallet:
            continue
        cid = pos.get("condition_id", "")
        tok = str(pos.get("token_id", ""))
        if not cid or not tok:
            continue

        onchain = _get_player_size_onchain(wallet, tok)
        if onchain is not None:
            old = _cache_get(player, cid, tok)
            if old is None or onchain >= old:
                # No decrease or first cache — safe to update
                _cache_set(player, cid, tok, onchain)
                refreshed += 1
            else:
                # Decrease detected — give handle_player_sell time to process.
                # Force update after 120s to prevent stale cache if monitor
                # missed the sell event entirely.
                entry = _player_size_cache.get((player, cid, tok))
                cache_age = int(time.time()) - entry["ts"] if entry else 999
                if cache_age > 120:
                    _cache_set(player, cid, tok, onchain)
                    refreshed += 1
                    print(f"[EXIT] cache force-update (stale {cache_age}s): "
                          f"{player} {old:.0f} → {onchain:.0f} | {pos.get('title','')[:40]}")
        time.sleep(0.1)  # gentle pacing between RPC calls

    if refreshed:
        print(f"[EXIT] cache refresh: updated {refreshed} player positions on-chain")


# === Duplicate-sell event guard ===
_recent_exit_fires = {}   # {(player, cid, token): last_ts_unix}
EXIT_DEDUP_WINDOW_SEC = 60
# BLOCKER-3 fix (2026-04-17): atomic check-and-set on dedup dict + sell serialization
_exit_dedup_lock = threading.Lock()
_sell_execution_lock = threading.Lock()  # serializes _execute_sell calls

# Threshold for "strong exit" — player dumped >= this % of their position.
PLAYER_EXIT_SELL_PCT_THRESHOLD = 0.70

# Ignore sells smaller than this % of player's position (dust / noise).
PLAYER_SELL_DUST_PCT = 0.10

# Profit/loss delta for deciding whether a sell was "in profit" or "in loss"
PROFIT_DELTA = 0.01

# === Cumulative-sell tracking (added 2026-04-17) ===
# Protects against denizz draining position via many small sells, each below
# the dust threshold. Records every sell event regardless of tier outcome;
# when the rolling-window sum crosses CUMULATIVE_SELL_THRESHOLD, the event
# is escalated by overriding sold_pct_player with cumulative% so the tier
# matrix produces a real exit.
# Counter resets after firing — allows re-fire if denizz keeps dribbling.
_cumulative_sells = {}   # {(player, cid, token): [(ts_unix, sold_pct), ...]}
_cumulative_lock = threading.Lock()


def check_exits():
    """Check all open positions for exit conditions. Called periodically."""
    data = tracker.load()
    # Self-heal any tracker duplicates so each (cid, token) is checked once
    merged = tracker.consolidate_duplicates(data)
    if merged:
        tracker.save(data)
        print(f"[EXIT] check_exits: consolidate_duplicates merged {merged} duplicate records")
        data = tracker.load()
    # Retry any sells that were marked _pending_exit_retry in previous cycles
    # (rescues exit signals lost to transient errors or precision drift).
    process_pending_retries(data)
    data = tracker.load()
    open_positions = tracker.get_open_positions(data)

    if not open_positions:
        return

    now = datetime.now(timezone.utc)

    for key, pos in list(open_positions.items()):
        token_id = pos.get("token_id", "")
        title = pos.get("title", "?")

        if not token_id:
            continue

        # Get current price
        prices = filters.get_orderbook_prices(token_id)
        if not prices:
            continue

        best_bid = prices[0]
        shares = pos.get("size_shares", 0)

        if shares < 0.5:
            continue

        # Legacy HP positions: apply standard exit rules (HP strategy removed in v2,
        # but old positions with tier="HP" may still exist in positions.json)

        # --- EXIT 1: Price reached 99c+ -> sell only if profitable ---
        entry = pos.get("avg_entry", pos.get("entry_price", 0))
        if best_bid >= EXIT_SELL_AT_PRICE and best_bid > entry:
            _prefix = ""
            print(f"{_prefix}[EXIT] Price target {best_bid:.3f} >= {EXIT_SELL_AT_PRICE}, entry was {entry:.3f} | {title[:50]}")
            if False:  # DRY_RUN killed
                continue
            _execute_sell(data, key, pos, shares, best_bid, "price_target_99c")
            data = tracker.load()  # reload after modification
            continue

        # --- EXIT 2: Stop-loss — custom per-position OR tiered by entry price ---
        # Global kill-switch (added 2026-04-18): if STOP_LOSS_ENABLED=False, skip
        # ALL stop-loss logic across the portfolio. Other exits (target take-profit,
        # follow-sell on player exit) still operate normally.
        try:
            from config import STOP_LOSS_ENABLED as _SL_ENABLED
        except ImportError:
            _SL_ENABLED = True   # default ON if config missing the constant
        if not _SL_ENABLED:
            continue
        # Skip entirely if position has `disable_stop_loss: true` flag (hedge positions
        # that must not be cut on price drops — they're insurance, expected to lose value).
        if pos.get("disable_stop_loss"):
            continue
        entry = pos.get("avg_entry", pos.get("entry_price", 0))
        if entry > 0.01:
            # Custom stop-loss overrides tier default
            custom_stop_price = pos.get("custom_stop_loss_price")
            if custom_stop_price:
                if best_bid <= float(custom_stop_price):
                    print(f"[EXIT] Custom stop-loss: bid {best_bid:.3f} <= {float(custom_stop_price):.3f} "
                          f"(entry {entry:.3f}) | {title[:50]}")
                    _execute_sell(data, key, pos, shares, best_bid, f"custom_stop_loss")
                    data = tracker.load()
                    continue
            else:
                stop_pct = get_stop_loss_pct(entry)
                drop_pct = (entry - best_bid) / entry
                if drop_pct >= stop_pct:
                    print(f"[EXIT] Stop-loss: price dropped {drop_pct:.0%} >= {stop_pct:.0%} "
                          f"(entry {entry:.3f} -> {best_bid:.3f}) | {title[:50]}")
                    _execute_sell(data, key, pos, shares, best_bid, f"stop_loss_{drop_pct:.0%}")
                    data = tracker.load()
                    continue

        # Time-stop removed in v2 — horizon filter at entry makes it unnecessary


def _mark_pending_retry(data, key: str, price: float, reason: str, err_reason: str):
    """Mark a position as pending retry so later exit cycles keep trying.

    Stored structure on the position:
        _pending_exit_retry: {
            "since":       ISO-8601 UTC timestamp of FIRST failure,
            "last_attempt": ISO-8601 UTC of most recent attempt,
            "attempts":    int,
            "last_price":  float (price at time of failure),
            "last_reason": str (why the exit was attempted — stop_loss, follow, etc.),
            "last_error":  str (short error reason),
        }
    """
    pos = data["positions"].get(key)
    if not pos:
        return
    now = datetime.now(timezone.utc).isoformat()
    pending = pos.get("_pending_exit_retry") or {}
    if not pending:
        pending["since"] = now
        pending["attempts"] = 0
    pending["last_attempt"] = now
    pending["attempts"] = int(pending.get("attempts", 0)) + 1
    pending["last_price"] = float(price)
    pending["last_reason"] = reason
    pending["last_error"] = err_reason
    pos["_pending_exit_retry"] = pending
    tracker.save(data)


def _clear_pending_retry(data, key: str):
    """Remove the _pending_exit_retry marker after a successful sell."""
    pos = data["positions"].get(key)
    if pos and "_pending_exit_retry" in pos:
        pos.pop("_pending_exit_retry", None)
        tracker.save(data)


def process_pending_retries(data=None):
    """Walk all open positions with a _pending_exit_retry marker and retry.

    Called from the main exit loop at the top of each cycle. Respects:
        - RETRY_WINDOW_MIN: how long since `since` we keep trying
        - RETRY_MAX_ATTEMPTS: hard cap
        - RETRY_MIN_SPACING_SEC: minimum delay since last attempt
    """
    try:
        from config import (
            RETRY_WINDOW_MIN, RETRY_MAX_ATTEMPTS, RETRY_MIN_SPACING_SEC,
        )
    except ImportError:
        RETRY_WINDOW_MIN, RETRY_MAX_ATTEMPTS, RETRY_MIN_SPACING_SEC = 30, 6, 60

    if data is None:
        data = tracker.load()
    now = datetime.now(timezone.utc)
    pending_keys = [
        k for k, p in data.get("positions", {}).items()
        if p.get("status") == "open" and p.get("_pending_exit_retry")
    ]
    if not pending_keys:
        return
    for key in pending_keys:
        pos = data["positions"].get(key, {})
        pending = pos.get("_pending_exit_retry", {})
        try:
            since = datetime.fromisoformat(pending.get("since"))
            last = datetime.fromisoformat(pending.get("last_attempt", pending.get("since")))
        except Exception:
            continue
        window_elapsed_min = (now - since).total_seconds() / 60.0
        spacing_elapsed_sec = (now - last).total_seconds()
        attempts = int(pending.get("attempts", 0))

        if window_elapsed_min > RETRY_WINDOW_MIN or attempts >= RETRY_MAX_ATTEMPTS:
            # Give up on retry — leave marker in place for audit, but stop trying.
            # (Cleared automatically when the position finally closes.)
            continue
        if spacing_elapsed_sec < RETRY_MIN_SPACING_SEC:
            continue

        price = float(pending.get("last_price", 0))
        reason = f"retry_pending({pending.get('last_reason', 'unknown')})"
        shares = float(pos.get("size_shares", 0) or 0)
        if shares < 0.5 or price <= 0.01:
            continue
        title = pos.get("title", "?")
        print(f"[EXIT:retry] Attempt #{attempts + 1} for {title[:50]} @ {price:.3f}")
        _execute_sell(data, key, pos, shares, price, reason)
        data = tracker.load()  # reload after _execute_sell may have mutated


def _execute_sell(data, key, pos, shares, price, reason):
    """Execute a sell order and record it.

    Handles partial fills: if timeout occurs after only part of the order
    is matched, records the filled portion (not the intended full size).
    Then retries the remainder at a lower price.

    On "insufficient balance" rejection: retries once with a larger safety
    margin (covers micro-share precision drift and race conditions).
    On other failures: records _pending_exit_retry so later cycles keep trying.

    2026-04-17: wrapped in _sell_execution_lock to serialize sell execution
    across threads (follow-sell, stop-loss, retry). Prevents cancel_all race
    and cross-token interference during burst scenarios.
    """
    with _sell_execution_lock:
        return _execute_sell_impl(data, key, pos, shares, price, reason)


def _execute_sell_impl(data, key, pos, shares, price, reason):
    try:
        from config import RETRY_SAFETY_MARGIN_MULT, SAFETY_MARGIN_SHARES
    except ImportError:
        RETRY_SAFETY_MARGIN_MULT = 5.0
        SAFETY_MARGIN_SHARES = 0.001

    token_id = pos.get("token_id", "")
    title = pos.get("title", "?")

    if False:  # DRY_RUN killed
        revenue = shares * price
        print(f"[DRY-RUN] Would SELL {shares:.1f} shares @ {price:.3f} = ${revenue:.2f} | {reason} | {title[:50]}")
        return

    # BLOCKER-2 fix (2026-04-17): cancel ONLY pending orders on THIS token,
    # not all orders globally. Global cancel_all() was killing parallel sell
    # orders on other tokens and entry-manager buy orders, causing burst-sell
    # cascading failures and missed entries.
    try:
        client = executor._get_client()
        orders = client.get_orders() or []
        cancelled = 0
        for o in orders:
            if str(o.get("asset_id", "")) == str(token_id):
                try:
                    client.cancel(o.get("id"))
                    cancelled += 1
                except Exception:
                    pass
        if cancelled > 0:
            import time as _time
            _time.sleep(0.5)
            print(f"[EXIT] Cancelled {cancelled} pending order(s) on token before sell | {title[:50]}")
    except Exception as e:
        print(f"[EXIT] Per-token cancel failed: {e}")

    # Re-read tracker for actual share count
    data = tracker.load()
    pos_fresh = data["positions"].get(key)
    if not pos_fresh or pos_fresh.get("status") != "open":
        print(f"[EXIT] Position {key[:16]} already closed, skipping sell")
        return
    actual_shares = pos_fresh.get("size_shares", 0)
    if actual_shares < 0.5:
        print(f"[EXIT] Position {key[:16]} has {actual_shares:.1f} shares, skipping")
        return
    shares = min(shares, actual_shares)

    result = executor.place_limit_sell(token_id, price, shares)

    # --- Handle precision-driven skip: on-chain balance too small ---
    if isinstance(result, dict) and result.get("error") == executor.SELL_SKIP_INSUFFICIENT_BALANCE:
        onchain = result.get("onchain")
        print(f"[EXIT] onchain balance too small ({onchain}) — clearing tracker row | {title[:50]}")
        data = tracker.load()
        pos2 = data["positions"].get(key)
        if pos2:
            pos2["size_shares"] = 0
            pos2["status"] = "sold"
            pos2.setdefault("sells", []).append({
                "shares": float(actual_shares),
                "price": 0,
                "revenue": 0,
                "pnl": 0,
                "reason": "exit_skip_onchain_empty",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            pos2.pop("_pending_exit_retry", None)
            tracker.save(data)
            # Lifecycle hook: this path bypasses tracker.record_sell, so we must
            # fire the on-close callback ourselves to clean stale signaled state.
            tracker._fire_on_close(
                pos2.get("condition_id", "") or "",
                str(pos2.get("token_id", "") or ""),
                pos2.get("signal_player", "") or "",
                "exit_skip_onchain_empty",
            )
        return

    # --- Handle total failure: retry once with larger safety margin ---
    if not result:
        retry_margin = SAFETY_MARGIN_SHARES * RETRY_SAFETY_MARGIN_MULT
        print(
            f"[EXIT] Sell order failed, retry #1 with safety_margin={retry_margin} | {title[:50]}"
        )
        result = executor.place_limit_sell(token_id, price, shares,
                                           safety_margin=retry_margin)

    # --- Still failed → mark pending, later cycles will try again ---
    if not result:
        err_reason = "api_error"
        print(f"[EXIT] Sell order failed (both attempts): {title[:50]}")
        tg.error(f"Sell failed: {title[:40]}")
        data = tracker.load()
        _mark_pending_retry(data, key, price, reason, err_reason)
        return

    # If we reached here, place_limit_sell returned a real order dict.
    # (An 'error' dict from SELL_SKIP_INSUFFICIENT_BALANCE was already handled above.)
    if not isinstance(result, dict) or not result.get("order_id"):
        # Defensive: unexpected shape — treat as failure and mark pending.
        print(f"[EXIT] Sell placed but no order_id: {title[:50]}")
        tg.error(f"Sell failed: {title[:40]}")
        data = tracker.load()
        _mark_pending_retry(data, key, price, reason, "no_order_id")
        return

    tg.sell_placed(title, reason, price, shares)
    print(f"[EXIT] SELL order placed: {title[:50]} | {shares:.1f} shares @ {price:.3f} | {reason}")

    # Wait for fill with detailed info to catch partial fills
    fill = executor.wait_for_fill_with_details(result["order_id"], timeout=300)
    status = fill.get("status", "UNKNOWN")
    matched = fill.get("size_matched", 0)
    original = fill.get("size_original", shares)

    if status == "MATCHED":
        revenue = shares * price
        data = tracker.load()
        tracker.record_sell(data, key, shares, price, revenue, reason)
        _clear_pending_retry(data, key)
        print(f"[EXIT] SOLD: {title[:50]} | ${revenue:.2f}")
        try:
            import limit_tracker
            limit_tracker.log_exit(token_id, title, price, shares, revenue)
        except Exception:
            pass
        return

    if status == "PARTIAL" and matched > 0.5:
        # Record the partial fill
        partial_revenue = round(matched * price, 2)
        data = tracker.load()
        tracker.record_sell(data, key, matched, price, partial_revenue, f"{reason}_partial")
        _clear_pending_retry(data, key)
        print(f"[EXIT] PARTIAL SOLD: {title[:50]} | {matched:.1f}/{original:.1f} sh @ {price:.3f} = ${partial_revenue:.2f}")
        try:
            import limit_tracker
            limit_tracker.log_exit(token_id, title, price, matched, partial_revenue)
        except Exception:
            pass
        # Try the remainder at lower price
        remainder = original - matched
        if remainder >= 0.5:
            new_price = round(price * 0.98, 2)
            if new_price > 0.01:
                print(f"[EXIT] Retry remainder {remainder:.1f} sh @ {new_price:.3f}")
                result2 = executor.place_limit_sell(token_id, new_price, remainder)
                if result2:
                    fill2 = executor.wait_for_fill_with_details(result2["order_id"], timeout=300)
                    s2 = fill2.get("status", "UNKNOWN")
                    m2 = fill2.get("size_matched", 0)
                    if s2 == "MATCHED":
                        rev2 = remainder * new_price
                        data = tracker.load()
                        tracker.record_sell(data, key, remainder, new_price, rev2, reason + "_retry")
                        print(f"[EXIT] RETRY SOLD: {remainder:.1f} @ {new_price:.3f}")
                    elif s2 == "PARTIAL" and m2 > 0.5:
                        rev2 = round(m2 * new_price, 2)
                        data = tracker.load()
                        tracker.record_sell(data, key, m2, new_price, rev2, reason + "_retry_partial")
                        print(f"[EXIT] RETRY PARTIAL SOLD: {m2:.1f}/{remainder:.1f} @ {new_price:.3f}")
        return

    # Nothing filled — adaptive retry ladder.
    # Fix 2026-04-22: previously retry used price × 0.98 (−2% of stale original),
    # which failed completely when bid collapsed (e.g. US x Iran Peace Apr 30
    # 22.04 01:19: our price $0.22 TIMEOUT, bid dropped to $0.14, retry
    # $0.216 — never filled). Adaptive ladder reads FRESH bid each retry
    # and submits at fractions below it until matched.
    # Ref: _analytics/2026-04-22_exit_retry_not_adaptive.md
    print(f"[EXIT] Sell not filled ({status}): {title[:50]} — entering adaptive retry")
    remaining = shares
    retry_ladder = [0.98, 0.95, 0.90]  # fractions below FRESH bid
    for attempt, factor in enumerate(retry_ladder, 1):
        if remaining < 0.5:
            break
        try:
            bid, _ask = filters.get_orderbook_prices(token_id)
        except Exception:
            bid = None
        if bid and bid > 0:
            base = float(bid)
        else:
            base = float(price)
        new_price = round(base * factor, 4)
        if new_price <= 0.01:
            break
        print(f"[EXIT] Retry {attempt}/{len(retry_ladder)}: "
              f"{remaining:.1f} sh @ ${new_price:.4f} (bid ${base:.4f}, factor {factor}) | {title[:40]}")
        result2 = executor.place_limit_sell(token_id, new_price, remaining)
        if not result2:
            continue
        fill2 = executor.wait_for_fill_with_details(result2["order_id"], timeout=180)
        s2 = fill2.get("status", "UNKNOWN")
        m2 = float(fill2.get("size_matched", 0) or 0)
        if s2 == "MATCHED":
            rev2 = remaining * new_price
            data = tracker.load()
            tracker.record_sell(data, key, remaining, new_price,
                                rev2, f"{reason}_retry{attempt}")
            print(f"[EXIT] RETRY{attempt} SOLD: {remaining:.1f} @ {new_price:.4f} | {title[:40]}")
            return
        if s2 == "PARTIAL" and m2 > 0.5:
            rev2 = round(m2 * new_price, 2)
            data = tracker.load()
            tracker.record_sell(data, key, m2, new_price,
                                rev2, f"{reason}_retry{attempt}_partial")
            print(f"[EXIT] RETRY{attempt} PARTIAL: {m2:.1f}/{remaining:.1f} @ {new_price:.4f}")
            remaining -= m2
    if remaining >= 0.5:
        print(f"[EXIT] Adaptive retry exhausted: {remaining:.1f} sh still open | {title[:40]}")


def handle_player_sell(player_name: str, event: dict):
    """Called when a monitor detects a player sell.

    ARCHITECTURE (rewritten 2026-04-10):
    The monitor is just a HINT — "look at this token". ALL sell decisions
    are based on ON-CHAIN TRUTH via CTF.balanceOf, not on event fields.

    Flow:
    1. Dedup guard (60s) — skip burst duplicates
    2. Read player's CURRENT on-chain balance
    3. Compare with CACHED balance (last known size)
    4. actual_sold = cached - current
       - If actual_sold <= 0 → PHANTOM (position didn't decrease), SKIP
       - If RPC failed → fail-safe, SKIP
    5. sold_pct = actual_sold / cached
    6. Apply decision matrix (rule 2a/2b/3, dust filter)
    7. Update cache with current balance
    """
    condition_id = event.get("condition_id", "")
    token_id = event.get("token_id", "")
    title = event.get("title", "?")
    source = event.get("source", "snapshot")

    # === STEP 1: DEDUP GUARD (atomic — BLOCKER-3 fix 2026-04-17) ===
    # check-and-set под одним локом, иначе два потока могут оба пройти guard.
    dedup_key = (player_name, condition_id, str(token_id))
    with _exit_dedup_lock:
        last_fire = _recent_exit_fires.get(dedup_key, 0)
        now_ts = time.time()
        if now_ts - last_fire < EXIT_DEDUP_WINDOW_SEC:
            age = now_ts - last_fire
            print(f"[EXIT] SKIP duplicate sell event ({age:.0f}s ago): "
                  f"{player_name} | {title[:50]}")
            return
        _recent_exit_fires[dedup_key] = now_ts

    # === STEP 2-4: ON-CHAIN TRUTH — compute actual_sold from blockchain ===
    sold_pct_player = None
    actual_sold = 0.0
    cached_size = 0.0

    player_wallet = (PLAYERS.get(player_name) or "").lower()
    if not player_wallet or not token_id:
        print(f"[EXIT] SKIP: missing wallet/token_id for {player_name} | {title[:50]}")
        return

    # Get current on-chain balance
    current_onchain = _get_player_size_onchain(player_wallet, token_id)
    if current_onchain is None:
        # RPC failed — fail-safe: do NOT sell
        print(f"[EXIT] RPC FAILED — skipping sell (fail-safe) | {title[:50]}")
        return

    # Get PEAK from history (approach C)
    peak_size = _peak_get(player_name, condition_id, str(token_id))
    if peak_size is None:
        # Not cached — lazy-load peak from activity (first time seeing this token)
        peak_size = _compute_player_peak(player_wallet, condition_id, str(token_id))
        _peak_set(player_name, condition_id, str(token_id), peak_size)

    # Also update legacy size cache (kept for phantom detection + compatibility)
    cached_size = _cache_get(player_name, condition_id, str(token_id))
    if cached_size is None:
        cached_size = current_onchain
    _cache_set(player_name, condition_id, str(token_id), current_onchain)

    # Peak should never be less than current — if it is, fix it
    if peak_size < current_onchain:
        peak_size = current_onchain
        _peak_set(player_name, condition_id, str(token_id), peak_size)

    # === PHANTOM CHECK (delta vs last cache, not peak) ===
    delta_sold = cached_size - current_onchain
    if delta_sold <= 0:
        if delta_sold < -0.5:
            print(f"[EXIT] PHANTOM: {player_name} INCREASED by {-delta_sold:.0f} sh "
                  f"(cache={cached_size:.0f} → onchain={current_onchain:.0f}) | {title[:50]}")
        elif delta_sold == 0:
            print(f"[EXIT] PHANTOM: delta=0 (cache={cached_size:.0f} == onchain) "
                  f"— cache refresh may have swallowed sell | {player_name} | {title[:50]}")
        return

    if peak_size <= 0:
        print(f"[EXIT] SKIP: peak_size=0 for {player_name} | {title[:50]}")
        return

    # === SOLD_PCT FROM DELTA (this sell event, not cumulative from peak) ===
    if cached_size <= 0:
        print(f"[EXIT] SKIP: cached_size=0 for {player_name} | {title[:50]}")
        return
    sold_pct_player = delta_sold / cached_size

    print(f"[EXIT] on-chain truth: {player_name} {cached_size:.0f} → {current_onchain:.0f} sh "
          f"(delta {delta_sold:.0f} = {sold_pct_player:.0%}) | {title[:50]}")

    # === CUMULATIVE TRACKING — record every event, escalate on threshold ===
    # Prevents denizz from draining via repeated sub-dust events (e.g. 5 × 8%).
    # If sum of recent sold_pct in window >= CUMULATIVE_SELL_THRESHOLD,
    # override sold_pct_player with the cumulative value so tier matrix sees
    # a real-sized sell. After fire, history clears so we don't re-trigger
    # immediately on the same accumulated activity.
    try:
        from config import CUMULATIVE_SELL_WINDOW_SEC, CUMULATIVE_SELL_THRESHOLD
    except ImportError:
        CUMULATIVE_SELL_WINDOW_SEC = 3600
        CUMULATIVE_SELL_THRESHOLD = 0.20
    cumul_key = (player_name, condition_id, str(token_id))
    cumul_now = time.time()
    with _cumulative_lock:
        history = _cumulative_sells.setdefault(cumul_key, [])
        history.append((cumul_now, float(sold_pct_player)))
        cutoff = cumul_now - float(CUMULATIVE_SELL_WINDOW_SEC)
        history[:] = [(t, p) for t, p in history if t >= cutoff]
        cumulative_pct = sum(p for _, p in history)
        n_events = len(history)
        will_escalate = (
            cumulative_pct >= float(CUMULATIVE_SELL_THRESHOLD)
            and cumulative_pct > sold_pct_player + 1e-9   # only when this individual event isn't already that big
        )
        if will_escalate:
            # Reset counter so next dribble-burst is independent
            _cumulative_sells[cumul_key] = []

    if will_escalate:
        print(f"[EXIT] CUMULATIVE TRIGGER: {player_name} cumul {cumulative_pct:.0%} "
              f"over {n_events} events in last {int(CUMULATIVE_SELL_WINDOW_SEC)//60}min "
              f"(this event {sold_pct_player:.0%}) — escalating | {title[:50]}")
        sold_pct_player = cumulative_pct

    # === STEP 5: Find our matching position ===
    data = tracker.load()
    merged = tracker.consolidate_duplicates(data)
    if merged:
        tracker.save(data)
        data = tracker.load()

    open_positions = tracker.get_open_positions(data)
    matched_key = None
    matched_pos = None
    for key, pos in open_positions.items():
        if pos.get("condition_id") != condition_id:
            continue
        if str(pos.get("token_id")) != str(token_id):
            continue
        matched_key = key
        matched_pos = pos
        break

    if matched_pos is None:
        return

    key = matched_key
    pos = matched_pos

    # Only exit if this player opened our position — OR position is "manual"
    # Manual-positions opt into follow-sell from any active player (any player
    # in config.PLAYERS). Cross-player protection between real players is kept:
    # e.g. signal_player="denizz" will still SKIP a "car" sell signal.
    #
    # Fix 2026-04-21: "unknown" / empty signal_player comes from
    # tracker.sync_with_onchain reverse-scan — we found an on-chain balance
    # with no matching tracker entry. These orphan positions have no known
    # opener, so cross-player protection is meaningless — allow follow-sell
    # from any active player, same as "manual". Otherwise we get stuck
    # holding adopted positions forever (e.g. 205 sh YES on Iran unrestricted
    # shipping Hormuz Apr — denizz exited 17.04, we stayed in because adopt
    # came with signal_player="unknown").
    # Ref: _analytics/2026-04-21_unknown_signal_player_blocks_follow_sell.md
    pos_signal_player = pos.get("signal_player", "")
    _orphan_signals = ("", "unknown", None)
    if (pos_signal_player not in _orphan_signals
            and pos_signal_player != player_name
            and pos_signal_player != "manual"):
        print(f"[EXIT] SKIP: {player_name} sold but position was opened by {pos_signal_player} | {title[:50]}")
        return
    if pos_signal_player == "manual":
        print(f"[EXIT] manual position following {player_name}: {title[:50]}")
    elif pos_signal_player in _orphan_signals:
        print(f"[EXIT] orphan-sync position ({pos.get('_adopted_from', '?')}) following {player_name}: {title[:50]}")

    our_shares = pos.get("size_shares", 0)
    if our_shares < 0.5:
        return

    # === STEP 6: DECISION MATRIX ===
    # Fetch current orderbook — needed for decision & actual sell.
    prices = filters.get_orderbook_prices(token_id)
    if not prices:
        return
    our_sell_price = prices[0]
    our_entry = pos.get("avg_entry", pos.get("entry_price", 0))
    we_in_profit = our_entry > 0.01 and our_sell_price >= our_entry * (1 + PROFIT_DELTA)

    # === DETERMINE IF PLAYER'S SELL WAS IN PROFIT OR LOSS FOR THEM ===
    player_sell_price = float(event.get("sell_price", 0) or 0)
    player_wallet = (PLAYERS.get(player_name) or "").lower()
    condition_id_for_cb = pos.get("condition_id", "")

    player_avg = 0.0
    if player_wallet and condition_id_for_cb:
        player_avg = filters.get_player_cost_basis(condition_id_for_cb, player_wallet, token_id)

    player_in_profit = None
    player_in_loss = None
    if player_avg > 0.01 and player_sell_price > 0.01:
        if player_sell_price > player_avg * (1 + PROFIT_DELTA):
            player_in_profit = True
            player_in_loss = False
        elif player_sell_price < player_avg * (1 - PROFIT_DELTA):
            player_in_profit = False
            player_in_loss = True
        else:
            player_in_profit = False
            player_in_loss = False

    # === DECISION MATRIX (tiered follow-sell from config) ===
    # sold_pct_player is computed from ON-CHAIN TRUTH (cache vs current)
    from config import FOLLOW_SELL_TIERS_PROFIT, FOLLOW_SELL_TIERS_LOSS

    sell_shares = 0.0
    reason = ""
    decision_log = ""

    if sold_pct_player is None:
        sell_shares = our_shares
        reason = f"{player_name}_unknown_pct_full"
        decision_log = "unknown sold%, default full exit"
    else:
        # Pick tier table based on our PnL
        tiers = FOLLOW_SELL_TIERS_PROFIT if we_in_profit else FOLLOW_SELL_TIERS_LOSS
        pnl_label = "PROFIT" if we_in_profit else "LOSS"

        # Fix 2026-04-21: cumul > tier table ceiling must force 100%.
        # CUMULATIVE TRIGGER can escalate sold_pct_player above 1.0 (e.g. 153%
        # when two sells within the rolling window each report against a
        # shrinking baseline). Tier tables end at (0.80, 1.01, 1.00) — any value
        # >= 1.01 falls through the loop with our_sell_fraction=0 and mis-logs
        # "dust sell" on what is actually a full/over-exit signal. Clamp to the
        # top tier's representative point so full-exit is fired.
        effective_pct = min(float(sold_pct_player), 0.9999)
        our_sell_fraction = 0.0
        for lo, hi, frac in tiers:
            if lo <= effective_pct < hi:
                our_sell_fraction = frac
                break

        pct_s = f"{sold_pct_player:.0%}"

        if our_sell_fraction <= 0:
            print(f"[EXIT] SKIP {player_name} dust sell ({pct_s}): "
                  f"we in {pnl_label}, below tier threshold | {title[:50]}")
            return

        sell_shares = our_shares * our_sell_fraction
        reason = f"{player_name}_follow_{pct_s}_sell{our_sell_fraction:.0%}"
        decision_log = (f"tiered: player sold {pct_s}, we {pnl_label}, "
                        f"sell {our_sell_fraction:.0%} of our {our_shares:.0f} sh")

    if sell_shares < 0.5:
        return

    _prefix = ""
    print(f"{_prefix}[EXIT] {player_name} → {decision_log} | {title[:50]}")

    # Sanity: if our bid is much worse than player's sell price, skip
    if player_sell_price > 0.01 and not we_in_profit:
        price_gap = (player_sell_price - our_sell_price) / player_sell_price if player_sell_price > 0 else 0
        if price_gap > 0.40:
            print(f"[EXIT] SKIP: our price {our_sell_price:.3f} is {price_gap:.0%} worse "
                  f"than {player_name} @ {player_sell_price:.3f} | {title[:50]}")
            return

    # === SETTLE WAIT (added 2026-04-17, variant B) ===
    # When denizz sells in HIS profit, his market sweep briefly compresses our
    # bid. Empirically the book recovers within ~30 sec in fast-recovery cases,
    # or never recovers in stuck cases. A short wait + bid refresh captures
    # the recovery without significant downside (LOSS-mode and panic-style
    # sells skip this — urgent path).
    try:
        from config import SLIPPAGE_SETTLE_ENABLED, SLIPPAGE_SETTLE_WAIT_SEC
    except ImportError:
        SLIPPAGE_SETTLE_ENABLED = False
        SLIPPAGE_SETTLE_WAIT_SEC = 0
    if SLIPPAGE_SETTLE_ENABLED and player_in_profit:
        print(f"[EXIT] Settle wait {SLIPPAGE_SETTLE_WAIT_SEC}s — denizz sold in profit, "
              f"giving book time to absorb | {title[:40]}")
        time.sleep(int(SLIPPAGE_SETTLE_WAIT_SEC))
        # Re-read post-absorption bid
        try:
            fresh = filters.get_orderbook_prices(token_id)
        except Exception as _e:
            fresh = None
            print(f"[EXIT] Refresh failed after settle ({_e}); using original bid")
        if fresh and fresh[0] > 0:
            old = our_sell_price
            our_sell_price = fresh[0]
            delta = our_sell_price - old
            print(f"[EXIT] Post-settle bid: ${our_sell_price:.3f} (was ${old:.3f}, "
                  f"delta {delta:+.3f}) | {title[:40]}")
        else:
            print(f"[EXIT] Post-settle: empty/invalid book; sticking to original ${our_sell_price:.3f}")

    _prefix = ""
    print(f"{_prefix}[EXIT] Following {player_name}: {sell_shares:.1f} sh @ {our_sell_price:.3f} | {title[:50]}")
    tg.send(f"{_prefix}Following {player_name} SELL:\n{title}\n"
            f"{sell_shares:.1f} sh @ {our_sell_price:.3f} ({reason})")
    _execute_sell(data, key, pos, sell_shares, our_sell_price, reason)


# Keep handle_target_sell as alias for compatibility
handle_target_sell = handle_player_sell


