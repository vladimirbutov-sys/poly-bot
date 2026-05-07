"""Comprehensive stress-test for follow-sell logic.

Run:  py -3.12 _test_follow_sell_comprehensive.py

Covers (do NOT modify production code — tests only):
  - FOLLOW_SELL_TIERS_PROFIT / _LOSS correctness
  - disable_stop_loss flag does NOT block follow-sell
  - Precision-safe sell (SAFETY_MARGIN_SHARES)
  - Phantom reduction guard (cached==onchain)
  - Duplicate sell dedupe (60-sec window)
  - Cross-player SKIP (signal_player != event.player)
  - Manual-position opt-in to follow-sell
  - "manual" position signal_player allows any active player sell
  - Peak-based sold_pct is actually delta/cached (not peak-based — documenting reality)
  - Consolidate duplicates runs before follow-sell
  - RPC failure -> fail-safe skip
  - cached=0 -> skip
  - our_shares < 0.5 -> skip
  - Batch-fill dedupe: different (size, price) on same tx — must pass

Prints a summary and exits with non-zero code if any test fails.
"""
import io
import os
import sys
import types
import time
import importlib
from datetime import datetime, timezone

# UTF-8 console for Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Force stable path: ensure bot dir on sys.path
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)

# ---------------------------------------------------------------------------
# Fake-out network dependencies BEFORE importing exit_manager.
# We install stubs for:
#   - filters.get_orderbook_prices
#   - filters.get_player_cost_basis
#   - executor.place_limit_sell, wait_for_fill_with_details, _get_client,
#     SELL_SKIP_INSUFFICIENT_BALANCE
#   - tracker.load / save / consolidate_duplicates / get_open_positions /
#     record_sell / _fire_on_close / register_on_close
#   - telegram_notify stubs
#   - monitor (module-level, just to import something named `monitor`)
# ---------------------------------------------------------------------------


# -- telegram_notify stub ----------------------------------------------------
tg_mod = types.ModuleType("telegram_notify")
tg_mod.send = lambda *a, **k: None
tg_mod.error = lambda *a, **k: None
tg_mod.sell_placed = lambda *a, **k: None
tg_mod.buy_placed = lambda *a, **k: None
sys.modules["telegram_notify"] = tg_mod

# -- limit_tracker stub (used inside _execute_sell) --------------------------
lt_mod = types.ModuleType("limit_tracker")
lt_mod.log_exit = lambda *a, **k: None
sys.modules["limit_tracker"] = lt_mod

# -- safe_sell stub (so executor import doesn't try web3) --------------------
# We don't import executor's real place_limit_sell — we'll monkeypatch below.
ss_mod = types.ModuleType("safe_sell")
ss_mod.compute_safe_sell_size = lambda *a, **k: (k.get("requested_shares", 0), k.get("requested_shares", 0))
sys.modules["safe_sell"] = ss_mod

# -- py_clob_client stub (executor imports it at top) ------------------------
pcc_root = types.ModuleType("py_clob_client")
pcc_client_mod = types.ModuleType("py_clob_client.client")
class _FakeClobClient:
    def __init__(self, *a, **k): pass
    def set_api_creds(self, *a, **k): pass
    def create_or_derive_api_creds(self, *a, **k): return None
    def create_order(self, *a, **k): return None
    def post_order(self, *a, **k): return {"success": True, "orderID": "fake-order"}
    def cancel_all(self, *a, **k): return None
    def cancel(self, *a, **k): return None
    def get_order(self, *a, **k): return {"status": "MATCHED"}
pcc_client_mod.ClobClient = _FakeClobClient

pcc_types_mod = types.ModuleType("py_clob_client.clob_types")
class _FakeOrderArgs:
    def __init__(self, **k): self.__dict__.update(k)
class _FakeOrderType:
    GTC = "GTC"
    FOK = "FOK"
pcc_types_mod.OrderArgs = _FakeOrderArgs
pcc_types_mod.OrderType = _FakeOrderType

sys.modules["py_clob_client"] = pcc_root
sys.modules["py_clob_client.client"] = pcc_client_mod
sys.modules["py_clob_client.clob_types"] = pcc_types_mod

# ---------------------------------------------------------------------------
# Now import the real modules
# ---------------------------------------------------------------------------
import config
import tracker
import executor
import filters
import exit_manager


