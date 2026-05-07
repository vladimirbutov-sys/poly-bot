"""Tests for resolve_position balance and PnL correctness (CRIT-2)."""
import sys, os, json, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import tracker

BANKROLL = 10000.0


@pytest.fixture
def fresh_data(tmp_path, monkeypatch):
    p = str(tmp_path / "positions.json")
    monkeypatch.setattr(tracker, "POSITIONS_FILE", p)
    data = {
        "positions": {},
        "stats": {
            "current_balance": BANKROLL,
            "total_pnl": 0.0,
            "peak_balance": BANKROLL,
            "wins": 0,
            "losses": 0,
        },
    }
    tracker.save(data)
    return data


def _add_position(data, key, size_shares, cost_usd, avg_entry, sells=None):
    data["positions"][key] = {
        "status": "open",
        "size_shares": size_shares,
        "cost_usd": cost_usd,
        "avg_entry": avg_entry,
        "sells": sells or [],
        "condition_id": "cid_test",
        "token_id": "tid_test",
        "signal_player": "denizz",
    }


# ---- Bug 1: current_balance doubled on win ----

def test_resolve_won_balance_not_doubled(fresh_data):
    """Win should add payout (=size_shares) to balance, not 2x."""
    data = fresh_data
    # Simulate: bought 1000 shares at $0.50 = $500 cost
    data["stats"]["current_balance"] = BANKROLL - 500  # after buy
    _add_position(data, "k1", size_shares=1000, cost_usd=500, avg_entry=0.50)

    tracker.resolve_position(data, "k1", won=True)

    # Payout = 1000 shares * $1 = $1000
    # Balance should be: (BANKROLL - 500) + 1000 = 10500
    assert data["stats"]["current_balance"] == BANKROLL - 500 + 1000


def test_resolve_lost_balance_unchanged(fresh_data):
    """Loss should NOT add anything to balance — cost already deducted at buy."""
    data = fresh_data
    data["stats"]["current_balance"] = BANKROLL - 500
    _add_position(data, "k1", size_shares=1000, cost_usd=500, avg_entry=0.50)

    tracker.resolve_position(data, "k1", won=False)

    # Lost = payout is $0. Balance stays at BANKROLL - 500
    assert data["stats"]["current_balance"] == BANKROLL - 500


# ---- Bug 2: net_new_pnl in lost branch ignores already_counted ----

def test_resolve_lost_with_partial_sells_pnl(fresh_data):
    """If we partially sold with +$20 PnL, then lost, total_pnl should not double-count."""
    data = fresh_data
    partial_sells = [{"pnl": 20.0, "shares": 200, "price": 0.60, "revenue": 120}]
    data["stats"]["current_balance"] = BANKROLL - 500 + 120  # after buy (-500) + partial sell (+120)
    data["stats"]["total_pnl"] = 20.0  # from partial sell

    # Remaining: 800 shares, cost ~$400
    _add_position(data, "k1", size_shares=800, cost_usd=400, avg_entry=0.50, sells=partial_sells)

    tracker.resolve_position(data, "k1", won=False)

    # Remaining 800 shares lost: PnL on remaining = -800 * 0.50 = -$400
    # total_pnl should be: 20 (partial) + (-400) (remaining loss) = -$380
    assert data["stats"]["total_pnl"] == pytest.approx(-380.0)


# ---- Bug 3: final_pnl double-counts partial sells on win ----

def test_resolve_won_final_pnl_correct(fresh_data):
    """final_pnl should be total PnL including partial sells, not double-counted."""
    data = fresh_data
    partial_sells = [{"pnl": 20.0, "shares": 200, "price": 0.60, "revenue": 120}]
    data["stats"]["current_balance"] = BANKROLL - 500 + 120
    data["stats"]["total_pnl"] = 20.0

    # Remaining: 800 shares at avg 0.50, cost $400
    _add_position(data, "k1", size_shares=800, cost_usd=400, avg_entry=0.50, sells=partial_sells)

    tracker.resolve_position(data, "k1", won=True)

    # Remaining 800 shares won: payout $800, cost $400, PnL on remaining = +$400
    # Total final_pnl = partial +$20 + remaining +$400 = +$420
    assert data["positions"]["k1"]["final_pnl"] == pytest.approx(420.0)
