"""
Comprehensive backtest: price-bucket win rates by category
Compares non-sports vs sports categories.
Also fetches fresh Polymarket API data for politics/geopolitics.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime

# ─── Config ───
SCANNER_PATH = "C:/Users/Honor/Desktop/Polymarket/Bots/97_scanner/scanner_data.json"
OUTPUT_PATH = "C:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/_analytics/data/backtest_low_price_2026-03-21.json"

NON_SPORTS = {"politics", "geopolitics", "tech", "other"}
SPORTS = {"sports_other", "soccer", "basketball", "esports", "hockey"}

BUCKETS = [
    ("<85",   0.00, 0.85),
    ("85-90", 0.85, 0.90),
    ("90-92", 0.90, 0.92),
    ("92-94", 0.92, 0.94),
    ("94-96", 0.94, 0.96),
    ("96-97", 0.96, 0.97),
    ("97-98", 0.97, 0.98),
    ("98-99", 0.98, 0.99),
    ("99+",   0.99, 2.00),
]

def get_bucket(price):
    for name, lo, hi in BUCKETS:
        if lo <= price < hi:
            return name
    return "<85" if price < 0.85 else "99+"

# ─── Load scanner data ───
print("=" * 80)
print("LOADING SCANNER DATA")
print("=" * 80)
with open(SCANNER_PATH, "r", encoding="utf-8") as f:
    raw = json.load(f)

markets = raw["markets"]
print(f"Total markets in scanner: {len(markets)}")
print(f"Scans done: {raw.get('scans', '?')}")
print()

# ─── Classify each market ───
results = []  # list of dicts

for token_id, m in markets.items():
    cat = m.get("category", "unknown")
    first_price = m.get("first_price", 0)
    max_price = m.get("max_price_seen", 0)
    resolved = m.get("resolved", False)
    resolution = m.get("resolution", None)  # could be "Yes"/"No"/None

    snapshots = m.get("snapshots", [])
    if not snapshots:
        continue

    last_snap = snapshots[-1]
    last_max_price = last_snap.get("max_price", 0)

    # Determine outcome
    # "won" = the high-outcome side resolved YES (price went to ~1.0)
    # "lost" = the high-outcome side dropped (price fell significantly)
    outcome = "unknown"

    if resolved:
        # If explicitly resolved
        if resolution == "Yes" or resolution == m.get("high_outcome"):
            outcome = "won"
        elif resolution == "No" or (resolution and resolution != m.get("high_outcome")):
            outcome = "lost"
        elif last_max_price >= 0.99:
            outcome = "won"
        elif last_max_price < 0.5:
            outcome = "lost"
    else:
        # Not marked resolved yet - use price heuristics
        if max_price >= 0.995 and last_max_price >= 0.99:
            outcome = "won"
        elif last_max_price < 0.5:
            outcome = "lost"
        elif last_max_price < 0.7:
            outcome = "likely_lost"
        # else stays unknown (still active)

    results.append({
        "token_id": token_id,
        "category": cat,
        "first_price": first_price,
        "max_price": max_price,
        "last_price": last_max_price,
        "resolved": resolved,
        "resolution": resolution,
        "outcome": outcome,
        "question": m.get("question", "")[:80],
        "volume": m.get("volume", 0),
        "neg_risk": m.get("neg_risk", False),
    })

print(f"Processed {len(results)} markets with snapshots")

# Count outcomes
from collections import Counter
outcome_counts = Counter(r["outcome"] for r in results)
print(f"Outcome distribution: {dict(outcome_counts)}")
print()

# ─── Build bucket tables ───
def build_table(filtered, label):
    """Build a price-bucket table for a filtered set of markets."""
    table = {}
    for b_name, _, _ in BUCKETS:
        table[b_name] = {"total": 0, "won": 0, "lost": 0, "unknown": 0, "likely_lost": 0}

    for r in filtered:
        bucket = get_bucket(r["first_price"])
        if bucket not in table:
            continue
        table[bucket]["total"] += 1
        if r["outcome"] == "won":
            table[bucket]["won"] += 1
        elif r["outcome"] == "lost":
            table[bucket]["lost"] += 1
        elif r["outcome"] == "likely_lost":
            table[bucket]["likely_lost"] += 1
        else:
            table[bucket]["unknown"] += 1

    print(f"\n{'='*80}")
    print(f"  {label}")
    print(f"  Total markets: {len(filtered)}")
    print(f"{'='*80}")
    print(f"{'Bucket':<10} {'Total':>7} {'Won':>7} {'Lost':>7} {'LikelyL':>8} {'Unknwn':>7} {'WinRate':>8} {'LossRate':>9} {'WR(known)':>10}")
    print("-" * 80)

    grand = {"total": 0, "won": 0, "lost": 0, "unknown": 0, "likely_lost": 0}

    for b_name, _, _ in BUCKETS:
        row = table[b_name]
        t = row["total"]
        w = row["won"]
        lo = row["lost"]
        ll = row["likely_lost"]
        u = row["unknown"]

        grand["total"] += t
        grand["won"] += w
        grand["lost"] += lo
        grand["likely_lost"] += ll
        grand["unknown"] += u

        wr = f"{w/t*100:.1f}%" if t > 0 else "-"
        lr = f"{lo/t*100:.1f}%" if t > 0 else "-"
        known = w + lo + ll
        wrk = f"{w/known*100:.1f}%" if known > 0 else "-"

        print(f"{b_name:<10} {t:>7} {w:>7} {lo:>7} {ll:>8} {u:>7} {wr:>8} {lr:>9} {wrk:>10}")

    t = grand["total"]
    w = grand["won"]
    lo = grand["lost"]
    ll = grand["likely_lost"]
    u = grand["unknown"]
    wr = f"{w/t*100:.1f}%" if t > 0 else "-"
    lr = f"{lo/t*100:.1f}%" if t > 0 else "-"
    known = w + lo + ll
    wrk = f"{w/known*100:.1f}%" if known > 0 else "-"
    print("-" * 80)
    print(f"{'TOTAL':<10} {t:>7} {w:>7} {lo:>7} {ll:>8} {u:>7} {wr:>8} {lr:>9} {wrk:>10}")

    return table

# ─── NON-SPORTS categories (each separately + combined) ───
print("\n" + "#" * 80)
print("#  SECTION 1: NON-SPORTS CATEGORIES")
print("#" * 80)

non_sports_all = [r for r in results if r["category"] in NON_SPORTS]
non_sports_table = build_table(non_sports_all, "ALL NON-SPORTS (politics + geopolitics + tech + other)")

for cat in sorted(NON_SPORTS):
    cat_filtered = [r for r in results if r["category"] == cat]
    if cat_filtered:
        build_table(cat_filtered, f"Category: {cat.upper()}")

# ─── SPORTS categories ───
print("\n" + "#" * 80)
print("#  SECTION 2: SPORTS CATEGORIES")
print("#" * 80)

sports_all = [r for r in results if r["category"] in SPORTS]
sports_table = build_table(sports_all, "ALL SPORTS (sports_other + soccer + basketball + esports + hockey)")

for cat in sorted(SPORTS):
    cat_filtered = [r for r in results if r["category"] == cat]
    if cat_filtered:
        build_table(cat_filtered, f"Category: {cat.upper()}")

# ─── COMPARISON TABLE ───
print("\n" + "#" * 80)
print("#  SECTION 3: SIDE-BY-SIDE COMPARISON (Non-Sports vs Sports)")
print("#" * 80)
print(f"\n{'Bucket':<10} {'NS Total':>9} {'NS Won':>7} {'NS WR%':>8} | {'SP Total':>9} {'SP Won':>7} {'SP WR%':>8} | {'Diff':>6}")
print("-" * 80)

for b_name, _, _ in BUCKETS:
    ns = non_sports_table[b_name]
    sp = sports_table[b_name]
    ns_wr = ns["won"]/ns["total"]*100 if ns["total"] > 0 else 0
    sp_wr = sp["won"]/sp["total"]*100 if sp["total"] > 0 else 0
    diff = ns_wr - sp_wr
    ns_wr_s = f"{ns_wr:.1f}%" if ns["total"] > 0 else "-"
    sp_wr_s = f"{sp_wr:.1f}%" if sp["total"] > 0 else "-"
    diff_s = f"{diff:+.1f}%" if ns["total"] > 0 and sp["total"] > 0 else "-"
    print(f"{b_name:<10} {ns['total']:>9} {ns['won']:>7} {ns_wr_s:>8} | {sp['total']:>9} {sp['won']:>7} {sp_wr_s:>8} | {diff_s:>6}")

# ─── KEY INSIGHT: 85-96 range deep dive ───
print("\n" + "#" * 80)
print("#  SECTION 4: DEEP DIVE — First Price 85c-96c (the 'discount zone')")
print("#" * 80)

for group_name, group_cats in [("NON-SPORTS", NON_SPORTS), ("SPORTS", SPORTS)]:
    discount = [r for r in results if r["category"] in group_cats and 0.85 <= r["first_price"] < 0.96]
    won = [r for r in discount if r["outcome"] == "won"]
    lost = [r for r in discount if r["outcome"] in ("lost", "likely_lost")]
    print(f"\n  {group_name} — Discount Zone (85-96c):")
    print(f"    Total: {len(discount)}")
    print(f"    Won: {len(won)} ({len(won)/len(discount)*100:.1f}%)" if discount else "    Won: 0")
    print(f"    Lost/Likely Lost: {len(lost)} ({len(lost)/len(discount)*100:.1f}%)" if discount else "    Lost: 0")
    if won:
        avg_first = sum(r["first_price"] for r in won) / len(won)
        print(f"    Avg first price of winners: {avg_first:.4f}")
    if lost:
        avg_first_l = sum(r["first_price"] for r in lost) / len(lost)
        print(f"    Avg first price of losers: {avg_first_l:.4f}")

# ─── Neg-risk analysis ───
print("\n" + "#" * 80)
print("#  SECTION 5: NEG-RISK vs STANDARD MARKETS")
print("#" * 80)

for nr_val, nr_label in [(True, "NEG-RISK"), (False, "STANDARD (non-neg-risk)")]:
    filtered = [r for r in results if r.get("neg_risk") == nr_val and r["category"] in NON_SPORTS]
    if filtered:
        build_table(filtered, f"{nr_label} — Non-Sports Only")

# ─── SECTION 6: Polymarket API — fresh resolved data ───
print("\n" + "#" * 80)
print("#  SECTION 6: FRESH DATA FROM POLYMARKET API (closed markets)")
print("#" * 80)

api_results = {}

for tag in ["politics", "geopolitics"]:
    url = f"https://gamma-api.polymarket.com/markets?closed=true&limit=100&tag={tag}"
    print(f"\nFetching: {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            api_data = json.loads(resp.read().decode("utf-8"))

        print(f"  Got {len(api_data)} markets for tag={tag}")

        # Analyze outcomes
        bucket_stats = defaultdict(lambda: {"total": 0, "won": 0, "lost": 0})

        for mkt in api_data:
            # Each market may have outcomePrices
            try:
                prices_str = mkt.get("outcomePrices", "[]")
                if isinstance(prices_str, str):
                    prices = json.loads(prices_str)
                else:
                    prices = prices_str
                prices = [float(p) for p in prices]
            except:
                continue

            if not prices:
                continue

            max_p = max(prices)
            resolved = mkt.get("closed", False)
            winner = mkt.get("winner", None)  # could be outcome index

            bucket = get_bucket(max_p)
            bucket_stats[bucket]["total"] += 1

            # Check resolution
            if resolved:
                # If any outcome price is >= 0.99, that outcome likely won
                if max_p >= 0.99:
                    bucket_stats[bucket]["won"] += 1
                elif max_p < 0.5:
                    bucket_stats[bucket]["lost"] += 1

        print(f"\n  {'Bucket':<10} {'Total':>7} {'Won':>7} {'WinRate':>8}")
        print(f"  {'-'*40}")
        for b_name, _, _ in BUCKETS:
            row = bucket_stats.get(b_name, {"total": 0, "won": 0, "lost": 0})
            t = row["total"]
            w = row["won"]
            wr = f"{w/t*100:.1f}%" if t > 0 else "-"
            print(f"  {b_name:<10} {t:>7} {w:>7} {wr:>8}")

        api_results[tag] = dict(bucket_stats)

    except Exception as e:
        print(f"  ERROR fetching {tag}: {e}")
        api_results[tag] = {"error": str(e)}

# ─── SECTION 7: Volume-weighted analysis ───
print("\n" + "#" * 80)
print("#  SECTION 7: HIGH-VOLUME MARKETS ONLY (volume > $10k)")
print("#" * 80)

high_vol = [r for r in results if r["volume"] >= 10000 and r["category"] in NON_SPORTS]
build_table(high_vol, "NON-SPORTS, Volume > $10,000")

high_vol_sports = [r for r in results if r["volume"] >= 10000 and r["category"] in SPORTS]
build_table(high_vol_sports, "SPORTS, Volume > $10,000")

# ─── SECTION 8: Summary stats ───
print("\n" + "#" * 80)
print("#  SECTION 8: EXECUTIVE SUMMARY")
print("#" * 80)

for label, cats in [("Non-Sports", NON_SPORTS), ("Sports", SPORTS)]:
    group = [r for r in results if r["category"] in cats]
    resolved_group = [r for r in group if r["outcome"] in ("won", "lost", "likely_lost")]
    won_group = [r for r in group if r["outcome"] == "won"]

    print(f"\n  {label}:")
    print(f"    Total markets tracked: {len(group)}")
    print(f"    With known outcome: {len(resolved_group)}")
    print(f"    Won (went to 99%+): {len(won_group)}")
    if resolved_group:
        print(f"    Overall win rate (known): {len(won_group)/len(resolved_group)*100:.1f}%")

    # Best buckets
    print(f"    Best entry points (by win rate among known outcomes, min 10 markets):")
    for b_name, lo, hi in BUCKETS:
        in_bucket = [r for r in group if lo <= r["first_price"] < hi and r["outcome"] in ("won", "lost", "likely_lost")]
        won_b = [r for r in in_bucket if r["outcome"] == "won"]
        if len(in_bucket) >= 10:
            print(f"      {b_name}: {len(won_b)}/{len(in_bucket)} = {len(won_b)/len(in_bucket)*100:.1f}%")

# ─── Save output ───
print("\n" + "=" * 80)
print("SAVING RESULTS")
print("=" * 80)

output = {
    "generated": datetime.now().isoformat(),
    "scanner_markets_total": len(markets),
    "processed_markets": len(results),
    "outcome_distribution": dict(outcome_counts),
    "non_sports_table": {},
    "sports_table": {},
    "api_results": {},
    "summary": {}
}

# Convert tables to serializable format
for b_name, _, _ in BUCKETS:
    output["non_sports_table"][b_name] = non_sports_table[b_name]
    output["sports_table"][b_name] = sports_table[b_name]

output["api_results"] = api_results

# Summary for each category
for cat in sorted(NON_SPORTS | SPORTS):
    cat_data = [r for r in results if r["category"] == cat]
    known = [r for r in cat_data if r["outcome"] in ("won", "lost", "likely_lost")]
    won = [r for r in cat_data if r["outcome"] == "won"]
    output["summary"][cat] = {
        "total": len(cat_data),
        "known_outcome": len(known),
        "won": len(won),
        "win_rate": round(len(won)/len(known)*100, 2) if known else None
    }

os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False, default=str)

print(f"Results saved to: {OUTPUT_PATH}")
print("\nDONE.")