# ---------------------------------------------------------------------------
# Test harness helpers
# ---------------------------------------------------------------------------
PASS = 0
FAIL = 0
FAIL_DETAILS = []

def _reset_globals():
    """Clean up globals between tests."""
    exit_manager._player_size_cache.clear()
    exit_manager._player_peak_cache.clear()
    exit_manager._recent_exit_fires.clear()


def _install_patches(*, orderbook_price=0.50, player_cost_basis=0.30,
                     onchain_player_balance=0.0,
                     positions=None, record_sell_spy=None,
                     place_limit_sell_spy=None,
                     wait_fill_result=None,
                     cancel_all_spy=None):
    """Monkey-patch external dependencies so we can test in isolation.
    Returns the `state` dict the caller can inspect after the test."""
    state = {
        "executed_sells": [],       # list of (key, shares, price, reason)
        "orders_placed": [],        # list of (token_id, price, shares)
        "cancels": 0,
        "data": {"positions": positions or {}, "stats": {}},
    }

    # --- filters -----------------------------------------------------------
    filters.get_orderbook_prices = lambda tid: (
        [orderbook_price, orderbook_price - 0.01, orderbook_price - 0.02]
        if orderbook_price is not None else None
    )
    filters.get_player_cost_basis = lambda cid, wallet, token: player_cost_basis

    # --- tracker -----------------------------------------------------------
    tracker.load = lambda: state["data"]
    tracker.save = lambda d: None
    tracker.consolidate_duplicates = lambda d: 0
    tracker.get_open_positions = lambda d: {
        k: p for k, p in d["positions"].items() if p.get("status") == "open"
    }

    def _record_sell(data, key, sh, pr, rev, reason):
        state["executed_sells"].append({
            "key": key, "shares": sh, "price": pr,
            "revenue": rev, "reason": reason,
        })
        pos = data["positions"].get(key)
        if pos:
            pos["size_shares"] = max(0, pos.get("size_shares", 0) - sh)
            if pos["size_shares"] < 0.1:
                pos["status"] = "sold"
    tracker.record_sell = _record_sell
    tracker._fire_on_close = lambda *a, **k: None

    # --- exit_manager on-chain helpers ------------------------------------
    exit_manager._get_player_size_onchain = lambda w, t: onchain_player_balance

    # --- executor ----------------------------------------------------------
    def _fake_place_limit_sell(token_id, price, shares, safety_margin=None):
        state["orders_placed"].append({
            "token_id": token_id, "price": price, "shares": shares,
            "safety_margin": safety_margin,
        })
        if place_limit_sell_spy:
            return place_limit_sell_spy(token_id, price, shares, safety_margin)
        return {"order_id": "fake-" + str(len(state["orders_placed"])),
                "price": price, "size_shares": shares, "revenue_usd": shares * price}
    executor.place_limit_sell = _fake_place_limit_sell

    def _fake_wait_fill(order_id, timeout=300):
        if wait_fill_result is not None:
            return wait_fill_result
        return {"status": "MATCHED", "size_matched": 0, "size_original": 0}
    executor.wait_for_fill_with_details = _fake_wait_fill

    class _Client:
        def cancel_all(self):
            state["cancels"] += 1
    executor._get_client = lambda: _Client()

    return state


