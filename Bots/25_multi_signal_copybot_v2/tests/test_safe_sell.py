"""Unit tests for safe_sell.compute_safe_sell_size.

Covers the Hezbollah precision bug: tracker shows 59.51 shares,
on-chain has 59.509092 → sell must not exceed 59.50.
"""
import math
import pytest
import safe_sell


# ---------- basic math ----------

def test_floor_to_clob_precision_rounds_down():
    assert safe_sell._floor_to_clob_precision(59.509092) == 59.50
    assert safe_sell._floor_to_clob_precision(59.51) == 59.51
    assert safe_sell._floor_to_clob_precision(59.999) == 59.99
    assert safe_sell._floor_to_clob_precision(0.01) == 0.01
    assert safe_sell._floor_to_clob_precision(0.009) == 0.0


# ---------- compute_safe_sell_size ----------

def test_onchain_less_than_requested_is_clamped_hezbollah_case():
    """The exact bug that triggered this fix."""
    safe, onchain = safe_sell.compute_safe_sell_size(
        token_id="99", requested_shares=59.51,
        balance_override=59.509092, safety_margin=0.001,
    )
    assert safe == 59.50            # never more than on-chain
    assert safe <= onchain - 0.001  # safety margin respected
    assert onchain == 59.509092


def test_onchain_exactly_equals_requested_floors_down():
    """Even if on-chain == requested, margin guarantees safe < onchain."""
    safe, onchain = safe_sell.compute_safe_sell_size(
        token_id="99", requested_shares=100.0,
        balance_override=100.0, safety_margin=0.001,
    )
    assert safe == 99.99
    assert safe < onchain


def test_onchain_more_than_requested_returns_requested():
    """Never sell more than caller asked for."""
    safe, onchain = safe_sell.compute_safe_sell_size(
        token_id="99", requested_shares=10.0,
        balance_override=1000.0, safety_margin=0.001,
    )
    assert safe == 9.99    # requested 10 - margin 0.001, floored
    assert onchain == 1000.0


def test_onchain_zero_returns_zero():
    safe, onchain = safe_sell.compute_safe_sell_size(
        token_id="99", requested_shares=50.0,
        balance_override=0.0, safety_margin=0.001,
    )
    assert safe == 0.0
    assert onchain == 0.0


def test_onchain_dust_below_safety_margin_returns_zero():
    """If balance is less than safety margin, we sell nothing."""
    safe, onchain = safe_sell.compute_safe_sell_size(
        token_id="99", requested_shares=50.0,
        balance_override=0.0005, safety_margin=0.001,
    )
    assert safe == 0.0


def test_rpc_failure_returns_zero_and_none():
    """When get_wallet_balance would return None, compute returns (0, None)
    so caller skips the sell instead of risking over-request."""
    # Pass balance_override=None is same path — simulate via None return
    # Using balance_override=None forces RPC path, so mock it
    import safe_sell as ss
    orig = ss.get_wallet_balance
    ss.get_wallet_balance = lambda *a, **k: None
    try:
        safe, onchain = ss.compute_safe_sell_size(
            token_id="99", requested_shares=50.0,
            wallet="0xWALLET", safety_margin=0.001,
        )
    finally:
        ss.get_wallet_balance = orig
    assert safe == 0.0
    assert onchain is None


def test_safety_margin_larger_than_balance_returns_zero():
    safe, onchain = safe_sell.compute_safe_sell_size(
        token_id="99", requested_shares=0.5,
        balance_override=0.5, safety_margin=1.0,  # margin > balance
    )
    assert safe == 0.0


def test_custom_retry_margin_is_respected():
    """On retry with 5× margin we want more slack."""
    safe_1, _ = safe_sell.compute_safe_sell_size(
        token_id="99", requested_shares=59.51,
        balance_override=59.509092, safety_margin=0.001,
    )
    safe_5, _ = safe_sell.compute_safe_sell_size(
        token_id="99", requested_shares=59.51,
        balance_override=59.509092, safety_margin=0.005,
    )
    assert safe_1 == 59.50
    assert safe_5 == 59.50  # both still floor to 59.50, but 5x case leaves more on-chain headroom


def test_requested_zero_returns_zero():
    safe, onchain = safe_sell.compute_safe_sell_size(
        token_id="99", requested_shares=0,
        balance_override=100.0, safety_margin=0.001,
    )
    assert safe == 0.0


# ---------- parse_insufficient_balance_error ----------

def test_parse_clob_insufficient_balance_real_example():
    msg = ("PolyApiException[status_code=400, error_message="
           "{'error': 'not enough balance / allowance: "
           "the balance is not enough -> "
           "balance: 59509092, order amount: 59510000'}]")
    result = safe_sell.parse_insufficient_balance_error(msg)
    assert result == (59509092, 59510000)


def test_parse_error_returns_none_for_unrelated_text():
    assert safe_sell.parse_insufficient_balance_error("Unknown error") is None
    assert safe_sell.parse_insufficient_balance_error("") is None
    assert safe_sell.parse_insufficient_balance_error(None) is None
