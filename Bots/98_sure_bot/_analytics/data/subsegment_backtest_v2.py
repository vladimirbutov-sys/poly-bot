"""
Subsegment Backtest v2 — 2026-03-25
Updated with 43K+ scanner markets. Classifies by type/subsegment.
Tests: current filters, match-only, and other scenarios.
"""
import json, sys, os, re
from datetime import datetime, timezone
from collections import defaultdict
import statistics

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')

SCANNER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "..", "..", "..", "97_scanner", "scanner_data.json")

print("Loading scanner data...")
with open(SCANNER_PATH, "r", encoding="utf-8") as f:
    sc = json.load(f)

# =====================================================================
# BOT FILTERS (exact copy from 98_sure_bot)
# =====================================================================
THRESHOLD_PATTERNS = [
    r'\bo/u\b', r'\bover\s*/?\s*under\b', r'\bover\b.*\d+', r'\bunder\b.*\d+',
    r'\bmore\s+than\s+\d+', r'\bless\s+than\s+\d+', r'\bat\s+least\s+\d+', r'\bexactly\s+\d+',
    r'\bbetween\s+\d+\s*(and|-)\s*\d+', r'\b\d+\+\s*(points?|goals?|runs?|kills?|maps?)',
    r'\bspread\b', r'\bhandi?cap\b', r'\btotal\s+(points?|goals?|runs?|kills?|maps?|rounds?)',
    r'\btemperature\b', r'\bbe\s+(above|below|between|greater|at\s+least)',
    r'\bdip\s+(to|below)\b', r'\bpump\s+(to|above)\b',
]
TOXIC = [r'\bposts?\b.*\d+-\d+', r'\btweets?\b', r'\bviews\b.*\bmillion\b', r'\bsubscribers\b']
SLOW = [r'\bseason\b', r'\bmost\b', r'\btransit\b']

def is_content_filtered(q):
    q = q.lower()
    for p in THRESHOLD_PATTERNS + TOXIC + SLOW:
        if re.search(p, q):
            return True
    return False

