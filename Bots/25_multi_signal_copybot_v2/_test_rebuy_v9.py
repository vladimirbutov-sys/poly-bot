"""Unit tests for V9 + rebuy trigger (2026-04-17).

Covers:
1. price_risk_mult boundary values (V9 tiers)
2. calculate_bet_formula_only on new_buy USD amounts
3. Hormuz-like happy path (EXECUTED ~$60)
4. Small buy below MIN_PLAYER_INVESTED → SKIP_SMALL_BUY
5. Throttle within window → SKIP_THROTTLE
6. MAX_POSITION cap → SKIP_TOO_SMALL
7. Kill-switch on cumulative PnL → SKIP_KILL_SWITCH
8. High-price bucket applies 0.80 multiplier
9. Whale buy ($50K) clamped by MAX_BET_USD
"""
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'buffer') else sys.stdout

import filters
import rebuy
import tracker
import config

PASS, FAIL = 0, 0


def _assert(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}")


def _reset_rebuy_state():
    """Clear in-memory rebuy state between tests."""
    rebuy._rebuy_last_ts.clear()
    rebuy._rebuy_exec_count = 0


def _isolate_log():
    """Redirect rebuy log to a temp file so tests don't pollute prod."""
    tmp = os.path.join(os.path.dirname(config.REBUY_LOG_PATH), "rebuy_log_TEST.jsonl")
    if os.path.exists(tmp):
        os.remove(tmp)
    config.REBUY_LOG_PATH = tmp
    return tmp


def test_1_price_risk_mult():
    print("\n[Test 1] price_risk_mult boundaries")
    cases = [
        (0.05, 0.40), (0.14, 0.40),
        (0.15, 0.70), (0.29, 0.70),
        (0.30, 1.00), (0.50, 1.00), (0.69, 1.00),
        (0.70, 0.90), (0.84, 0.90),
        (0.85, 0.80), (0.98, 0.80),
    ]
    for price, expected in cases:
        got = filters.price_risk_mult(price)
        _assert(got == expected, f"price={price} → {got} (want {expected})")


def test_2_formula_only():
    print("\n[Test 2] calculate_bet_formula_only on new_buy amounts")
    # formula = 31.75*ln(x) - 177, × price_bet_mult(1.0 for <0.82) × price_risk_mult
    # $500 @ 0.40: ln(500)=6.215 → 31.75*6.215-177 = 20.3 × 1.0 × 0.70 = 14.21
    got = filters.calculate_bet_formula_only(500.0, 0.25)
    _assert(abs(got - 14.21) < 0.05, f"$500 @ 0.25 → ${got} (want ~14.21)")
    # $3967 @ 0.27 (Hormuz): ln(3967)=8.286 → 31.75*8.286-177 = 86.08 × 1.0 × 0.70 = 60.26
    got = filters.calculate_bet_formula_only(3967.0, 0.27)
    _assert(abs(got - 60.26) < 0.1, f"$3967 @ 0.27 → ${got} (want ~60.26)")
    # $3967 @ 0.50 (sweet spot, no cut): 86.08 × 1.0 × 1.0 = 86.08
    got = filters.calculate_bet_formula_only(3967.0, 0.50)
    _assert(abs(got - 86.08) < 0.1, f"$3967 @ 0.50 → ${got} (want ~86.08)")
    # Whale $50K: ln(50000)=10.82 → 31.75*10.82-177 = 166.5 → below MAX 250
    # × 1.0 × price_risk(0.30)=1.0 → 166.53
    got = filters.calculate_bet_formula_only(50000.0, 0.40)
    _assert(abs(got - 166.53) < 0.2, f"$50K @ 0.40 → ${got} (want ~166.53, no cap)")
    # Whale $500K: ln=13.12 → 31.75*13.12-177 = 239.6 → below MAX 250
    got = filters.calculate_bet_formula_only(500000.0, 0.40)
    _assert(abs(got - 239.6) < 0.5, f"$500K @ 0.40 → ${got} (want ~239.6, no cap)")
    # Whale $5M clamped at MAX_BET 250: 31.75*ln(5M)-177 = 347.8 → capped to 250
    got = filters.calculate_bet_formula_only(5000000.0, 0.40)
    _assert(abs(got - 250.0) < 0.5, f"$5M @ 0.40 → ${got} (want 250, clamped)")


