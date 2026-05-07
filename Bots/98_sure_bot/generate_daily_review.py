#!/usr/bin/env python3
"""
Daily Review Generator for 98_sure_bot.
Generates markdown report at 09:00 MSK daily.
Run via Windows Task Scheduler.
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

MSK = timezone(timedelta(hours=3))
BOT_DIR = Path(r"C:\Users\Honor\Desktop\Polymarket\Bots\98_sure_bot")
ANALYTICS_DIR = BOT_DIR / "_analytics"
POSITIONS_FILE = BOT_DIR / "positions.json"
LOG_FILE = BOT_DIR / "bot_log.txt"
CONFIG_FILE = BOT_DIR / "config.py"


def load_positions():
    with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_config():
    config = {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^(\w+)\s*=\s*(.+?)(?:\s*#.*)?$", line)
            if m:
                key, val = m.group(1), m.group(2).strip()
                config[key] = val
    return config


def classify_market(title, category=""):
    t = title.lower()
    if re.search(r"(election|mayoral|gubernat|next prime minister|next.*løgma|part of the next gov|win.*seats)", t):
        return "Elections"
    if re.search(r"trump.*(say|post|truth social)", t):
        return "Trump say/post"
    if re.search(r"(military|russia|hezbollah|iran|strike|capture|war|gaza|ukraine|kyiv)", t):
        return "Geopolitics"
    if re.search(r"(hormuz|strait|ship|transit)", t):
        return "Shipping"
    if re.search(r"(temperature|weather|\d+\s*°)", t):
        return "Weather"
    if re.search(r"(counter-strike|dota|valorant|lol:|league of legends)", t):
        return "Esports"
    if re.search(r"(ufc|boxing|mma|fight night)", t):
        return "Fighting"
    if category in ("sports", "sports_other", "soccer"):
        return "Sports"
    if category == "crypto":
        return "Crypto"
    if category in ("politics", "geopolitics"):
        return "Politics/Geo"
    return "Other"


def get_polymarket_link(title):
    """Best-effort link from title."""
    slug = re.sub(r"[^a-z0-9\s]", "", title.lower())
    slug = re.sub(r"\s+", "-", slug.strip())[:60]
    return f"https://polymarket.com/event/{slug}"


def generate_review():
    now = datetime.now(MSK)
    data = load_positions()
    config = load_config()
    stats = data.get("stats", {})
    positions = data.get("positions", {})

    # Classify positions
    won = [p for p in positions.values() if p.get("status") == "won"]
    lost = [p for p in positions.values() if p.get("status") == "lost"]
    open_pos = [p for p in positions.values() if p.get("status") == "open"]

    won_pnl = sum(p.get("pnl", 0) for p in won)
    lost_pnl = sum(p.get("pnl", 0) for p in lost)
    open_cost = sum(p.get("cost_usd", 0) for p in open_pos)
    total_resolved = len(won) + len(lost)
    win_rate = len(won) / total_resolved * 100 if total_resolved else 0

    # Rolling windows
    def rolling(days):
        cutoff = (now - timedelta(days=days)).isoformat()
        w = [p for p in won if p.get("resolved_at", "") >= cutoff]
        l = [p for p in lost if p.get("resolved_at", "") >= cutoff]
        pnl = sum(p.get("pnl", 0) for p in w) + sum(p.get("pnl", 0) for p in l)
        return len(w), len(l), pnl

    w7, l7, pnl7 = rolling(7)
    w30, l30, pnl30 = rolling(30)

    # By category (resolved)
    cat_stats = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0})
    for p in won:
        c = classify_market(p.get("title", ""), p.get("category", ""))
        cat_stats[c]["w"] += 1
        cat_stats[c]["pnl"] += p.get("pnl", 0)
    for p in lost:
        c = classify_market(p.get("title", ""), p.get("category", ""))
        cat_stats[c]["l"] += 1
        cat_stats[c]["pnl"] += p.get("pnl", 0)

    # By price bucket
    buckets = [(0.96, 0.975), (0.975, 0.98), (0.98, 0.985), (0.985, 0.99), (0.99, 0.995)]
    bucket_stats = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0})
    for p in won + lost:
        price = p.get("entry_price", 0)
        for lo, hi in buckets:
            if lo <= price < hi:
                key = f"{lo*100:.1f}-{hi*100:.1f}c"
                bucket_stats[key]["w" if p.get("status") == "won" else "l"] += 1
                bucket_stats[key]["pnl"] += p.get("pnl", 0)
                break

    # Open by category
    open_cat = defaultdict(lambda: {"count": 0, "cost": 0})
    for p in open_pos:
        c = classify_market(p.get("title", ""), p.get("category", ""))
        open_cat[c]["count"] += 1
        open_cat[c]["cost"] += p.get("cost_usd", 0)

    # Stuck positions (>48h past end_date)
    now_utc = datetime.now(timezone.utc)
    stuck = []
    for k, p in positions.items():
        if p.get("status") != "open":
            continue
        end = p.get("end_date", "")
        if not end:
            continue
        try:
            ed = datetime.fromisoformat(end.replace("Z", "+00:00"))
            hours_overdue = (now_utc - ed).total_seconds() / 3600
            if hours_overdue >= 48:
                stuck.append({
                    "title": p.get("title", ""),
                    "cost": p.get("cost_usd", 0),
                    "end_date": end[:10],
                    "hours_overdue": hours_overdue,
                    "neg_risk": p.get("neg_risk", False),
                    "category": classify_market(p.get("title", ""), p.get("category", "")),
                    "condition_id": p.get("condition_id", ""),
                })
        except:
            pass

    stuck.sort(key=lambda x: -x["hours_overdue"])
    stuck_total = sum(s["cost"] for s in stuck)
    stuck_by_cat = defaultdict(list)
    for s in stuck:
        stuck_by_cat[s["category"]].append(s)

    # Resolve times (last 7d wins)
    resolve_times = []
    cutoff_7d = (now_utc - timedelta(days=7)).isoformat()
    for p in won:
        if p.get("resolved_at", "") >= cutoff_7d:
            ts = p.get("timestamp", "")
            ra = p.get("resolved_at", "")
            if ts and ra:
                try:
                    t0 = datetime.fromisoformat(ts)
                    t1 = datetime.fromisoformat(ra)
                    hours = (t1 - t0).total_seconds() / 3600
                    resolve_times.append(hours)
                except:
                    pass

    resolve_times.sort()
    median_resolve = resolve_times[len(resolve_times) // 2] if resolve_times else 0
    avg_resolve = sum(resolve_times) / len(resolve_times) if resolve_times else 0

    # USDC balance
    try:
        sys.path.insert(0, str(BOT_DIR))
        from redeemer import get_usdc_balance_usd
        usdc_balance = get_usdc_balance_usd()
    except:
        usdc_balance = 0

    # Build report
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%Y-%m-%d %H:%M MSK")

    lines = []
    lines.append(f"# Daily Review — {time_str}")
    lines.append("")

    # Warnings
    warnings = []
    if stuck:
        warnings.append(f"- {len(stuck)} positions stuck >48h (${stuck_total:.2f} frozen)")
    if usdc_balance < 15:
        warnings.append(f"- Low USDC balance: ${usdc_balance:.2f}")
    if open_cost > 900:
        warnings.append(f"- High capital utilization: ${open_cost:.2f} in positions")

    if warnings:
        lines.append("## WARNINGS")
        lines.extend(warnings)
        lines.append("")

    # Performance
    lines.append("## 1. Performance")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| USDC Balance | ${usdc_balance:.2f} |")
    lines.append(f"| Open Positions | {len(open_pos)} (${open_cost:.2f} frozen) |")
    lines.append(f"| Total Assets | ${usdc_balance + open_cost:.2f} |")
    lines.append(f"| Realized PnL | ${won_pnl + lost_pnl:+.2f} |")
    lines.append(f"| W/L (all time) | {len(won)}/{len(lost)} ({win_rate:.1f}%) |")
    lines.append("")

    # Rolling
    lines.append("### Rolling Windows")
    lines.append("| Period | W/L | PnL |")
    lines.append("|--------|-----|-----|")
    lines.append(f"| 7d | {w7}/{l7} | ${pnl7:+.2f} |")
    lines.append(f"| 30d | {w30}/{l30} | ${pnl30:+.2f} |")
    lines.append("")

    # By category
    lines.append("### By Category (resolved)")
    lines.append("| Category | W/L | WR | PnL |")
    lines.append("|----------|-----|----|-----|")
    for cat, s in sorted(cat_stats.items(), key=lambda x: -(x[1]["w"] + x[1]["l"])):
        total = s["w"] + s["l"]
        wr = s["w"] / total * 100 if total else 0
        lines.append(f"| {cat} | {s['w']}/{s['l']} | {wr:.1f}% | ${s['pnl']:+.2f} |")
    lines.append("")

    # By price bucket
    lines.append("### By Price Bucket")
    lines.append("| Bucket | W/L | PnL |")
    lines.append("|--------|-----|-----|")
    for bucket in ["96.0-97.5c", "97.5-98.0c", "98.0-98.5c", "98.5-99.0c", "99.0-99.5c"]:
        s = bucket_stats.get(bucket, {"w": 0, "l": 0, "pnl": 0})
        lines.append(f"| {bucket} | {s['w']}/{s['l']} | ${s['pnl']:+.2f} |")
    lines.append("")

    # Open by category
    lines.append("### Open Positions by Category")
    lines.append("| Category | Count | Frozen |")
    lines.append("|----------|-------|--------|")
    for cat, s in sorted(open_cat.items(), key=lambda x: -x[1]["cost"]):
        lines.append(f"| {cat} | {s['count']} | ${s['cost']:.2f} |")
    lines.append("")

    # Resolve times
    if resolve_times:
        lines.append("### Resolve Times (7d)")
        lines.append(f"- Median: {median_resolve:.1f}h")
        lines.append(f"- Average: {avg_resolve:.1f}h")
        lines.append(f"- Sample: {len(resolve_times)} positions")
        lines.append("")

    # STUCK POSITIONS
    if stuck:
        lines.append("## 2. Stuck Positions (>48h past end_date)")
        lines.append("")
        lines.append(f"**Total: {len(stuck)} positions, ${stuck_total:.2f} frozen**")
        lines.append("")

        for cat, positions_list in sorted(stuck_by_cat.items(), key=lambda x: -sum(s["cost"] for s in x[1])):
            cat_cost = sum(s["cost"] for s in positions_list)
            lines.append(f"### {cat} ({len(positions_list)} positions, ${cat_cost:.2f})")
            lines.append("")
            for s in sorted(positions_list, key=lambda x: -x["hours_overdue"]):
                days = s["hours_overdue"] / 24
                link = get_polymarket_link(s["title"])
                lines.append(f"- [{s['title'][:70]}]({link})")
                lines.append(f"  - End: {s['end_date']} | Overdue: {days:.1f}d | ${s['cost']:.2f} | neg_risk={s['neg_risk']}")
            lines.append("")
    else:
        lines.append("## 2. Stuck Positions")
        lines.append("None (all within 48h of end_date)")
        lines.append("")

    # SCANNER MARKET SUPPLY
    scanner_file = Path(r"C:\Users\Honor\Desktop\Polymarket\Bots\97_scanner\scanner_data.json")
    if scanner_file.exists():
        try:
            with open(scanner_file, "r", encoding="utf-8") as f:
                scanner = json.load(f)
            sc_markets = scanner.get("markets", {})
            sc_resolved = {k: m for k, m in sc_markets.items() if m.get("resolved")}

            # Bot-eligible (price >= threshold)
            sc_eligible = {k: m for k, m in sc_resolved.items()
                          if m.get("first_price", 0) >= 0.96}

            def _scanner_won(m):
                res = m.get("resolution")
                if isinstance(res, dict):
                    return res.get("winner") == m.get("high_outcome")
                return res == "win"

            sc_wins = sum(1 for m in sc_eligible.values() if _scanner_won(m))
            sc_losses = sum(1 for m in sc_eligible.values() if m.get("resolved") and not _scanner_won(m))
            sc_total = sc_wins + sc_losses
            sc_wr = sc_wins / sc_total * 100 if sc_total else 0

            # By category
            sc_by_cat = defaultdict(lambda: {"total": 0, "losses": 0})
            for m in sc_eligible.values():
                cat = m.get("category", "other")
                sc_by_cat[cat]["total"] += 1
                if m.get("resolved") and not _scanner_won(m):
                    sc_by_cat[cat]["losses"] += 1

            # Resolve times
            sc_resolve_times = defaultdict(list)
            for m in sc_eligible.values():
                neg = m.get("neg_risk", False)
                typ = "neg_risk" if neg else "regular"
                # Calculate resolve time from snapshots if available
                first_seen = m.get("first_seen", "")
                resolved_at = ""
                snapshots = m.get("snapshots", [])
                if snapshots and len(snapshots) >= 2:
                    resolved_at = snapshots[-1].get("timestamp", "")
                if first_seen and resolved_at:
                    try:
                        t0 = datetime.fromisoformat(first_seen)
                        t1 = datetime.fromisoformat(resolved_at)
                        hours = (t1 - t0).total_seconds() / 3600
                        if 0 < hours < 720:  # sanity check
                            sc_resolve_times[typ].append(hours)
                    except:
                        pass

            lines.append("## Scanner Market Supply (97_scanner)")
            lines.append("")
            lines.append(f"Total resolved: {len(sc_resolved)} | Bot-eligible: {sc_total}")
            lines.append(f"W/L: {sc_wins}/{sc_losses} ({sc_wr:.2f}% WR)")
            lines.append("")

            # By type resolve times
            if sc_resolve_times:
                lines.append("### Resolve Times by Type")
                lines.append("| Type | Median | Count |")
                lines.append("|------|--------|-------|")
                for typ in ["regular", "neg_risk"]:
                    times = sorted(sc_resolve_times.get(typ, []))
                    if times:
                        median = times[len(times) // 2]
                        lines.append(f"| {typ} | {median:.1f}h | {len(times)} |")
                lines.append("")

            # By category
            lines.append("### By Category (scanner, bot-eligible)")
            lines.append("| Category | Total | Losses | Loss Rate | ")
            lines.append("|----------|-------|--------|-----------|")
            for cat, s in sorted(sc_by_cat.items(), key=lambda x: -x[1]["total"]):
                lr = s["losses"] / s["total"] * 100 if s["total"] else 0
                lines.append(f"| {cat} | {s['total']} | {s['losses']} | {lr:.2f}% |")
            lines.append("")
        except Exception as e:
            lines.append(f"## Scanner Market Supply")
            lines.append(f"Error loading scanner data: {e}")
            lines.append("")

    # Config snapshot
    lines.append("## 3. Config")
    lines.append("")
    for key in ["BET_SIZE_REGULAR", "BET_SIZE_NEG_RISK", "MAX_PRICE", "MAX_TOTAL_FROZEN",
                 "MAX_END_DATE_REGULAR", "MAX_END_DATE_NEG_RISK", "MAX_NEG_RISK_FROZEN",
                 "SCAN_INTERVAL"]:
        val = config.get(key, "?")
        lines.append(f"- {key}: {val}")
    lines.append("")

    # Active filters
    lines.append("## 4. Active Filters")
    lines.append("- Sub-match (map/game/set/KO/TKO/draw/totals)")
    lines.append("- Elections (election/mayoral/prime minister/government)")
    lines.append("- Slow markets (top/season/most/transit/strait/ships/weekly/monthly)")
    lines.append("- Duplicate event (max 1 position per event)")
    lines.append(f"- Max frozen: ${config.get('MAX_TOTAL_FROZEN', '?')}")
    lines.append("")

    # Write
    report_path = ANALYTICS_DIR / f"{date_str}_daily-review.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Report saved: {report_path}")
    return report_path


if __name__ == "__main__":
    generate_review()
