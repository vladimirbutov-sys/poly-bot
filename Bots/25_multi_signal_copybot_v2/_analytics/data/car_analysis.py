"""
Car Copy-Strategy Analysis v2
Uses existing positions data (801 records) + fresh activity data.
"""
import json, time, requests, os, sys, math
from datetime import datetime, timezone, timedelta
from collections import defaultdict

BASE = "c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/_analytics/data"
DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
CAR_EOA = "0x8dECBB0645dDD89c905670F2544aA5a9c5624c42"
CAR_WALLET = "0x7c3db723f1d4d8cb9c550095203b686cb11e5c6b"  # proxy wallet

# ============================================================
# STEP 1: Fetch all Car activity (trade-level)
# ============================================================
def fetch_car_activity():
    all_rows = []
    offset = 0
    while True:
        print(f"  Fetching activity offset={offset}...", flush=True)
        try:
            r = requests.get(
                f"{DATA_API}/activity",
                params={"user": CAR_WALLET, "limit": 500, "offset": offset},
                timeout=30,
            )
            if r.status_code == 400:
                print(f"  HTTP 400 at offset={offset}, stopping.")
                break
            r.raise_for_status()
            batch = r.json()
            if not batch:
                break
            all_rows.extend(batch)
            print(f"    Got {len(batch)} rows (total {len(all_rows)})", flush=True)
            if len(batch) < 500:
                break
            offset += 500
            time.sleep(0.3)
        except Exception as e:
            print(f"  Error at offset={offset}: {e}")
            break
    return all_rows

# ============================================================
# STEP 1b: Fetch market metadata
# ============================================================
def fetch_market_metadata(condition_ids):
    cache_path = os.path.join(BASE, "car_markets_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    else:
        cache = {}

    missing = [c for c in condition_ids if c not in cache]
    print(f"  Markets: {len(cache)} cached, {len(missing)} to fetch", flush=True)

    for i in range(0, len(missing), 20):
        batch = missing[i:i+20]
        cid_str = ",".join(batch)
        try:
            r = requests.get(
                f"{GAMMA_API}/markets",
                params={"condition_ids": cid_str},
                timeout=20,
            )
            if r.ok:
                for m in r.json():
                    cid = m.get("conditionId") or m.get("condition_id", "")
                    if cid:
                        cache[cid] = m
            print(f"    Fetched {min(i+20, len(missing))}/{len(missing)} markets", flush=True)
        except Exception as e:
            print(f"    Market fetch error: {e}")
        time.sleep(0.3)

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f)
    return cache