def test_3_happy_path_hormuz():
    print("\n[Test 3] Hormuz-like happy path: EXECUTED")
    _reset_rebuy_state()
    log_path = _isolate_log()
    # Disable smoke-test initial cap for this test to verify full sizing logic
    orig_initial_n = config.REBUY_INITIAL_N
    config.REBUY_INITIAL_N = 0
    # Monkey-patch tracker.get_available_balance
    import tracker as _t
    orig_gab = _t.get_available_balance
    _t.get_available_balance = lambda *_args, **_kw: 5000.0
    # Monkey-patch entry_manager.execute_part1 to just record call
    import entry_manager as _em
    orig_ep = _em.execute_part1
    calls = []
    _em.execute_part1 = lambda *args, **kw: calls.append((args, kw))
    try:
        result = rebuy.try_rebuy(
            cid="0xtest_hormuz", token_id="tok1",
            title="Strait of Hormuz traffic", outcome="Yes",
            event_slug="strait-of-hormuz-traffic", entry_price=0.27,
            new_buy_usd=3967.0, our_cost=170.88,
            denizz_net_invested=8916.0, player_name="denizz",
        )
        _assert(result is True, "try_rebuy returned True")
        # Thread-based execution — give it a moment
        time.sleep(0.3)
        _assert(len(calls) >= 1, f"execute_part1 called (got {len(calls)} calls)")
        # Check log
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                lines = [json.loads(l) for l in f if l.strip()]
            _assert(any(ev.get("decision") == "EXECUTED" for ev in lines),
                    "log contains EXECUTED event")
            # Check size is ~60 (no smoke cap)
            execs = [ev for ev in lines if ev.get("decision") == "EXECUTED"]
            if execs:
                sz = execs[0].get("final", 0)
                _assert(50 <= sz <= 70, f"rebuy size ${sz} in [50, 70]")
    finally:
        config.REBUY_INITIAL_N = orig_initial_n
        _t.get_available_balance = orig_gab
        _em.execute_part1 = orig_ep


def test_3b_smoke_cap():
    print("\n[Test 3b] Smoke-test cap active → rebuy capped at $20")
    _reset_rebuy_state()
    log_path = _isolate_log()
    # Initial cap = $20 (default), N = 3
    import tracker as _t
    orig_gab = _t.get_available_balance
    _t.get_available_balance = lambda *_args, **_kw: 5000.0
    import entry_manager as _em
    orig_ep = _em.execute_part1
    _em.execute_part1 = lambda *a, **k: None
    try:
        result = rebuy.try_rebuy(
            cid="0xtest_smoke", token_id="tok1",
            title="Hormuz-smoke", outcome="Yes",
            event_slug="hormuz-smoke", entry_price=0.27,
            new_buy_usd=3967.0, our_cost=170.88,
            denizz_net_invested=8916.0, player_name="denizz",
        )
        _assert(result is True, "executed even with smoke cap")
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        execs = [ev for ev in lines if ev.get("decision") == "EXECUTED"]
        if execs:
            sz = execs[0].get("final", 0)
            _assert(sz == 20.0, f"smoke cap applied: ${sz} (want $20)")
            proposed = execs[0].get("proposed", 0)
            _assert(50 <= proposed <= 70, f"proposed was ${proposed} (pre-cap, want ~$60)")
    finally:
        _t.get_available_balance = orig_gab
        _em.execute_part1 = orig_ep


def test_4_small_buy():
    print("\n[Test 4] Small buy < $500 → SKIP_SMALL_BUY")
    _reset_rebuy_state()
    log_path = _isolate_log()
    result = rebuy.try_rebuy(
        cid="0xtest_small", token_id="tok1", title="Test market", outcome="Yes",
        event_slug="test", entry_price=0.40, new_buy_usd=300.0, our_cost=100.0,
        denizz_net_invested=5000.0, player_name="denizz",
    )
    _assert(result is False, "small buy returns False")
    with open(log_path, "r", encoding="utf-8") as f:
        lines = [json.loads(l) for l in f if l.strip()]
    _assert(any(ev.get("decision") == "SKIP_SMALL_BUY" for ev in lines),
            "log contains SKIP_SMALL_BUY")