# =====================================================================
# SUBSEGMENT CLASSIFICATION
# =====================================================================
def classify_market(question, category):
    q = question.lower()
    cat = (category or "").lower()

    # Type detection
    is_match = bool(re.search(r'\bwin\b|\bbeat\b|\bdefeat\b|\badvance\b|\bqualif', q))
    is_draw = bool(re.search(r'\bdraw\b|\btie\b', q))
    is_sub_match = bool(re.search(r'\bmap\s*\d|\bgame\s*\d|\bset\s*\d|\bhalf\b|\bperiod\b|\binning\b|\bround\s*\d', q))
    is_threshold = bool(re.search(
        r'\b(above|below|over|under|between|more than|less than|at least|exactly|dip to|pump to)\b'
        r'|\b\d+\+\s*(points?|goals?|runs?|kills?)'
        r'|\bspread\b|\bhandi?cap\b|\btotal\s+(points?|goals?|runs?|kills?)', q))
    is_prop = bool(re.search(
        r'\bscore\s*(first|a|any)\b|\bfirst\s*(goal|blood|point|td)\b'
        r'|\bpenalt(y|ies)\b|\bred\s*card\b|\byellow\s*card\b'
        r'|\bcorners?\b|\baces?\b|\bstrikes?\b|\bhome\s*run\b'
        r'|\bassist\b|\brebound\b|\bblock\b|\bsteals?\b', q))
    is_counting = bool(re.search(
        r'\bhow\s+many\b|\bnumber\s+of\b|\bcount\b|\btimes?\b.*\d+'
        r'|\bearth\s*quake\b|\bviews?\b|\bsubscrib', q))
    is_weather = bool(re.search(r'\btemperature\b|\btemp\b.*\d+.*[°FC]|\bhighest\s+temp|\blowest\s+temp|\bweather\b', q))

    # Sport detection
    is_soccer = cat in ('soccer',) or bool(re.search(r'\bfc\b|\bunited\b|\bcity\b.*fc|\breal\b.*madrid|\bliga\b|\bpremier\s+league\b|\bserie\s+a\b|\bbundesliga\b|\bligue\b|\blaliga\b', q))
    is_esports = cat in ('esports',) or bool(re.search(r'\besports?\b|\bcounter-?strike\b|\bvalorант\b|\bdota\b|\bleague\s+of\s+legends\b|\boverwatch\b', q))
    is_crypto = cat in ('crypto',) or bool(re.search(r'\bbitcoin\b|\bethereum\b|\beth\b|\bbtc\b|\bsolana\b|\bsol\b|\bcrypto\b|\btoken\b|\bcoin\b', q))
    is_politics = cat in ('politics', 'geopolitics')
    is_sports = cat in ('sports_other', 'soccer', 'basketball', 'hockey', 'tennis', 'american_football', 'fighting', 'cricket', 'esports')

    # Determine market_type
    if is_weather:
        market_type = "weather"
    elif is_draw:
        market_type = "draw"
    elif is_sub_match:
        market_type = "sub_match"
    elif is_threshold:
        market_type = "threshold"
    elif is_counting:
        market_type = "counting"
    elif is_prop:
        market_type = "prop"
    elif is_match:
        market_type = "match_outcome"
    else:
        market_type = "other"

    # Determine subsegment
    if is_weather:
        subsegment = "weather"
    elif market_type == "threshold":
        if is_crypto:
            subsegment = "crypto_price"
        elif is_sports or is_soccer or is_esports:
            subsegment = "sports_threshold"
        else:
            subsegment = "other_threshold"
    elif market_type == "match_outcome":
        if is_soccer:
            subsegment = "soccer_match"
        elif is_esports:
            subsegment = "esports_match"
        elif is_sports:
            subsegment = "sports_match"
        elif is_politics:
            subsegment = "election"
        else:
            subsegment = "other_match"
    elif market_type == "prop":
        if is_soccer:
            subsegment = "soccer_prop"
        elif is_esports:
            subsegment = "esports_prop"
        elif is_sports:
            subsegment = "sports_prop"
        else:
            subsegment = "other_prop"
    elif market_type == "counting":
        if bool(re.search(r'earth\s*quake', q)):
            subsegment = "earthquake_count"
        elif bool(re.search(r'views?\b|subscrib', q)):
            subsegment = "social_media_count"
        else:
            subsegment = "other_count"
    elif market_type == "sub_match":
        if is_esports:
            subsegment = "esports_game_map"
        else:
            subsegment = "other_sub_match"
    elif market_type == "draw":
        subsegment = "draw"
    else:  # other
        if is_crypto:
            subsegment = "crypto_other"
        elif is_politics:
            subsegment = "politics_other"
        elif is_esports:
            subsegment = "esports_other"
        elif is_sports:
            subsegment = "sports_other"
        elif bool(re.search(r'\bstock\b|\bindex\b|\bs&p\b|\bnasdaq\b|\bdow\b', q)):
            subsegment = "stock_index"
        elif bool(re.search(r'\btech\b|\bai\b|\bapple\b|\bgoogle\b|\bmicrosoft\b|\bopen\s*ai\b', q)):
            subsegment = "tech_other"
        else:
            subsegment = "uncategorized"

    return market_type, subsegment


def parse_dt(s):
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# =====================================================================
# PREPARE ALL RESOLVED MARKETS (price filter only)
# =====================================================================
print("Preparing resolved markets...")
all_markets = []
for mid, m in sc.get("markets", {}).items():
    res = m.get("resolution")
    if not res or not isinstance(res, dict) or not res.get("closed"):
        continue

    max_p = m.get("max_price_seen", 0) or 0
    cat = (m.get("category", "") or "").lower()
    neg_risk = bool(m.get("neg_risk"))
    question = m.get("question", "")

    # Price filter
    if cat in ("politics", "geopolitics"):
        if max_p < 0.96:
            continue
    else:
        if max_p < 0.975:
            continue
    if max_p > 0.995:
        continue

    ho = m.get("high_outcome", "")
    w = res.get("winner", "")
    if not ho or not w:
        continue

    ed = parse_dt(m.get("end_date", ""))
    fs = parse_dt(m.get("first_seen", ""))
    days_to_end = None
    if ed and fs:
        days_to_end = (ed - fs).total_seconds() / 86400
        if days_to_end < 0:
            days_to_end = None  # past end_date

    rt = m.get("resolve_time_hours")
    liq = m.get("liquidity", 0) or 0
    vol = m.get("volume", 0) or 0

    mtype, subseg = classify_market(question, cat)

    all_markets.append({
        "question": question,
        "neg_risk": neg_risk,
        "days_to_end": days_to_end,
        "resolve_hours": rt if rt and rt > 0 else None,
        "entry_price": min(max_p, 0.995),
        "won": ho == w,
        "category": cat,
        "liquidity": liq,
        "volume": vol,
        "market_type": mtype,
        "subsegment": subseg,
        "content_filtered": is_content_filtered(question),
    })