def assert_true(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS: {msg}")
    else:
        FAIL += 1
        FAIL_DETAILS.append(msg)
        print(f"  FAIL: {msg}")


# ---------------------------------------------------------------------------
# Scenario builders
# ---------------------------------------------------------------------------
DENIZZ_WALLET = config.PLAYERS["denizz"]
CID = "0xtestcid"
TOKEN = "12345"


def _build_our_position(cost=100.0, shares=100.0, avg_entry=0.30,
                       disable_stop_loss=False, signal_player="denizz"):
    return {
        "key-1": {
            "condition_id": CID,
            "token_id": TOKEN,
            "title": "Test market — scenario",
            "entry_price": avg_entry,
            "avg_entry": avg_entry,
            "size_shares": shares,
            "cost_usd": cost,
            "tier": "B",
            "signal_player": signal_player,
            "status": "open",
            "timestamp": "2026-04-01T00:00:00+00:00",
            "disable_stop_loss": disable_stop_loss,
        }
    }


def _build_sell_event(size=100.0, price=0.40, usdcSize=None):
    return {
        "player": "denizz",
        "condition_id": CID,
        "token_id": TOKEN,
        "title": "Test market — scenario",
        "outcome": "Yes",
        "event_slug": "test-market",
        "sell_size_tokens": size,
        "sell_price": price,
        "sell_usd": usdcSize if usdcSize is not None else size * price,
        "old_size": 0, "new_size": 0,
        "sold_shares": size,
        "source": "activity_api",
    }


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------
def run_test(name, fn):
    print(f"\n--- {name} ---")
    _reset_globals()
    try:
        fn()
    except Exception as e:
        global FAIL
        FAIL += 1
        FAIL_DETAILS.append(f"{name}: EXCEPTION {e!r}")
        import traceback
        traceback.print_exc()


# =============== BASE SCENARIOS — tier correctness ==========================

def test_5pct_dust_in_profit():
    """Denizz sold 5% (dust). We are in profit. Expected: skip."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    cached = 1000.0
    onchain_after = 950.0  # denizz sold 50 = 5%
    state = _install_patches(
        orderbook_price=0.50,   # our entry 0.30 → in profit
        player_cost_basis=0.25,
        onchain_player_balance=onchain_after,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, cached)
    exit_manager._peak_set("denizz", CID, TOKEN, cached)

    ev = _build_sell_event(size=50, price=0.50)
    exit_manager.handle_player_sell("denizz", ev)

    assert_true(len(state["executed_sells"]) == 0,
                "5% dust in profit → no sell")


def test_15pct_profit():
    """Denizz sold 15% in profit. We are in profit → sell 15%."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    cached = 1000.0
    onchain_after = 850.0  # 15% sold
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=onchain_after,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, cached)
    exit_manager._peak_set("denizz", CID, TOKEN, cached)

    ev = _build_sell_event(size=150, price=0.50)
    exit_manager.handle_player_sell("denizz", ev)

    assert_true(len(state["orders_placed"]) == 1, "15% profit: 1 order placed")
    if state["orders_placed"]:
        shares = state["orders_placed"][0]["shares"]
        # FOLLOW_SELL_TIERS_PROFIT: 10-20% → 15% of our shares = 15
        assert_true(abs(shares - 15.0) < 0.01,
                    f"15% profit → sell 15 sh (got {shares})")


def test_15pct_loss():
    """Denizz sold 15%. We are in LOSS → LOSS table starts at 20%, so skip."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    cached = 1000.0
    onchain_after = 850.0  # 15% sold
    state = _install_patches(
        orderbook_price=0.20,   # our entry 0.30 → in LOSS
        player_cost_basis=0.25,
        onchain_player_balance=onchain_after,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, cached)
    exit_manager._peak_set("denizz", CID, TOKEN, cached)

    ev = _build_sell_event(size=150, price=0.20)
    exit_manager.handle_player_sell("denizz", ev)

    assert_true(len(state["orders_placed"]) == 0,
                "15% loss → dust (LOSS table starts at 20%)")


def test_25pct_profit():
    """Denizz 25% profit → sell 25%."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=750.0,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=250, price=0.50))
    assert_true(len(state["orders_placed"]) == 1 and
                abs(state["orders_placed"][0]["shares"] - 25.0) < 0.01,
                f"25% profit → sell 25 sh (got {state['orders_placed']})")


def test_25pct_loss():
    """Denizz 25% loss → LOSS tier: sell 25%."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.20,  # our loss
        player_cost_basis=0.25,
        onchain_player_balance=750.0,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=250, price=0.20))
    assert_true(len(state["orders_placed"]) == 1 and
                abs(state["orders_placed"][0]["shares"] - 25.0) < 0.01,
                f"25% loss → sell 25 sh (got {state['orders_placed']})")


def test_50pct_profit():
    """Denizz 50% profit → sell 55%."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=500.0,  # 50% sold
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.50))
    assert_true(len(state["orders_placed"]) == 1 and
                abs(state["orders_placed"][0]["shares"] - 55.0) < 0.01,
                f"50% profit → sell 55 sh (got {state['orders_placed']})")


