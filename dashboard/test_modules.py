"""Quick test: load all modules and show data."""
import sys
sys.path.insert(0, ".")

import config
print("Config OK, bots:", list(config.BOTS.keys()))

import data_reader
stats = data_reader.read_bot_stats()
for bot_id, s in stats.items():
    print(f"  {bot_id}: balance=${s['current_balance']:.2f}, open={s['open']}, pnl=${s['total_pnl']:+.2f}")

scanner = data_reader.read_scanner_stats()
if scanner:
    print(f"  Scanner: {scanner['total_markets']} markets, {scanner['resolved']} resolved, {scanner['win_rate']:.1f}% WR")

import bot_manager
statuses = bot_manager.get_all_statuses()
for bot_id, st in statuses.items():
    print(f"  {bot_id}: {st['status']}")

import settings_editor
s98 = settings_editor.read_bot_settings("98_sure_bot")
if s98:
    print(f"  98_sure_bot settings: {len(s98)} params")
    for p in s98:
        print(f"    {p['name']} = {p['value']}")

print("\nAll modules OK!")
