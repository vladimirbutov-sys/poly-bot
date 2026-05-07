"""CLI: switch / inspect the active bot variant (A | B).

Usage:
    python _switch_variant.py A          # write "A" to _bot_variant.txt
    python _switch_variant.py B          # write "B" to _bot_variant.txt
    python _switch_variant.py status     # print current state
    python _switch_variant.py clear      # remove _bot_variant.txt (fall back to config)

The bot picks up the change within `VARIANT_RELOAD_INTERVAL_SEC` seconds
(default 30) without requiring a restart.
"""
from __future__ import annotations

import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import config
import variant


def _file_path() -> str:
    project_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(project_dir, config.VARIANT_FILE)


def cmd_status() -> int:
    snap = variant.get_variant_status()
    print(f"Active variant: {snap['active']}")
    print(f"Source:         {snap['source']}")
    print(f"Config default: {snap['config_default']}")
    print(f"File status:    {snap['file_status']}  (path: {_file_path()})")
    print(f"Variant B band: [{snap['floor']:.2f}, {snap['ceil']:.2f}] live best ask")
    print(f"Cache age:      {snap['cached_for_sec']}s "
          f"(reload interval {config.VARIANT_RELOAD_INTERVAL_SEC}s)")
    return 0


def cmd_set(target: str) -> int:
    target = target.strip().upper()
    if target not in ("A", "B"):
        print(f"ERROR: invalid variant {target!r}; expected A or B")
        return 2
    path = _file_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write(target)
    # Force reread to confirm it stuck.
    new_value = variant.get_active_variant(force_reload=True)
    print(f"OK wrote {target!r} -> {path}")
    print(f"   active variant now: {new_value}")
    print(f"   bot will pick up the change within "
          f"{config.VARIANT_RELOAD_INTERVAL_SEC}s")
    return 0


def cmd_clear() -> int:
    path = _file_path()
    if not os.path.exists(path):
        print(f"No file at {path} (already cleared)")
    else:
        os.remove(path)
        print(f"OK removed {path}")
    new_value = variant.get_active_variant(force_reload=True)
    print(f"   active variant now: {new_value} (from config default "
          f"{config.BOT_VARIANT!r})")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        return cmd_status()
    cmd = argv[1].strip().lower()
    if cmd in ("a", "b"):
        return cmd_set(cmd.upper())
    if cmd == "status":
        return cmd_status()
    if cmd == "clear":
        return cmd_clear()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