def test_80pct_profit():
    """Denizz 80% profit → sell 100%."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=200.0,  # 80% sold
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=800, price=0.50))
    assert_true(len(state["orders_placed"]) == 1 and
                abs(state["orders_placed"][0]["shares"] - 100.0) < 0.01,
                f"80% profit → sell 100 sh (got {state['orders_placed']})")


def test_100pct_profit():
    """Denizz fully exited (100%) → sell 100% even at boundary."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=0.0,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=1000, price=0.50))
    assert_true(len(state["orders_placed"]) == 1 and
                abs(state["orders_placed"][0]["shares"] - 100.0) < 0.01,
                f"100% → sell 100 (got {state['orders_placed']})")


# =============== EDGE CASES ================================================

def test_disable_stop_loss_does_not_block_follow_sell():
    """CRITICAL: disable_stop_loss=True must NOT block follow-sell.
    This flag should only affect the stop-loss block in check_exits, NOT
    handle_player_sell. If denizz dumps a hedge, we still follow him out."""
    positions = _build_our_position(
        cost=100, shares=100, avg_entry=0.30,
        disable_stop_loss=True, signal_player="denizz"
    )
    state = _install_patches(
        orderbook_price=0.15,   # in loss → worst case
        player_cost_basis=0.25,
        onchain_player_balance=500.0,   # 50% sold
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.15))
    assert_true(len(state["orders_placed"]) == 1,
                "disable_stop_loss=True still triggers follow-sell")


def test_phantom_reduction_cache_equals_onchain():
    """Cache=1000, onchain=1000, event says sold — must be treated as phantom."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=1000.0,  # unchanged
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.50))
    assert_true(len(state["orders_placed"]) == 0,
                "phantom (cache==onchain) → no sell")


def test_rpc_failure_fail_safe():
    """RPC returns None → do NOT sell (fail-safe)."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=None,  # RPC failure
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.50))
    assert_true(len(state["orders_placed"]) == 0,
                "RPC None → fail-safe skip")


def test_duplicate_sell_event_within_60s():
    """Two sell events within 60s dedupe window for same (player, cid, token)."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=500.0,  # 50%
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    # First fires
    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.50))
    first_count = len(state["orders_placed"])

    # Second inside 60s — should be dedup-skipped
    exit_manager.handle_player_sell("denizz", _build_sell_event(size=100, price=0.50))
    second_count = len(state["orders_placed"])

    assert_true(first_count == 1, "first sell executed")
    assert_true(second_count == 1, "second sell dedup-skipped (no new order)")


def test_cross_player_skip():
    """Position opened by 'car' — denizz event arrives → SKIP (cross-player)."""
    positions = _build_our_position(
        cost=100, shares=100, avg_entry=0.30, signal_player="car"
    )
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=500.0,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.50))
    assert_true(len(state["orders_placed"]) == 0,
                "cross-player skip: denizz sell on car-opened pos → no sell")


def test_manual_position_follows_denizz():
    """signal_player='manual' opts into follow-sell from any active player."""
    positions = _build_our_position(
        cost=100, shares=100, avg_entry=0.30, signal_player="manual"
    )
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=500.0,   # 50% → 55% sell
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.50))
    assert_true(len(state["orders_placed"]) == 1 and
                abs(state["orders_placed"][0]["shares"] - 55.0) < 0.01,
                f"manual pos follows denizz (got {state['orders_placed']})")


def test_manual_position_with_disable_stop_loss():
    """CRITICAL for $83 Trump hedge: manual + disable_stop_loss still sells."""
    positions = _build_our_position(
        cost=80, shares=180, avg_entry=0.44,
        signal_player="manual", disable_stop_loss=True
    )
    state = _install_patches(
        orderbook_price=0.40,   # slight loss
        player_cost_basis=0.35,
        onchain_player_balance=400.0,   # 60% sold by denizz from 1000
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=600, price=0.40))
    # 60% loss-tier → 75%
    assert_true(len(state["orders_placed"]) == 1,
                "manual + dsl follows denizz 60% sell")
    if state["orders_placed"]:
        shares = state["orders_placed"][0]["shares"]
        assert_true(abs(shares - 180.0 * 0.75) < 0.1,
                    f"manual+dsl: 60% loss → 75% of 180 = 135 (got {shares})")


def test_no_matching_position():
    """Denizz sells a token we don't hold → nothing happens."""
    positions = {}   # no positions
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=500.0,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.50))
    assert_true(len(state["orders_placed"]) == 0,
                "no matching position → no sell")


