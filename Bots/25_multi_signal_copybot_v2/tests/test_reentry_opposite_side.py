"""Regression tests for 2026-04-21 bug:
has_position_on_condition in main.handle_buy was blocking fresh signals on
the OPPOSITE side of a binary market when we already held an open position
on the other side (e.g. manual YES blocking denizz's NO re-entry).

Fix: replaced with tracker.has_open_position_on_token (same-side / same-token
check). See _analytics/2026-04-21_subm_double_entry_guard_too_coarse.md.

Reference incident:
  Will Trump visit Pakistan by May 31? (CID 0x2017a6a234…)
  2026-04-21 09:59:47 SKIP: Already have position on this sub-market
  — BUG: we held manual YES, denizz bought NO, should have entered.
"""
import pytest


# ---------- Unit tests for the new tracker helper ----------

def test_tracker_has_open_position_on_token_empty():
    import tracker
    data = {"positions": {}}
    assert tracker.has_open_position_on_token(data, "abc") is False


def test_tracker_has_open_position_on_token_matches():
    import tracker
    data = {"positions": {
        "k1": {"status": "open", "token_id": "42"},
        "k2": {"status": "open", "token_id": "55"},
    }}
    assert tracker.has_open_position_on_token(data, "42") is True
    assert tracker.has_open_position_on_token(data, "55") is True
    assert tracker.has_open_position_on_token(data, "999") is False


def test_tracker_has_open_position_on_token_ignores_sold():
    import tracker
    data = {"positions": {
        "k1": {"status": "sold", "token_id": "42"},
        "k2": {"status": "lost", "token_id": "42"},
    }}
    assert tracker.has_open_position_on_token(data, "42") is False


def test_tracker_has_open_position_on_token_handles_empty_token():
    import tracker
    data = {"positions": {"k1": {"status": "open", "token_id": "42"}}}
    assert tracker.has_open_position_on_token(data, "") is False
    assert tracker.has_open_position_on_token(data, None) is False


def test_tracker_has_open_position_on_token_string_vs_int():
    """Tokens come as strings from API but might be ints in tracker rows.
    Helper should handle either."""
    import tracker
    data = {"positions": {
        "k1": {"status": "open", "token_id": 42},  # int form
    }}
    assert tracker.has_open_position_on_token(data, "42") is True
    assert tracker.has_open_position_on_token(data, 42) is True


# ---------- Binary-market side independence ----------

def test_condition_check_unchanged():
    """Regression: has_position_on_condition is untouched — still matches on cid."""
    import tracker
    data = {"positions": {
        "k1": {"status": "open", "condition_id": "0xCID",
               "token_id": "YES_TOK"},
    }}
    assert tracker.has_position_on_condition(data, "0xCID") is True
    # Coarser than our new helper — returns True even though the YES token differs
    # from a hypothetical NO signal.  Callers that want side-awareness must use
    # has_open_position_on_token.
    assert tracker.has_open_position_on_token(data, "NO_TOK") is False
    assert tracker.has_open_position_on_token(data, "YES_TOK") is True


# ---------- The actual bug scenario: Pakistan-style ----------

def test_manual_yes_open_does_not_block_denizz_no_signal():
    """Pakistan incident reproducer.
    Tracker state at 2026-04-21 09:59 was:
      - signal_player=denizz NO: status=sold
      - signal_player=manual YES: status=open
    denizz re-entered with BUY NO. Before fix, handle_buy SKIPed because
    has_position_on_condition returned True. After fix, has_open_position_on_token
    returns False for NO token → path proceeds.
    """
    import tracker
    data = {"positions": {
        "old_denizz_no": {
            "status": "sold", "condition_id": "0xCID",
            "token_id": "NO_TOK", "outcome": "No", "signal_player": "denizz",
        },
        "manual_yes": {
            "status": "open", "condition_id": "0xCID",
            "token_id": "YES_TOK", "outcome": "Yes", "signal_player": "manual",
        },
    }}

    # The new side-aware check: denizz signals NO (NO_TOK) — nothing open on NO → allow
    assert tracker.has_open_position_on_token(data, "NO_TOK") is False, \
        "New NO signal must not be blocked by open YES on the opposite side"

    # Sanity: old (buggy) condition-level check DID return True — showing the bug
    assert tracker.has_position_on_condition(data, "0xCID") is True


def test_same_side_open_blocks_new_signal():
    """Non-regression: if we have OPEN position on the SAME side as incoming
    signal (and _signaled_keys path doesn't catch it for some reason), the
    token-level check still blocks — preventing double-entry on same outcome."""
    import tracker
    data = {"positions": {
        "denizz_no": {
            "status": "open", "condition_id": "0xCID",
            "token_id": "NO_TOK", "outcome": "No", "signal_player": "denizz",
        },
    }}
    # denizz signals BUY NO again — same token → should block
    assert tracker.has_open_position_on_token(data, "NO_TOK") is True
