"""Read-only audit: find all manual positions + check if denizz holds them.

A position is 'manual' if ANY of:
    - signal_player == "manual"
    - tier == "manual"
    - _adopted_from starts with "manual_"

For each OPEN manual position, queries Polymarket data-api to see whether
denizz currently holds the same (conditionId, asset).
"""
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
from config import PLAYERS, POSITIONS_FILE

DATA_API = 'https://data-api.polymarket.com'

def is_manual(pos: dict) -> bool:
    if pos.get("signal_player") == "manual":
        return True
    if pos.get("tier") == "manual":
        return True
    adopted = str(pos.get("_adopted_from", "") or "")
    if adopted.startswith("manual_"):
        return True
    return False


def fetch_denizz_positions(wallet: str) -> dict:
    """Return {(conditionId, asset): size} for denizz's CURRENT portfolio."""
    out = {}
    try:
        r = requests.get(
            f"{DATA_API}/positions",
            params={"user": wallet.lower(), "limit": 500, "sizeThreshold": 0},
            timeout=20,
        )
        for p in r.json():
            cid = p.get("conditionId", "")
            asset = str(p.get("asset", ""))
            size = float(p.get("size", 0) or 0)
            if cid and asset:
                out[(cid, asset)] = size
    except Exception as e:
        print(f"[AUDIT] Error fetching denizz positions: {e}")
    return out


def main():
    if not os.path.exists(POSITIONS_FILE):
        print(f"positions.json not found at {POSITIONS_FILE}")
        return

    with open(POSITIONS_FILE, encoding="utf-8") as f:
        data = json.load(f)

    manual_rows = []
    for key, pos in data.get("positions", {}).items():
        if is_manual(pos):
            manual_rows.append((key, pos))

    # Fetch denizz current portfolio once for all OPEN manual positions
    denizz_wallet = PLAYERS.get("denizz", "")
    denizz_portfolio = {}
    if any(p.get("status") == "open" for _, p in manual_rows):
        if denizz_wallet:
            print(f"[AUDIT] fetching denizz portfolio (wallet {denizz_wallet[:10]}...)...")
            denizz_portfolio = fetch_denizz_positions(denizz_wallet)
            print(f"[AUDIT] denizz has {len(denizz_portfolio)} positions on-chain\n")

    print("=" * 100)
    print(f"MANUAL POSITIONS AUDIT — {POSITIONS_FILE}")
    print("=" * 100)
    print(f"Total manual rows found: {len(manual_rows)}")
    print()

    if not manual_rows:
        print("No manual positions found.")
        return

    open_count = 0
    closed_count = 0
    open_cost_total = 0.0
    denizz_overlap_count = 0
    denizz_overlap_cost = 0.0

    for key, pos in manual_rows:
        status = pos.get("status", "?")
        cid = pos.get("condition_id", "")
        token = str(pos.get("token_id", ""))
        title = (pos.get("title", "?") or "?")[:70]
        outcome = pos.get("outcome", "?")
        shares = float(pos.get("size_shares", 0) or 0)
        cost = float(pos.get("cost_usd", 0) or 0)
        avg_entry = float(pos.get("avg_entry", 0) or 0)
        ts = pos.get("timestamp", "?")
        adopted = pos.get("_adopted_from", "—")
        signal_player = pos.get("signal_player", "—")
        tier = pos.get("tier", "—")

        if status == "open":
            open_count += 1
            open_cost_total += cost
        else:
            closed_count += 1

        print(f"  KEY            : {key[:40]}...")
        print(f"  Title          : {title}")
        print(f"  Outcome        : {outcome}   Status: {status}")
        print(f"  size_shares    : {shares:,.4f}   cost_usd: ${cost:,.2f}   avg_entry: {avg_entry:.4f}")
        print(f"  signal_player  : {signal_player}   tier: {tier}")
        print(f"  _adopted_from  : {adopted}")
        print(f"  timestamp      : {ts}")

        if status == "open" and denizz_portfolio:
            denizz_size = denizz_portfolio.get((cid, token), 0)
            if denizz_size > 0:
                print(f"  denizz_currently_holds: {denizz_size:,.2f} shares  ← OVERLAP")
                denizz_overlap_count += 1
                denizz_overlap_cost += cost
            else:
                print(f"  denizz_currently_holds: 0 (not in portfolio)")
        print()

    print("=" * 100)
    print("SUMMARY")
    print("=" * 100)
    print(f"  Total manual positions : {len(manual_rows)}  (open: {open_count}, closed: {closed_count})")
    print(f"  Open manual cost_usd   : ${open_cost_total:,.2f}")
    print(f"  Overlap with denizz    : {denizz_overlap_count} position(s), ${denizz_overlap_cost:,.2f}")
    if open_count and denizz_overlap_count == 0:
        print("  → No overlap with denizz currently. After patch these positions will only exit")
        print("    via stop-loss / target / resolve (denizz doesn't hold them = no signal to follow).")
    elif denizz_overlap_count:
        print(f"  → After patch, these {denizz_overlap_count} position(s) will start following denizz's sells.")
    print()


if __name__ == "__main__":
    main()