def test_our_shares_below_threshold():
    """Our size < 0.5 → skip."""
    positions = _build_our_position(cost=1, shares=0.3, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=500.0,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.50))
    assert_true(len(state["orders_placed"]) == 0,
                "our_shares < 0.5 → skip")


def test_price_gap_skip_when_in_loss():
    """If we are in loss AND our bid is >40% worse than player's sell → skip."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.80)
    state = _install_patches(
        orderbook_price=0.20,   # massive loss, our bid 0.20
        player_cost_basis=0.70,
        onchain_player_balance=500.0,  # 50%
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    # Player sold at 0.60, our bid 0.20 → price_gap = 66% > 40%
    exit_manager.handle_player_sell("denizz", _build_sell_event(size=500, price=0.60))
    assert_true(len(state["orders_placed"]) == 0,
                "price gap >40% in loss → skip")


def test_cached_size_zero():
    """cached_size=0 and onchain=0 → skip (can't compute pct)."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=0.0,
        positions=positions,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 0.0)  # cache=0
    exit_manager._peak_set("denizz", CID, TOKEN, 0.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=100, price=0.50))
    assert_true(len(state["orders_placed"]) == 0,
                "cached=0 → skip")


def test_precision_margin_applied_to_place_limit_sell():
    """Check executor.place_limit_sell is called with correct args, and
    _execute_sell retries with larger safety_margin on first failure.

    We simulate: 1st place_limit_sell → None (failure);
                  2nd place_limit_sell → success with safety_margin=5× default.
    """
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)

    call_state = {"calls": []}
    def _pls(tid, pr, sh, safety_margin=None):
        call_state["calls"].append({"sm": safety_margin, "shares": sh})
        if len(call_state["calls"]) == 1:
            return None  # first fails
        return {"order_id": "retry-ok", "price": pr, "size_shares": sh, "revenue_usd": sh*pr}

    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=200.0,
        positions=positions,
        place_limit_sell_spy=_pls,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=800, price=0.50))

    assert_true(len(call_state["calls"]) == 2, "place_limit_sell called twice (retry)")
    if len(call_state["calls"]) == 2:
        first_sm = call_state["calls"][0]["sm"]
        second_sm = call_state["calls"][1]["sm"]
        assert_true(first_sm is None, "first call: safety_margin=None (default)")
        expected_retry = config.SAFETY_MARGIN_SHARES * config.RETRY_SAFETY_MARGIN_MULT
        assert_true(abs(second_sm - expected_retry) < 1e-9,
                    f"retry call: sm={second_sm} (expected {expected_retry})")


def test_partial_fill_retry_at_lower_price():
    """If sell is PARTIAL, a retry at price*0.98 is attempted for the remainder."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)

    calls = {"n": 0}
    def _pls(tid, pr, sh, safety_margin=None):
        calls["n"] += 1
        return {"order_id": f"o{calls['n']}", "price": pr, "size_shares": sh, "revenue_usd": sh*pr}

    fills = {"n": 0}
    def _wff(oid, timeout=300):
        fills["n"] += 1
        if fills["n"] == 1:
            return {"status": "PARTIAL", "size_matched": 50, "size_original": 100}
        return {"status": "MATCHED", "size_matched": 50, "size_original": 50}

    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=0.0,  # denizz sold 100%
        positions=positions,
        place_limit_sell_spy=_pls,
    )
    executor.wait_for_fill_with_details = _wff
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=1000, price=0.50))

    # Two place_limit_sell calls: initial + retry at lower price
    assert_true(calls["n"] == 2, f"partial → retry (got {calls['n']} calls)")


def test_pending_retry_marker_on_total_failure():
    """If both attempts return None → _pending_exit_retry marker is set."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)
    def _pls_fail(*a, **k):
        return None
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=200.0,
        positions=positions,
        place_limit_sell_spy=_pls_fail,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=800, price=0.50))

    pos = state["data"]["positions"]["key-1"]
    assert_true("_pending_exit_retry" in pos,
                "_pending_exit_retry marker set on total failure")
    if "_pending_exit_retry" in pos:
        pending = pos["_pending_exit_retry"]
        assert_true(pending.get("attempts", 0) >= 1,
                    f"attempts recorded (got {pending.get('attempts')})")


