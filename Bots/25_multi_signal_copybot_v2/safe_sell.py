"""Precision-safe sell-size calculation.

Root cause addressed here:
    positions.json stores size_shares rounded to 2 decimals (e.g. 59.51),
    but the on-chain CTF balance has 6-decimal precision (e.g. 59.509092).
    Sending 59.51 to the CLOB translates to 59,510,000 micro-shares while
    on-chain has only 59,509,092 → exchange rejects the whole order with
    "not enough balance" (observed 2026-04-15, Hezbollah ceasefire signal
    from denizz — missed exit).

This module queries the real on-chain balance BEFORE every sell and returns
a size that is guaranteed ≤ on-chain, minus a safety margin for race-
conditions with other operations.
"""
import math
from typing import Tuple, Optional

try:
    from config import SAFETY_MARGIN_SHARES
except ImportError:
    SAFETY_MARGIN_SHARES = 0.001

# CLOB-API precision: orders are accepted with at most 2 decimals on size.
# Floor (never ceil) so we don't over-request by 1 micro-share.
CLOB_SIZE_DECIMALS = 2
CLOB_SIZE_STEP = 10 ** CLOB_SIZE_DECIMALS  # 100 → 2 decimals


def _floor_to_clob_precision(x: float) -> float:
    """Floor x to the CLOB size precision (2 decimals), never up."""
    return math.floor(x * CLOB_SIZE_STEP) / CLOB_SIZE_STEP


def get_wallet_balance(wallet: str, token_id: str,
                       rpc_url: Optional[str] = None) -> Optional[float]:
    """Read wallet's token balance from Polygon CTF.balanceOf.

    Returns:
        float shares (balance / 1e6), or None on RPC error.
    """
    try:
        from web3 import Web3
        if rpc_url is None:
            from config import POLYGON_RPC
            rpc_url = POLYGON_RPC
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 10}))
        ctf = w3.eth.contract(
            address=Web3.to_checksum_address(
                "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"),
            abi=[{"constant": True,
                  "inputs": [{"name": "a", "type": "address"},
                             {"name": "id", "type": "uint256"}],
                  "name": "balanceOf",
                  "outputs": [{"name": "", "type": "uint256"}],
                  "type": "function", "stateMutability": "view"}],
        )
        raw = ctf.functions.balanceOf(
            Web3.to_checksum_address(wallet), int(token_id)
        ).call()
        return raw / 1e6
    except Exception as e:
        # Caller should handle None (retry later, or skip sell)
        print(f"[SAFE_SELL] on-chain RPC error: {e}")
        return None


def compute_safe_sell_size(
    token_id: str,
    requested_shares: float,
    wallet: Optional[str] = None,
    safety_margin: Optional[float] = None,
    balance_override: Optional[float] = None,
) -> Tuple[float, Optional[float]]:
    """Compute a sell-size guaranteed to be ≤ on-chain balance.

    Args:
        token_id:          ERC-1155 token id (string, decimal)
        requested_shares:  what the caller wants to sell (from tracker)
        wallet:            our wallet address; if None, read from config.OUR_WALLET
        safety_margin:     shares to reserve for precision/race conditions;
                           if None, use config.SAFETY_MARGIN_SHARES
        balance_override:  for tests — skip the RPC call and use this balance

    Returns:
        (safe_size, onchain_balance)
            safe_size        — shares to actually order (≥0, 2-decimal),
                               0.0 means DO NOT SELL
            onchain_balance  — the balance we queried, or None if RPC failed
                               (None means "could not verify, caller decides")
    """
    if safety_margin is None:
        safety_margin = SAFETY_MARGIN_SHARES
    if wallet is None:
        from config import OUR_WALLET
        wallet = OUR_WALLET

    if balance_override is not None:
        onchain = balance_override
    else:
        onchain = get_wallet_balance(wallet, token_id)

    if onchain is None:
        # RPC failed — we cannot verify. Return (0, None) so caller skips
        # the sell rather than risk an over-request.
        return (0.0, None)

    if onchain <= 0:
        return (0.0, onchain)

    # Cap at what the user asked for — never sell more than requested
    target = min(float(requested_shares), onchain)
    # Subtract safety margin to survive float/race rounding
    target -= safety_margin
    if target <= 0:
        return (0.0, onchain)

    safe = _floor_to_clob_precision(target)
    # Defensive: floor could still leave a hair > onchain due to fp,
    # though in practice it never does. Re-check:
    if safe > onchain:
        safe = _floor_to_clob_precision(onchain - safety_margin)
    if safe < 0:
        safe = 0.0
    return (safe, onchain)


def parse_insufficient_balance_error(error_text: str) -> Optional[Tuple[int, int]]:
    """Parse CLOB error message like:

        "the balance is not enough -> balance: 59509092, order amount: 59510000"

    Returns:
        (balance_micro, order_micro) if both numbers found, else None.
    """
    import re
    if not error_text:
        return None
    m_bal = re.search(r"balance[:\s]+(\d+)", error_text)
    m_ord = re.search(r"order[^:]*[:\s]+(\d+)", error_text)
    if not m_bal or not m_ord:
        return None
    try:
        return (int(m_bal.group(1)), int(m_ord.group(1)))
    except ValueError:
        return None
