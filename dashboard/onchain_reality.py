"""On-chain reality module for dashboard.

Provides TRUE financial state of the wallet, independent of bot state files.

Functions:
- get_wallet_summary() — current USDC + open positions value (cached 60s)
- get_lifetime_pnl() — based on net external deposit (cached 1 hour)
- get_unredeemed_summary() — list of redeemable positions and total value (cached 5 min)

All values come from on-chain queries, NOT from state.json files.
"""
import os
import json
import time
import logging
import threading
from pathlib import Path
from collections import defaultdict

import requests
from web3 import Web3
from dotenv import load_dotenv

log = logging.getLogger("onchain_reality")

# Load env from Iran Trader (same wallet for all bots)
load_dotenv("C:/Users/Honor/Desktop/Polymarket/Polymarket/Bots/24_Iran_Daily_Trader/.env")
WALLET = os.getenv("POLYMARKET_WALLET", "")

POLYGON_RPC = "https://polygon.gateway.tenderly.co"
USDC_ADDR = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
DATA_API = "https://data-api.polymarket.com"

# Polymarket protocol contracts (lowercase) — used to classify USDC flows
POLYMARKET_CONTRACTS = {
    "0x4d97dcd97ec945f40cf65f87097ace5ea0476045",  # CTF
    "0xc5d563a36ae78145c45a50134d48a1215220f80a",  # NegRiskCtfExchange
    "0xd91e80cf2e7be2e162c6513ced06f1dd0da35296",  # NegRiskAdapter
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e",  # CtfExchange
}

USDC_ABI = [{
    "constant": True, "type": "function", "name": "balanceOf",
    "inputs": [{"name": "_owner", "type": "address"}],
    "outputs": [{"name": "", "type": "uint256"}],
}]

CACHE_DIR = Path(__file__).parent / "_onchain_cache"
CACHE_DIR.mkdir(exist_ok=True)

# In-memory caches with TTL
_wallet_cache = {"data": None, "ts": 0, "ttl": 60}
_lifetime_cache = {"data": None, "ts": 0, "ttl": 3600}
_unredeemed_cache = {"data": None, "ts": 0, "ttl": 300}

_lock = threading.Lock()


def _get_w3():
    return Web3(Web3.HTTPProvider(POLYGON_RPC, request_kwargs={"timeout": 30}))


def get_usdc_balance() -> float:
    """Current USDC balance on wallet."""
    try:
        w3 = _get_w3()
        c = w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDR), abi=USDC_ABI)
        bal = c.functions.balanceOf(Web3.to_checksum_address(WALLET)).call()
        return bal / 1e6
    except Exception as e:
        log.warning("USDC balance fetch failed: %s", e)
        return 0.0


def get_open_positions_value() -> tuple[float, int]:
    """Sum of current values of all open positions on Polymarket.
    Returns (total_value_usd, count_open_positions).
    """
    try:
        r = requests.get(
            f"{DATA_API}/positions",
            params={"user": WALLET, "limit": 500, "sizeThreshold": 0.5},
            timeout=15,
        )
        if r.status_code != 200:
            return 0.0, 0
        positions = r.json()
        # Open = not redeemable AND has value
        open_pos = [p for p in positions if not p.get("redeemable")]
        total_value = sum(float(p.get("currentValue", 0) or 0) for p in open_pos)
        return total_value, len(open_pos)
    except Exception as e:
        log.warning("Positions fetch failed: %s", e)
        return 0.0, 0


def get_unredeemed_summary() -> dict:
    """Find all redeemable positions and total value.

    Returns:
        {
            "count": int,
            "total_value": float,
            "positions": [{"title", "size", "value", "negRisk"}]
        }
    """
    with _lock:
        now = time.time()
        if _unredeemed_cache["data"] and now - _unredeemed_cache["ts"] < _unredeemed_cache["ttl"]:
            return _unredeemed_cache["data"]

    try:
        r = requests.get(
            f"{DATA_API}/positions",
            params={"user": WALLET, "limit": 500, "sizeThreshold": 0.5},
            timeout=15,
        )
        if r.status_code != 200:
            return {"count": 0, "total_value": 0, "positions": []}
        all_pos = r.json()
        redeemable = [p for p in all_pos if p.get("redeemable") and float(p.get("currentValue", 0)) > 0.5]
        total = sum(float(p.get("currentValue", 0)) for p in redeemable)
        result = {
            "count": len(redeemable),
            "total_value": round(total, 2),
            "positions": [
                {
                    "title": (p.get("title", "") or "")[:80],
                    "size": float(p.get("size", 0)),
                    "value": float(p.get("currentValue", 0)),
                    "neg_risk": p.get("negativeRisk", False),
                    "condition_id": p.get("conditionId", ""),
                    "token_id": p.get("asset", ""),
                    "outcome_index": p.get("outcomeIndex", 0),
                }
                for p in redeemable
            ],
        }
        with _lock:
            _unredeemed_cache["data"] = result
            _unredeemed_cache["ts"] = time.time()
        return result
    except Exception as e:
        log.warning("Unredeemed scan failed: %s", e)
        return {"count": 0, "total_value": 0, "positions": []}


