"""One-shot migration: purge stale entries from buy_buffers.json.

Context (2026-04-15): before the lifecycle-callback patch, closing a position
(manual sell, auto follow-sell, onchain_sync_disappeared, market redemption)
did NOT clear the corresponding entries from buy_buffers.json. As a result
the disk state accumulated buf_keys for positions that have been closed for
days or weeks. Those stale entries cause new denizz buys on the same market
to be misclassified as tier-upgrades with nonsensical increments.

This script:
  1. Backs up buy_buffers.json -> buy_buffers.json.pre_migration_backup_<ts>
  2. Loads positions.json and builds open_per_player[player] = {f"{cid}_{tok}"}
     for positions with status in ("open", "filled").
  3. Removes any entry in signaled[player] or buffers[player] whose buf_key
     is NOT in open_per_player[player].
  4. Writes the cleaned buy_buffers.json atomically (.tmp + os.replace).
  5. Prints a summary: removed / kept / per-player breakdown.

Run ONCE after deploying the Phase 2 patch. Restart the bot afterwards so
the in-memory state matches the cleaned disk state.
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


def main():
    if not os.path.exists(BUFFERS_FILE):
        print(f"[MIGRATE] No buy_buffers.json at {BUFFERS_FILE} — nothing to do.")
        return 0
    if not os.path.exists(POSITIONS_FILE):
        print(f"[MIGRATE] No positions.json at {POSITIONS_FILE} — aborting.")
        return 1

    # 1) Backup
    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup = f"{BUFFERS_FILE}.pre_migration_backup_{ts}"
    with open(BUFFERS_FILE, "r", encoding="utf-8") as src, \
         open(backup, "w", encoding="utf-8") as dst:
        dst.write(src.read())
    print(f"[MIGRATE] Backup written: {backup}")

    # 2) Build open_per_player from positions.json
    positions_data = _load_json(POSITIONS_FILE)
    open_per_player: dict = {}
    for oid, p in positions_data.get("positions", {}).items():
        if p.get("status") not in ("open", "filled"):
            continue
        sp = p.get("signal_player") or ""
        if not sp:
            continue
        cid = p.get("condition_id") or ""
        tok = str(p.get("token_id") or "")
        if not cid or not tok:
            continue
        open_per_player.setdefault(sp, set()).add(f"{cid}_{tok}")

    total_open_keys = sum(len(v) for v in open_per_player.values())
    print(f"[MIGRATE] Open positions in tracker: {total_open_keys} "
          f"across {len(open_per_player)} player(s)")

    # 3) Walk buy_buffers.json and remove stale entries
    buffers_data = _load_json(BUFFERS_FILE)
    signaled = buffers_data.get("signaled", {})
    buffers = buffers_data.get("buffers", {})

    removed_signaled = 0
    removed_buffers = 0
    kept_signaled = 0
    kept_buffers = 0
    removed_log = []

    # signaled: dict[player, list[str]]
    for player, key_list in list(signaled.items()):
        open_keys = open_per_player.get(player, set())
        new_list = []
        for buf_key in key_list:
            if buf_key in open_keys:
                new_list.append(buf_key)
                kept_signaled += 1
            else:
                removed_signaled += 1
                removed_log.append(f"  signaled[{player}] -= {buf_key[:40]}")
        signaled[player] = new_list

    # buffers: dict[player, dict[buf_key, buf_obj]]
    for player, buf_dict in list(buffers.items()):
        open_keys = open_per_player.get(player, set())
        for buf_key in list(buf_dict.keys()):
            if buf_key in open_keys:
                kept_buffers += 1
            else:
                del buf_dict[buf_key]
                removed_buffers += 1
                removed_log.append(f"  buffers[{player}] -= {buf_key[:40]}")

    # 4) Atomic write
    buffers_data["signaled"] = signaled
    buffers_data["buffers"] = buffers
    _atomic_write(BUFFERS_FILE, buffers_data)

    # 5) Report
    print("[MIGRATE] Removed entries:")
    if removed_log:
        for line in removed_log:
            print(line)
    else:
        print("  (none)")
    print(f"[MIGRATE] Summary: removed_signaled={removed_signaled}, "
          f"removed_buffers={removed_buffers}, "
          f"kept_signaled={kept_signaled}, kept_buffers={kept_buffers}")
    print(f"[MIGRATE] Clean buy_buffers.json written to {BUFFERS_FILE}")
    print("[MIGRATE] DONE. Restart the bot so in-memory state matches disk.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
