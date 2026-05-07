"""Comprehensive test for the on-chain-based sell logic.

25 scenarios covering: phantom sells, real sells, edge cases,
decision matrix, and historical incidents.

Does NOT call real APIs — all data is mocked.

Usage: py -3.12 -u -X utf8 _test_sell_logic.py
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# We test the LOGIC of handle_player_sell by simulating:
#  - _player_size_cache (what bot remembers)
#  - _get_player_size_onchain (what blockchain returns)
#  - tracker data (our open positions)
#  - event dict (what monitor sends)
# We capture what the function WOULD DO by intercepting _execute_sell.

import exit_manager
import importlib
importlib.reload(exit_manager)

# === Mock infrastructure ===
_mock_onchain = {}  # {token_id: balance}
_mock_tracker_data = {"positions": {}, "stats": {"total_bets": 0, "wins": 0, "losses": 0, "sells": 0, "total_pnl": 0, "peak_balance": 2000, "current_balance": 2000}}
_sell_calls = []  # records of (key, shares, price, reason)
_print_log = []


def _mock_get_player_size_onchain(wallet, token_id):
    return _mock_onchain.get(str(token_id))


def _mock_execute_sell(data, key, pos, shares, price, reason):
    _sell_calls.append({"key": key, "shares": shares, "price": price, "reason": reason})


def _mock_tracker_load():
    import copy
    return copy.deepcopy(_mock_tracker_data)


def _mock_tracker_save(data):
    pass


def _mock_consolidate(data):
    return 0


def _mock_get_open(data):
    return {k: v for k, v in data.get("positions", {}).items() if v.get("status") == "open"}


def _mock_orderbook(token_id):
    return (0.50, 0.51)  # (best_bid, best_ask)


def _mock_cost_basis(cid, wallet, tok):
    return 0.40  # default: player avg entry


def _mock_tg_send(msg):
    pass


def _mock_tg_sell_placed(*a, **kw):
    pass


def _mock_tg_error(*a, **kw):
    pass


# Patch everything
exit_manager._get_player_size_onchain = _mock_get_player_size_onchain
exit_manager._execute_sell = _mock_execute_sell
exit_manager.tracker.load = _mock_tracker_load
exit_manager.tracker.save = _mock_tracker_save
exit_manager.tracker.consolidate_duplicates = _mock_consolidate
exit_manager.tracker.get_open_positions = _mock_get_open
exit_manager.filters.get_orderbook_prices = _mock_orderbook
exit_manager.filters.get_player_cost_basis = _mock_cost_basis
exit_manager.tg.send = _mock_tg_send
exit_manager.tg.sell_placed = _mock_tg_sell_placed
exit_manager.tg.error = _mock_tg_error


# === Test helper ===
def setup(cache_size, onchain_size, our_shares=100, our_entry=0.50,
          token="tok1", cid="cid1", player="denizz"):
    """Reset state for a single test."""
    global _mock_tracker_data
    _sell_calls.clear()
    exit_manager._recent_exit_fires.clear()
    exit_manager._player_size_cache.clear()

    if cache_size is not None:
        exit_manager._cache_set(player, cid, token, cache_size)

    _mock_onchain.clear()
    if onchain_size is not None:
        _mock_onchain[token] = onchain_size

    _mock_tracker_data = {
        "positions": {
            "pos1": {
                "condition_id": cid,
                "token_id": token,
                "title": "Test Market",
                "outcome": "No",
                "status": "open",
                "signal_player": player,
                "size_shares": our_shares,
                "avg_entry": our_entry,
                "entry_price": our_entry,
            }
        },
        "stats": {"total_bets": 1, "wins": 0, "losses": 0, "sells": 0,
                  "total_pnl": 0, "peak_balance": 2000, "current_balance": 2000},
    }


def fire_sell(old_size=0, sold_shares=0, sell_price=0.45, source="activity_api",
              token="tok1", cid="cid1", player="denizz", reason=None):
    """Fire a sell event."""
    event = {
        "player": player,
        "condition_id": cid,
        "token_id": token,
        "title": "Test Market",
        "outcome": "No",
        "event_slug": "test",
        "old_size": old_size,
        "new_size": max(0, old_size - sold_shares) if old_size > 0 else 0,
        "sold_shares": sold_shares,
        "sell_price": sell_price,
        "source": source,
    }
    if reason:
        event["reason"] = reason
    exit_manager.handle_player_sell(player, event)


def result():
    """Return what happened: BLOCKED, FULL_EXIT, MIRROR_N%, SKIP_DUST, etc."""
    if not _sell_calls:
        return "BLOCKED"
    call = _sell_calls[0]
    shares = call["shares"]
    reason = call["reason"]
    if "big_dump" in reason or "merge" in reason or "full" in reason:
        return "FULL_EXIT"
    if "mirror" in reason:
        pct = round(shares / 100 * 100)  # assuming our_shares=100
        return f"MIRROR_{pct}%"
    return f"SELL_{shares:.0f}sh"


# =========================================================
# TESTS
# =========================================================
passed = 0
failed = 0
total = 0


def check(test_id, label, expected):
    global passed, failed, total
    total += 1
    actual = result()
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    if not ok:
        failed += 1
        print(f"  {status} {test_id}: {label}")
        print(f"       expected={expected}, got={actual}")
        if _sell_calls:
            print(f"       sell_calls={_sell_calls}")
    else:
        passed += 1
        print(f"  {status} {test_id}: {label}")


print("=" * 60)
print("SELL LOGIC TEST SUITE — 25 scenarios")
print("=" * 60)

# --- Group A: Phantom sells (should be BLOCKED) ---
print("\n--- Group A: Phantom sells ---")

# A1: API pagination drop — position "disappeared"
setup(cache_size=396000, onchain_size=396000)
fire_sell(old_size=396000, sold_shares=396000)
check("A1", "API pagination drop — onchain=cache=396k", "BLOCKED")

# A2: Activity replay, old_size=0, player still holds
setup(cache_size=396000, onchain_size=396000)
fire_sell(old_size=0, sold_shares=500)
check("A2", "Activity replay, old_size=0, player holds 396k", "BLOCKED")

# A3: Startup recovery phantom, sold=0
setup(cache_size=396000, onchain_size=396000)
fire_sell(old_size=0, sold_shares=0)
check("A3", "Startup recovery phantom (sold=0, player holds 396k)", "BLOCKED")

# A4: Snapshot jitter — tiny change <dust
setup(cache_size=10000, onchain_size=9960)
fire_sell(old_size=10000, sold_shares=40)
check("A4", "Snapshot jitter — actual_sold 40/10000=0.4% → dust", "BLOCKED")

# A5: Double phantom in 1 second
setup(cache_size=396000, onchain_size=396000)
fire_sell(old_size=0, sold_shares=504)
fire_sell(old_size=0, sold_shares=504)  # dedup should catch
check("A5", "Double phantom (2 events, both blocked)", "BLOCKED")

# --- Group B: Real sells (should pass) ---
print("\n--- Group B: Real sells ---")

# B1: Real 100% dump, old_size known
setup(cache_size=5000, onchain_size=0)
fire_sell(old_size=5000, sold_shares=5000)
check("B1", "Real 100% dump (onchain=0)", "FULL_EXIT")

# B2: Real 100% dump, old_size=0 (activity)
setup(cache_size=5000, onchain_size=0)
fire_sell(old_size=0, sold_shares=5000)
check("B2", "Real 100% dump, old_size=0 (activity)", "FULL_EXIT")

# B3: Real 30% partial, old_size known
setup(cache_size=10000, onchain_size=7000)
fire_sell(old_size=10000, sold_shares=3000, sell_price=0.35)
check("B3", "Real 30% partial (player loss → rule 2a)", "MIRROR_30%")

# B4: Real 30% partial, old_size=0 (activity)
setup(cache_size=10000, onchain_size=7000)
fire_sell(old_size=0, sold_shares=3000, sell_price=0.35)
check("B4", "Real 30% partial, old_size=0 (activity)", "MIRROR_30%")

# B5: Real 80% dump
setup(cache_size=10000, onchain_size=2000)
fire_sell(old_size=0, sold_shares=8000)
check("B5", "Real 80% dump (rule 3)", "FULL_EXIT")

# B6: Real 5% dust sell
setup(cache_size=10000, onchain_size=9500)
fire_sell(old_size=0, sold_shares=500)
check("B6", "Real 5% dust sell → SKIP", "BLOCKED")

# --- Group C: Edge cases ---
print("\n--- Group C: Edge cases ---")

# C1: RPC error (onchain=None)
setup(cache_size=5000, onchain_size=None)
fire_sell(old_size=5000, sold_shares=5000)
check("C1", "RPC error (onchain=None) → fail-safe SKIP", "BLOCKED")

# C2: No cache (first time)
setup(cache_size=None, onchain_size=3000)
fire_sell(old_size=0, sold_shares=1000)
check("C2", "No cache baseline → SKIP (cache initialized for next time)", "BLOCKED")

# C3: Player INCREASED position (actual_sold < 0)
setup(cache_size=5000, onchain_size=7000)
fire_sell(old_size=5000, sold_shares=0)
check("C3", "Player increased (5k→7k) → PHANTOM", "BLOCKED")

# C4: Merge event (bypass verify)
setup(cache_size=5000, onchain_size=5000)  # onchain still there but merge
fire_sell(old_size=5000, sold_shares=5000, reason="MERGE_EXIT", source="merge")
check("C4", "Merge event → bypass verify, FULL EXIT", "FULL_EXIT")

# C5: Dedup — 2nd event after 30 seconds
setup(cache_size=10000, onchain_size=7000)
fire_sell(old_size=0, sold_shares=3000, sell_price=0.35)
_sell_calls.clear()  # clear first result
# Simulate 30s later (still within 60s window)
# Don't reset dedup fires
_mock_onchain["tok1"] = 7000
exit_manager._cache_set("denizz", "cid1", "tok1", 7000)  # cache updated by first call
fire_sell(old_size=0, sold_shares=3000, sell_price=0.35)
check("C5", "Dedup: 2nd event after 0s → SKIP", "BLOCKED")

# C6: Dedup expired — 2nd event after 70 seconds
setup(cache_size=10000, onchain_size=7000)
fire_sell(old_size=0, sold_shares=3000, sell_price=0.35)
_sell_calls.clear()
# Simulate 70s by backdating the dedup entry
exit_manager._recent_exit_fires[("denizz", "cid1", "tok1")] = time.time() - 70
# Reset cache to simulate a second real sell
exit_manager._cache_set("denizz", "cid1", "tok1", 7000)
_mock_onchain["tok1"] = 4000  # player sold more
fire_sell(old_size=0, sold_shares=3000, sell_price=0.35)
# 3000/7000 = 43% → partial mirror
actual = result()
check("C6", "Dedup expired (70s) → new sell processed", "MIRROR_43%")

# --- Group D: Decision matrix ---
print("\n--- Group D: Decision matrix ---")

# For D1-D4: player sold 30% (cache=10000, onchain=7000)
# Player avg=0.40 (from mock), vary sell_price for profit/loss

# D1: partial 30%, player loss (sell 0.35 < avg 0.40), we in loss (entry 0.50, bid 0.50)
setup(cache_size=10000, onchain_size=7000, our_entry=0.50)
fire_sell(sell_price=0.35)
check("D1", "Partial 30%, player loss, we loss → MIRROR (rule 2a)", "MIRROR_30%")

# D2: partial 30%, player loss, we in profit (entry 0.40, bid 0.50)
setup(cache_size=10000, onchain_size=7000, our_entry=0.40)
fire_sell(sell_price=0.35)
check("D2", "Partial 30%, player loss, we profit → MIRROR (rule 2a)", "MIRROR_30%")

# D3: partial 30%, player profit (sell 0.55 > avg 0.40), we profit (entry 0.40)
setup(cache_size=10000, onchain_size=7000, our_entry=0.40)
fire_sell(sell_price=0.55)
check("D3", "Partial 30%, player profit, we profit → MIRROR (rule 2b)", "MIRROR_30%")

# D4: partial 30%, player profit, we in loss (entry 0.55)
setup(cache_size=10000, onchain_size=7000, our_entry=0.55)
fire_sell(sell_price=0.55)
check("D4", "Partial 30%, player profit, we loss → SKIP", "BLOCKED")

# D5: big dump 80%
setup(cache_size=10000, onchain_size=2000)
fire_sell(sell_price=0.45)
check("D5", "Big dump 80% → FULL EXIT (rule 3)", "FULL_EXIT")

# D6: dust 5%
setup(cache_size=10000, onchain_size=9500)
fire_sell(sell_price=0.45)
check("D6", "Dust 5% → SKIP", "BLOCKED")

# --- Group E: Historical incidents ---
print("\n--- Group E: Historical incidents ---")

# E1: Iran April 15 phantom (API pagination, denizz holds 396k)
setup(cache_size=396316, onchain_size=396316, our_shares=504)
fire_sell(old_size=396316, sold_shares=396316)
check("E1", "Iran Apr15 phantom (API pagination, denizz holds 396k)", "BLOCKED")

# E2: Iranian regime fall phantom (denizz holds 252k)
setup(cache_size=252000, onchain_size=252000, our_shares=202)
fire_sell(old_size=0, sold_shares=202)
check("E2", "Iranian regime fall phantom (old_size=0, denizz holds 252k)", "BLOCKED")

# E3: Hezbollah June 30 burst (7 events, denizz sold 29%)
# First event should go through, rest should dedup
setup(cache_size=6200, onchain_size=4400, our_shares=72)  # 29% sold
fire_sell(sell_price=0.38)  # player loss (0.38 < avg 0.40) → rule 2a
first_result = result()
_sell_calls.clear()
for i in range(6):
    fire_sell(sell_price=0.38)
check("E3", "Hezbollah Jun30 burst: 1st mirror, rest dedup → only 1 sell", "BLOCKED")
# Verify first one was a mirror
assert first_result.startswith("MIRROR"), f"E3 first event should be MIRROR, got {first_result}"
print(f"       (first event was: {first_result} ✓)")

# E4: Trump Iran real 100% dump (denizz onchain=0)
setup(cache_size=5000, onchain_size=0, our_shares=189)
fire_sell(sell_price=0.53)
check("E4", "Trump Iran real 100% dump (onchain=0)", "FULL_EXIT")

# E5: Hezbollah Apr 30 real partial 29% (denizz loss sell)
setup(cache_size=27000, onchain_size=19170, our_shares=279)  # 29% sold
fire_sell(sell_price=0.53)  # 0.53 > avg 0.40 → player in profit
# But we set our_entry=0.50, bid=0.50 → we_in_profit is borderline
# With default mock: bid=0.50, entry=0.50, PROFIT_DELTA=0.01 → NOT in profit
# Player profit, we NOT in profit → SKIP rule 2b
check("E5", "Hezbollah Apr30 29% player profit, we NOT in profit → SKIP", "BLOCKED")


# === SUMMARY ===
print(f"\n{'='*60}")
print(f"RESULTS: {passed}/{total} PASS, {failed} FAIL")
print(f"{'='*60}")
if failed == 0:
    print("ALL TESTS PASSED ✓")
else:
    print(f"⚠ {failed} TESTS FAILED")
sys.exit(0 if failed == 0 else 1)