print(f"Total resolved (price filter): {len(all_markets)}")
wins_all = sum(1 for m in all_markets if m["won"])
losses_all = sum(1 for m in all_markets if not m["won"])
print(f"  W/L: {wins_all}/{losses_all} (WR {wins_all/(wins_all+losses_all)*100:.2f}%)")


# =====================================================================
# ANALYSIS 1: RAW — by type (NO content/vol/liq filters, only price)
# =====================================================================
print("\n" + "=" * 100)
print("ANALYSIS 1: ALL RESOLVED by MARKET TYPE (price filter only)")
print("=" * 100)

types = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0.0, "cost": 0.0, "rh": []})
for m in all_markets:
    t = types[m["market_type"]]
    bet = 4.0 if m["neg_risk"] else 7.5
    if m["won"]:
        t["w"] += 1
        shares = bet / m["entry_price"]
        t["pnl"] += shares - bet
    else:
        t["l"] += 1
        t["pnl"] -= bet
    t["cost"] += bet
    if m["resolve_hours"]:
        t["rh"].append(m["resolve_hours"])

print(f"{'Type':>16} | {'Total':>6} | {'W':>5} | {'L':>4} | {'WR%':>6} | {'LR%':>6} | {'PnL':>9} | {'ROI%':>6} | {'Med Res':>8}")
print("-" * 95)
for name in sorted(types.keys(), key=lambda x: -(types[x]["w"] + types[x]["l"])):
    t = types[name]
    total = t["w"] + t["l"]
    lr = t["l"] / total * 100 if total > 0 else 0
    wr = t["w"] / total * 100 if total > 0 else 0
    roi = t["pnl"] / t["cost"] * 100 if t["cost"] > 0 else 0
    med = f"{statistics.median(t['rh']):.0f}h" if t["rh"] else "n/a"
    print(f"{name:>16} | {total:6d} | {t['w']:5d} | {t['l']:4d} | {wr:5.2f}% | {lr:5.2f}% | ${t['pnl']:+8.2f} | {roi:+5.2f}% | {med:>8}")


# =====================================================================
# ANALYSIS 2: RAW — by subsegment (price filter only)
# =====================================================================
print("\n" + "=" * 100)
print("ANALYSIS 2: ALL RESOLVED by SUBSEGMENT (price filter only)")
print("=" * 100)

subs = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0.0, "cost": 0.0, "rh": [], "losses": []})
for m in all_markets:
    s = subs[m["subsegment"]]
    bet = 4.0 if m["neg_risk"] else 7.5
    if m["won"]:
        s["w"] += 1
        shares = bet / m["entry_price"]
        s["pnl"] += shares - bet
    else:
        s["l"] += 1
        s["pnl"] -= bet
        s["losses"].append(m["question"][:60])
    s["cost"] += bet
    if m["resolve_hours"]:
        s["rh"].append(m["resolve_hours"])

print(f"{'Subsegment':>22} | {'Total':>6} | {'W':>5} | {'L':>4} | {'LR%':>6} | {'PnL':>9} | {'ROI%':>6} | {'Med Res':>8}")
print("-" * 90)
for name in sorted(subs.keys(), key=lambda x: -(subs[x]["w"] + subs[x]["l"])):
    s = subs[name]
    total = s["w"] + s["l"]
    lr = s["l"] / total * 100 if total > 0 else 0
    roi = s["pnl"] / s["cost"] * 100 if s["cost"] > 0 else 0
    med = f"{statistics.median(s['rh']):.0f}h" if s["rh"] else "n/a"
    marker = " <<<" if lr > 1.0 else ""
    print(f"{name:>22} | {total:6d} | {s['w']:5d} | {s['l']:4d} | {lr:5.2f}% | ${s['pnl']:+8.2f} | {roi:+5.2f}% | {med:>8}{marker}")