def test_5_throttle():
    print("\n[Test 5] Throttle: second call within window → SKIP_THROTTLE")
    _reset_rebuy_state()
    log_path = _isolate_log()
    # First call succeeds (but without actually placing order — mock execute)
    import tracker as _t
    orig_gab = _t.get_available_balance
    _t.get_available_balance = lambda *a, **k: 5000.0
    import entry_manager as _em
    orig_ep = _em.execute_part1
    _em.execute_part1 = lambda *a, **k: None
    try:
        r1 = rebuy.try_rebuy(
            cid="0xtest_throttle", token_id="tok1", title="X", outcome="Yes",
            event_slug="x", entry_price=0.40, new_buy_usd=2000.0, our_cost=100.0,
            denizz_net_invested=5000.0, player_name="denizz",
        )
        _assert(r1 is True, "first call executed")
        # Second call immediately — should throttle
        r2 = rebuy.try_rebuy(
            cid="0xtest_throttle", token_id="tok1", title="X", outcome="Yes",
            event_slug="x", entry_price=0.40, new_buy_usd=2000.0, our_cost=100.0,
            denizz_net_invested=5000.0, player_name="denizz",
        )
        _assert(r2 is False, "second call throttled")
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        _assert(any(ev.get("decision") == "SKIP_THROTTLE" for ev in lines),
                "log contains SKIP_THROTTLE")
    finally:
        _t.get_available_balance = orig_gab
        _em.execute_part1 = orig_ep


def test_6_max_position_cap():
    print("\n[Test 6] MAX_POSITION almost reached → SKIP_TOO_SMALL")
    _reset_rebuy_state()
    log_path = _isolate_log()
    # our_cost=$295 → remaining_cap = 300-295 = $5 < MIN_BET_USD_LIVE $10
    import tracker as _t
    orig_gab = _t.get_available_balance
    _t.get_available_balance = lambda *a, **k: 5000.0
    try:
        result = rebuy.try_rebuy(
            cid="0xtest_cap", token_id="tok1", title="X", outcome="Yes",
            event_slug="x", entry_price=0.27, new_buy_usd=3967.0, our_cost=295.0,
            denizz_net_invested=8916.0, player_name="denizz",
        )
        _assert(result is False, "near-cap returns False")
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        _assert(any(ev.get("decision") == "SKIP_TOO_SMALL" for ev in lines),
                "log contains SKIP_TOO_SMALL")
    finally:
        _t.get_available_balance = orig_gab


def test_7_kill_switch():
    print("\n[Test 7] Kill-switch: cumulative PnL < threshold")
    _reset_rebuy_state()
    log_path = _isolate_log()
    # Monkey-patch _cumulative_rebuy_pnl
    orig_pnl = rebuy._cumulative_rebuy_pnl
    rebuy._cumulative_rebuy_pnl = lambda: -200.0
    try:
        result = rebuy.try_rebuy(
            cid="0xtest_kill", token_id="tok1", title="X", outcome="Yes",
            event_slug="x", entry_price=0.40, new_buy_usd=2000.0, our_cost=100.0,
            denizz_net_invested=5000.0, player_name="denizz",
        )
        _assert(result is False, "kill-switch blocks execution")
        with open(log_path, "r", encoding="utf-8") as f:
            lines = [json.loads(l) for l in f if l.strip()]
        _assert(any(ev.get("decision") == "SKIP_KILL_SWITCH" for ev in lines),
                "log contains SKIP_KILL_SWITCH")
    finally:
        rebuy._cumulative_rebuy_pnl = orig_pnl


def test_8_high_price():
    print("\n[Test 8] High-price bucket 0.87 applies ×0.80")
    # Formula $3967: 86.08; price_mult @ 0.87 = 0.65; price_risk = 0.80
    # → 86.08 × 0.65 × 0.80 = 44.76
    got = filters.calculate_bet_formula_only(3967.0, 0.87)
    _assert(abs(got - 44.76) < 0.1, f"$3967 @ 0.87 → ${got} (want ~44.76)")


def test_9_whale_buy():
    print("\n[Test 9] Whale buy $50K clamped at MAX_BET with price risk 1.0")
    # $50K, price 0.45 (sweet): ln=10.82; 31.75*10.82-177=166.53; no clamp; ×1.0×1.0
    got = filters.calculate_bet_formula_only(50000.0, 0.45)
    _assert(abs(got - 166.53) < 0.2, f"$50K @ 0.45 → ${got} (no MAX clamp at this level)")
    # $5M clamped at 250 × 1.0 × 1.0 = 250
    got = filters.calculate_bet_formula_only(5000000.0, 0.45)
    _assert(abs(got - 250.0) < 0.5, f"$5M @ 0.45 → ${got} (want 250 — MAX clamp)")


def main():
    print("=" * 60)
    print("V9 + Rebuy Trigger Unit Tests")
    print("=" * 60)
    test_1_price_risk_mult()
    test_2_formula_only()
    test_3_happy_path_hormuz()
    test_3b_smoke_cap()
    test_4_small_buy()
    test_5_throttle()
    test_6_max_position_cap()
    test_7_kill_switch()
    test_8_high_price()
    test_9_whale_buy()
    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