# ============================================================
# MAIN ANALYSIS
# ============================================================
def main():
    print("=" * 60)
    print("  CAR COPY-STRATEGY ANALYSIS v2")
    print("=" * 60)

    # ========================================
    # Load existing positions data (801 items)
    # ========================================
    pos_path = os.path.join(BASE, "car_closed_positions_raw.json")
    with open(pos_path, "r", encoding="utf-8", errors="replace") as f:
        positions_raw = json.load(f)
    print(f"\n[DATA] Loaded {len(positions_raw)} position records from car_closed_positions_raw.json")

    # ========================================
    # Fetch fresh activity data
    # ========================================
    activity_path = os.path.join(BASE, "car_activity_full.json")
    if os.path.exists(activity_path):
        with open(activity_path, "r", encoding="utf-8") as f:
            activity = json.load(f)
        if len(activity) < 50:
            print(f"  Cache has only {len(activity)} rows, re-fetching...")
            activity = fetch_car_activity()
            with open(activity_path, "w", encoding="utf-8") as f:
                json.dump(activity, f)
    else:
        print("\n[STEP 1] Fetching Car activity from API...")
        activity = fetch_car_activity()
        with open(activity_path, "w", encoding="utf-8") as f:
            json.dump(activity, f)

    print(f"  Activity rows: {len(activity)}")
    if len(activity) >= 3500:
        print("  WARNING: Hit 3500-row cap, data may be incomplete!")

    # Parse activity timestamps
    for r in activity:
        ts = r.get("timestamp", 0)
        if isinstance(ts, (int, float)) and ts > 0:
            r["_dt"] = datetime.fromtimestamp(ts, tz=timezone.utc)
        elif isinstance(ts, str) and ts:
            try:
                r["_dt"] = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except:
                r["_dt"] = None
        else:
            r["_dt"] = None

    dated_activity = [r for r in activity if r.get("_dt")]
    if dated_activity:
        act_earliest = min(r["_dt"] for r in dated_activity)
        act_latest = max(r["_dt"] for r in dated_activity)
        act_days = max(1, (act_latest - act_earliest).days)
        print(f"  Activity date range: {act_earliest.date()} to {act_latest.date()} ({act_days} days)")

    # Parse positions timestamps
    for p in positions_raw:
        ts = p.get("timestamp", 0)
        if isinstance(ts, (int, float)) and ts > 0:
            p["_dt"] = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            p["_dt"] = None

    dated_pos = [p for p in positions_raw if p.get("_dt")]
    if dated_pos:
        pos_earliest = min(p["_dt"] for p in dated_pos)
        pos_latest = max(p["_dt"] for p in dated_pos)
        pos_days = max(1, (pos_latest - pos_earliest).days)
        print(f"  Positions date range: {pos_earliest.date()} to {pos_latest.date()} ({pos_days} days)")

    # ========================================
    # Fetch market metadata for all condition IDs
    # ========================================
    all_cids = set()
    for p in positions_raw:
        cid = p.get("conditionId", "")
        if cid:
            all_cids.add(cid)
    for r in activity:
        cid = r.get("conditionId") or r.get("condition_id") or ""
        if cid:
            all_cids.add(cid)

    print(f"\n[STEP 1b] Fetching market metadata for {len(all_cids)} CIDs...")
    markets = fetch_market_metadata(list(all_cids))

    # ========================================
    # STEP 2: PROFILE CAR
    # ========================================
    print("\n" + "=" * 60)
    print("  STEP 2: CAR PROFILE")
    print("=" * 60)

    # --- 2.1 General Statistics ---
    # Activity type breakdown
    type_counts = defaultdict(int)
    type_volume = defaultdict(float)
    for r in activity:
        t = r.get("type", "UNKNOWN")
        type_counts[t] += 1
        sz = float(r.get("size", 0) or 0)
        pr = float(r.get("price", 0) or 0)
        usd_size = float(r.get("usdcSize", 0) or 0)
        type_volume[t] += usd_size if usd_size > 0 else sz * pr

    # From positions data
    total_bought_usd = sum(
        float(p.get("totalBought", 0) or 0) * float(p.get("avgPrice", 0) or 0)
        for p in positions_raw
    )
    total_realized_pnl = sum(float(p.get("realizedPnl", 0) or 0) for p in positions_raw)
    unique_markets = len(set(p.get("conditionId", "") for p in positions_raw if p.get("conditionId")))

    print(f"\n  --- 2.1 General Statistics ---")
    print(f"  Position records: {len(positions_raw)}")
    print(f"  Activity rows: {len(activity)}")
    print(f"  Unique markets (from positions): {unique_markets}")
    print(f"  Lifetime realized P&L: ${total_realized_pnl:,.0f}")
    print(f"  Avg realized P&L per position: ${total_realized_pnl / len(positions_raw):,.0f}")
    print(f"\n  Activity by type:")
    for t in sorted(type_counts.keys()):
        print(f"    {t}: {type_counts[t]} events, ${type_volume[t]:,.0f} volume")

    # Trades per day
    if dated_activity:
        trades_per_day = len(activity) / act_days
        print(f"\n  Trades per day: {trades_per_day:.1f}")

    # --- 2.2 Trade Classification ---
    print(f"\n  --- 2.2 Trade Classification ---")

    # Group activity by conditionId
    cid_activity = defaultdict(list)
    for r in activity:
        cid = r.get("conditionId") or r.get("condition_id") or ""
        if cid:
            cid_activity[cid].append(r)

    # Identify merge CIDs from activity
    merge_cids = set()
    for cid, events in cid_activity.items():
        for e in events:
            if (e.get("type") or "").upper() in ("MERGE", "SPLIT"):
                merge_cids.add(cid)

    # Group positions by conditionId to detect both-sides buying
    cid_positions = defaultdict(list)
    for p in positions_raw:
        cid = p.get("conditionId", "")
        if cid:
            cid_positions[cid].append(p)

    # CIDs where Car bought BOTH Yes and No
    both_sides_cids = set()
    for cid, plist in cid_positions.items():
        outcomes = set(p.get("outcome", "").strip() for p in plist)
        if "Yes" in outcomes and "No" in outcomes:
            both_sides_cids.add(cid)

    # Classify each position
    classifications = []
    for p in positions_raw:
        cid = p.get("conditionId", "")
        outcome = p.get("outcome", "")
        avg_price = float(p.get("avgPrice", 0) or 0)
        total_bought = float(p.get("totalBought", 0) or 0)
        realized_pnl = float(p.get("realizedPnl", 0) or 0)
        cur_price = float(p.get("curPrice", 0) or 0)
        title = p.get("title", "?")
        event_slug = p.get("eventSlug", "")
        end_date = p.get("endDate", "")
        asset = p.get("asset", "")

        buy_usd = total_bought * avg_price

        # Classify
        is_merge_cid = cid in merge_cids
        is_both_sides = cid in both_sides_cids

        if is_merge_cid and is_both_sides:
            classification = "merge_arbitrage"
        elif is_merge_cid:
            # Merge exists on this CID but Car only bought one side
            # Likely still merge-related (bought the other side via different token)
            classification = "merge_related"
        elif is_both_sides:
            # Bought both sides but no merge event in our activity window
            # Could be hedge or failed merge attempt
            classification = "both_sides_no_merge"
        else:
            # Pure direction bet
            # Sub-classify by hold time estimate
            # Use position timestamp as entry, endDate as potential exit
            classification = "direction_bet"

        # Estimate exit price
        # If realizedPnl exists and totalBought > 0:
        # pnl = revenue - cost, cost = totalBought * avgPrice
        # revenue = pnl + cost
        cost = buy_usd
        revenue = realized_pnl + cost
        if total_bought > 0:
            exit_price_est = revenue / total_bought
        else:
            exit_price_est = avg_price

        # Win/loss
        is_win = realized_pnl > 0
        roi = realized_pnl / cost if cost > 0 else 0

        classifications.append({
            "cid": cid,
            "asset": asset,
            "outcome": outcome,
            "classification": classification,
            "avg_price": avg_price,
            "total_bought_shares": total_bought,
            "buy_usd": buy_usd,
            "realized_pnl": realized_pnl,
            "exit_price_est": exit_price_est,
            "cur_price": cur_price,
            "roi": roi,
            "is_win": is_win,
            "title": title,
            "event_slug": event_slug,
            "end_date": end_date,
            "timestamp": p.get("timestamp", 0),
        })

    # Aggregate
    class_summary = defaultdict(lambda: {
        "count": 0, "buy_usd": 0, "pnl": 0, "wins": 0, "losses": 0,
        "rois": [], "buy_usds": [],
    })
    for c in classifications:
        cl = c["classification"]
        s = class_summary[cl]
        s["count"] += 1
        s["buy_usd"] += c["buy_usd"]
        s["pnl"] += c["realized_pnl"]
        s["rois"].append(c["roi"])
        s["buy_usds"].append(c["buy_usd"])
        if c["is_win"]:
            s["wins"] += 1
        else:
            s["losses"] += 1

    total_positions = len(classifications)
    print(f"\n  Total positions: {total_positions}")
    print(f"  CIDs with merge events (in activity): {len(merge_cids)}")
    print(f"  CIDs with both sides bought: {len(both_sides_cids)}")
    print()

    for cl in ["direction_bet", "merge_arbitrage", "merge_related", "both_sides_no_merge"]:
        s = class_summary.get(cl)
        if not s or s["count"] == 0:
            continue
        n = s["count"]
        pct = n / total_positions * 100
        wr = s["wins"] / n * 100
        avg_roi = sum(s["rois"]) / n * 100
        med_roi = sorted(s["rois"])[n // 2] * 100
        avg_buy = s["buy_usd"] / n
        print(f"  {cl}:")
        print(f"    Count: {n} ({pct:.1f}%)")
        print(f"    Volume: ${s['buy_usd']:,.0f} (avg ${avg_buy:,.0f})")
        print(f"    P&L: ${s['pnl']:,.0f}")
        print(f"    Win rate: {wr:.1f}% ({s['wins']}W / {s['losses']}L)")
        print(f"    Avg ROI: {avg_roi:.1f}% | Median ROI: {med_roi:.1f}%")
        print()

    # Direction bet % vs merge %
    dir_count = class_summary["direction_bet"]["count"]
    merge_count = (class_summary["merge_arbitrage"]["count"]
                   + class_summary["merge_related"]["count"]
                   + class_summary["both_sides_no_merge"]["count"])
    dir_pct = dir_count / total_positions * 100 if total_positions > 0 else 0
    merge_pct = merge_count / total_positions * 100 if total_positions > 0 else 0

    print(f"  KEY FINDING: Direction bets = {dir_count} ({dir_pct:.1f}%), "
          f"Merge/both-sides = {merge_count} ({merge_pct:.1f}%)")

    # --- 2.3 Merge deep dive ---
    print(f"\n  --- 2.3 Merge Arbitrage Deep Dive ---")
    merge_positions = [c for c in classifications if c["classification"] in ("merge_arbitrage", "merge_related")]
    if merge_positions:
        merge_total_pnl = sum(c["realized_pnl"] for c in merge_positions)
        merge_avg_pnl = merge_total_pnl / len(merge_positions)
        merge_total_vol = sum(c["buy_usd"] for c in merge_positions)
        print(f"  Merge positions: {len(merge_positions)}")
        print(f"  Merge total P&L: ${merge_total_pnl:,.0f}")
        print(f"  Merge avg P&L: ${merge_avg_pnl:,.0f}")
        print(f"  Merge total volume: ${merge_total_vol:,.0f}")
        # Top merge P&Ls
        merge_sorted = sorted(merge_positions, key=lambda x: -x["realized_pnl"])
        print(f"\n  Top 5 merge positions by P&L:")
        for m in merge_sorted[:5]:
            print(f"    ${m['realized_pnl']:+,.0f} | {m['title'][:60]} | {m['outcome']}")
        print(f"\n  Bottom 5 merge positions:")
        for m in merge_sorted[-5:]:
            print(f"    ${m['realized_pnl']:+,.0f} | {m['title'][:60]} | {m['outcome']}")

    # --- 2.4 Direction bet deep dive ---
    print(f"\n  --- 2.4 Direction Bet Deep Dive ---")
    dir_positions = [c for c in classifications if c["classification"] == "direction_bet"]
    if dir_positions:
        dir_total_pnl = sum(c["realized_pnl"] for c in dir_positions)
        dir_total_vol = sum(c["buy_usd"] for c in dir_positions)
        dir_wins = sum(1 for c in dir_positions if c["is_win"])
        dir_wr = dir_wins / len(dir_positions) * 100
        dir_avg_roi = sum(c["roi"] for c in dir_positions) / len(dir_positions) * 100
        print(f"  Direction bets: {len(dir_positions)}")
        print(f"  Total P&L: ${dir_total_pnl:,.0f}")
        print(f"  Total volume: ${dir_total_vol:,.0f}")
        print(f"  Win rate: {dir_wr:.1f}%")
        print(f"  Avg ROI: {dir_avg_roi:.1f}%")

        # By price bucket
        price_buckets = defaultdict(lambda: {"count": 0, "pnl": 0, "vol": 0, "wins": 0})
        for c in dir_positions:
            p = c["avg_price"]
            if p < 0.10: b = "0-10c"
            elif p < 0.20: b = "10-20c"
            elif p < 0.30: b = "20-30c"
            elif p < 0.50: b = "30-50c"
            elif p < 0.70: b = "50-70c"
            elif p < 0.82: b = "70-82c"
            elif p < 0.90: b = "82-90c"
            else: b = "90c+"
            price_buckets[b]["count"] += 1
            price_buckets[b]["pnl"] += c["realized_pnl"]
            price_buckets[b]["vol"] += c["buy_usd"]
            if c["is_win"]: price_buckets[b]["wins"] += 1

        print(f"\n  Direction bets by entry price:")
        for b in ["0-10c", "10-20c", "20-30c", "30-50c", "50-70c", "70-82c", "82-90c", "90c+"]:
            s = price_buckets[b]
            if s["count"] == 0:
                continue
            wr = s["wins"] / s["count"] * 100
            roi = s["pnl"] / s["vol"] * 100 if s["vol"] > 0 else 0
            print(f"    {b}: {s['count']} trades, P&L ${s['pnl']:+,.0f}, WR {wr:.0f}%, ROI {roi:.1f}%")

        # Top winners/losers
        dir_sorted = sorted(dir_positions, key=lambda x: -x["realized_pnl"])
        print(f"\n  Top 10 direction bet winners:")
        for c in dir_sorted[:10]:
            print(f"    ${c['realized_pnl']:+,.0f} | {c['avg_price']:.3f} | {c['title'][:55]} | {c['outcome']}")
        print(f"\n  Top 10 direction bet losers:")
        for c in dir_sorted[-10:]:
            print(f"    ${c['realized_pnl']:+,.0f} | {c['avg_price']:.3f} | {c['title'][:55]} | {c['outcome']}")

    # ========================================
    # STEP 3: COPY SIMULATION
    # ========================================
    print("\n" + "=" * 60)
    print("  STEP 3: COPY-STRATEGY SIMULATION")
    print("=" * 60)

    # Bot parameters
    PLAYER_BET_TIERS = [(500, 30), (2000, 25), (5000, 50), (10000, 95)]
    MAX_SLIPPAGE_TIERS = [
        (0.00, 0.10, 0.020), (0.10, 0.20, 0.030), (0.20, 0.30, 0.030),
        (0.30, 0.50, 0.030), (0.50, 0.70, 0.030), (0.70, 0.82, 0.030),
        (0.82, 0.88, 0.015), (0.88, 0.92, 0.010), (0.92, 0.95, 0.006),
        (0.95, 0.97, 0.003), (0.97, 0.99, 0.002),
    ]
    PRICE_BET_MULTIPLIERS = [
        (0.00, 0.15, 0.7), (0.15, 0.50, 1.0), (0.50, 0.70, 0.9),
        (0.70, 0.82, 0.8), (0.82, 0.90, 0.4), (0.90, 0.98, 0.3),
    ]
    LONG_HORIZON_CUTOFF = datetime(2026, 12, 1, tzinfo=timezone.utc)

    CATEGORY_KEYWORDS = {
        "politics": ["trump", "tariff", "doge", "cabinet", "executive order",
            "approval rating", "greenland", "deport", "impeach",
            "pete hegseth", "tulsi", "rfk", "bessent", "gold card",
            "congress", "senate", "democrat", "republican",
            "pardon", "veto", "white house", "presidential"],
        "geopolitics": ["nato", "china", "venezuela", "sanctions", "nuclear",
            "trade deal", "blockade", "taiwan", "ceasefire",
            "north korea", "kim jong"],
        "iran": ["iran", "tehran", "hezbollah", "lebanon", "israel strike", "iranian"],
        "russia_ukraine": ["ukraine", "russia", "putin", "zelensky", "crimea", "donbas", "kherson"],
        "elections": ["election", "vote", "ballot", "primary", "runoff", "governor", "mayor", "referendum"],
        "entertainment": ["super bowl", "oscar", "grammy", "ufc", "nfl", "nba",
            "album", "movie", "chess", "eurovision", "world series",
            "ballon d'or", "premier league"],
        "oil": ["oil", "crude", "brent", "wti", "gold (gc)", "commodity"],
        "tech": ["nvidia", "apple", "google", "meta", "tesla", "microsoft", "amazon"],
    }
    EXCLUDED_KW = ["bitcoin", "btc", "ethereum", "eth", "solana", "sol",
        "crypto", "token", "defi", "nft", "fed rate", "inflation", "cpi",
        "gdp", "unemployment", "interest rate", "fomc", "federal reserve"]
    POLITICS_CATS = {"politics", "geopolitics", "iran", "russia_ukraine", "elections"}

    def get_max_slippage(price):
        for mn, mx, s in MAX_SLIPPAGE_TIERS:
            if mn <= price < mx: return s
        return 0.015

    def get_price_mult(price):
        for mn, mx, m in PRICE_BET_MULTIPLIERS:
            if mn <= price < mx: return m
        return 1.0

    def calc_bet_size(player_invested, entry_price):
        total = sum(inc for min_usd, inc in PLAYER_BET_TIERS if player_invested >= min_usd)
        return round(total * get_price_mult(entry_price), 2)

    def classify_category(text):
        text = text.lower()
        for kw in EXCLUDED_KW:
            if kw in text: return None
        for cat, keywords in CATEGORY_KEYWORDS.items():
            for kw in keywords:
                if kw in text: return cat
        return None

    def is_long_horizon(end_str):
        if not end_str: return False
        try:
            s = str(end_str).replace("Z", "+00:00")
            ed = datetime.fromisoformat(s) if "T" in s else datetime.strptime(s, "%Y-%m-%d")
            if ed.tzinfo is None: ed = ed.replace(tzinfo=timezone.utc)
            return ed >= LONG_HORIZON_CUTOFF
        except: return False

    level_names = {
        0: "No filter (copy everything incl. merge)",
        1: "Filter confirmed merges/both-sides",
        2: "Level 1 + politics/geopolitics only",
        3: "Level 2 + min $1000 Car invested",
    }

    sim_results = {}
    for level in range(4):
        trades = []
        for c in classifications:
            cl = c["classification"]
            buy_usd = c["buy_usd"]
            entry_price = c["avg_price"]
            exit_price = c["exit_price_est"]
            title = c["title"]
            event_slug = c["event_slug"]
            end_date = c["end_date"]

            # Level filters
            if level >= 1 and cl in ("merge_arbitrage", "merge_related", "both_sides_no_merge"):
                continue
            if level >= 2:
                cat = classify_category(title + " " + (event_slug or ""))
                if cat is None or cat not in POLITICS_CATS:
                    continue
            if level >= 3 and buy_usd < 1000:
                continue

            # Price filter (10c - 98c)
            if entry_price < 0.10 or entry_price > 0.98:
                continue

            # Min invested $500
            if buy_usd < 500:
                continue

            # Our entry with slippage
            max_slip = get_max_slippage(entry_price)
            slippage_entry = min(0.01, max_slip)
            our_entry = entry_price + slippage_entry

            # Our exit with 1c slippage
            our_exit = exit_price - 0.01
            if our_exit <= 0:
                our_exit = 0.01

            # Bet size
            bet_size = calc_bet_size(buy_usd, entry_price)

            # Long-horizon multiplier
            if is_long_horizon(end_date):
                bet_size = round(bet_size * 0.2, 2)

            if bet_size < 10:
                continue

            # Shares and P&L
            if our_entry <= 0:
                continue
            our_shares = bet_size / our_entry
            our_pnl = our_shares * (our_exit - our_entry)
            our_roi = (our_exit - our_entry) / our_entry if our_entry > 0 else 0

            cat_label = classify_category(title + " " + (event_slug or "")) or "unknown"

            trades.append({
                "cid": c["cid"],
                "title": title,
                "classification": cl,
                "category": cat_label,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "our_entry": our_entry,
                "our_exit": our_exit,
                "bet_size": bet_size,
                "our_pnl": our_pnl,
                "our_roi": our_roi,
                "car_buy_usd": buy_usd,
                "car_pnl": c["realized_pnl"],
                "car_roi": c["roi"],
                "outcome": c["outcome"],
                "timestamp": c["timestamp"],
            })

        sim_results[level] = trades

    # Print results
    sim_summary = {}
    for level in range(4):
        trades = sim_results[level]
        print(f"\n  --- Level {level}: {level_names[level]} ---")
        if not trades:
            print(f"  NO TRADES passed filters")
            sim_summary[level] = {"n": 0}
            continue

        total_pnl = sum(t["our_pnl"] for t in trades)
        wins = sum(1 for t in trades if t["our_pnl"] > 0)
        losses = len(trades) - wins
        wr = wins / len(trades) * 100
        avg_pnl = total_pnl / len(trades)
        total_invested = sum(t["bet_size"] for t in trades)
        total_roi = total_pnl / total_invested * 100 if total_invested > 0 else 0

        # Max drawdown
        sorted_by_time = sorted(trades, key=lambda x: x.get("timestamp", 0))
        cum = 0; peak = 0; max_dd = 0
        for t in sorted_by_time:
            cum += t["our_pnl"]
            if cum > peak: peak = cum
            dd = peak - cum
            if dd > max_dd: max_dd = dd

        print(f"  Trades: {len(trades)}")
        print(f"  Total P&L: ${total_pnl:+,.2f}")
        print(f"  Win rate: {wr:.1f}% ({wins}W / {losses}L)")
        print(f"  Avg P&L per trade: ${avg_pnl:+,.2f}")
        print(f"  Total invested: ${total_invested:,.0f}")
        print(f"  Total ROI: {total_roi:+.1f}%")
        print(f"  Max drawdown: ${max_dd:,.2f}")

        # Category breakdown
        cat_pnl = defaultdict(lambda: {"n": 0, "pnl": 0})
        for t in trades:
            cat_pnl[t["category"]]["n"] += 1
            cat_pnl[t["category"]]["pnl"] += t["our_pnl"]
        print(f"\n  By category:")
        for cat, s in sorted(cat_pnl.items(), key=lambda x: -x[1]["pnl"]):
            print(f"    {cat}: {s['n']} trades, P&L ${s['pnl']:+,.2f}")

        # Top/bottom
        sorted_trades = sorted(trades, key=lambda x: -x["our_pnl"])
        print(f"\n  Top 5 winners:")
        for t in sorted_trades[:5]:
            print(f"    ${t['our_pnl']:+,.2f} (bet ${t['bet_size']:.0f}) | {t['entry_price']:.3f}->{t['exit_price']:.3f} | {t['title'][:50]}")
        print(f"  Top 5 losers:")
        for t in sorted_trades[-5:]:
            print(f"    ${t['our_pnl']:+,.2f} (bet ${t['bet_size']:.0f}) | {t['entry_price']:.3f}->{t['exit_price']:.3f} | {t['title'][:50]}")

        sim_summary[level] = {
            "n": len(trades), "total_pnl": total_pnl, "wr": wr,
            "avg_pnl": avg_pnl, "total_invested": total_invested,
            "total_roi": total_roi, "max_dd": max_dd,
        }

    # ========================================
    # STEP 4: DENIZZ COMPARISON
    # ========================================
    print("\n" + "=" * 60)
    print("  STEP 4: CAR vs DENIZZ COMPARISON")
    print("=" * 60)

    denizz_path = os.path.join(BASE, "denizz_activity_full.json")
    if os.path.exists(denizz_path):
        with open(denizz_path, "r", encoding="utf-8") as f:
            denizz_rows = json.load(f)
        d_types = defaultdict(int)
        d_vol = defaultdict(float)
        for r in denizz_rows:
            t = r.get("type", "UNKNOWN")
            d_types[t] += 1
            usd = float(r.get("usdcSize", 0) or 0)
            if usd == 0:
                usd = float(r.get("size", 0) or 0) * float(r.get("price", 0) or 0)
            d_vol[t] += usd
        d_cids = set(r.get("conditionId") or r.get("condition_id") or "" for r in denizz_rows)
        d_cids.discard("")
        d_merges = sum(1 for r in denizz_rows if (r.get("type") or "").upper() in ("MERGE", "SPLIT"))

        print(f"\n  {'Metric':<35} {'Car':>15} {'denizz':>15}")
        print(f"  {'-'*35} {'-'*15} {'-'*15}")
        print(f"  {'Activity rows':<35} {len(activity):>15,} {len(denizz_rows):>15,}")
        print(f"  {'Unique markets':<35} {unique_markets:>15,} {len(d_cids):>15,}")
        print(f"  {'Position records':<35} {len(positions_raw):>15,} {'N/A':>15}")
        car_merges = type_counts.get("MERGE", 0) + type_counts.get("SPLIT", 0)
        print(f"  {'Merge/Split events':<35} {car_merges:>15,} {d_merges:>15,}")
        print(f"  {'Lifetime realized P&L':<35} {'$'+f'{total_realized_pnl:,.0f}':>15} {'$447k+':>15}")
        print(f"  {'Merge % of positions':<35} {merge_pct:>14.1f}% {'~0%':>15}")
        print(f"  {'Direction bet %':<35} {dir_pct:>14.1f}% {'~100%':>15}")
    else:
        print("  denizz data not found, skipping comparison")

    # ========================================
    # WRITE REPORT
    # ========================================
    print("\n[STEP 5] Writing report...")

    report_path = "c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot/_analytics/2026-04-10_car-copy-strategy-analysis.md"
    rp = []
    rp.append("# Car Copy-Strategy Analysis")
    rp.append(f"**Date:** 2026-04-10")
    rp.append(f"**EOA Wallet:** `{CAR_EOA}`")
    rp.append(f"**Proxy Wallet:** `{CAR_WALLET}`")
    rp.append(f"**Position records:** {len(positions_raw)} | **Activity rows:** {len(activity)}")
    if len(activity) >= 3500:
        rp.append("**WARNING: Activity data hit 3500-row API cap. Incomplete trade-level data.**")
    if dated_pos:
        rp.append(f"**Position date range:** {pos_earliest.date()} to {pos_latest.date()} ({pos_days} days)")
    if dated_activity:
        rp.append(f"**Activity date range:** {act_earliest.date()} to {act_latest.date()} ({act_days} days)")
    rp.append("")

    rp.append("## 1. General Statistics")
    rp.append("")
    rp.append(f"- **{len(positions_raw)}** position records across **{unique_markets}** unique markets")
    rp.append(f"- **{len(activity)}** activity rows (trade-level events)")
    rp.append(f"- **Lifetime realized P&L: ${total_realized_pnl:,.0f}**")
    rp.append(f"- Avg P&L per position: ${total_realized_pnl / max(1, len(positions_raw)):,.0f}")
    rp.append("")
    rp.append("### Activity by type")
    rp.append("| Type | Count | Volume |")
    rp.append("|------|-------|--------|")
    for t in sorted(type_counts.keys()):
        rp.append(f"| {t} | {type_counts[t]} | ${type_volume[t]:,.0f} |")
    rp.append("")

    rp.append("## 2. Trade Classification")
    rp.append("")
    rp.append("| Classification | Count | % | Volume | P&L | Win Rate | Avg ROI |")
    rp.append("|---------------|-------|---|--------|-----|----------|---------|")
    for cl in ["direction_bet", "merge_arbitrage", "merge_related", "both_sides_no_merge"]:
        s = class_summary.get(cl)
        if not s or s["count"] == 0: continue
        n = s["count"]
        pct = n / total_positions * 100
        wr = s["wins"] / n * 100
        avg_roi = sum(s["rois"]) / n * 100
        rp.append(f"| {cl} | {n} | {pct:.1f}% | ${s['buy_usd']:,.0f} | ${s['pnl']:,.0f} | {wr:.1f}% | {avg_roi:.1f}% |")
    rp.append("")
    rp.append(f"**Direction bets: {dir_count} ({dir_pct:.1f}%) | Merge/both-sides: {merge_count} ({merge_pct:.1f}%)**")
    rp.append("")

    rp.append("## 3. Direction Bet Analysis")
    rp.append("")
    if dir_positions:
        rp.append(f"- Count: {len(dir_positions)}")
        rp.append(f"- Total P&L: ${sum(c['realized_pnl'] for c in dir_positions):,.0f}")
        rp.append(f"- Win rate: {sum(1 for c in dir_positions if c['is_win']) / len(dir_positions) * 100:.1f}%")
        rp.append(f"- Avg ROI: {sum(c['roi'] for c in dir_positions) / len(dir_positions) * 100:.1f}%")
    rp.append("")

    rp.append("## 4. Copy-Strategy Simulation")
    rp.append("")
    rp.append("Simulated with denizz tiers ($30/$55/$105/$200), 1c slippage both sides,")
    rp.append("price filter 10-98c, MIN_INVESTED $500, long-horizon 0.2x.")
    rp.append("")
    rp.append("| Level | Description | Trades | P&L | WR | ROI | Max DD |")
    rp.append("|-------|------------|--------|-----|-----|-----|--------|")
    for level in range(4):
        s = sim_summary[level]
        if s["n"] == 0:
            rp.append(f"| {level} | {level_names[level]} | 0 | - | - | - | - |")
        else:
            rp.append(f"| {level} | {level_names[level]} | {s['n']} | ${s['total_pnl']:+,.0f} | {s['wr']:.1f}% | {s['total_roi']:+.1f}% | ${s['max_dd']:,.0f} |")
    rp.append("")

    # Recommendation
    rp.append("## 5. Recommendation")
    rp.append("")

    best_level = None
    best_pnl = -999999
    for level in range(4):
        s = sim_summary[level]
        if s["n"] > 0 and s.get("total_pnl", -999999) > best_pnl:
            best_pnl = s.get("total_pnl", 0)
            best_level = level

    if best_level is not None and best_pnl > 0:
        s = sim_summary[best_level]
        rp.append(f"### Marginally profitable at Level {best_level}")
        rp.append(f"- P&L: ${s['total_pnl']:+,.0f} over {s['n']} trades")
        rp.append(f"- Win rate: {s['wr']:.1f}%")
        rp.append(f"- ROI: {s['total_roi']:+.1f}%")
        rp.append(f"- Max drawdown: ${s['max_dd']:,.0f}")
        rp.append("")
        rp.append("**Risks:**")
        rp.append(f"- Merge contamination: {merge_pct:.1f}% of Car's positions involve merges/both-sides buying")
        rp.append(f"- The merge-prep filter was disabled (97% false positive rate in backtest)")
        rp.append(f"- Running Car parallel with denizz risks cascade exits on shared markets")
        rp.append(f"- Sample size of {s['n']} trades may not be statistically significant")
        rp.append("")
        rp.append("**Verdict:** Proceed with EXTREME caution. The profit margin is thin and the")
        rp.append("merge-contamination risk remains the #1 failure mode.")
    else:
        rp.append("### NOT PROFITABLE")
        rp.append("")
        if best_level is not None:
            s = sim_summary[best_level]
            rp.append(f"Best result: Level {best_level} ({level_names[best_level]})")
            rp.append(f"- P&L: ${s.get('total_pnl', 0):+,.0f} over {s['n']} trades")
            rp.append(f"- Win rate: {s.get('wr', 0):.1f}%")
        rp.append("")
        rp.append("**Why it fails:**")
        rp.append(f"1. **Merge contamination ({merge_pct:.1f}%):** Large fraction of Car's activity is merge-arbitrage,")
        rp.append(f"   which is inherently non-directional. Copying these buys as direction signals loses money.")
        rp.append(f"2. **Slippage eats edge:** After 1c entry + 1c exit slippage, Car's marginal direction-bet")
        rp.append(f"   edge (if any) disappears.")
        rp.append(f"3. **April 7-9 incident root cause unchanged:** The merge-prep detection filter has 97%")
        rp.append(f"   false positive rate. Without a reliable filter, every merge-prep buy from Car gets")
        rp.append(f"   interpreted as a direction signal.")
        rp.append("")
        rp.append("**Verdict:** Do NOT re-add Car to the copybot.")
        rp.append("denizz is the sole proven alpha source (+$447k lifetime, ~100% directional).")

    if os.path.exists(denizz_path):
        rp.append("")
        rp.append("## 6. Car vs denizz Comparison")
        rp.append("")
        rp.append(f"| Metric | Car | denizz |")
        rp.append(f"|--------|-----|--------|")
        rp.append(f"| Activity rows | {len(activity)} | {len(denizz_rows)} |")
        rp.append(f"| Unique markets | {unique_markets} | {len(d_cids)} |")
        rp.append(f"| Merge events | {car_merges} | {d_merges} |")
        rp.append(f"| Lifetime P&L | ${total_realized_pnl:,.0f} | $447,000+ |")
        rp.append(f"| Merge % | {merge_pct:.1f}% | ~0% |")
        rp.append(f"| Direction % | {dir_pct:.1f}% | ~100% |")
        rp.append(f"| Style | Mixed (direction + merge arb) | Pure directional |")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(rp))
    print(f"  Report: {report_path}")

    # ========================================
    # CONSOLE SUMMARY
    # ========================================
    print("\n" + "=" * 60)
    print("  CONSOLE SUMMARY")
    print("=" * 60)
    print(f"  Car: {len(positions_raw)} positions, {len(activity)} activity rows, {unique_markets} markets")
    if dated_pos:
        print(f"  Period: {pos_earliest.date()} to {pos_latest.date()} ({pos_days} days)")
    print(f"  Lifetime P&L: ${total_realized_pnl:,.0f}")
    print(f"  Direction bets: {dir_count} ({dir_pct:.1f}%)")
    print(f"  Merge/both-sides: {merge_count} ({merge_pct:.1f}%)")
    print()
    print("  Copy simulation (denizz tiers, 1c slippage):")
    for level in range(4):
        s = sim_summary[level]
        if s["n"] == 0:
            print(f"    L{level}: No trades passed filters")
        else:
            print(f"    L{level}: {s['n']} trades, P&L ${s['total_pnl']:+,.2f}, WR {s['wr']:.1f}%, ROI {s['total_roi']:+.1f}%")
    print()
    if best_level is not None and best_pnl > 0:
        s = sim_summary[best_level]
        print(f"  VERDICT: Marginal profit at L{best_level} (${best_pnl:+,.0f}), but {merge_pct:.1f}% merge risk.")
        print(f"  Recommendation: Do NOT re-add without reliable merge filter.")
    else:
        print(f"  VERDICT: NOT PROFITABLE at any filter level.")
        print(f"  Recommendation: Keep Car removed. denizz is the sole alpha source.")
    print("=" * 60)


if __name__ == "__main__":
    main()
