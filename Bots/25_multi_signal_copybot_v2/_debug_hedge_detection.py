"""
READ-ONLY debug for 2026-04-15 18:29:29 hedge-detection miss.

Simulates detect_hedge_signal() for the exact incident without any side effects.
Prints every intermediate variable so we can see where is_hedge flipped to False.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from config import HEDGE_RATIO_MAX, PLAYERS  # noqa: E402


def simulate(condition_id, signal_player, our_outcome, player_invested, event_slug):
    print("=" * 70)
    print(f"INPUT: cond_id={condition_id[:30]}... player={signal_player} "
          f"our_outcome={our_outcome} invested=${player_invested} slug={event_slug}")
    print("=" * 70)

    # === replicate detect_hedge_signal line-by-line ===
    if player_invested <= 0:
        print("EARLY RETURN: player_invested <= 0")
        return

    opposite = "No" if our_outcome.strip().capitalize() == "Yes" else "Yes"
    wallet = PLAYERS.get(signal_player, "")
    print(f"opposite         = {opposite}")
    print(f"wallet           = {wallet}")
    if not wallet:
        print("EARLY RETURN: no wallet")
        return

    # Step 1 — we SKIP the HTTP call and assume 0 (denizz has no opposite on
    # April 21 cond_id — he is the BUYER of Yes, and has no No on that exact
    # condition_id). The bug is not in step 1 — log confirmed cross-market
    # branch was entered, so primary_usd from step 1 was <= 0.
    primary_usd_step1 = 0.0
    primary_source = "same-condition"
    print(f"[step1] primary_usd (assumed 0; real HTTP call skipped) = {primary_usd_step1}")

    # Step 2 — cross-market via tracker
    pos_file = os.path.join(HERE, "positions.json")
    with open(pos_file, "r") as f:
        data = json.load(f)

    our_opposite_usd = 0.0
    matched = []
    if primary_usd_step1 <= 0 and event_slug:
        for _k, _p in data.get("positions", {}).items():
            if _p.get("status") != "open":
                continue
            if _p.get("event_slug", "") != event_slug:
                continue
            if _p.get("condition_id", "") == condition_id:
                continue
            pos_outcome = (_p.get("outcome", "") or "").strip().capitalize()
            if pos_outcome == opposite:
                cost = float(_p.get("cost_usd", 0) or 0)
                our_opposite_usd += cost
                matched.append((_k[:30], _p.get("outcome"), cost,
                               _p.get("condition_id", "")[:30]))

    print(f"[step2] matched open opposite positions: {len(matched)}")
    for m in matched:
        print(f"        {m}")
    print(f"[step2] our_opposite_usd = ${our_opposite_usd}")

    primary_usd = primary_usd_step1
    if our_opposite_usd > 0:
        # Critical: same expression as filters.py:594
        primary_usd = max(our_opposite_usd, player_invested / HEDGE_RATIO_MAX)
        primary_source = "cross-market-tracker"
        print(f"[step2] primary_usd after max() = {primary_usd!r}")
        print(f"        (player_invested / HEDGE_RATIO_MAX = "
              f"{player_invested / HEDGE_RATIO_MAX!r})")
        print(f"        (our_opposite_usd             = {our_opposite_usd!r})")

    if primary_usd <= 0:
        print("EARLY RETURN: primary_usd <= 0")
        return

    ratio = player_invested / primary_usd
    print(f"[final] ratio = {ratio!r}")
    print(f"[final] HEDGE_RATIO_MAX = {HEDGE_RATIO_MAX!r}")
    print(f"[final] ratio <= HEDGE_RATIO_MAX -> {ratio <= HEDGE_RATIO_MAX}")
    print(f"[final] ratio  > HEDGE_RATIO_MAX -> {ratio > HEDGE_RATIO_MAX}")
    print(f"[final] (ratio - HEDGE_RATIO_MAX) = {ratio - HEDGE_RATIO_MAX!r}")

    is_hedge = ratio <= HEDGE_RATIO_MAX
    print()
    print(f">>> is_hedge = {is_hedge}")
    print(f">>> primary_source = {primary_source}")


if __name__ == "__main__":
    simulate(
        condition_id="0x1507c50c86fb307e4f1acd9d740b000000000000000000000000000000000000",
        signal_player="denizz",
        our_outcome="Yes",
        player_invested=4696.0,
        event_slug="trump-announces-end-of-military-operations-against-iran-by",
    )
