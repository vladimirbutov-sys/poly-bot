"""Monitor all 4 players for new trades.

Runs one polling thread per player (4 threads total).
Each thread detects BUY / SELL / MERGE and calls the corresponding callback.
"""
import time
import threading
import requests
from config import PLAYERS, DATA_API, POLL_INTERVAL


# === On-chain verify for phantom-sell protection ===
# Before triggering a SELL callback from the snapshot-diff path, we verify
# the player's token balance directly on-chain via CTF.balanceOf.
# This catches the #1 source of phantom sells: data-api pagination dropping
# a position from the response (denizz has 450+ positions, pagination is
# fragile). On-chain never lies.
#
# Fail-safe: if RPC call fails → do NOT fire the sell (better to miss a
# real exit by 25 seconds than to sell $300+ on a phantom).
_CTF_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
_CTF_ABI = [{"constant": True,
             "inputs": [{"name": "a", "type": "address"}, {"name": "id", "type": "uint256"}],
             "name": "balanceOf",
             "outputs": [{"name": "", "type": "uint256"}],
             "type": "function", "stateMutability": "view"}]
_w3_instance = None


def _get_w3():
    global _w3_instance
    if _w3_instance is None:
        try:
            from web3 import Web3
            from config import POLYGON_RPC
            _w3_instance = Web3(Web3.HTTPProvider(POLYGON_RPC, request_kwargs={"timeout": 10}))
        except Exception as e:
            print(f"[MONITOR] web3 init error: {e}")
    return _w3_instance


def _verify_player_balance_onchain(wallet: str, token_id: str) -> float | None:
    """Check player's REAL token balance on Polygon via CTF.balanceOf.

    Returns balance in shares (float), or None on any error.
    None means "we don't know" → caller should NOT assume sell happened.
    """
    try:
        w3 = _get_w3()
        if w3 is None:
            return None
        from web3 import Web3
        ctf = w3.eth.contract(
            address=Web3.to_checksum_address(_CTF_ADDRESS),
            abi=_CTF_ABI,
        )
        raw = ctf.functions.balanceOf(
            Web3.to_checksum_address(wallet), int(token_id)
        ).call()
        return raw / 1e6
    except Exception as e:
        print(f"[MONITOR] on-chain verify error: {e}")
        return None