# =====================================================================
# ANALYSIS 3: WITH BOT FILTERS — by type
# =====================================================================
print("\n" + "=" * 100)
print("ANALYSIS 3: WITH BOT FILTERS (content + vol>=3K + liq>=500 + end_date)")
print("=" * 100)

filtered = []
for m in all_markets:
    if m["content_filtered"]:
        continue
    if m["volume"] < 3000 or m["liquidity"] < 500:
        continue
    # end_date filter: current bot settings
    if m["days_to_end"] is not None:
        if m["neg_risk"]:
            if m["days_to_end"] > 3:
                continue
        else:
            if m["days_to_end"] > 2:
                continue
    else:
        continue  # no end_date = skip (current bot behavior)
    filtered.append(m)

print(f"Markets passing all filters: {len(filtered)}")

ft = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0.0, "cost": 0.0, "rh": []})
for m in filtered:
    t = ft[m["market_type"]]
    bet = 4.0 if m["neg_risk"] else 7.5
    if m["won"]:
        t["w"] += 1
        shares = bet / m["entry_price"]
        t["pnl"] += shares - bet
    else:
        t["l"] += 1
        t["pnl"] -= bet
    t["cost"] += bet
    if m["resolve_hours"]:
        t["rh"].append(m["resolve_hours"])

print(f"\n{'Type':>16} | {'Total':>6} | {'W':>5} | {'L':>4} | {'WR%':>6} | {'LR%':>6} | {'PnL':>9} | {'ROI%':>6} | {'Med Res':>8}")
print("-" * 95)
total_w = total_l = 0
total_pnl = total_cost = 0.0
for name in sorted(ft.keys(), key=lambda x: -(ft[x]["w"] + ft[x]["l"])):
    t = ft[name]
    total = t["w"] + t["l"]
    total_w += t["w"]; total_l += t["l"]
    total_pnl += t["pnl"]; total_cost += t["cost"]
    lr = t["l"] / total * 100 if total > 0 else 0
    wr = t["w"] / total * 100 if total > 0 else 0
    roi = t["pnl"] / t["cost"] * 100 if t["cost"] > 0 else 0
    med = f"{statistics.median(t['rh']):.0f}h" if t["rh"] else "n/a"
    print(f"{name:>16} | {total:6d} | {t['w']:5d} | {t['l']:4d} | {wr:5.2f}% | {lr:5.2f}% | ${t['pnl']:+8.2f} | {roi:+5.2f}% | {med:>8}")
grand_total = total_w + total_l
print(f"{'TOTAL':>16} | {grand_total:6d} | {total_w:5d} | {total_l:4d} | {total_w/grand_total*100:5.2f}% | {total_l/grand_total*100:5.2f}% | ${total_pnl:+8.2f} | {total_pnl/total_cost*100:+5.2f}% |")


# =====================================================================
# ANALYSIS 4: WITH CONTENT FILTER ONLY (no vol/liq/enddate) — by subseg
# =====================================================================
print("\n" + "=" * 100)
print("ANALYSIS 4: CONTENT FILTERED ONLY (no vol/liq/end_date limits)")
print("=" * 100)

content_only = [m for m in all_markets if not m["content_filtered"]]
print(f"Markets after content filter: {len(content_only)}")

cs = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0.0, "cost": 0.0, "rh": [], "losses": []})
for m in content_only:
    s = cs[m["subsegment"]]
    bet = 4.0 if m["neg_risk"] else 7.5
    if m["won"]:
        s["w"] += 1
        shares = bet / m["entry_price"]
        s["pnl"] += shares - bet
    else:
        s["l"] += 1
        s["pnl"] -= bet
        s["losses"].append(m["question"][:60])
    s["cost"] += bet
    if m["resolve_hours"]:
        s["rh"].append(m["resolve_hours"])

total_w = sum(s["w"] for s in cs.values())
total_l = sum(s["l"] for s in cs.values())
print(f"W/L: {total_w}/{total_l} (WR {total_w/(total_w+total_l)*100:.2f}%)")