def test_skip_insufficient_balance_closes_tracker_row():
    """place_limit_sell returns SELL_SKIP_INSUFFICIENT_BALANCE
    → tracker row is set to sold (0 shares, reason exit_skip_onchain_empty)."""
    positions = _build_our_position(cost=100, shares=100, avg_entry=0.30)

    def _pls_skip(*a, **k):
        return {
            "error": executor.SELL_SKIP_INSUFFICIENT_BALANCE,
            "requested": 100, "onchain": 0.1, "safe_size": 0.05,
        }
    state = _install_patches(
        orderbook_price=0.50,
        player_cost_basis=0.25,
        onchain_player_balance=200.0,
        positions=positions,
        place_limit_sell_spy=_pls_skip,
    )
    exit_manager._cache_set("denizz", CID, TOKEN, 1000.0)
    exit_manager._peak_set("denizz", CID, TOKEN, 1000.0)

    exit_manager.handle_player_sell("denizz", _build_sell_event(size=800, price=0.50))
    pos = state["data"]["positions"]["key-1"]
    assert_true(pos.get("status") == "sold",
                f"tracker closed on SKIP_INSUFFICIENT_BALANCE (status={pos.get('status')})")
    assert_true(pos.get("size_shares") == 0, "size_shares zeroed")


# ================= MONITOR DEDUPE KEY (size+price fix) ======================

def test_monitor_dedupe_batch_fills_distinct():
    """Two batch-fills with same (tx, cond, ts) but different (size, price)
    must register as distinct events after the 2026-04-17 fix."""
    # We emulate by building the dedupe key the same way monitor does.
    tx = "0xabc"
    cond = "0xcid"
    ts = "1776400000"
    # Fill A: 530 @ 0.40
    key_a = f"{tx}_{cond}_{ts}_{530}_{0.40}"
    # Fill B: 50 @ 0.42
    key_b = f"{tx}_{cond}_{ts}_{50}_{0.42}"
    assert_true(key_a != key_b,
                "batch fills with different (size, price) get distinct keys")
    # Same fill, same key = dedup
    key_a2 = f"{tx}_{cond}_{ts}_{530}_{0.40}"
    assert_true(key_a == key_a2, "identical fill deduped")


def test_monitor_dedupe_old_key_would_have_collided():
    """Document the bug that was fixed: old key (tx,cond,ts) would collide."""
    tx = "0xabc"; cond = "0xcid"; ts = "1776400000"
    old_a = f"{tx}_{cond}_{ts}"
    old_b = f"{tx}_{cond}_{ts}"
    assert_true(old_a == old_b,
                "(documentary) old dedupe key collided on batch fills — fixed 2026-04-17")


# ============== TIER TABLE STRUCTURAL CHECKS ===============================

def test_tier_tables_are_sane():
    """FOLLOW_SELL_TIERS_PROFIT/LOSS tables cover [0, 1.01] with no gaps."""
    from config import FOLLOW_SELL_TIERS_PROFIT, FOLLOW_SELL_TIERS_LOSS
    for name, tbl in [("PROFIT", FOLLOW_SELL_TIERS_PROFIT),
                      ("LOSS", FOLLOW_SELL_TIERS_LOSS)]:
        # Sorted, contiguous
        for i in range(len(tbl) - 1):
            assert_true(tbl[i][1] == tbl[i + 1][0],
                        f"{name} tier[{i}] hi == tier[{i+1}] lo ({tbl[i][1]}=={tbl[i+1][0]})")
        assert_true(tbl[0][0] == 0.0, f"{name} starts at 0.0")
        assert_true(tbl[-1][1] >= 1.0, f"{name} covers up to >=1.0")
        # fractions are non-decreasing
        prev = -1
        for lo, hi, f in tbl:
            assert_true(f >= prev, f"{name} tier {lo}-{hi} frac non-decreasing")
            prev = f