def fetch_recent_activity(wallet: str, limit: int = 20) -> list:
    try:
        resp = requests.get(
            f"{DATA_API}/activity",
            params={"user": wallet, "limit": limit},
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        print(f"[MONITOR] Activity error ({wallet[:8]}...): {e}")
    return []


def fetch_positions(wallet: str, limit: int = 100) -> list:
    try:
        all_pos = []
        offset = 0
        while True:
            resp = requests.get(
                f"{DATA_API}/positions",
                params={"user": wallet, "sizeThreshold": 0,
                        "limit": limit, "offset": offset},
                timeout=15,
            )
            if resp.status_code != 200:
                break
            batch = resp.json()
            if not batch:
                break
            all_pos.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return all_pos
    except Exception as e:
        print(f"[MONITOR] Positions error ({wallet[:8]}...): {e}")
    return []


def build_snapshot(positions: list) -> dict:
    snap = {}
    for p in positions:
        key = f"{p.get('conditionId', '')}_{p.get('outcomeIndex', '')}"
        snap[key] = {
            "conditionId": p.get("conditionId", ""),
            "outcomeIndex": p.get("outcomeIndex", 0),
            "title": p.get("title", ""),
            "outcome": p.get("outcome", ""),
            "eventSlug": p.get("eventSlug", ""),
            "size": float(p.get("size", 0) or 0),
            "totalBought": float(p.get("totalBought", 0) or 0),
            "avgPrice": float(p.get("avgPrice", 0) or 0),
            "asset": p.get("asset", ""),
        }
    return snap


def _poll_player(player_name: str, wallet: str,
                 on_buy, on_sell, on_merge,
                 start_time: int):
    """Polling loop for a single player."""
    seen_keys = set()
    initial = fetch_recent_activity(wallet, 100)

    # --- STARTUP RECOVERY ---
    # Look for sells in the recent history that happened AFTER one of our
    # open positions was opened by THIS player. Without this, a restart that
    # happens shortly after a player sell will silently skip the follow-sell.
    try:
        import tracker as _tr
        from datetime import datetime as _dt
        _data = _tr.load()
        _our_open = [
            (k, p) for k, p in _data.get("positions", {}).items()
            if p.get("status") == "open"
            and p.get("signal_player") == player_name
            and not p.get("manual_hold")
        ]
        if _our_open:
            _recovered = 0
            # Process oldest -> newest so multiple sells on same market apply in order
            for trade in sorted(initial, key=lambda t: int(t.get("timestamp", 0) or 0)):
                if (trade.get("type", "") or "").upper() != "TRADE":
                    continue
                _side = (trade.get("side", "") or "").upper()
                _sz = float(trade.get("size", 0) or 0)
                if not (_side == "SELL" or _sz < 0):
                    continue
                _cond = trade.get("conditionId", "")
                _asset = trade.get("asset", "") or trade.get("tokenId", "")
                _trade_ts = int(trade.get("timestamp", 0) or 0)
                for _k, _pos in _our_open:
                    if _pos.get("condition_id") != _cond:
                        continue
                    if _pos.get("token_id") != _asset:
                        continue
                    # Only catch up sells that occurred AFTER we opened our position
                    _pos_ts_str = _pos.get("timestamp", "") or ""
                    try:
                        _pos_dt = _dt.fromisoformat(_pos_ts_str.replace("Z", "+00:00"))
                        _pos_ts = int(_pos_dt.timestamp())
                    except Exception:
                        _pos_ts = 0
                    if _pos_ts and _pos_ts >= _trade_ts:
                        continue
                    _title = trade.get("title", "")
                    print(f"[MONITOR:{player_name}] RECOVERY: missed sell — {_title[:60]} @ {float(trade.get('price', 0) or 0):.3f}")
                    _sell_event = {
                        "player": player_name,
                        "condition_id": _cond,
                        "token_id": _asset,
                        "title": _title,
                        "outcome": trade.get("outcome", ""),
                        "event_slug": trade.get("eventSlug", "") or trade.get("slug", ""),
                        "sell_size_tokens": abs(_sz),
                        "sell_price": float(trade.get("price", 0) or 0),
                        "sell_usd": float(trade.get("usdcSize", 0) or 0),
                        "old_size": 0,
                        "new_size": 0,
                        "sold_shares": abs(_sz),
                        "source": "activity_api",
                    }
                    try:
                        on_sell(player_name, _sell_event)
                        _recovered += 1
                    except Exception as e:
                        print(f"[MONITOR:{player_name}] Recovery sell callback error: {e}")
                    break  # this trade is handled
            if _recovered > 0:
                print(f"[MONITOR:{player_name}] Startup recovery: processed {_recovered} missed sell(s)")
    except Exception as e:
        print(f"[MONITOR:{player_name}] Recovery error: {e}")
    # --- END STARTUP RECOVERY ---

    for trade in initial:
        tx = trade.get("transactionHash", "")
        cond = trade.get("conditionId", "")
        ts = str(trade.get("timestamp", ""))
        # Dedupe fix 2026-04-17: include size+price so batch-order fills
        # with same (tx, cond, ts) but different execution prices register
        # as distinct trades (bug: Netanyahu $530 + $50 same-tx missed).
        size = trade.get("size", "")
        price = trade.get("price", "")
        seen_keys.add(f"{tx}_{cond}_{ts}_{size}_{price}")

    positions = fetch_positions(wallet)
    prev_snapshot = build_snapshot(positions)
    cycle = 0

    print(f"[MONITOR:{player_name}] Started. {len(seen_keys)} existing trades marked.")

    consecutive_errors = 0
    while True:
        try:
            cycle += 1

            # --- Activity: BUY / SELL / MERGE ---
            activities = fetch_recent_activity(wallet, 100)
            for trade in activities:
                tx = trade.get("transactionHash", "")
                cond = trade.get("conditionId", "")
                ts_val = trade.get("timestamp", 0)
                # Dedupe fix 2026-04-17: must match seed-key format (line ~205)
                size_key = trade.get("size", "")
                price_key = trade.get("price", "")
                trade_key = f"{tx}_{cond}_{ts_val}_{size_key}_{price_key}"

                if trade_key in seen_keys:
                    continue
                seen_keys.add(trade_key)

                trade_ts = int(ts_val) if ts_val else 0
                if trade_ts < start_time:
                    continue

                trade_type = trade.get("type", "").upper()

                if trade_type == "TRADE":
                    token_id = trade.get("asset", "") or trade.get("tokenId", "")
                    price = float(trade.get("price", 0) or 0)
                    usdc_size = float(trade.get("usdcSize", 0) or 0)
                    size = float(trade.get("size", 0) or 0)
                    side = trade.get("side", "").upper()
                    title = trade.get("title", "Unknown")
                    outcome = trade.get("outcome", "")
                    event_slug = trade.get("eventSlug", "") or trade.get("slug", "")

                    if not token_id or price <= 0:
                        continue

                    if side == "SELL" or size < 0:
                        print(f"[MONITOR:{player_name}] SELL: {title[:50]} {outcome} @ {price:.3f}")
                        sell_event = {
                            "player": player_name,
                            "condition_id": cond,
                            "token_id": token_id,
                            "title": title,
                            "outcome": outcome,
                            "event_slug": event_slug,
                            "sell_size_tokens": abs(size),
                            "sell_price": price,
                            "sell_usd": usdc_size,
                            "old_size": 0, "new_size": 0,
                            "sold_shares": abs(size),
                            "source": "activity_api",
                        }
                        try:
                            on_sell(player_name, sell_event)
                        except Exception as e:
                            print(f"[MONITOR:{player_name}] Sell callback error: {e}")
                        continue

                    if size <= 0:
                        continue

                    print(f"[MONITOR:{player_name}] BUY: {title[:50]} {outcome} @ {price:.3f} ${usdc_size:.0f}")
                    buy_event = {
                        "player": player_name,
                        "token_id": token_id,
                        "condition_id": cond,
                        "price": price,
                        "size": size,
                        "cost_usd": usdc_size,
                        "title": title,
                        "outcome": outcome,
                        "event_slug": event_slug,
                        "tx_hash": tx,
                    }
                    try:
                        on_buy(player_name, buy_event)
                    except Exception as e:
                        print(f"[MONITOR:{player_name}] Buy callback error: {e}")

                elif trade_type == "MERGE":
                    usdc_size = float(trade.get("usdcSize", 0) or 0)
                    title = trade.get("title", "Unknown")
                    token_id_merge = trade.get("asset", "") or trade.get("tokenId", "")
                    outcome = trade.get("outcome", "")
                    event_slug = trade.get("eventSlug", "") or trade.get("slug", "")
                    print(f"[MONITOR:{player_name}] MERGE: {title[:50]} ${usdc_size:.0f}")
                    merge_event = {
                        "player": player_name,
                        "condition_id": cond,
                        "token_id": token_id_merge,
                        "title": title,
                        "outcome": outcome,
                        "event_slug": event_slug,
                        "usdc_size": usdc_size,
                        "reason": "MERGE_EXIT",
                    }
                    try:
                        on_merge(player_name, merge_event)
                    except Exception as e:
                        print(f"[MONITOR:{player_name}] Merge callback error: {e}")

                elif trade_type == "SPLIT":
                    title = trade.get("title", "Unknown")
                    print(f"[MONITOR:{player_name}] SPLIT: {title[:50]}")

            # --- Position snapshot: detect sells every 5 cycles ---
            if cycle % 5 == 0:
                positions = fetch_positions(wallet)
                curr_snapshot = build_snapshot(positions)

                for key, prev in prev_snapshot.items():
                    curr = curr_snapshot.get(key)
                    if curr is None:
                        if prev["size"] > 0.1:
                            # Position DISAPPEARED from snapshot. This could be:
                            #  (a) player really sold 100%, or
                            #  (b) data-api pagination dropped it (denizz has 450+ positions)
                            # VERIFY on-chain before triggering sell.
                            onchain_bal = _verify_player_balance_onchain(wallet, prev["asset"])
                            if onchain_bal is None:
                                # RPC failed — fail-safe: do NOT sell
                                print(f"[MONITOR:{player_name}] SNAPSHOT: {prev['title'][:45]} "
                                      f"disappeared but on-chain verify FAILED — skipping (fail-safe)")
                                continue
                            if onchain_bal > prev["size"] * 0.05:
                                # Player still holds significant amount on-chain —
                                # this is a PHANTOM sell from API pagination issue
                                print(f"[MONITOR:{player_name}] PHANTOM SELL blocked: "
                                      f"{prev['title'][:45]} — API says gone but on-chain "
                                      f"shows {onchain_bal:.0f} sh (prev {prev['size']:.0f})")
                                continue
                            # Confirmed: on-chain balance is near zero → real exit
                            event = {
                                "player": player_name,
                                "condition_id": prev["conditionId"],
                                "token_id": prev["asset"],
                                "title": prev["title"],
                                "outcome": prev["outcome"],
                                "event_slug": prev["eventSlug"],
                                "old_size": prev["size"],
                                "new_size": 0,
                                "sold_shares": prev["size"],
                            }
                            try:
                                on_sell(player_name, event)
                            except Exception as e:
                                print(f"[MONITOR:{player_name}] Sell callback error: {e}")
                    elif curr["size"] < prev["size"] - 0.5:
                        sold = prev["size"] - curr["size"]
                        # Size DECREASED in snapshot. Verify on-chain that the
                        # reduction is real, not an API fluctuation.
                        onchain_bal = _verify_player_balance_onchain(wallet, prev["asset"])
                        if onchain_bal is not None and onchain_bal > prev["size"] * 0.95:
                            # On-chain still shows ~same size → phantom reduction
                            print(f"[MONITOR:{player_name}] PHANTOM REDUCTION blocked: "
                                  f"{prev['title'][:45]} — API says -{sold:.0f} sh but "
                                  f"on-chain still {onchain_bal:.0f} sh")
                            continue
                        if onchain_bal is None:
                            # RPC failed — fail-safe: skip
                            print(f"[MONITOR:{player_name}] SNAPSHOT: {prev['title'][:45]} "
                                  f"size drop but on-chain verify FAILED — skipping (fail-safe)")
                            continue
                        # Confirmed or on-chain confirms reduction
                        actual_sold = prev["size"] - onchain_bal
                        if actual_sold < 0.5:
                            continue  # negligible change
                        event = {
                            "player": player_name,
                            "condition_id": prev["conditionId"],
                            "token_id": prev["asset"],
                            "title": prev["title"],
                            "outcome": prev["outcome"],
                            "event_slug": prev["eventSlug"],
                            "old_size": prev["size"],
                            "new_size": onchain_bal,
                            "sold_shares": actual_sold,
                        }
                        try:
                            on_sell(player_name, event)
                        except Exception as e:
                            print(f"[MONITOR:{player_name}] Sell callback error: {e}")

                prev_snapshot = curr_snapshot

            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            backoff = min(POLL_INTERVAL * (2 ** min(consecutive_errors, 4)), 300)
            print(f"[MONITOR:{player_name}] Poll error (#{consecutive_errors}, backoff {backoff}s): {e}")
            time.sleep(backoff)
            continue

        time.sleep(POLL_INTERVAL)


def poll_loop(on_buy, on_sell, on_merge):
    """Start one monitoring thread per player. Blocks forever."""
    start_time = int(time.time())
    threads = []

    for player_name, wallet in PLAYERS.items():
        t = threading.Thread(
            target=_poll_player,
            args=(player_name, wallet, on_buy, on_sell, on_merge, start_time),
            name=f"monitor-{player_name}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        time.sleep(1)  # stagger startup to avoid rate limits

    print(f"[MONITOR] All {len(threads)} player threads started.")

    # Keep main thread alive + check thread health
    while True:
        time.sleep(120)
        for t in threads:
            if not t.is_alive():
                player = t.name.replace("monitor-", "")
                print(f"[MONITOR] THREAD DEAD: {t.name} — restarting")
                wallet = PLAYERS.get(player, "")
                if wallet:
                    new_t = threading.Thread(
                        target=_poll_player,
                        args=(player, wallet, on_buy, on_sell, on_merge, start_time),
                        name=f"monitor-{player}",
                        daemon=True,
                    )
                    new_t.start()
                    threads = [x for x in threads if x != t] + [new_t]
                    print(f"[MONITOR] THREAD RESTARTED: {t.name}")