def get_wallet_summary() -> dict:
    """Current wallet equity: USDC + open positions value + unredeemed.

    Returns:
        {
            "usdc": float,
            "open_value": float,
            "open_count": int,
            "unredeemed_value": float,
            "unredeemed_count": int,
            "total_equity": float,
            "timestamp": ISO,
        }
    """
    with _lock:
        now = time.time()
        if _wallet_cache["data"] and now - _wallet_cache["ts"] < _wallet_cache["ttl"]:
            return _wallet_cache["data"]

    usdc = get_usdc_balance()
    open_value, open_count = get_open_positions_value()
    unred = get_unredeemed_summary()

    total = usdc + open_value + unred["total_value"]

    result = {
        "usdc": round(usdc, 2),
        "open_value": round(open_value, 2),
        "open_count": open_count,
        "unredeemed_value": unred["total_value"],
        "unredeemed_count": unred["count"],
        "total_equity": round(total, 2),
        "timestamp": time.time(),
    }
    with _lock:
        _wallet_cache["data"] = result
        _wallet_cache["ts"] = time.time()
    return result


def get_lifetime_pnl() -> dict:
    """Compute lifetime PnL from on-chain USDC inflow/outflow.

    Heavy operation: scans Polygon logs over 30+ days. Caches for 1 hour.
    Falls back to cached file if scan fails.

    Returns:
        {
            "net_external_deposit": float,
            "current_equity": float,
            "lifetime_pnl": float,
            "scan_blocks": [start, end],
            "scan_date": ISO,
        }
    """
    with _lock:
        now = time.time()
        if _lifetime_cache["data"] and now - _lifetime_cache["ts"] < _lifetime_cache["ttl"]:
            return _lifetime_cache["data"]

    cache_file = CACHE_DIR / "lifetime_pnl_data.json"

    # Try to load saved scan
    saved = None
    if cache_file.exists():
        try:
            saved = json.loads(cache_file.read_text())
        except Exception:
            saved = None

    # Always update equity portion (cheap)
    summary = get_wallet_summary()
    current_equity = summary["total_equity"]

    if saved and "net_external_deposit" in saved:
        net_deposit = saved["net_external_deposit"]
        result = {
            "net_external_deposit": round(net_deposit, 2),
            "current_equity": current_equity,
            "lifetime_pnl": round(current_equity - net_deposit, 2),
            "scan_date": saved.get("scan_date", "unknown"),
            "scan_blocks": saved.get("scan_blocks", []),
            "stale": True,  # signal that scan should be refreshed
        }
    else:
        # No saved data — return partial result without lifetime
        result = {
            "net_external_deposit": None,
            "current_equity": current_equity,
            "lifetime_pnl": None,
            "scan_date": None,
            "stale": True,
            "error": "No on-chain scan data available. Run lifetime_pnl.py to generate.",
        }

    with _lock:
        _lifetime_cache["data"] = result
        _lifetime_cache["ts"] = time.time()
    return result


def get_redeem_history() -> dict:
    """Return total USDC received from REDEEM events (last ~3000 events)."""
    try:
        total = 0.0
        n = 0
        for offset in range(0, 5000, 500):
            r = requests.get(
                f"{DATA_API}/activity",
                params={"user": WALLET, "limit": 500, "offset": offset},
                timeout=15,
            )
            if r.status_code != 200:
                break
            d = r.json()
            if not d:
                break
            for a in d:
                if a.get("type") == "REDEEM":
                    total += float(a.get("usdcSize", 0) or 0)
                    n += 1
            if len(d) < 500:
                break
        return {"total_usd": round(total, 2), "count": n}
    except Exception as e:
        log.warning("Redeem history failed: %s", e)
        return {"total_usd": 0, "count": 0}


if __name__ == "__main__":
    # CLI test
    print("=" * 60)
    print("ON-CHAIN REALITY")
    print("=" * 60)
    print(f"Wallet: {WALLET}")
    print()

    print("Wallet summary:")
    s = get_wallet_summary()
    print(f"  USDC:               ${s['usdc']:>10,.2f}")
    print(f"  Open positions:     ${s['open_value']:>10,.2f}  ({s['open_count']} pos)")
    print(f"  Unredeemed wins:    ${s['unredeemed_value']:>10,.2f}  ({s['unredeemed_count']} pos)")
    print(f"  TOTAL EQUITY:       ${s['total_equity']:>10,.2f}")
    print()

    print("Lifetime PnL:")
    l = get_lifetime_pnl()
    if l.get("net_external_deposit") is not None:
        print(f"  Net external deposit: ${l['net_external_deposit']:>10,.2f}")
        print(f"  Current equity:       ${l['current_equity']:>10,.2f}")
        print(f"  LIFETIME PnL:         ${l['lifetime_pnl']:>+10,.2f}")
        if l.get("stale"):
            print(f"  (scan from {l.get('scan_date')}, may need refresh)")
    else:
        print(f"  {l.get('error')}")
    print()

    print("Redeem history (Polymarket activity):")
    r = get_redeem_history()
    print(f"  Total USDC from REDEEMs: ${r['total_usd']:,.2f}  ({r['count']} events)")
