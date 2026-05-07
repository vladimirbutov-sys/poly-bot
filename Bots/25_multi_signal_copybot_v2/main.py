"""
Multi-Signal Copy-Trading Bot
==============================
Signal:  ANY of 3 players buys $500+ (Car, aenews2, denizz)
Guard:   NONE of the other 2 players have $500+ on opposite side
Sizing:  Per-player additive tiers × price multiplier (based on WR/ROI backtest)
Exit:    Follow the player who gave the signal
Price:   Car/aenews2: 10-82c | denizz: 15-82c
"""
import sys
import os
import time
import logging
import threading
from datetime import datetime, timezone, timedelta

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BOT_DIR, "bot.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.__stderr__),
    ],
)
_log = logging.getLogger("multi_signal_bot")


class _PrintToLog:
    def write(self, msg):
        msg = msg.rstrip()
        if msg:
            _log.info(msg)
    def flush(self):
        pass


sys.stdout = _PrintToLog()

import telegram_notify as tg
import telegram_cmd
import daily_report
import tracker
import monitor
import filters
import entry_manager
import exit_manager
import redeemer
from mode_manager import mode_manager
from config import (
    BANKROLL, POSITIONS_CHECK_INTERVAL, MIN_PLAYER_INVESTED,
    PLAYERS, DRY_RUN,
)

# Per-player buy buffer: {player -> {buf_key -> {total_usd, buys, notified}}}
# `buys` is a list of [timestamp, cost_usd] pairs so we can prune by age
# and recompute total_usd from the survivors.
BUFFER_WINDOW = 86400  # 24h — buys older than this are pruned from buffer
BUY_BUFFERS_FILE = os.path.join(BOT_DIR, "buy_buffers.json")
_buffers_lock = threading.Lock()
_entry_lock = threading.Lock()  # Bug 1+2+6 fix: prevents parallel handle_buy() race condition


def _load_buffers():
    """Load buffers + signaled keys from disk. Returns (buffers_dict, signaled_dict)."""
    import json as _json
    try:
        if os.path.exists(BUY_BUFFERS_FILE):
            with open(BUY_BUFFERS_FILE, "r", encoding="utf-8") as f:
                d = _json.load(f)
            buffers = {name: d.get("buffers", {}).get(name, {}) for name in PLAYERS}
            signaled = {name: set(d.get("signaled", {}).get(name, [])) for name in PLAYERS}
            n_bufs = sum(len(b) for b in buffers.values())
            n_sig = sum(len(s) for s in signaled.values())
            print(f"[BUFFER] Loaded from disk: {n_bufs} buffer(s), {n_sig} signaled key(s)")
            return buffers, signaled
    except Exception as e:
        print(f"[BUFFER] Load error: {e}")
    return {name: {} for name in PLAYERS}, {name: set() for name in PLAYERS}


def _save_buffers():
    """Atomically persist buffers + signaled keys to disk."""
    import json as _json
    try:
        with _buffers_lock:
            payload = {
                "buffers": _buy_buffers,
                "signaled": {name: list(keys) for name, keys in _signaled_keys.items()},
            }
            tmp = BUY_BUFFERS_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                _json.dump(payload, f)
            os.replace(tmp, BUY_BUFFERS_FILE)
    except Exception as e:
        print(f"[BUFFER] Save error: {e}")


def _prune_buffer(buf: dict) -> None:
    """Drop buys older than BUFFER_WINDOW; recompute total_usd from survivors."""
    now = time.time()
    cutoff = now - BUFFER_WINDOW
    fresh = []
    for b in buf.get("buys", []):
        # Backwards compat: old format was a bare timestamp (float).
        if isinstance(b, (list, tuple)):
            ts = float(b[0])
            cost = float(b[1]) if len(b) > 1 else 0.0
        else:
            ts = float(b)
            cost = 0.0
        if ts >= cutoff:
            fresh.append([ts, cost])
    buf["buys"] = fresh
    buf["total_usd"] = sum(b[1] for b in fresh)


_buy_buffers, _signaled_keys = _load_buffers()

# === VARIANT 1: tier-upgrade throttle ===
# {(cid, token): last_upgrade_ts} — prevents cascade double-entry when
# partial fills + data-api lag cause formula to re-fire within seconds.
_tier_upgrade_last_ts = {}
_throttle_lock = threading.Lock()


def _get_already_bet_v1(player_name: str, buf: dict, condition_id: str, token_id: str) -> float:
    """Variant 1: read already_bet from tracker.cost_usd (live) with grace-period
    fallback to buf.last_tier_bet. Returns 0 if feature flag is off (legacy path).

    Flag: config.USE_ONCHAIN_COST. When False returns legacy buf.last_tier_bet.
    """
    from config import USE_ONCHAIN_COST, ONCHAIN_COST_GRACE_SEC
    legacy = float(buf.get("last_tier_bet", 0.0) or 0.0)
    if not USE_ONCHAIN_COST:
        return legacy
    try:
        data = tracker.load()
        cost, last_ts = tracker.get_cost_on_token(data, condition_id, token_id)
        # Grace: if record_position was very recent, trust cost as-is (ignore any race with sync)
        now = int(time.time())
        recent = (last_ts > 0) and ((now - last_ts) < ONCHAIN_COST_GRACE_SEC)
        print(f"[VARIANT1] already_bet: tracker ${cost:.2f} (legacy buf ${legacy:.2f}) "
              f"recent={recent} | {condition_id[:16]}")
        return cost
    except Exception as e:
        print(f"[VARIANT1] get_cost fallback: {e}")
        return legacy