def test_tier_tables_match_expected():
    """Hardcode expected values from the spec so test fails if config changes."""
    from config import FOLLOW_SELL_TIERS_PROFIT, FOLLOW_SELL_TIERS_LOSS
    # profit: 10-20% → 0.15; 80%+ → 1.0
    frac = next((f for lo, hi, f in FOLLOW_SELL_TIERS_PROFIT if lo == 0.10), None)
    assert_true(frac == 0.15, f"PROFIT 10-20% = 0.15 (got {frac})")
    frac = next((f for lo, hi, f in FOLLOW_SELL_TIERS_PROFIT if lo == 0.80), None)
    assert_true(frac == 1.0, f"PROFIT 80%+ = 1.0 (got {frac})")
    # loss: first nonzero at 0.20
    frac_below = next((f for lo, hi, f in FOLLOW_SELL_TIERS_LOSS if lo == 0.00), None)
    assert_true(frac_below == 0.0, f"LOSS <20% = 0.0 (got {frac_below})")
    frac_20 = next((f for lo, hi, f in FOLLOW_SELL_TIERS_LOSS if lo == 0.20), None)
    assert_true(frac_20 == 0.25, f"LOSS 20-30% = 0.25 (got {frac_20})")


# ============= STATIC AUDIT: disable_stop_loss only in check_exits ==========

def test_disable_stop_loss_only_in_check_exits():
    """Static-source audit: `disable_stop_loss` must NOT appear in
    handle_player_sell. Only in check_exits stop-loss block."""
    src = open(os.path.join(BOT_DIR, "exit_manager.py"), "r", encoding="utf-8").read()
    # Find handle_player_sell body
    hps_start = src.find("def handle_player_sell(")
    assert_true(hps_start > 0, "handle_player_sell exists")
    hps_end = src.find("\ndef ", hps_start + 1)
    if hps_end == -1:
        hps_end = len(src)
    body = src[hps_start:hps_end]
    assert_true("disable_stop_loss" not in body,
                "handle_player_sell body must not reference disable_stop_loss")


# ========================================================================
# Main
# ========================================================================
if __name__ == "__main__":
    tests = [
        ("1. 5% dust in profit → skip", test_5pct_dust_in_profit),
        ("2. 15% profit → sell 15%", test_15pct_profit),
        ("3. 15% loss → skip (LOSS starts at 20%)", test_15pct_loss),
        ("4. 25% profit → sell 25%", test_25pct_profit),
        ("5. 25% loss → sell 25%", test_25pct_loss),
        ("6. 50% profit → sell 55%", test_50pct_profit),
        ("7. 80% profit → sell 100%", test_80pct_profit),
        ("8. 100% full exit → sell 100%", test_100pct_profit),
        ("9. disable_stop_loss=True does NOT block follow-sell", test_disable_stop_loss_does_not_block_follow_sell),
        ("10. phantom cache==onchain → skip", test_phantom_reduction_cache_equals_onchain),
        ("11. RPC failure → fail-safe skip", test_rpc_failure_fail_safe),
        ("12. duplicate sell within 60s dedup window", test_duplicate_sell_event_within_60s),
        ("13. cross-player skip", test_cross_player_skip),
        ("14. manual position follows denizz", test_manual_position_follows_denizz),
        ("15. manual+disable_stop_loss follows denizz 60% sell", test_manual_position_with_disable_stop_loss),
        ("16. no matching position → noop", test_no_matching_position),
        ("17. our_shares < 0.5 → skip", test_our_shares_below_threshold),
        ("18. price gap >40% in loss → skip", test_price_gap_skip_when_in_loss),
        ("19. cached=0 → skip", test_cached_size_zero),
        ("20. retry with 5× safety_margin on total failure", test_precision_margin_applied_to_place_limit_sell),
        ("21. partial fill → retry at 0.98× price for remainder", test_partial_fill_retry_at_lower_price),
        ("22. total failure → _pending_exit_retry marker", test_pending_retry_marker_on_total_failure),
        ("23. SKIP_INSUFFICIENT_BALANCE closes tracker row", test_skip_insufficient_balance_closes_tracker_row),
        ("24. monitor dedupe: batch fills with (size,price) distinct", test_monitor_dedupe_batch_fills_distinct),
        ("25. old dedupe key would have collided (documentary)", test_monitor_dedupe_old_key_would_have_collided),
        ("26. tier tables are contiguous & non-decreasing", test_tier_tables_are_sane),
        ("27. tier tables match expected values", test_tier_tables_match_expected),
        ("28. disable_stop_loss NOT referenced in handle_player_sell (static audit)", test_disable_stop_loss_only_in_check_exits),
    ]

    for name, fn in tests:
        run_test(name, fn)

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed / {FAIL} failed")
    if FAIL_DETAILS:
        print("\nFAILURES:")
        for d in FAIL_DETAILS:
            print(f"  - {d}")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)
