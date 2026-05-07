"""Tests for approach C: peak computation from activity history."""
import sys
sys.path.insert(0, '.')

import exit_manager as em
from config import PLAYERS


def test_1_synthetic_peak():
    """Synthetic events: BUY 100, SELL 30, BUY 50 -> peak should be 120."""
    # Simulate events (we'll monkey-patch requests to return our synthetic data)
    import requests
    class MockResp:
        def __init__(self, data):
            self._data = data
            self.ok = True
        def json(self):
            return self._data
    events = [
        {"timestamp": 100, "type": "TRADE", "side": "BUY",  "size": 100, "asset": "TOKEN_X"},
        {"timestamp": 200, "type": "TRADE", "side": "SELL", "size": 30,  "asset": "TOKEN_X"},
        {"timestamp": 300, "type": "TRADE", "side": "BUY",  "size": 50,  "asset": "TOKEN_X"},
    ]
    _orig_get = requests.get
    _orig_onchain = em._get_player_size_onchain
    requests.get = lambda *a, **k: MockResp(events if k.get('params',{}).get('offset',0) == 0 else [])
    em._get_player_size_onchain = lambda *a, **k: 120.0

    peak = em._compute_player_peak("0xwallet", "0xcid", "TOKEN_X")
    print(f"Test 1 (BUY 100, SELL 30, BUY 50): peak = {peak} (expected 120)")
    assert peak == 120, f"expected 120, got {peak}"

    requests.get = _orig_get
    em._get_player_size_onchain = _orig_onchain
    print("  PASS")


def test_2_filter_token_id():
    """Events for different tokens should be filtered out."""
    import requests
    class MockResp:
        def __init__(self, data):
            self._data = data
            self.ok = True
        def json(self):
            return self._data
    events = [
        {"timestamp": 100, "type": "TRADE", "side": "BUY",  "size": 500, "asset": "OTHER_TOKEN"},
        {"timestamp": 200, "type": "TRADE", "side": "BUY",  "size": 100, "asset": "TOKEN_X"},
        {"timestamp": 300, "type": "TRADE", "side": "SELL", "size": 20,  "asset": "TOKEN_X"},
    ]
    _orig_get = requests.get
    _orig_onchain = em._get_player_size_onchain
    requests.get = lambda *a, **k: MockResp(events if k.get('params',{}).get('offset',0) == 0 else [])
    em._get_player_size_onchain = lambda *a, **k: 80.0

    peak = em._compute_player_peak("0xwallet", "0xcid", "TOKEN_X")
    print(f"Test 2 (filter by token_id): peak = {peak} (expected 100)")
    assert peak == 100, f"expected 100, got {peak}"

    requests.get = _orig_get
    em._get_player_size_onchain = _orig_onchain
    print("  PASS")


def test_3_redeem_resets():
    """REDEEM event should zero balance."""
    import requests
    class MockResp:
        def __init__(self, data):
            self._data = data
            self.ok = True
        def json(self):
            return self._data
    events = [
        {"timestamp": 100, "type": "TRADE", "side": "BUY", "size": 1000, "asset": "TOKEN_X"},
        {"timestamp": 200, "type": "REDEEM",                "size": 1000, "asset": "TOKEN_X"},
        {"timestamp": 300, "type": "TRADE", "side": "BUY", "size": 50,   "asset": "TOKEN_X"},
    ]
    _orig_get = requests.get
    _orig_onchain = em._get_player_size_onchain
    requests.get = lambda *a, **k: MockResp(events if k.get('params',{}).get('offset',0) == 0 else [])
    em._get_player_size_onchain = lambda *a, **k: 50.0

    peak = em._compute_player_peak("0xwallet", "0xcid", "TOKEN_X")
    print(f"Test 3 (REDEEM resets): peak = {peak} (expected 1000 — historical max before redeem)")
    assert peak == 1000, f"expected 1000, got {peak}"

    requests.get = _orig_get
    em._get_player_size_onchain = _orig_onchain
    print("  PASS")


def test_4_empty_history():
    """Empty history should return current on-chain as peak."""
    import requests
    class MockResp:
        def __init__(self, data):
            self._data = data
            self.ok = True
        def json(self):
            return self._data
    _orig_get = requests.get
    _orig_onchain = em._get_player_size_onchain
    requests.get = lambda *a, **k: MockResp([])
    em._get_player_size_onchain = lambda *a, **k: 42.0

    peak = em._compute_player_peak("0xwallet", "0xcid", "TOKEN_X")
    print(f"Test 4 (empty history): peak = {peak} (expected 42 — current on-chain fallback)")
    assert peak == 42, f"expected 42, got {peak}"

    requests.get = _orig_get
    em._get_player_size_onchain = _orig_onchain
    print("  PASS")


def test_5_peak_never_below_onchain():
    """If computed peak < current on-chain, override to on-chain value."""
    import requests
    class MockResp:
        def __init__(self, data):
            self._data = data
            self.ok = True
        def json(self):
            return self._data
    # Old events show max 50, but current on-chain is 200 (maybe missed events)
    events = [
        {"timestamp": 100, "type": "TRADE", "side": "BUY",  "size": 50,  "asset": "TOKEN_X"},
        {"timestamp": 200, "type": "TRADE", "side": "SELL", "size": 20,  "asset": "TOKEN_X"},
    ]
    _orig_get = requests.get
    _orig_onchain = em._get_player_size_onchain
    requests.get = lambda *a, **k: MockResp(events if k.get('params',{}).get('offset',0) == 0 else [])
    em._get_player_size_onchain = lambda *a, **k: 200.0

    peak = em._compute_player_peak("0xwallet", "0xcid", "TOKEN_X")
    print(f"Test 5 (peak < onchain safety): peak = {peak} (expected 200)")
    assert peak == 200, f"expected 200, got {peak}"

    requests.get = _orig_get
    em._get_player_size_onchain = _orig_onchain
    print("  PASS")


def test_6_real_denizz_position():
    """Integration test: compute peak for a real denizz position.
    Use April 30 Trump military ops NO where we know denizz sold massively."""
    # condition_id from positions.json for "Trump announces end ... April 30th"
    # _real position key was 0xreal_a166938b981ad3140f594d1fceebb067
    import tracker
    data = tracker.load()
    wallet = PLAYERS.get("denizz", "").lower()
    found = False
    for k, p in data.get("positions", {}).items():
        if "end of military operations" not in p.get("title","").lower():
            continue
        cid = p.get("condition_id", "")
        tok = str(p.get("token_id", ""))
        if not cid or not tok:
            continue
        peak = em._compute_player_peak(wallet, cid, tok)
        print(f"Test 6 (real): {p.get('title','')[:60]} | {p.get('outcome')} | peak = {peak:.0f}")
        onchain = em._get_player_size_onchain(wallet, tok)
        print(f"       current on-chain: {onchain:.0f}, sold from peak: {(peak-(onchain or 0))/peak*100 if peak > 0 else 0:.1f}%")
        assert peak >= 0, f"negative peak: {peak}"
        if onchain is not None:
            assert peak >= onchain - 0.5, f"peak ({peak}) < onchain ({onchain})"
        found = True
    assert found, "no matching real position"
    print("  PASS")


if __name__ == "__main__":
    print("=" * 60)
    print("Peak calculation tests (approach C)")
    print("=" * 60)
    test_1_synthetic_peak()
    test_2_filter_token_id()
    test_3_redeem_resets()
    test_4_empty_history()
    test_5_peak_never_below_onchain()
    print()
    print("--- Integration test with real data ---")
    test_6_real_denizz_position()
    print()
    print("=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