def _throttle_allows_upgrade(condition_id: str, token_id: str) -> bool:
    """Variant 1: throttle tier-upgrade to max 1 per (cid, token) per N sec."""
    from config import USE_ONCHAIN_COST, TIER_UPGRADE_THROTTLE_SEC
    if not USE_ONCHAIN_COST:
        return True  # legacy path has no throttle
    key = (condition_id, str(token_id))
    now = time.time()
    with _throttle_lock:
        last = _tier_upgrade_last_ts.get(key, 0)
        if now - last < TIER_UPGRADE_THROTTLE_SEC:
            print(f"[VARIANT1] upgrade throttled ({now-last:.0f}s < {TIER_UPGRADE_THROTTLE_SEC}s) | {condition_id[:16]}")
            return False
        _tier_upgrade_last_ts[key] = now
        return True


def _rehydrate_from_tracker():
    """Sync _signaled_keys + buffer state with current tracker state.

    Two directions:
      1. ADD signaled_keys for open positions (so tier upgrade keeps working
         after a restart).
      2. REMOVE signaled_keys + reset last_tier_bet for positions that are
         no longer open (sold/won/lost). Without this, stale signaled_keys
         from past positions block new legitimate signals on the same market
         when the player re-enters after we've exited.
    """
    try:
        # Bug 5 fix: start fresh — only trust tracker, not stale disk state.
        # Prevents DRY_RUN ghost keys from persisting across mode switches.
        for sp in PLAYERS:
            _signaled_keys[sp].clear()

        data = tracker.load()
        # Build the set of buf_keys that SHOULD be signaled (= open positions)
        open_keys_per_player = {name: set() for name in PLAYERS}
        for oid, p in data.get("positions", {}).items():
            if p.get("status") not in ("open", "filled"):
                continue
            sp = p.get("signal_player", "")
            if not sp or sp not in PLAYERS:
                continue
            cid = p.get("condition_id", "")
            tok = p.get("token_id", "")
            if not cid or not tok:
                continue
            open_keys_per_player[sp].add(f"{cid}_{tok}")

        added_sigs = 0
        added_bufs = 0
        cleared_sigs = 0

        # Direction 1: ADD signaled_keys for open positions
        # ONLY for positions that were entered via bot signal (not adopted/migrated)
        for oid, p in data.get("positions", {}).items():
            if p.get("status") not in ("open", "filled"):
                continue
            sp = p.get("signal_player", "")
            if not sp or sp not in PLAYERS:
                continue
            # Skip adopted/migrated positions — they were not bot-signaled entries
            if p.get("_adopted_from") or sp == "unknown":
                continue
            cid = p.get("condition_id", "")
            tok = p.get("token_id", "")
            if not cid or not tok:
                continue
            buf_key = f"{cid}_{tok}"
            if buf_key not in _signaled_keys[sp]:
                _signaled_keys[sp].add(buf_key)
                added_sigs += 1
            if buf_key not in _buy_buffers[sp]:
                cost = float(p.get("cost_usd", 0) or 0)
                entry = float(p.get("avg_entry") or p.get("entry_price") or 0)
                _buy_buffers[sp][buf_key] = {
                    "buys": [],
                    "total_usd": 0.0,
                    "notified": True,
                    "first_price": entry,
                    "last_tier_bet": cost,
                }
                added_bufs += 1

        # Direction 2: REMOVE signaled_keys for buf_keys not in open positions.
        # These are stale entries from positions that were closed (sold/won/lost);
        # leaving them in place blocks re-entry after player re-enters the market.
        for sp in PLAYERS:
            stale = set()
            for buf_key in list(_signaled_keys[sp]):
                if buf_key not in open_keys_per_player[sp]:
                    stale.add(buf_key)
            for buf_key in stale:
                _signaled_keys[sp].discard(buf_key)
                cleared_sigs += 1

        # Direction 3 (2026-04-15 + 2026-04-17 refinement): REMOVE stale
        # entries from _buy_buffers — but ONLY for markets where we
        # previously placed bets (last_tier_bet > 0) and the position is
        # now gone. Without this guard the re-entry after close gets
        # misclassified as a tier-upgrade with negative increment (the
        # original 2026-04-15 bug).
        #
        # 2026-04-17 fix: previously this cleared ALL buffers without an
        # open position, including pure-accumulating buffers for new
        # markets we haven't entered yet. That prevented MIN_PLAYER_INVESTED
        # from ever being reached on new signals (Lebanon-Jun30 missed the
        # $872 cumulative because every cycle reset it to $0). Now we
        # preserve buffers with last_tier_bet == 0 — those are legitimate
        # accumulation toward the $500 entry threshold.
        cleared_bufs = 0
        for sp in PLAYERS:
            open_keys = open_keys_per_player[sp]
            for buf_key, buf in list(_buy_buffers[sp].items()):
                if buf_key in open_keys:
                    continue  # have open position → keep buffer (active state)
                if float(buf.get("last_tier_bet", 0) or 0) > 0:
                    # We previously bet on this market and it's now closed →
                    # genuinely stale, drop it.
                    del _buy_buffers[sp][buf_key]
                    cleared_bufs += 1
                # else: never bet (last_tier_bet == 0) → preserve, this is
                # accumulation toward MIN_PLAYER_INVESTED threshold.

        if added_sigs or added_bufs or cleared_sigs or cleared_bufs:
            print(f"[BUFFER] Rehydrated from tracker: +{added_sigs} signaled, "
                  f"+{added_bufs} buffers, -{cleared_sigs} stale signals, "
                  f"-{cleared_bufs} stale buffer entries cleared")
            _save_buffers()
    except Exception as e:
        print(f"[BUFFER] Rehydrate error: {e}")


_rehydrate_from_tracker()