print(f"\n{'Subsegment':>22} | {'Total':>6} | {'W':>5} | {'L':>4} | {'LR%':>6} | {'PnL':>9} | {'ROI%':>6} | {'Med Res':>8}")
print("-" * 90)
for name in sorted(cs.keys(), key=lambda x: -(cs[x]["w"] + cs[x]["l"])):
    s = cs[name]
    total = s["w"] + s["l"]
    lr = s["l"] / total * 100 if total > 0 else 0
    roi = s["pnl"] / s["cost"] * 100 if s["cost"] > 0 else 0
    med = f"{statistics.median(s['rh']):.0f}h" if s["rh"] else "n/a"
    marker = " <<<" if lr > 1.0 else ""
    print(f"{name:>22} | {total:6d} | {s['w']:5d} | {s['l']:4d} | {lr:5.2f}% | ${s['pnl']:+8.2f} | {roi:+5.2f}% | {med:>8}{marker}")


# =====================================================================
# ANALYSIS 5: SCENARIO COMPARISON
# =====================================================================
print("\n" + "=" * 100)
print("ANALYSIS 5: SCENARIO COMPARISON")
print("=" * 100)

def eval_scenario(markets_list, label):
    w = sum(1 for m in markets_list if m["won"])
    l = sum(1 for m in markets_list if not m["won"])
    t = w + l
    pnl = 0.0
    cost = 0.0
    for m in markets_list:
        bet = 4.0 if m["neg_risk"] else 7.5
        cost += bet
        if m["won"]:
            shares = bet / m["entry_price"]
            pnl += shares - bet
        else:
            pnl -= bet
    lr = l / t * 100 if t > 0 else 0
    roi = pnl / cost * 100 if cost > 0 else 0
    return {"label": label, "n": t, "w": w, "l": l, "lr": lr, "pnl": pnl, "roi": roi}

# Base = content filtered
base = content_only

scenarios = []
# A. Current bot filters (content + vol + liq + enddate)
scenarios.append(eval_scenario(filtered, "A. Current bot config"))
# B. Match outcome only
scenarios.append(eval_scenario([m for m in base if m["market_type"] == "match_outcome"], "B. Match outcome only"))
# C. Match + draw + sub_match
scenarios.append(eval_scenario([m for m in base if m["market_type"] in ("match_outcome", "draw", "sub_match")], "C. Match+draw+sub_match"))
# D. Content filter only (no vol/liq/ed)
scenarios.append(eval_scenario(base, "D. Content filter only"))
# E. Content + vol>=1K (relaxed)
scenarios.append(eval_scenario([m for m in base if m["volume"] >= 1000], "E. Content + vol>=1K"))
# F. Content + vol>=1K + liq>=200
scenarios.append(eval_scenario([m for m in base if m["volume"] >= 1000 and m["liquidity"] >= 200], "F. + liq>=200"))
# G. Content + vol>=1K + liq>=200 + enddate<=5
ed5 = [m for m in base if m["volume"] >= 1000 and m["liquidity"] >= 200 and
       (m["days_to_end"] is not None and m["days_to_end"] <= 5)]
scenarios.append(eval_scenario(ed5, "G. + enddate<=5"))
# H. Content + vol>=1K + liq>=200 + include no_enddate
ed_or_none = [m for m in base if m["volume"] >= 1000 and m["liquidity"] >= 200 and
              (m["days_to_end"] is None or m["days_to_end"] <= 5)]
scenarios.append(eval_scenario(ed_or_none, "H. + allow no_enddate"))
# I. Only sports match outcomes
scenarios.append(eval_scenario([m for m in base if m["subsegment"] in ("soccer_match", "sports_match", "esports_match")],
                               "I. Sports matches only"))
# J. Everything except toxic subsegments
safe = [m for m in base if m["subsegment"] not in ("weather", "earthquake_count", "soccer_prop")]
scenarios.append(eval_scenario(safe, "J. Remove toxic subseg"))

print(f"{'Scenario':>30} | {'Markets':>7} | {'W':>5} | {'L':>4} | {'LR%':>6} | {'PnL':>9} | {'ROI%':>6}")
print("-" * 85)
for s in scenarios:
    print(f"{s['label']:>30} | {s['n']:7d} | {s['w']:5d} | {s['l']:4d} | {s['lr']:5.2f}% | ${s['pnl']:+8.2f} | {s['roi']:+5.2f}%")


