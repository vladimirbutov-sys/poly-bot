"""Repeatable cleanup: purge stale entries from buy_buffers.json.

Context (2026-04-15, follow-up to _migrate_cleanup_buffers.py):
The original migration script correctly cleaned the disk, but stale entries
re-accumulated because:

  1. Every handle_buy(...) call in main.py writes a buffer entry via _get_buf()
     BEFORE any signal/size filter runs. If the buy is later filtered out
     (no position opened), the buffer entry persists.

  2. Events arriving on markets the bot chose not to trade (23 of the 51
     re-added keys aren't even in positions.json) still leave buffer droppings.

  3. main._rehydrate_from_tracker Direction 2 only scans _signaled_keys,
     not _buy_buffers. So stale _buy_buffers entries are never cleaned on
     startup.

Definition of stale (per task 2026-04-15 follow-up):
  - buf_key is stale if no position with matching (condition_id, token_id)
    has status == "open" in positions.json.
  - For stale keys: REMOVE the entire entry from buffers[player]
    (not just reset last_tier_bet).
  - Entries with an open position: LEAVE AS IS — even if last_tier_bet > 0
    (legitimate tier-upgrade state).

Idempotent. Safe to re-run.

Usage:
    python _cleanup_stale_buffers.py            # dry-run report
    python _cleanup_stale_buffers.py --apply    # actually write
"""
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
BUFFERS_FILE = os.path.join(HERE, "buy_buffers.json")
POSITIONS_FILE = os.path.join(HERE, "positions.json")


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _atomic_write(path, payload):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _build_open_keys(positions_data):
    """Return {player: {f'{cid}_{tok}'}} for status == 'open' positions only."""
    out = {}
    for oid, p in positions_data.get("positions", {}).items():
        if p.get("status") != "open":
            continue
        sp = p.get("signal_player") or ""
        cid = p.get("condition_id") or ""
        tok = str(p.get("token_id") or "")
        if not sp or not cid or not tok:
            continue
        out.setdefault(sp, set()).add(f"{cid}_{tok}")
    return out


def _build_title_lookup(positions_data):
    """Return {f'{cid}_{tok}': latest_title} across all positions (any status)."""
    out = {}
    for oid, p in positions_data.get("positions", {}).items():
        cid = p.get("condition_id") or ""
        tok = str(p.get("token_id") or "")
        title = p.get("title") or "?"
        if cid and tok:
            out[f"{cid}_{tok}"] = title
    return out


def main(apply_changes: bool = False) -> int:
    if not os.path.exists(BUFFERS_FILE):
        print(f"[CLEANUP] No buy_buffers.json at {BUFFERS_FILE}")
        return 0
    if not os.path.exists(POSITIONS_FILE):
        print(f"[CLEANUP] No positions.json at {POSITIONS_FILE} - aborting")
        return 1

    positions_data = _load_json(POSITIONS_FILE)
    buffers_data = _load_json(BUFFERS_FILE)

    open_per_player = _build_open_keys(positions_data)
    title_lookup = _build_title_lookup(positions_data)

    total_open = sum(len(v) for v in open_per_player.values())
    print(f"[CLEANUP] Open positions across all players: {total_open}")

    signaled = buffers_data.get("signaled", {})
    buffers = buffers_data.get("buffers", {})

    removed_buffers = []   # list of (player, buf_key, title, last_tier_bet)
    removed_signaled = []  # list of (player, buf_key)
    kept_buffers = 0
    kept_signaled = 0

    # Clean signaled[player]
    for player, key_list in list(signaled.items()):
        open_keys = open_per_player.get(player, set())
        new_list = []
        for buf_key in key_list:
            if buf_key in open_keys:
                new_list.append(buf_key)
                kept_signaled += 1
            else:
                removed_signaled.append((player, buf_key))
        signaled[player] = new_list

    # Clean buffers[player]
    for player, buf_dict in list(buffers.items()):
        open_keys = open_per_player.get(player, set())
        for buf_key in list(buf_dict.keys()):
            if buf_key in open_keys:
                kept_buffers += 1
            else:
                entry = buf_dict[buf_key]
                ltb = entry.get("last_tier_bet", 0) or 0
                title = title_lookup.get(buf_key, "(not in positions.json)")
                removed_buffers.append((player, buf_key, title, ltb))
                if apply_changes:
                    del buf_dict[buf_key]

    # Report
    print(f"[CLEANUP] buffers: kept={kept_buffers}, stale_to_remove={len(removed_buffers)}")
    print(f"[CLEANUP] signaled: kept={kept_signaled}, stale_to_remove={len(removed_signaled)}")
    if removed_buffers:
        print("[CLEANUP] Stale buffer entries:")
        for player, bk, title, ltb in removed_buffers:
            marker = " (LTB>0)" if ltb > 0 else ""
            print(f"  - buffers[{player}] {bk[:44]}... ltb=${ltb:.2f}{marker}  {title[:60]}")

    if not apply_changes:
        print("[CLEANUP] DRY-RUN only. Re-run with --apply to write changes.")
        return 0

    # Backup before write
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup = f"{BUFFERS_FILE}.pre_fix_stale_tier_bet_{ts}"
    with open(BUFFERS_FILE, "r", encoding="utf-8") as src, \
         open(backup, "w", encoding="utf-8") as dst:
        dst.write(src.read())
    print(f"[CLEANUP] Backup written: {os.path.basename(backup)}")

    buffers_data["signaled"] = signaled
    buffers_data["buffers"] = buffers
    _atomic_write(BUFFERS_FILE, buffers_data)
    print(f"[CLEANUP] Clean buy_buffers.json written.")
    return 0


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    sys.exit(main(apply_changes=apply))