def _on_position_closed(cid: str, token_id: str, signal_player: str, reason: str):
    """Lifecycle callback — fired by tracker whenever a position becomes fully
    closed (manual sell, auto follow-sell, onchain_sync_disappeared, market
    redemption, exit_skip_onchain_empty).

    Purpose: purge stale _signaled_keys / _buy_buffers entries so the next
    legitimate signal on the same market isn't misclassified as a tier-upgrade
    with a nonsensical increment.

    Safe to call multiple times (idempotent). Guards against unknown players
    (e.g. adopted on-chain positions with signal_player='unknown') and disk
    write errors.
    """
    if not signal_player:
        return
    buf_key = f"{cid}_{token_id}"
    try:
        keys_set = _signaled_keys.get(signal_player)
        if keys_set is not None:
            keys_set.discard(buf_key)
        buf_dict = _buy_buffers.get(signal_player)
        if buf_dict is not None:
            buf_dict.pop(buf_key, None)
    except Exception as e:
        print(f"[LIFECYCLE] Cleanup error for {signal_player}/{buf_key[:30]}: {e}")
        return
    try:
        _save_buffers()
    except Exception as e:
        print(f"[LIFECYCLE] Save buffers after close failed: {e}")
    short_cid = cid[:20] if cid else "?"
    print(f"[LIFECYCLE] Cleaned state for {signal_player} on {short_cid}... (reason={reason})")


# Register the cleanup handler at import time so it's active before any
# monitor thread starts. register_on_close is idempotent (dedupes same fn).
tracker.register_on_close(_on_position_closed)


def _get_buf(player_name: str, buf_key: str, entry_price: float) -> dict:
    buf = _buy_buffers[player_name]
    if buf_key not in buf:
        buf[buf_key] = {
            "buys": [],
            "total_usd": 0.0,
            "notified": False,
            "first_price": entry_price,
            "last_tier_bet": 0.0,  # how much we already placed for this position
        }
    _prune_buffer(buf[buf_key])
    return buf[buf_key]


# Car and aenews2 removed 2026-04-09 — only denizz is active.
# Old Car-specific blacklist (ceasefire/meeting/diplomatic) kept only as
# historical note.

# === Rule C: post-exit whipsaw protection ===
# If we recently exited a position on this (cid, token) and the new entry
# price is within N% of our previous exit price, we're likely re-entering
# the same noise pocket (player flipping positions). Block.
#
# Two refinements after Hezbollah Apr 30 incident on 2026-04-09:
#   (Variant A) Manual exits (flagged with manual_exit=True or sell reason
#     starting with "manual_") are NOT considered for whipsaw — when the
#     human closed a position there is no relationship to player flipping,
#     so re-entry on a fresh denizz buy must be allowed.
#   (Variant D) Tightened threshold from 10% to 5%. The original 10% was
#     too wide and blocked legitimate re-accumulation signals (e.g. denizz
#     refilling 5300 USD across 12 buys at 0.51-0.56 after our manual exit
#     at 0.558 was treated as whipsaw because the move was only 5.6%).
POST_EXIT_WINDOW_HOURS = 12
POST_EXIT_PRICE_CHANGE_MIN = 0.05  # 5% (was 10%, tightened 2026-04-09)


def _is_manual_sell(sell: dict) -> bool:
    """Return True if a tracker sells[] record represents a human action,
    not a follow-the-player exit. Manual sells must NOT trigger Rule C."""
    if sell.get("manual_exit") is True:
        return True
    reason = (sell.get("reason") or "").lower()
    if reason.startswith("manual_") or reason == "manual":
        return True
    return False


def _recent_exit_on_market(cid: str, token: str, hours: int = POST_EXIT_WINDOW_HOURS):
    """Scan tracker for AUTOMATED sells on (cid, token) in the last N hours.
    Manual sells are skipped — they were not the bot reacting to the player.

    Returns (latest_exit_ts, latest_exit_price, latest_exit_pnl) of the latest
    non-manual sell, or None if there is none in the window.
    """
    if not cid or not token:
        return None
    try:
        data = tracker.load()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        latest_ts = None
        latest_price = 0.0
        latest_pnl = 0.0
        for oid, p in data.get("positions", {}).items():
            if p.get("condition_id", "") != cid:
                continue
            if p.get("token_id", "") != token:
                continue
            for s in p.get("sells", []):
                if _is_manual_sell(s):
                    continue  # Variant A: skip human-driven exits
                ts_str = s.get("timestamp", "")
                if not ts_str:
                    continue
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except Exception:
                    continue
                if ts < cutoff:
                    continue
                price = float(s.get("price", 0) or 0)
                if price <= 0:
                    continue
                if latest_ts is None or ts > latest_ts:
                    latest_ts = ts
                    latest_price = price
                    latest_pnl = float(s.get("pnl", 0) or 0)
        if latest_ts is not None:
            return (latest_ts, latest_price, latest_pnl)
    except Exception as e:
        print(f"[MAIN] _recent_exit_on_market error: {e}")
    return None