# =====================================================================
# ANALYSIS 6: ALL LOSSES — detailed
# =====================================================================
print("\n" + "=" * 100)
print("ANALYSIS 6: ALL LOSSES (content filtered, any vol/liq)")
print("=" * 100)
losses = [m for m in content_only if not m["won"]]
print(f"Total losses: {len(losses)}")

# Group by subsegment
loss_by_sub = defaultdict(list)
for m in losses:
    loss_by_sub[m["subsegment"]].append(m)

print(f"\n{'Subsegment':>22} | {'Losses':>6} | {'Examples'}")
print("-" * 90)
for sub in sorted(loss_by_sub.keys(), key=lambda x: -len(loss_by_sub[x])):
    items = loss_by_sub[sub]
    examples = "; ".join(m["question"][:40] for m in items[:2])
    print(f"{sub:>22} | {len(items):6d} | {examples}")

# =====================================================================
# ANALYSIS 7: COMPARISON WITH 03-23 (delta)
# =====================================================================
print("\n" + "=" * 100)
print("ANALYSIS 7: DELTA vs 2026-03-23 analysis")
print("=" * 100)
print(f"Previous: 38,063 markets total → now: {len(sc.get('markets', {}))} markets")
print(f"Previous resolved (price filter): ~7,331 with vol>=3K → now: {len(all_markets)} (any vol)")
print(f"Previous losses: 36 (with vol>=3K) → now: {losses_all} (any vol)")
print(f"Content-filtered markets: {len(content_only)}")
print(f"  W/L: {sum(1 for m in content_only if m['won'])}/{sum(1 for m in content_only if not m['won'])}")

# =====================================================================
# ANALYSIS 8: category breakdown for content-filtered
# =====================================================================
print("\n" + "=" * 100)
print("ANALYSIS 8: BY POLYMARKET CATEGORY (content filtered)")
print("=" * 100)

cats = defaultdict(lambda: {"w": 0, "l": 0, "pnl": 0.0, "cost": 0.0})
for m in content_only:
    c = cats[m["category"] or "unknown"]
    bet = 4.0 if m["neg_risk"] else 7.5
    c["cost"] += bet
    if m["won"]:
        c["w"] += 1
        c["pnl"] += bet / m["entry_price"] - bet
    else:
        c["l"] += 1
        c["pnl"] -= bet

print(f"{'Category':>20} | {'Total':>6} | {'W':>5} | {'L':>4} | {'LR%':>6} | {'PnL':>9} | {'ROI%':>6}")
print("-" * 75)
for name in sorted(cats.keys(), key=lambda x: -(cats[x]["w"] + cats[x]["l"])):
    c = cats[name]
    total = c["w"] + c["l"]
    lr = c["l"] / total * 100 if total > 0 else 0
    roi = c["pnl"] / c["cost"] * 100 if c["cost"] > 0 else 0
    print(f"{name:>20} | {total:6d} | {c['w']:5d} | {c['l']:4d} | {lr:5.2f}% | ${c['pnl']:+8.2f} | {roi:+5.2f}%")


# =====================================================================
# Save results as JSON
# =====================================================================
output = {
    "date": "2026-03-25",
    "total_scanner_markets": len(sc.get("markets", {})),
    "total_resolved_price_filter": len(all_markets),
    "total_content_filtered": len(content_only),
    "total_bot_filtered": len(filtered),
    "by_type": {},
    "by_subsegment": {},
    "scenarios": [s for s in scenarios],
    "losses": [{"question": m["question"], "subsegment": m["subsegment"], "category": m["category"],
                "neg_risk": m["neg_risk"], "volume": m["volume"], "liquidity": m["liquidity"]}
               for m in losses],
}

for name in types:
    t = types[name]
    total = t["w"] + t["l"]
    output["by_type"][name] = {"n": total, "w": t["w"], "l": t["l"],
                               "lr": t["l"]/total*100 if total else 0,
                               "pnl": round(t["pnl"], 2)}

for name in subs:
    s = subs[name]
    total = s["w"] + s["l"]
    output["by_subsegment"][name] = {"n": total, "w": s["w"], "l": s["l"],
                                     "lr": s["l"]/total*100 if total else 0,
                                     "pnl": round(s["pnl"], 2)}

out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "subsegment_backtest_v2_2026-03-25.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=2, ensure_ascii=False, default=str)
print(f"\nSaved results to: {out_path}")

print("\nDone.")
