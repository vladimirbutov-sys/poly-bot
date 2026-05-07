"""Monday restart time analysis — compare 06/09/12 ET."""
import json
from datetime import datetime, timezone

with open("c:/Users/Honor/Desktop/Polymarket/Bots/10_oil_swing_bot/theta_calibration.json", "r") as f:
    data = json.load(f)

# Build Monday lookup: {date: {et_hour: {wti, yes100, yes105}}}
mondays = {}
for point in data["chart"]:
    dt = datetime.fromtimestamp(point["t"], tz=timezone.utc)
    if dt.weekday() != 0:
        continue
    date_str = dt.strftime("%Y-%m-%d")
    is_edt = date_str >= "2026-03-09"
    et_offset = 4 if is_edt else 5
    h_et = (dt.hour - et_offset) % 24

    if date_str not in mondays:
        mondays[date_str] = {}
    mondays[date_str][h_et] = {
        "wti": point.get("wti"),
        "yes100": point.get("yes100"),
        "yes105": point.get("yes105"),
    }

dates_with_prices = ["2026-03-02", "2026-03-09", "2026-03-16"]

print("=== VOLATILITY (WTI range in each window) ===")
for date in dates_with_prices:
    d = mondays[date]
    for window_name, start, end in [("06-09 ET", 6, 9), ("09-12 ET", 9, 12), ("12-15 ET", 12, 15)]:
        prices = [d[h]["wti"] for h in range(start, end + 1) if h in d and d[h]["wti"]]
        if prices:
            rng = max(prices) - min(prices)
            print(
                "%s %s: WTI range $%.2f ($%.2f-$%.2f)"
                % (date, window_name, rng, min(prices), max(prices))
            )
    print()

print("=== NO PRICE AT ENTRY vs END OF DAY (ET 18-19) ===")
for date in dates_with_prices:
    d = mondays[date]
    eod = d.get(19) or d.get(18)
    if not eod:
        continue

    for entry_h in [6, 9, 12]:
        entry = d.get(entry_h)
        if not entry or not entry["yes100"]:
            continue

        no100_entry = 1 - entry["yes100"]
        no100_eod = 1 - eod["yes100"] if eod["yes100"] else None

        no105_entry = (1 - entry["yes105"]) if entry["yes105"] else None
        no105_eod = (1 - eod["yes105"]) if eod and eod["yes105"] else None

        pnl100 = ((no100_eod - no100_entry) / no100_entry * 100) if no100_entry and no100_eod else None
        pnl105 = ((no105_eod - no105_entry) / no105_entry * 100) if no105_entry and no105_eod else None

        wti_entry = entry["wti"]
        wti_eod = eod["wti"] if eod["wti"] else 0
        print("%s entry %02d ET:" % (date, entry_h))
        print("  WTI: $%.2f -> $%.2f" % (wti_entry, wti_eod))
        if pnl100 is not None:
            print("  NO100: %.4f -> %.4f = %+.1f%%" % (no100_entry, no100_eod, pnl100))
        if pnl105 is not None:
            print("  NO105: %.4f -> %.4f = %+.1f%%" % (no105_entry, no105_eod, pnl105))
    print()

print("=== WTI 3-HOUR TREND AFTER ENTRY ===")
for date in dates_with_prices:
    d = mondays[date]
    for start_h in [6, 9, 12]:
        entry_wti = d.get(start_h, {}).get("wti")
        later_h = start_h + 3
        later_wti = d.get(later_h, {}).get("wti")
        if entry_wti and later_wti:
            change = later_wti - entry_wti
            print(
                "%s %02d->%02d ET: WTI $%.2f -> $%.2f (%+.2f)"
                % (date, start_h, later_h, entry_wti, later_wti, change)
            )
    print()

print("=== AVERAGE METRICS ACROSS 3 MONDAYS ===")
for entry_h in [6, 9, 12]:
    wti_ranges = []
    pnl100_list = []
    pnl105_list = []
    for date in dates_with_prices:
        d = mondays[date]
        # Volatility in 3h after entry
        prices = [d[h]["wti"] for h in range(entry_h, entry_h + 3) if h in d and d[h]["wti"]]
        if prices:
            wti_ranges.append(max(prices) - min(prices))

        # P&L
        entry = d.get(entry_h)
        eod = d.get(19) or d.get(18)
        if entry and eod and entry["yes100"] and eod["yes100"]:
            no_e = 1 - entry["yes100"]
            no_x = 1 - eod["yes100"]
            if no_e > 0:
                pnl100_list.append((no_x - no_e) / no_e * 100)
        if entry and eod and entry.get("yes105") and eod.get("yes105"):
            no_e = 1 - entry["yes105"]
            no_x = 1 - eod["yes105"]
            if no_e > 0:
                pnl105_list.append((no_x - no_e) / no_e * 100)

    avg_vol = sum(wti_ranges) / len(wti_ranges) if wti_ranges else 0
    avg_pnl100 = sum(pnl100_list) / len(pnl100_list) if pnl100_list else 0
    avg_pnl105 = sum(pnl105_list) / len(pnl105_list) if pnl105_list else 0
    win100 = sum(1 for x in pnl100_list if x > 0)
    win105 = sum(1 for x in pnl105_list if x > 0)

    print("Entry %02d ET:" % entry_h)
    print("  Avg WTI 3h range: $%.2f" % avg_vol)
    print("  NO100 avg P&L: %+.1f%% (wins: %d/%d)" % (avg_pnl100, win100, len(pnl100_list)))
    print("  NO105 avg P&L: %+.1f%% (wins: %d/%d)" % (avg_pnl105, win105, len(pnl105_list)))
    print()