def handle_buy(player_name: str, event: dict):
    """Process a BUY from any of the 4 players."""
    try:
        token_id = event["token_id"]
        condition_id = event.get("condition_id", "")
        title = event.get("title", "Unknown")
        outcome = event.get("outcome", "")
        entry_price = event["price"]
        cost_usd = event.get("cost_usd", 0)
        event_slug = event.get("event_slug", "")

        buf_key = f"{condition_id}_{token_id}"

        # === BOT VARIANT FILTER (A/B) ===
        # Variant A: pass-through. Variant B: skip buys whose live best ask
        # falls outside [VARIANT_B_PRICE_FLOOR, VARIANT_B_PRICE_CEIL].
        # Applies to every buy-event branch below (Path A, top-up, hedge, rebuy).
        try:
            import variant as _variant
            _skip, _reason = _variant.should_skip_buy_for_variant(token_id, title)
            if _skip:
                print(f"[FILTER] {_reason}")
                return
        except Exception as _e:
            # Fail-OPEN on internal error so the bot keeps working as variant A.
            print(f"[VARIANT] WARN: filter raised {type(_e).__name__}: {_e} — passing through")

        # === ON-CHAIN CHECK (moved ABOVE ratio filter so _size_before is known) ===
        # Check denizz's REAL pre-event share balance on-chain. If he already
        # holds non-dust shares on this token, the event is a TOP-UP — we must
        # route to the tier-upgrade branch regardless of whether our internal
        # _signaled_keys contains the key.
        # Fail-safe: on RPC failure (None) we SKIP the event.
        from config import TOPUP_DUST_SHARES, TOPUP_RATIO_TIERS
        _force_tier_upgrade = False
        _size_before = 0.0
        _cache_hit = False
        if player_name == "denizz":
            try:
                _event_size_shares = float(
                    event.get("size")
                    or event.get("size_shares")
                    or (float(cost_usd or 0) / float(entry_price or 1) if entry_price else 0.0)
                    or 0.0
                )
            except Exception:
                _event_size_shares = 0.0
            _wallet = PLAYERS.get(player_name, "")
            _size_before, _cache_hit = filters.get_denizz_size_before_event(
                _wallet, token_id, _event_size_shares,
                cid=condition_id, player_name=player_name,
            )
            if _size_before is None:
                print(f"[MAIN:{player_name}] SKIP: top-up detection RPC failed "
                      f"(fail-safe) | {title[:50]}")
                return

        # === RATIO FILTER (replaces MIN_BUY_EVENT_USD) ===
        # If denizz already has a position (non-dust shares), check whether this
        # buy is noise (<3% of his existing position value). If so, SKIP.
        # If no prior position (new market), let everything through to the buffer.
        _noise_ratio_threshold = TOPUP_RATIO_TIERS[0][1]  # 0.03 = 3%
        if _size_before > TOPUP_DUST_SHARES:
            denizz_position_usd = _size_before * float(entry_price or 0)
            if denizz_position_usd > 0:
                ratio = float(cost_usd or 0) / denizz_position_usd
                if ratio < _noise_ratio_threshold:
                    print(f"[MAIN:{player_name}] SKIP: noise topup {ratio:.1%} "
                          f"(${float(cost_usd or 0):.0f} / ${denizz_position_usd:.0f}) | {title[:50]}")
                    return

        # === TOP-UP DETECTION (on-chain classification) — Bugfix #1 2026-04-15 ===
        if player_name == "denizz":
            if _size_before > TOPUP_DUST_SHARES and buf_key not in _signaled_keys[player_name]:
                _src = "cache" if _cache_hit else "on-chain"
                # Bug fix: only force tier-upgrade if WE already have an open
                # position on this condition.  When we don't, the event must go
                # through Path A (new entry) so it gets sized via Rule A+.
                _our_data = tracker.load()
                _we_have_position = tracker.has_position_on_condition(_our_data, condition_id)
                if _we_have_position:
                    print(f"[MAIN:{player_name}] TOP-UP detected {_src} "
                          f"(size_before={_size_before:.2f} > dust {TOPUP_DUST_SHARES:.2f}) "
                          f"but no prior signal — routing to tier-upgrade path | {title[:50]}")
                    _force_tier_upgrade = True
                else:
                    print(f"[MAIN:{player_name}] TOP-UP detected {_src} "
                          f"(size_before={_size_before:.2f} > dust {TOPUP_DUST_SHARES:.2f}) "
                          f"but WE have no position — staying on Path A | {title[:50]}")

        # === HEDGE DETECTION (time-series umbrella) ===
        hedge_result = filters.detect_timeseries_hedge(
            event_slug, condition_id, outcome, player_name,
            float(cost_usd or 0), title
        )
        if hedge_result["is_hedge"]:
            if not hedge_result["should_buy"]:
                print(f"[MAIN:{player_name}] SKIP hedge: {hedge_result['reason']} | {title[:50]}")
                return
            # Override bet size with proportional hedge
            hedge_usd = hedge_result["hedge_usd"]
            print(f"[MAIN:{player_name}] HEDGE BUY: ${hedge_usd:.2f} "
                  f"(our primary ${hedge_result['our_primary_usd']:.0f}, "
                  f"denizz primary ${hedge_result['denizz_primary_usd']:.0f}) | {title[:50]}")
            # Execute directly, bypass buffer/tier-upgrade
            import entry_manager as _hedge_em
            data = tracker.load()
            available = tracker.get_available_balance(data)
            hedge_usd = min(hedge_usd, available)
            if hedge_usd >= 5.0:
                def _do_hedge(tok=token_id, pr=entry_price, inc=hedge_usd,
                              c=condition_id, t=title, out=outcome, e=event_slug, pl=player_name):
                    _hedge_em.execute_part1(tok, pr, inc, c, t, out, e, tier="hedge", signal_player=pl)
                threading.Thread(target=_do_hedge, daemon=True).start()
            return

        buf = _get_buf(player_name, buf_key, entry_price)
        buf["buys"].append([time.time(), cost_usd])
        # Recompute total from buys list (prune already ran in _get_buf)
        buf["total_usd"] = sum(b[1] for b in buf["buys"])

        total_spent = buf["total_usd"]
        buy_count = len(buf["buys"])

        # TG notification on first crossing of $500 threshold (regardless of bot entry)
        min_invested = MIN_PLAYER_INVESTED.get(player_name, 500)
        if total_spent >= 500 and not buf["notified"]:
            buf["notified"] = True
            # Find what other players hold on this market (for context)
            opposition_note = _get_opposition_context(condition_id, outcome, player_name)
            tg.player_buy(player_name, title, outcome, entry_price, total_spent, opposition_note)

        # Below minimum for this player → buffer and wait.
        # BUT: skip this gate when position is already open (tier-upgrade) or
        # on-chain top-up detected — MIN_PLAYER_INVESTED is only for NEW signals.
        _is_upgrade_path = buf_key in _signaled_keys[player_name] or _force_tier_upgrade
        if total_spent < min_invested and not _is_upgrade_path:
            print(f"[MAIN:{player_name}] Buffering buy #{buy_count}: ${cost_usd:.0f} (total ${total_spent:.0f}, need ${min_invested:.0f})")
            return

        # Already signaled — check if player moved to a higher tier (top-up).
        # `_force_tier_upgrade` is set above when on-chain detection saw denizz
        # already holds non-dust shares on this token but our _signaled_keys is
        # empty (market seen by bot for the first time). In that case we take
        # the same tier-upgrade code path so Rule A+ / TOPUP_RATIO_TIERS size
        # the late entry correctly. We do NOT write to _signaled_keys here —
        # that write continues to happen ONLY in the Path A branch below
        # (hygiene of _signaled_keys is scoped to a separate task).
        if _is_upgrade_path:
            # HP strategy removed in v2 — no HP position check needed
            buf["buys"] = []
            buf["total_usd"] = 0.0

            # Fetch the player's REAL invested amount from positions API.
            # Bug fix: relying only on `total_spent` (= buffer accumulated since
            # bot started) misses all of the player's pre-bot-start history,
            # so tier upgrades never fired for positions where the player
            # had history before our bot launched.
            try:
                real_invested = filters.get_player_invested_on_token(
                    condition_id, PLAYERS[player_name], token_id
                )
            except Exception as e:
                print(f"[MAIN:{player_name}] tier-upgrade fetch error: {e}")
                real_invested = 0.0
            effective_invested = max(total_spent, real_invested)

            # --- Rule B: Tier upgrade price gate (refined) ---
            # Naive version would block any upgrade where current price > 2x
            # player's weighted avg. But a player who bought huge size cheap
            # and is NOW adding big at a higher price is showing conviction —
            # their new buy is itself at the high price. That's a valid signal
            # to follow, even though their historical avg is lower than current.
            #
            # The correct block condition is: player's CURRENT buy happening
            # right now (event['price']) is much lower than our entry. If the
            # player is paying the same price we'd pay, they're showing
            # fresh conviction — follow. Only block if our entry is far above
            # where the player is actually trading.
            try:
                player_avg_for_upgrade = filters.get_player_avg_price(
                    condition_id, PLAYERS[player_name], token_id
                )
            except Exception:
                player_avg_for_upgrade = 0.0
            # The triggering buy's price — this is what the player paid on
            # this specific BUY event (not their historical avg).
            triggering_buy_price = float(event.get("price", 0) or 0)
            if triggering_buy_price > 0 and entry_price > 0:
                current_buy_mult = entry_price / triggering_buy_price
                if current_buy_mult > 1.5:
                    # We'd pay 50%+ more than the player is paying RIGHT NOW.
                    # This is the real "we're chasing" scenario.
                    print(f"[MAIN:{player_name}] TIER UPGRADE BLOCKED (Rule B): "
                          f"our entry {entry_price:.3f} is {current_buy_mult:.1f}x "
                          f"the player's CURRENT buy price {triggering_buy_price:.3f} "
                          f"(>1.5x = we'd pay much worse than player right now) | {title[:40]}")
                    return

            new_bet = filters.calculate_bet_size(player_name, effective_invested, entry_price)

            # Variant 1: use tracker.cost_usd (live) when feature-flag on,
            # else fall back to legacy buf.last_tier_bet
            already_bet = _get_already_bet_v1(player_name, buf, condition_id, token_id)
            increment = round(new_bet - already_bet, 2)

            # Rule A+ applies to the INCREMENT, not the total. The already-paid
            # portion was sized correctly when it was placed; only the new
            # money should be scaled down for late entry. Fixed 2026-04-09:
            # previously the multiplier was applied to new_bet, which caused
            # increment to be (scaled_new_bet - already_bet) — sometimes
            # negative or undersized — and broke last_tier_bet bookkeeping.
            size_mult_up, mult_reason_up = filters.calculate_entry_size_multiplier(
                player_avg_for_upgrade, entry_price
            )
            if size_mult_up < 1.0 and increment > 0:
                increment_before = increment
                increment = round(increment * size_mult_up, 2)
                print(f"[MAIN:{player_name}] upgrade late-gate: {mult_reason_up} | "
                      f"increment ${increment_before:.2f} -> ${increment:.2f}")

            # Horizon multiplier (graduated by days to end_date) — composes with Rule A+
            try:
                _mi = filters.get_market_info(token_id)
                _end_date_str = ""
                if _mi:
                    _end_date_str = _mi.get("endDate") or _mi.get("end_date") or ""
            except Exception:
                _end_date_str = ""
            hz_mult, hz_reason = filters.get_horizon_multiplier(_end_date_str)
            if hz_mult == 0.0 and increment > 0:
                _prefix = ""
                print(f"{_prefix}[MAIN:{player_name}] upgrade BLOCKED: {hz_reason} | {title[:40]}")
                return
            if hz_mult < 1.0 and increment > 0:
                increment_before = increment
                increment = round(increment * hz_mult, 2)
                _prefix = ""
                print(f"{_prefix}[MAIN:{player_name}] upgrade horizon: {hz_reason} | "
                      f"increment ${increment_before:.2f} -> ${increment:.2f}")

            # === SLIPPAGE CHECK (tier-upgrade path) ===
            # Mirrors check_signal STEP 6 — block tier-upgrade if our ask is
            # too far above the player's triggering buy price. Without this,
            # a bot could chase pumps e.g. denizz buys @ 0.165 → ask jumps
            # to 0.222 (5.7c slippage) → bot would still buy in old logic.
            # Fail-safe: if orderbook unavailable → skip slippage check
            # (same behavior as check_signal; we don't block legit upgrades
            # on transient CLOB errors).
            if increment > 0:
                _prices = filters.get_orderbook_prices(token_id)
                if _prices is not None:
                    _current_ask = _prices[1]
                    _slippage = _current_ask - entry_price
                    _max_slip = filters.get_max_slippage(entry_price)
                    # Use 0.0005 tolerance to match check_signal's float-safe comparison
                    if _slippage > _max_slip + 0.0005:
                        print(f"[MAIN:{player_name}] TIER UPGRADE BLOCKED (slippage): "
                              f"ask {_current_ask:.3f} - denizz {entry_price:.3f} = "
                              f"{_slippage:.3f} > max {_max_slip:.3f} | {title[:40]}")
                        return

            from config import MIN_UPGRADE_USD
            upgrade_min = MIN_UPGRADE_USD  # $15 minimum for tier upgrade
            if increment >= upgrade_min:
                # Variant 1: throttle check before any side-effects
                if not _throttle_allows_upgrade(condition_id, token_id):
                    return
                data = tracker.load()
                available = tracker.get_available_balance(data)
                increment = min(increment, available)
                if increment >= upgrade_min and tracker.has_position_on_event(data, event_slug):
                    _prefix = ""
                    print(f"{_prefix}[MAIN:{player_name}] TIER UPGRADE: {player_name} now ${effective_invested:.0f} "
                          f"(buffer ${total_spent:.0f}, api ${real_invested:.0f}) → adding ${increment:.0f} | {title[:40]}")
                    # Track ACTUAL spent (= already_bet + scaled increment),
                    # not the pre-scale new_bet — otherwise the next upgrade
                    # would think we already paid more than we did.
                    buf["last_tier_bet"] = round(already_bet + increment, 2)

                    if False:  # DRY_RUN killed
                        print(f"[DRY-RUN] Would UPGRADE +${increment:.0f} @ {entry_price:.3f} | {title[:50]}")
                        return

                    cid = condition_id
                    es = event_slug

                    # Variant 1: mark pending order as in_flight BEFORE dispatch
                    from config import USE_ONCHAIN_COST
                    if USE_ONCHAIN_COST:
                        tracker.add_in_flight(cid, token_id, increment)

                    def _do_upgrade(tok=token_id, pr=entry_price, inc=increment,
                                    c=cid, t=title, out=outcome, e=es, pl=player_name):
                        try:
                            entry_manager.execute_part1(
                                tok, pr, inc, c, t, out, e, tier="upgrade",
                                signal_player=pl,
                            )
                        finally:
                            # Variant 1: clear in_flight regardless of fill/timeout outcome
                            from config import USE_ONCHAIN_COST as _UOC
                            if _UOC:
                                tracker.clear_in_flight(c, tok, inc)
                    threading.Thread(target=_do_upgrade, daemon=True).start()
                elif increment >= upgrade_min:
                    # Diagnostic: tier-upgrade was eligible by amount but we have
                    # no tracked position on this event — log instead of silently
                    # falling through (was the root cause of lost events).
                    print(f"[MAIN:{player_name}] TIER UPGRADE SKIP: no position on event "
                          f"{event_slug[:30]} (inc ${increment:.0f}) | {title[:40]}")
            else:
                print(f"[MAIN:{player_name}] Already signaled (inc ${increment:.0f} < ${upgrade_min:.0f} min @ ${effective_invested:.0f}): {title[:50]}")
                # V9 REBUY TRIGGER: state-based missed this signal because our cost
                # exceeds formula(net_invested). But denizz made a fresh buy — if
                # large enough, this is a reversal re-entry we should follow.
                try:
                    import rebuy as _rebuy
                    _rebuy.try_rebuy(
                        cid=condition_id, token_id=token_id, title=title,
                        outcome=outcome, event_slug=event_slug,
                        entry_price=entry_price,
                        new_buy_usd=float(cost_usd or 0),
                        our_cost=already_bet,
                        denizz_net_invested=effective_invested,
                        player_name=player_name,
                    )
                except Exception as _e:
                    print(f"[REBUY] error: {_e}")
            return

        # --- Rule C: Post-exit whipsaw protection ---
        # Block new entry if ALL THREE conditions are true:
        # 1. We exited on this exact (cid, token) within POST_EXIT_WINDOW_HOURS
        # 2. Current price is within POST_EXIT_PRICE_CHANGE_MIN of exit price
        # 3. PnL of the last sell was <= 0 (loss or break-even)
        # If the last exit was profitable (PnL > 0), allow re-entry.
        recent_exit = _recent_exit_on_market(condition_id, token_id)
        if recent_exit is not None:
            exit_ts, exit_price, exit_pnl = recent_exit
            if exit_price > 0 and entry_price > 0:
                price_change = abs(entry_price - exit_price) / exit_price
                age_h = (datetime.now(timezone.utc) - exit_ts).total_seconds() / 3600
                if price_change < POST_EXIT_PRICE_CHANGE_MIN:
                    if exit_pnl > 0:
                        # Profitable exit — allow re-entry (not whipsaw)
                        _prefix = ""
                        print(f"{_prefix}[MAIN:{player_name}] Rule C ALLOW: previous exit was "
                              f"profitable (PnL ${exit_pnl:.2f}) — re-entry permitted | {title[:40]}")
                    else:
                        # Fix 2026-04-21: override whipsaw when player is making
                        # a LARGE new accumulation — signals conviction re-entry,
                        # not a passive retest of the same losing setup.
                        # Two overrides (either triggers):
                        #   (a) single buy event >= $1500
                        #   (b) cumulative 24h buffer >= $3000
                        # Ref: _analytics/2026-04-21_rule_c_blocks_large_accumulation.md
                        RULE_C_OVERRIDE_SINGLE_BUY_USD = 1500.0
                        RULE_C_OVERRIDE_BUFFER_USD = 3000.0
                        _event_usd = float(cost_usd or 0)
                        _buffer_total = float(total_spent or 0)
                        if _event_usd >= RULE_C_OVERRIDE_SINGLE_BUY_USD:
                            print(f"[MAIN:{player_name}] RULE C OVERRIDE: "
                                  f"single buy ${_event_usd:.0f} >= ${RULE_C_OVERRIDE_SINGLE_BUY_USD:.0f} "
                                  f"— conviction signal, ignoring whipsaw | {title[:40]}")
                        elif _buffer_total >= RULE_C_OVERRIDE_BUFFER_USD:
                            print(f"[MAIN:{player_name}] RULE C OVERRIDE: "
                                  f"buffer ${_buffer_total:.0f} >= ${RULE_C_OVERRIDE_BUFFER_USD:.0f} "
                                  f"— heavy accumulation, ignoring whipsaw | {title[:40]}")
                        else:
                            _prefix = ""
                            print(f"{_prefix}[MAIN:{player_name}] RULE C SKIP: recent exit "
                                  f"{age_h:.1f}h ago @ {exit_price:.3f}, new entry @ "
                                  f"{entry_price:.3f} ({price_change*100:.1f}% change "
                                  f"< {POST_EXIT_PRICE_CHANGE_MIN*100:.0f}%), PnL ${exit_pnl:.2f} <= 0 "
                                  f"— whipsaw | {title[:40]}")
                            return
                else:
                    _prefix = ""
                    print(f"{_prefix}[MAIN:{player_name}] Rule C allow: exit {age_h:.1f}h ago @ "
                          f"{exit_price:.3f}, entry @ {entry_price:.3f} ({price_change*100:.1f}% moved)")

        # === CRITICAL SECTION: _entry_lock prevents parallel entries on same market ===
        # Bug 1+2+6 fix: without this lock, 3 parallel monitor events can all pass
        # has_position_on_condition() before any writes to tracker, causing 3x entry.
        with _entry_lock:
            # Tracker limits
            data = tracker.load()
            ok, reason = tracker.can_open_new(data)
            if not ok:
                tg.skip(title, f"[{player_name}] {reason}")
                print(f"[MAIN:{player_name}] SKIP: {reason}")
                return

            # Fix 2026-04-21: check same-TOKEN (same outcome), not entire
            # condition. Binary markets have YES and NO as independent outcomes.
            # Blocking at condition level caused us to miss denizz re-entry on
            # Pakistan (May 31) because we held a manual YES on the same market.
            # Ref: _analytics/2026-04-21_subm_double_entry_guard_too_coarse.md
            if token_id and tracker.has_open_position_on_token(data, token_id):
                print(f"[MAIN:{player_name}] SKIP: Already have open position on this token {title[:40]}")
                return

            # Signal check (category, price, opposition, sizing)
            event["_buffer_total_usd"] = total_spent
            event["_buffer_buy_count"] = buy_count
            passed, bet_size, reason, info = filters.check_signal(
                token_id, entry_price, event, signal_player=player_name
            )
            if not passed:
                tg.skip(title, f"[{player_name}] {reason}")
                print(f"[MAIN:{player_name}] SKIP: {reason}")
                return

            available = tracker.get_available_balance(data)
            min_bet = mode_manager.get_min_bet()

            if bet_size < min_bet:
                print(f"[MAIN:{player_name}] SKIP: bet ${bet_size:.2f} < min ${min_bet:.2f}")
                return
            if bet_size > available:
                bet_size = available
                if bet_size < min_bet:
                    print(f"[MAIN:{player_name}] SKIP: insufficient balance (${available:.2f})")
                    return

            # Mark as signaled IMMEDIATELY (inside lock) — prevents parallel entries
            _signaled_keys[player_name].add(buf_key)
            buf["last_tier_bet"] = bet_size

            player_invested = info.get("player_invested", 0)
            opposition = info.get("opposition", {})
            print(f"\n{'='*60}")
            print(f"[MAIN] SIGNAL from {player_name}: {title}")
            print(f"  Category: {info.get('category', '?')}")
            print(f"  {player_name} invested: ${player_invested:,.0f} -> our bet: ${bet_size:.0f}")
            print(f"  Entry: {entry_price:.3f} | Outcome: {outcome}")
            print(f"  Opposition: {opposition.get('reason', '?')}")
            print(f"{'='*60}\n")

            tier = "B"
            if player_invested >= 10000:
                tier = "S+"
            elif player_invested >= 5000:
                tier = "S"
            elif player_invested >= 2000:
                tier = "A"

            tg.signal_detected(player_name, title, outcome, entry_price, tier, bet_size)

            cid = info.get("condition_id", condition_id)
            es = info.get("event_slug", event_slug)

            def _do_entry():
                entry_manager.execute_part1(
                    token_id, entry_price, bet_size,
                    cid, title, outcome, es, tier,
                    signal_player=player_name,
                )

            thread = threading.Thread(target=_do_entry, daemon=True)
            thread.start()
        # === END CRITICAL SECTION ===

    except Exception as e:
        print(f"[MAIN] CRITICAL ERROR handle_buy ({player_name}): {e}")
        mode_manager.record_error(str(e))
    finally:
        # Persist buffer + signaled keys so a restart doesn't wipe them.
        _save_buffers()


