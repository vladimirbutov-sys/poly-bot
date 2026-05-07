"""Snapshot: open Iran positions (on-chain balanceOf) + live prices + candidate gaps."""
import sys, io, json, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import tracker, filters
from safe_sell import get_wallet_balance
from config import OUR_WALLET
import httpx

IRAN_KEYWORDS = [
    "iran", "hormuz", "uranium", "khamenei", "pahlavi", "hezbollah",
    "litani", "lebanon", "enrich", "regime", "nuclear deal",
    "israel x hezbollah", "france", "uk", "germany strike",
    "military operations against iran"
]

def is_iran(title, slug):
    t = (title or "").lower() + " " + (slug or "").lower()
    return any(k in t for k in IRAN_KEYWORDS)

data = tracker.load()
positions = data.get("positions") or {}

# Group open by (cid, token_id, outcome) — sum shares and cost (since tracker may split)
open_groups = {}
for key, p in positions.items():
    if p.get("status") != "open":
        continue
    if not is_iran(p.get("title", ""), p.get("event_slug", "")):
        continue
    tok = p.get("token_id")
    cid = p.get("condition_id")
    side = p.get("outcome")
    title = p.get("title")
    slug = p.get("event_slug")
    g = open_groups.setdefault((cid, tok, side), {"title": title, "slug": slug, "shares": 0.0, "cost": 0.0, "avg_entry": 0.0})
    g["shares"] += float(p.get("size_shares") or 0)
    g["cost"] += float(p.get("cost_usd") or 0)

print("=" * 100)
print("OUR OPEN IRAN POSITIONS (tracker -> on-chain -> live)")
print("=" * 100)
print(f"{'Title':60s} {'Side':5s} {'Track':>9s} {'Chain':>9s} {'Cost$':>8s} {'Bid':>6s} {'Ask':>6s} {'Mid':>6s} {'MtM$':>8s}")
print("-" * 130)

total_cost = 0.0
total_mtm = 0.0
rows = []
for (cid, tok, side), g in open_groups.items():
    onchain = get_wallet_balance(OUR_WALLET, tok)
    bid, ask = filters.get_orderbook_prices(tok)
    mid = (bid + ask) / 2 if (bid and ask) else (bid or ask or 0.0)
    shares_use = onchain if onchain > 0 else g["shares"]
    mtm = shares_use * mid
    total_cost += g["cost"]
    total_mtm += mtm
    title = (g["title"] or "")[:58]
    print(f"{title:60s} {side:5s} {g['shares']:9.2f} {onchain:9.2f} {g['cost']:8.2f} {bid:6.3f} {ask:6.3f} {mid:6.3f} {mtm:8.2f}")
    rows.append({
        "cid": cid, "token_id": tok, "side": side, "title": g["title"], "slug": g["slug"],
        "tracker_shares": g["shares"], "onchain_shares": onchain, "cost_usd": g["cost"],
        "bid": bid, "ask": ask, "mid": mid, "mtm": mtm
    })

print("-" * 130)
print(f"TOTAL COST: ${total_cost:.2f}   TOTAL MtM: ${total_mtm:.2f}   UNREAL: ${total_mtm-total_cost:+.2f}")

# ----- candidate gap markets (from BRAIN report) -----
# Fetch live prices and deadlines from Gamma API
GAMMA = "https://gamma-api.polymarket.com/markets"

candidate_slugs = [
    ("will-the-us-invade-iran-before-2027", "NO"),
    ("will-france-uk-or-germany-strike-iran-by-june-30", "NO"),
    ("us-obtains-iranian-enriched-uranium-by-december-31", "NO"),
    ("will-the-iranian-regime-fall-by-the-end-of-2026", "NO"),
    ("will-reza-pahlavi-enter-iran-by-december-31", "NO"),
    ("will-reza-pahlavi-enter-iran-by-june-30", "NO"),
    ("iran-leadership-change-by-june-30", "NO"),
    ("iran-leadership-change-by-december-31", "NO"),
    ("iran-coup-attempt-by-june-30", "NO"),
    ("us-iran-nuclear-deal-before-2027", "NO"),
    ("iran-agrees-to-surrender-enriched-uranium-stockpile-by-december-31-2026", "NO"),
    ("israel-withdraws-from-lebanon-by-may-31-2026", "NO"),
    ("israeli-forces-cross-the-litani-river-by-june-30", "NO"),
    ("will-mojtaba-khamenei-be-head-of-state-in-iran-end-of-2026", "YES"),
    ("trump-announces-end-of-military-operations-against-iran-by-april-21st", "NO"),
]

print("\n" + "=" * 100)
print("CANDIDATE GAP MARKETS (live CLOB + deadlines)")
print("=" * 100)
print(f"{'Slug':60s} {'Side':4s} {'Bid':>6s} {'Ask':>6s} {'Mid':>6s} {'Deadline':12s} {'Active':6s}")
print("-" * 110)

def fetch_market(slug):
    try:
        with httpx.Client(timeout=15) as c:
            r = c.get(GAMMA, params={"slug": slug})
            r.raise_for_status()
            ms = r.json()
            if not ms:
                return None
            return ms[0] if isinstance(ms, list) else ms
    except Exception as e:
        return {"error": str(e)}

cand_rows = []
for slug, side in candidate_slugs:
    m = fetch_market(slug)
    if not m or (isinstance(m, dict) and m.get("error")):
        print(f"{slug[:58]:60s} {side:4s}   (fetch error)")
        continue
    # outcome tokens
    tokens = m.get("clobTokenIds") or m.get("clob_token_ids")
    if isinstance(tokens, str):
        try:
            tokens = json.loads(tokens)
        except Exception:
            tokens = None
    if not tokens:
        print(f"{slug[:58]:60s} {side:4s}   (no clob tokens)")
        continue
    outcomes = m.get("outcomes")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except Exception:
            outcomes = ["Yes", "No"]
    idx = 0 if side.upper() == "YES" else 1
    try:
        token_id = str(tokens[idx])
    except Exception:
        print(f"{slug[:58]:60s} {side:4s}   (token index err)")
        continue
    bid, ask = filters.get_orderbook_prices(token_id)
    mid = (bid + ask) / 2 if (bid and ask) else (bid or ask or 0.0)
    end_date = m.get("endDate") or m.get("end_date_iso") or m.get("endDateIso") or ""
    active = m.get("active", "") and not m.get("closed", False)
    end_short = (end_date or "")[:10]
    print(f"{slug[:58]:60s} {side:4s} {bid:6.3f} {ask:6.3f} {mid:6.3f} {end_short:12s} {str(active)[:6]:6s}")
    cand_rows.append({
        "slug": slug, "side": side, "token_id": token_id, "bid": bid, "ask": ask, "mid": mid,
        "end_date": end_date, "active": active, "condition_id": m.get("conditionId") or m.get("condition_id")
    })

out = {"open_positions": rows, "candidates": cand_rows, "total_cost": total_cost, "total_mtm": total_mtm}
outpath = os.path.join(os.path.dirname(__file__), "_analytics", "_snapshot_2026-04-21.json")
os.makedirs(os.path.dirname(outpath), exist_ok=True)
with open(outpath, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2)
print(f"\nSaved -> {outpath}")
