"""
Quick verification: on-chain positions vs v2 state.
Run anytime to check if sync is working.

Exit code 0 = all matched
Exit code 1 = mismatches found
"""
import json
import sys
import httpx
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "98_sure_bot", ".env"))
WALLET = os.getenv("POLYMARKET_WALLET", "")

def main():
    # On-chain truth
    r = httpx.get(
        "https://data-api.polymarket.com/positions",
        params={"user": WALLET, "limit": 500, "sizeThreshold": 0.5},
        timeout=20,
    )
    onchain = [p for p in r.json() if float(p.get("currentValue", 0)) > 1]

    # v2 state
    with open(os.path.join(os.path.dirname(__file__), "positions.json")) as f:
        v2 = json.load(f)
    v2_open = {}
    for k, p in v2.get("positions", {}).items():
        if p.get("status") == "open":
            key = (p.get("condition_id", ""), str(p.get("token_id", "")))
            v2_open[key] = p

    matched = 0
    missing = []
    for p in onchain:
        key = (p.get("conditionId", ""), p.get("asset", ""))
        if key in v2_open:
            matched += 1
        else:
            missing.append(p)

    print(f"On-chain (value>$1): {len(onchain)}")
    print(f"v2 open:             {len(v2_open)}")
    print(f"Matched:             {matched}")
    print(f"Missing from v2:     {len(missing)}")

    if missing:
        print()
        for p in sorted(missing, key=lambda x: -float(x.get("currentValue", 0))):
            t = (p.get("title", "") or "")[:50]
            print(f"  MISSING: ${float(p.get('currentValue', 0)):>7.2f} {p.get('outcome', '?')} {t}")
        print("\nRESULT: FAIL — sync is NOT working")
        sys.exit(1)
    else:
        print("\nRESULT: OK — all on-chain positions are in v2")
        sys.exit(0)

if __name__ == "__main__":
    main()