def handle_sell(player_name: str, event: dict):
    """Player sold — exit our position if it was opened because of this player."""
    title = event.get("title", "?")
    print(f"[MAIN:{player_name}] SELL detected: {title[:50]}")

    def _do_exit():
        exit_manager.handle_player_sell(player_name, event)

    thread = threading.Thread(target=_do_exit, daemon=True)
    thread.start()


def handle_merge(player_name: str, event: dict):
    """Player merged YES+NO tokens → exit our position."""
    condition_id = event.get("condition_id", "")
    title = event.get("title", "?")
    print(f"[MAIN:{player_name}] MERGE: {title[:50]}")

    data = tracker.load()
    for key, pos in tracker.get_open_positions(data).items():
        if pos.get("condition_id") == condition_id and pos.get("signal_player") == player_name:
            sell_event = {
                "player": player_name,
                "condition_id": condition_id,
                "token_id": pos["token_id"],
                "title": title,
                "outcome": pos.get("outcome", ""),
                "event_slug": pos.get("event_slug", ""),
                "sold_shares": pos.get("size_shares", 0),
                "old_size": pos.get("size_shares", 0),
                "new_size": 0,
                "source": "merge",
                "reason": "MERGE_EXIT",
            }
            def _do_exit():
                exit_manager.handle_player_sell(player_name, sell_event)
            threading.Thread(target=_do_exit, daemon=True).start()
            break


def _get_opposition_context(condition_id: str, outcome: str, signal_player: str) -> str:
    """Quick check of other players' positions for TG notification context."""
    if not condition_id:
        return ""
    our_side = outcome.strip().capitalize()
    opposite = "No" if our_side == "Yes" else "Yes"
    notes = []
    from config import PLAYERS as ALL_PLAYERS
    for name, wallet in ALL_PLAYERS.items():
        if name == signal_player:
            continue
        same_usd = filters.get_player_usd_on_outcome(condition_id, wallet, our_side)
        opp_usd = filters.get_player_usd_on_outcome(condition_id, wallet, opposite)
        if same_usd >= 500:
            notes.append(f"{name}: {our_side} ${same_usd:,.0f} ✅")
        elif opp_usd >= 500:
            notes.append(f"{name}: {opposite} ${opp_usd:,.0f} ❌")
    return " | ".join(notes)


def periodic_checks():
    _rehydrate_counter = 0
    _cache_refresh_counter = 0
    _sync_counter = 0
    while True:
        try:
            exit_manager.check_exits()
            entry_manager.check_pending_parts()
            mode_manager.check_promotion()
            telegram_cmd.check_commands(mode_manager)
            # Every 5 minutes, sync signaled_keys with tracker
            _rehydrate_counter += 1
            if _rehydrate_counter >= max(1, 300 // max(POSITIONS_CHECK_INTERVAL, 1)):
                _rehydrate_from_tracker()
                _rehydrate_counter = 0
            # Every ~60 seconds, refresh player size cache on-chain
            # for tokens where WE have open positions (2-10 RPC calls)
            _cache_refresh_counter += 1
            if _cache_refresh_counter >= max(1, 60 // max(POSITIONS_CHECK_INTERVAL, 1)):
                exit_manager.refresh_cache_for_open_positions()
                _cache_refresh_counter = 0
            # Every ~5 minutes, sync tracker shares with on-chain reality
            _sync_counter += 1
            if _sync_counter >= max(1, 300 // max(POSITIONS_CHECK_INTERVAL, 1)):
                data = tracker.load()
                tracker.sync_with_onchain(data)
                _sync_counter = 0
        except Exception as e:
            print(f"[PERIODIC] Error: {e}")
            mode_manager.record_error(str(e), critical=False)
        time.sleep(POSITIONS_CHECK_INTERVAL)


def main():
    # Singleton via exclusive file lock (msvcrt.locking).
    # Open a lock file and hold an exclusive lock for the entire process lifetime.
    # If another instance tries to lock the same file → IOError → exit.
    import msvcrt
    _lock_path = os.path.join(BOT_DIR, "bot.lock")
    try:
        # Open in write mode — creates if not exists
        _lock_fd = open(_lock_path, "w")
        # Try exclusive lock on first byte (non-blocking)
        msvcrt.locking(_lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        # Keep _lock_fd open for entire process lifetime — do NOT close it
        print(f"[STARTUP] Singleton lock acquired (PID {os.getpid()})")
    except (IOError, OSError) as _lock_err:
        print(f"[FATAL] Another v2 instance is already running. Lock error: {_lock_err}")
        sys.exit(1)

    print("=" * 60)
    print("  MULTI-SIGNAL COPY-BOT v2")
    _dr = ""
    print(f"  Mode: {mode_manager.get_mode_label()}{_dr}")
    print(f"  Bankroll: ${BANKROLL:.0f}")
    print(f"  Signal players: {', '.join(PLAYERS.keys())}")
    print(f"  Price range: 30-95c | Opposition block: $500+")
    print(f"  Price: Car/aenews2: 10-82c | denizz: 15-82c")
    print(f"  Bet sizing: per-player additive tiers")
    print(f"  Started: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    tg.startup(BANKROLL)

    data = tracker.load()
    stats = data["stats"]
    onchain_bal = tracker.get_onchain_balance()
    internal_bal = stats['current_balance']
    if onchain_bal is not None:
        print(f"  Balance (on-chain): ${onchain_bal:.2f}  (internal counter: ${internal_bal:.2f})")
    else:
        print(f"  Balance (internal):  ${internal_bal:.2f}  (on-chain unavailable)")
    print(f"  Open positions: {tracker.count_open(data)}")
    print(f"  P&L: ${stats['total_pnl']:+.2f}")
    print("=" * 60)

    telegram_cmd.init()
    redeemer.start_background()
    daily_report.start_background()

    # Initialize player size cache from data-api (for on-chain sell verification)
    for pname, pwallet in PLAYERS.items():
        exit_manager.init_player_cache(pname, pwallet)

    # Approach C: load historical PEAK for each open position from activity history
    exit_manager.init_player_peaks()

    check_thread = threading.Thread(target=periodic_checks, daemon=True)
    check_thread.start()

    try:
        monitor.poll_loop(
            on_buy=handle_buy,
            on_sell=handle_sell,
            on_merge=handle_merge,
        )
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down...")
        tg.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    main()
