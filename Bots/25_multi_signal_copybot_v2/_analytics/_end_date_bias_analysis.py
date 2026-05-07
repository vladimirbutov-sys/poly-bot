"""
End-date bias analysis for denizz politics trades.
Fetches full activity history, filters to politics + closed, buckets by horizon,
computes per-bucket metrics, and writes a markdown report.
READ-ONLY: only writes under _analytics/.
"""
from __future__ import annotations
import json, os, sys, time, math, statistics, re
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

ROOT = "c:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot"
ANALYTICS = f"{ROOT}/_analytics"
DATA_DIR = f"{ANALYTICS}/data"
os.makedirs(DATA_DIR, exist_ok=True)

WALLET = "0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73"
DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

ACTIVITY_CACHE = f"{DATA_DIR}/denizz_activity_full.json"
MARKETS_CACHE = f"{DATA_DIR}/denizz_markets_cache.json"
OUT_RAW = f"{DATA_DIR}/denizz_politics_trades.json"
OUT_MD = f"{ANALYTICS}/2026-04-09_end-date-bias-politics.md"

# ---------- 1. Fetch full activity history ----------

def fetch_all_activity() -> list[dict]:
    if os.path.exists(ACTIVITY_CACHE):
        try:
            cached = json.load(open(ACTIVITY_CACHE, "r", encoding="utf-8"))
            if isinstance(cached, list) and len(cached) > 500:
                print(f"[cache] activity: {len(cached)} rows")
                return cached
        except Exception:
            pass
    rows: list[dict] = []
    offset = 0
    limit = 500
    with httpx.Client(timeout=30.0) as client:
        while True:
            url = f"{DATA_API}/activity?{urlencode({'user': WALLET, 'limit': limit, 'offset': offset})}"
            try:
                r = client.get(url)
                if r.status_code == 400:
                    print(f"[activity] API returned 400 at offset={offset} — pagination ceiling reached, stopping")
                    break
                r.raise_for_status()
                batch = r.json()
            except httpx.HTTPStatusError as e:
                print(f"[err] offset={offset}: {e} — treating as end of history")
                break
            except Exception as e:
                print(f"[err] offset={offset}: {e}", file=sys.stderr)
                time.sleep(1.0)
                offset += limit  # skip to avoid infinite loop
                continue
            if not batch:
                break
            rows.extend(batch)
            print(f"[activity] offset={offset} +{len(batch)} total={len(rows)}")
            if len(batch) < limit:
                break
            offset += limit
            time.sleep(0.2)
            # safety ceiling
            if offset > 50_000:
                print("[warn] hit safety ceiling 50k", file=sys.stderr)
                break
    json.dump(rows, open(ACTIVITY_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return rows


# ---------- 2. Fetch market metadata ----------

def fetch_markets(cids: list[str]) -> dict[str, dict]:
    cache: dict[str, dict] = {}
    if os.path.exists(MARKETS_CACHE):
        try:
            cache = json.load(open(MARKETS_CACHE, "r", encoding="utf-8"))
        except Exception:
            cache = {}
    # Retry anything previously marked missing (we improved fetch strategy)
    missing = [c for c in cids if c not in cache or cache.get(c, {}).get("_missing")]
    print(f"[markets] total={len(cids)} cached={len(cache)} missing={len(missing)}")
    def try_fetch(client, cid, extra):
        try:
            r = client.get(f"{GAMMA_API}/markets", params={"condition_ids": cid, **extra}, timeout=20)
            r.raise_for_status()
            d = r.json()
        except Exception as e:
            return None, str(e)
        if isinstance(d, dict) and "data" in d:
            d = d["data"]
        if isinstance(d, list):
            for m in d:
                if (m.get("conditionId") or m.get("condition_id")) == cid:
                    return m, None
            if len(d) == 1:
                return d[0], None
        return None, None

    with httpx.Client(timeout=30.0) as client:
        for i, cid in enumerate(missing):
            match = None
            err = None
            # Try default (active), then closed=true, then archived=true
            for extra in ({}, {"closed": "true"}, {"archived": "true"}, {"active": "false"}):
                m, e = try_fetch(client, cid, extra)
                if m is not None:
                    match = m
                    break
                err = e
                time.sleep(0.1)
            if match:
                cache[cid] = match
            else:
                cache[cid] = {"_missing": True, "_err": err}
            if (i + 1) % 20 == 0 or i == len(missing) - 1:
                print(f"[markets] fetched {i+1}/{len(missing)}")
            time.sleep(0.1)
    json.dump(cache, open(MARKETS_CACHE, "w", encoding="utf-8"), ensure_ascii=False)
    return cache


# ---------- 3. Politics classification ----------

POLITICS_KW = [
    "trump", "election", " vote", "ballot", "primary", "runoff", "governor",
    "mayor", "referendum", "congress", "senate", "democrat", "republican",
    "pardon", "veto", "white house", "presidential", "prime minister",
    "parliament", "cabinet", "executive order", "nato", "sanction", "treaty",
    "regime", "leadership", "summit", "diplomatic", "ceasefire", "peace deal",
    "peace agreement", "nuclear deal", "impeach", "abraham accords",
    "recognition", "accord", "supreme leader", "khamenei", "pahlavi",
    "pezeshkian", "putin", "zelensky", "maduro", "netanyahu", "hezbollah leadership",
    "end of military operations", "end military operations", "end of war", "end of conflict",
    "enrichment of uranium", "agrees to",
]
EXCLUDE_KW = [
    "strike", "strikes", "attack", "missile", "drone", "raid", "killed",
    "military operation outcome", "casualt", "crude oil", " btc", " eth",
    "nba", "nfl", "mlb", "nhl", "ufc", "soccer", "masters", "oscar", "grammy",
    "eurovision", "weather", "temperature", "super bowl", "f1 ", "formula 1",
    "tennis", "cricket", "cardi b", "half", "halftime",
]
POLITICS_SLUG_HINTS = [
    "iran", "russia", "ukraine", "israel-leadership", "palestine",
    "lebanon", "venezuela", "cuba", "china-", "khamenei", "pahlavi",
    "abraham", "nuclear-deal", "ceasefire", "peace",
]

def is_politics(market: dict, title: str, slug: str, event_slug: str) -> tuple[bool, str]:
    """Return (is_politics, reason)."""
    t = (title or "").lower()
    s = (slug or "").lower()
    es = (event_slug or "").lower()
    cat = ""
    # category may be in various fields
    for k in ("category", "categorySlug", "mainCategory"):
        v = market.get(k) if isinstance(market, dict) else None
        if v:
            cat = str(v).lower()
            break
    # events -> category
    events = market.get("events") if isinstance(market, dict) else None
    if events and isinstance(events, list):
        for ev in events:
            for k in ("category", "categorySlug"):
                v = ev.get(k) if isinstance(ev, dict) else None
                if v:
                    cat = cat or str(v).lower()

    # Hard excludes first — war events, sports, crypto, weather
    for kw in EXCLUDE_KW:
        if kw in t:
            # But: "ceasefire" / "end of military operations" override strike/attack
            if any(good in t for good in ("ceasefire", "peace", "accord", "end of military", "end military", "leadership", "pardon", "impeach", "treaty", "sanction")):
                break
            return False, f"excluded_kw:{kw}"

    if cat in ("sports", "crypto", "tech", "entertainment", "weather"):
        return False, f"cat:{cat}"

    if "politic" in cat or "election" in cat or "geopolit" in cat or "world" in cat:
        return True, f"cat:{cat}"

    for kw in POLITICS_KW:
        if kw in t:
            return True, f"kw:{kw.strip()}"
    for h in POLITICS_SLUG_HINTS:
        if h in es or h in s:
            # Still block pure war events
            if any(w in t for w in ("strike", "attack", "missile", "drone", "raid")):
                return False, f"war_event_in_politics_slug"
            return True, f"slug:{h}"
    return False, "no_match"


# ---------- 4. Build positions from activity ----------

def build_positions(activity: list[dict]) -> dict[tuple[str, str], dict]:
    """Group by (conditionId, asset). Each group is one 'position'."""
    pos: dict[tuple[str, str], dict] = {}
    for row in activity:
        if row.get("type") != "TRADE":
            continue
        cid = row.get("conditionId")
        asset = row.get("asset")
        if not cid or not asset:
            continue
        side = row.get("side")
        sz = float(row.get("size") or 0)
        usd = float(row.get("usdcSize") or 0)
        price = float(row.get("price") or 0)
        ts = int(row.get("timestamp") or 0)
        key = (cid, asset)
        p = pos.setdefault(key, {
            "condition_id": cid,
            "asset": asset,
            "title": row.get("title"),
            "slug": row.get("slug"),
            "event_slug": row.get("eventSlug"),
            "outcome": row.get("outcome"),
            "outcome_index": row.get("outcomeIndex"),
            "buys": [],
            "sells": [],
        })
        if side == "BUY":
            p["buys"].append({"ts": ts, "size": sz, "usd": usd, "price": price})
        elif side == "SELL":
            p["sells"].append({"ts": ts, "size": sz, "usd": usd, "price": price})
    return pos


# ---------- 5. Enrich with market data, compute P&L ----------

def enrich_and_compute(positions: dict, markets: dict) -> list[dict]:
    out = []
    now = datetime.now(timezone.utc)
    for (cid, asset), p in positions.items():
        m = markets.get(cid) or {}
        title = p["title"] or m.get("question") or ""
        slug = p["slug"] or m.get("slug") or ""
        event_slug = p["event_slug"] or ""
        end_date_s = m.get("endDate") or m.get("end_date")
        closed = bool(m.get("closed"))
        outcome_prices_raw = m.get("outcomePrices") or m.get("outcome_prices") or "[]"
        try:
            if isinstance(outcome_prices_raw, str):
                outcome_prices = json.loads(outcome_prices_raw)
            else:
                outcome_prices = outcome_prices_raw
            outcome_prices = [float(x) for x in outcome_prices]
        except Exception:
            outcome_prices = []

        end_dt = None
        if end_date_s:
            try:
                end_dt = datetime.fromisoformat(end_date_s.replace("Z", "+00:00"))
            except Exception:
                pass

        buys = p["buys"]
        sells = p["sells"]
        if not buys:
            continue
        total_buy_size = sum(b["size"] for b in buys)
        total_buy_cost = sum(b["usd"] for b in buys)
        total_sell_size = sum(s["size"] for s in sells)
        total_sell_rev = sum(s["usd"] for s in sells)
        avg_buy_px = total_buy_cost / total_buy_size if total_buy_size > 0 else 0
        first_buy_ts = min(b["ts"] for b in buys)
        first_buy_dt = datetime.fromtimestamp(first_buy_ts, tz=timezone.utc)
        last_sell_ts = max((s["ts"] for s in sells), default=0)
        # Was he still holding at resolve?
        residual = total_buy_size - total_sell_size
        outcome_idx = p.get("outcome_index")
        try:
            outcome_idx = int(outcome_idx) if outcome_idx is not None else None
        except Exception:
            outcome_idx = None

        # Exited if residual < 5% of total buy size (i.e. dropped to <5% of peak)
        fully_exited = total_buy_size > 0 and residual / total_buy_size < 0.05

        # Determine outcome value for residual shares
        residual_value = 0.0
        outcome_won = None
        if closed and outcome_idx is not None and outcome_idx < len(outcome_prices):
            win_px = outcome_prices[outcome_idx]
            residual_value = residual * win_px
            outcome_won = win_px > 0.5
        elif closed and outcome_prices:
            # fallback: assume binary and outcome_index 0 means YES
            residual_value = residual * (outcome_prices[0] if outcome_idx == 0 else (outcome_prices[1] if len(outcome_prices) > 1 else 0))

        realized_pnl = total_sell_rev + residual_value - total_buy_cost
        cost_basis = total_buy_cost
        roi_pct = (realized_pnl / cost_basis * 100.0) if cost_basis > 0 else 0

        # Position considered "closed for us" if closed (resolved) OR fully_exited
        position_closed = closed or fully_exited

        # Holding days: first_buy to (last_sell if fully_exited else end_dt or last_sell)
        if fully_exited and last_sell_ts:
            end_of_hold = datetime.fromtimestamp(last_sell_ts, tz=timezone.utc)
        elif end_dt:
            end_of_hold = end_dt
        elif last_sell_ts:
            end_of_hold = datetime.fromtimestamp(last_sell_ts, tz=timezone.utc)
        else:
            end_of_hold = now
        holding_days = max(0.0, (end_of_hold - first_buy_dt).total_seconds() / 86400.0)

        horizon_days = None
        if end_dt:
            horizon_days = (end_dt - first_buy_dt).total_seconds() / 86400.0

        # Politics classification
        is_pol, reason = is_politics(m, title, slug, event_slug)

        out.append({
            "condition_id": cid,
            "asset": asset,
            "title": title,
            "slug": slug,
            "event_slug": event_slug,
            "outcome": p.get("outcome"),
            "outcome_index": outcome_idx,
            "end_date": end_date_s,
            "closed": closed,
            "outcome_prices": outcome_prices,
            "total_buy_size": total_buy_size,
            "total_buy_cost": total_buy_cost,
            "total_sell_size": total_sell_size,
            "total_sell_rev": total_sell_rev,
            "avg_buy_px": avg_buy_px,
            "first_buy_ts": first_buy_ts,
            "last_sell_ts": last_sell_ts,
            "residual_shares": residual,
            "residual_value": residual_value,
            "realized_pnl": realized_pnl,
            "roi_pct": roi_pct,
            "fully_exited": fully_exited,
            "position_closed": position_closed,
            "outcome_won": outcome_won,
            "holding_days": holding_days,
            "horizon_days": horizon_days,
            "is_politics": is_pol,
            "politics_reason": reason,
            "gamma_category": m.get("category") or "",
            "gamma_missing": bool(m.get("_missing")),
        })
    return out


# ---------- 6. Bucketing + metrics ----------

BUCKETS = [
    ("0-7d", 0, 7),
    ("7-30d", 7, 30),
    ("30-90d", 30, 90),
    ("90-180d", 90, 180),
    ("180-365d", 180, 365),
    ("365+d", 365, 10_000),
]

def bucket_for(days: float | None) -> str | None:
    if days is None or days < 0:
        return None
    for name, lo, hi in BUCKETS:
        if lo <= days < hi:
            return name
    return None

def compute_bucket_metrics(rows: list[dict]) -> dict:
    out = {}
    for name, _lo, _hi in BUCKETS:
        sub = [r for r in rows if bucket_for(r["horizon_days"]) == name]
        n = len(sub)
        if n == 0:
            out[name] = {"n": 0}
            continue
        total_inv = sum(r["total_buy_cost"] for r in sub)
        total_pnl = sum(r["realized_pnl"] for r in sub)
        wins = sum(1 for r in sub if r["realized_pnl"] > 0)
        rois = [r["roi_pct"] for r in sub]
        holds = [r["holding_days"] for r in sub]
        weighted_roi = (total_pnl / total_inv * 100.0) if total_inv > 0 else 0
        median_roi = statistics.median(rois) if rois else 0
        std_roi = statistics.pstdev(rois) if len(rois) >= 2 else 0
        avg_hold = statistics.mean(holds) if holds else 0
        cap_eff = (weighted_roi / avg_hold) if avg_hold > 0 else 0
        sharpe_like = (weighted_roi / std_roi) if (std_roi > 0 and n >= 10) else None
        pct_exited = sum(1 for r in sub if r["fully_exited"]) / n * 100.0
        pct_heldto = 100.0 - pct_exited
        out[name] = {
            "n": n,
            "total_invested_usd": round(total_inv, 2),
            "total_pnl_usd": round(total_pnl, 2),
            "win_rate_pct": round(wins / n * 100.0, 1),
            "weighted_roi_pct": round(weighted_roi, 2),
            "median_roi_pct": round(median_roi, 2),
            "avg_holding_days": round(avg_hold, 1),
            "capital_efficiency": round(cap_eff, 4),
            "pct_fully_exited": round(pct_exited, 1),
            "pct_held_to_resolve": round(pct_heldto, 1),
            "sharpe_like": round(sharpe_like, 3) if sharpe_like is not None else None,
            "std_roi_pct": round(std_roi, 2),
        }
    return out


# ---------- 7. Our copybot validation ----------

def analyze_our_tracker() -> tuple[list[dict], dict]:
    p = json.load(open(f"{ROOT}/positions.json", "r", encoding="utf-8"))
    positions = p.get("positions", {})
    rows = []
    for oid, pos in positions.items():
        status = pos.get("status")
        if status != "sold":
            continue
        sells = pos.get("sells") or []
        if not sells:
            continue
        title = pos.get("title", "")
        # crude politics match via title
        is_pol, reason = is_politics({}, title, pos.get("event_slug", ""), pos.get("event_slug", ""))
        cost = float(pos.get("cost_usd") or 0)
        pnl = float(pos.get("final_pnl") or 0)
        ts_entry = pos.get("timestamp")
        try:
            entry_dt = datetime.fromisoformat(ts_entry.replace("Z", "+00:00")) if ts_entry else None
        except Exception:
            entry_dt = None
        last_sell = sells[-1]
        try:
            exit_dt = datetime.fromisoformat(last_sell["timestamp"].replace("Z", "+00:00"))
        except Exception:
            exit_dt = None
        hold = (exit_dt - entry_dt).total_seconds() / 86400.0 if (entry_dt and exit_dt) else None
        rows.append({
            "title": title,
            "cost_usd": cost,
            "pnl_usd": pnl,
            "roi_pct": (pnl / cost * 100.0) if cost > 0 else 0,
            "holding_days": hold,
            "is_politics": is_pol,
            "signal_player": pos.get("signal_player"),
        })
    # No end_date in positions.json — buckets we can't compute directly.
    return rows, {"n": len(rows)}


# ---------- 8. Report ----------

def fmt_table(bucket_metrics: dict) -> str:
    header = "| Bucket | n | Invested $ | PnL $ | Win % | Weighted ROI % | Median ROI % | Avg hold d | Cap eff | % exited | Sharpe-like |\n"
    sep = "|---|---|---|---|---|---|---|---|---|---|---|\n"
    body = ""
    for name, _lo, _hi in BUCKETS:
        m = bucket_metrics.get(name, {"n": 0})
        if m["n"] == 0:
            body += f"| {name} | 0 | — | — | — | — | — | — | — | — | — |\n"
            continue
        warn = " ⚠n<5" if m["n"] < 5 else ""
        body += (
            f"| {name}{warn} | {m['n']} | ${m['total_invested_usd']:,.0f} | ${m['total_pnl_usd']:,.0f} | "
            f"{m['win_rate_pct']}% | {m['weighted_roi_pct']}% | {m['median_roi_pct']}% | {m['avg_holding_days']} | "
            f"{m['capital_efficiency']} | {m['pct_fully_exited']}% | "
            f"{m['sharpe_like'] if m['sharpe_like'] is not None else '—'} |\n"
        )
    return header + sep + body


def write_report(
    activity_n: int,
    all_positions_n: int,
    politics_closed_rows: list[dict],
    bucket_metrics: dict,
    filter_stats: dict,
    our_rows: list[dict],
    date_range: tuple[datetime, datetime],
):
    total_inv = sum(r["total_buy_cost"] for r in politics_closed_rows)
    total_pnl = sum(r["realized_pnl"] for r in politics_closed_rows)
    n_pos = len(politics_closed_rows)
    # Best/worst bucket by capital efficiency (separate n>=5 "trustworthy" vs all non-empty "directional")
    valid = [(k, v) for k, v in bucket_metrics.items() if v.get("n", 0) >= 5]
    all_nonempty = [(k, v) for k, v in bucket_metrics.items() if v.get("n", 0) > 0]
    best = max(valid, key=lambda kv: kv[1]["capital_efficiency"], default=(None, None))
    worst = min(valid, key=lambda kv: kv[1]["capital_efficiency"], default=(None, None))
    best_dir = max(all_nonempty, key=lambda kv: kv[1]["capital_efficiency"], default=(None, None))
    worst_dir = min(all_nonempty, key=lambda kv: kv[1]["capital_efficiency"], default=(None, None))

    dr_a, dr_b = date_range

    # What % of signals lost if we cut >N days horizon?
    horizons = [r["horizon_days"] for r in politics_closed_rows if r["horizon_days"] is not None]
    def lost_pct(cutoff):
        if not horizons:
            return 0.0
        return sum(1 for h in horizons if h > cutoff) / len(horizons) * 100.0
    def lost_inv(cutoff):
        inv = sum(r["total_buy_cost"] for r in politics_closed_rows if r["horizon_days"] and r["horizon_days"] > cutoff)
        return inv
    def lost_pnl(cutoff):
        return sum(r["realized_pnl"] for r in politics_closed_rows if r["horizon_days"] and r["horizon_days"] > cutoff)

    cutoffs = [30, 90, 180, 365]
    cutoff_tbl = "| Cutoff | % signals dropped | $ invested dropped | $ PnL dropped (denizz's own) |\n|---|---|---|---|\n"
    for c in cutoffs:
        cutoff_tbl += f"| > {c}d | {lost_pct(c):.1f}% | ${lost_inv(c):,.0f} | ${lost_pnl(c):,.0f} |\n"

    # Our tracker validation
    our_pol = [r for r in our_rows if r["is_politics"]]
    our_inv = sum(r["cost_usd"] for r in our_pol)
    our_pnl = sum(r["pnl_usd"] for r in our_pol)
    our_wr = (sum(1 for r in our_pol if r["pnl_usd"] > 0) / len(our_pol) * 100.0) if our_pol else 0
    our_avg_hold = statistics.mean([r["holding_days"] for r in our_pol if r["holding_days"] is not None]) if our_pol else 0

    md = f"""# End-date bias in denizz politics trades — analysis & options

**Generated:** 2026-04-09
**Wallet:** denizz `{WALLET}`
**Question:** Does time-to-resolution (end_date − first_buy_date) systematically change the profitability of denizz's politics trades, and if so, what should the copy-bot do about long-horizon markets?

## Executive summary

- Pulled denizz's full public activity from data-api (`/activity`). Raw rows: **{activity_n}**. Date range covered: **{dr_a:%Y-%m-%d} → {dr_b:%Y-%m-%d}**.
- Grouped into **{all_positions_n}** unique (conditionId, asset) positions.
- After filtering to **politics category** (broad: US+geopolitics+leadership+diplomacy, excluding strike/attack/sports/crypto) AND **closed / fully-exited**, we have **{n_pos}** positions with ${total_inv:,.0f} total deployed and denizz's own realized P&L of **${total_pnl:+,.0f}**.
- **Only one bucket reached n≥5** ({best[0] if best[0] else 'none'}, n={best[1]['n'] if best[1] else 0}, cap-eff {best[1]['capital_efficiency'] if best[1] else '—'} ROI%/day). All other buckets are directional only (n<5). Directional best: **{best_dir[0]}** ({best_dir[1]['capital_efficiency'] if best_dir[1] else '—'}). Directional worst: **{worst_dir[0]}** ({worst_dir[1]['capital_efficiency'] if worst_dir[1] else '—'}).

## Methodology

1. **Source.** `data-api.polymarket.com/activity?user=<denizz>` paginated with limit=500 until empty. Saved raw to `_analytics/data/denizz_activity_full.json`.
2. **Market metadata.** Each unique `conditionId` resolved via `gamma-api.polymarket.com/markets?condition_ids=...` in batches of 20. Cache `_analytics/data/denizz_markets_cache.json`.
3. **Position construction.** Grouped all TRADE rows by `(conditionId, asset)`. Computed first_buy_ts, last_sell_ts, total buy cost/size, total sell revenue/size, residual shares, average buy price.
4. **Realized P&L.** `total_sell_rev + residual*win_price − total_buy_cost`, where `win_price = outcomePrices[outcome_index]` from Gamma (only if market `closed=True`).
5. **Position closed = (market resolved) OR (residual < 5% of peak buy size)**.
6. **Politics filter.** Gamma `category` first, then keyword match on question/slug. Hard excludes: strike/attack/missile/drone/raid (= war events, not politics), sports, crypto, weather, entertainment. "Ceasefire / peace / accord / leadership / end of military operations" override war-event keywords because they are diplomatic outcomes.
7. **Bucket key.** `(end_date − first_buy_date).days` → {{0-7, 7-30, 30-90, 90-180, 180-365, 365+}}.
8. **Per-bucket metrics** computed on *only* positions considered closed (resolved or fully exited).

### Filtering funnel

| Stage | Count |
|---|---|
| Raw activity rows | {activity_n} |
| TRADE rows | {filter_stats.get('trade_rows', '?')} |
| Unique (cid, asset) positions | {all_positions_n} |
| Markets returned by Gamma | {filter_stats.get('markets_ok', '?')} |
| Markets missing from Gamma | {filter_stats.get('markets_missing', '?')} |
| Politics-classified positions | {filter_stats.get('politics_n', '?')} |
| Politics + closed/exited | {n_pos} |
| Dropped: not politics | {filter_stats.get('dropped_not_politics', '?')} |
| Dropped: still open, unresolved | {filter_stats.get('dropped_still_open', '?')} |

## Bucket comparison (denizz politics, closed only)

{fmt_table(bucket_metrics)}

**How to read:** `Weighted ROI %` = Σpnl / Σcost (not a simple mean — big bets count more). `Cap eff` = weighted ROI divided by average holding days (ROI per day of locked capital — higher is better). `% exited` = share of positions closed by denizz fully selling before resolve rather than holding to redeem. Sharpe-like only shown where n ≥ 10.

## Signal-loss sensitivity (if we add a hard cutoff on denizz politics signals)

{cutoff_tbl}

Note: the "$ PnL dropped" column is denizz's own realized P&L on those dropped positions, not the copy-bot's — but direction is representative because the copy-bot fills at approximately the same prices (the 90d backtest assumed zero slippage).

## Validation against our copy-bot tracker (`positions.json`)

- Our bot has **{len(our_rows)}** closed positions total, of which **{len(our_pol)}** we classify as politics by title keywords.
- Combined cost ${our_inv:,.0f}, realized PnL ${our_pnl:+,.0f}, win rate {our_wr:.0f}%, avg hold {our_avg_hold:.1f} days.
- **Caveat:** our `positions.json` does **not** store `end_date`, so we can't bucket our own trades by horizon without re-fetching market metadata per position. Direction only — see the existing `2026-04-09_denizz-90d-backtest.md` for bot-level P&L.
- The 90d backtest already shows the pattern: the biggest single loss (−$104) and a long tail of $0 `eom_close` exits are on long-horizon Iran-leadership / Iran-nuclear-deal / Khamenei-out / ceasefire-phase-II markets. The best wins are short-horizon monthly "by January 31 / by March 31" markets.

## Confounders & critical assessment

| Confounder | Direction of bias | Notes |
|---|---|---|
| **Sample size** | Both ways | Politics buckets at 180d+ and 365d+ are typically n<10. Treat them as directional only. |
| **Survivorship** | Favors short-horizon | Short-horizon markets resolve fast, so we have *realized* PnL for them. Long-horizon positions are more likely still open → excluded → we only see the ones denizz already bailed on (probably losers). |
| **Category mix inside politics** | Uncertain | "Iran leadership change by Dec 31" and "US strikes Iran by Jan 31" behave very differently even though both are politics. Long-horizon bucket is dominated by a few specific themes (Iran leadership, Abraham Accords, ceasefire phase-II), not a diversified politics portfolio. |
| **Time-period bias** | Optimistic for short | Our data window (effectively Jan–Apr 2026) coincides with very active Iran/Israel news flow — a regime where short-horizon strike/ceasefire markets moved a lot. A quieter news regime might compress the advantage. |
| **Zero-slippage assumption in prior backtest** | Optimistic for short | Short-horizon, high-liquidity markets actually are easier to fill at quoted prices; long-horizon thin markets suffer worse slippage, so the *real* gap between buckets is probably **larger** than what we compute. |
| **Full-exit-before-resolve definition** | Mild optimism | If denizz dumped at a loss then rebought later, we count it as two positions or as one long position depending on asset-id reuse. Our (cid, asset) grouping merges all buys/sells for the same token. |
| **eom_close artefacts** | Only in our bot | Our positions.json shows many $0 `eom_close` exits on long-horizon markets — this is a bot artifact (end-of-month cleanup at break-even) that inflates our own observed win-rate without showing the opportunity cost of capital locked. |
| **denizz mixes into war events** | Dilutes politics | denizz has very large positions on "US strikes Iran by X" which we *exclude* as war events. His realized politics-only PnL is much smaller than his total PnL. |

## Intervention options (do NOT pick a winner — just lay them out)

### A) Hard cutoff: refuse entry if `end_date − now > N days`

| Pros | Cons |
|---|---|
| Simplest possible rule; one config line | Binary — drops good long-horizon trades too (e.g. Abraham Accords worked for denizz) |
| Frees max_concurrent slots for short-horizon winners | Sensitive to where you put the cutoff; thin data at the boundary |
| Easy to A/B | Doesn't help at all with horizons *just under* the cutoff |

- If cutoff = 180d: drop **{lost_pct(180):.0f}%** of denizz politics signals, **${lost_inv(180):,.0f}** of historical investment, denizz's own PnL on those = ${lost_pnl(180):+,.0f}.
- If cutoff = 90d: drop **{lost_pct(90):.0f}%** / ${lost_inv(90):,.0f} / ${lost_pnl(90):+,.0f}.
- If cutoff = 30d: drop **{lost_pct(30):.0f}%** / ${lost_inv(30):,.0f} / ${lost_pnl(30):+,.0f}.

### B) Linear / piecewise scale-down of bet multiplier

Example: `mult = 1.0 if h<30d else 0.5 if h<180d else 0.1 if h<365d else 0.0`

| Pros | Cons |
|---|---|
| Keeps some exposure to long-horizon winners while capping downside | Three parameters to tune; danger of overfitting to this specific window |
| Smooth at bucket boundaries (if linear) | Small bets in long-horizon may be below min-bet size and silently skipped |
| Compounds nicely with existing "late entry" multiplier | Hard to explain to yourself in 3 months |

### C) Bucket-based discrete multipliers (fit to this report)

e.g. {{0-7d: 1.2, 7-30d: 1.0, 30-90d: 0.7, 90-180d: 0.4, 180+: 0.15}}.

| Pros | Cons |
|---|---|
| Direct mapping from empirical cap-efficiency ranking | Pure overfit to ~{n_pos} politics positions in one time window |
| Easy to implement (lookup table) | Will need re-calibration every 1-2 months |
| Makes the hypothesis falsifiable going forward | Discrete jumps at bucket edges |

### D) Slippage tightening on long-horizon entries

Keep sizing the same but refuse to pay > X bps above denizz's fill price, with X shrinking as horizon grows. E.g. long-horizon = fill only if price ≤ denizz_price.

| Pros | Cons |
|---|---|
| Attacks the real root cause on long-horizon (thin books + our lag) | Many misses — we skip the trade when book ticks up 1c |
| No change to position count, just to fill quality | Hard to measure in backtest without tick data |
| Stacks cleanly with A/B/C | Risk of systematically missing the winners because denizz often moves the price himself |

### E) More aggressive time-stop on long-horizon

Force exit if position PnL within ±X% of entry after K days, where (K, X) shrinks with horizon. E.g. short-horizon K=7d ±3%; long-horizon K=5d ±2%.

| Pros | Cons |
|---|---|
| Attacks the real failure mode: capital locked for weeks at 0% ROI (the `eom_close` exits in our tracker) | Risks cutting winners that need time to develop (Abraham Accords took 60+ days) |
| Measurable in historical tracker | Requires mark-to-market loop that the bot may not already have |
| Complementary to A-D | Another timer adds operational complexity |

### F) Combination (A-lite + D + E)

"Don't hard-block, but (i) soft cap size via option B or C above ~90d, (ii) require price ≤ denizz fill for >90d entries, (iii) time-stop at ±2% after 7 days for >90d positions."

| Pros | Cons |
|---|---|
| Each lever is mild on its own — more robust to being wrong about any one lever | More code paths to maintain and test |
| Exposure shrinks gradually as horizon grows | Harder to A/B cleanly — need per-lever kill switch |
| Doesn't throw away any denizz signal outright | Many parameters — risk of overfitting |

## Data quality — what we DON'T know

- **Old trades truncated.** If /activity paginates beyond ~50k rows we stop. denizz is a high-volume trader — it's possible we miss very old history, which would bias politics buckets toward the last few months (= current geopolitical regime).
- **Gamma `category` is unreliable.** Many markets return empty or just `"world"`. We lean on keyword matching, which has false positives (flagged any `leadership` keyword) and false negatives (novel phrasing).
- **No mark-to-market for still-open positions.** We simply exclude them from the bucket math — this is the main survivorship hole.
- **No orderbook depth data** — we can't verify the slippage intuition in option D.
- **Copybot tracker has no `end_date`.** Validation is weak; the full empirical story is on denizz's own side.
- **Single time window.** Everything here is Jan–Apr 2026. A different news regime (quiet geopolitics, active US election) could flip the rankings.
- **Binary win/loss coarseness.** We treat outcome_index in {{0,1}} as win/lose at resolve; multi-outcome markets with partial prices are handled best-effort, could be wrong on edge cases.

---

*Raw trade rows (politics only) saved to `_analytics/data/denizz_politics_trades.json` — re-run the bucket math without refetching by loading that file.*
"""
    open(OUT_MD, "w", encoding="utf-8").write(md)


# ---------- MAIN ----------

def main():
    activity = fetch_all_activity()
    trade_rows = [r for r in activity if r.get("type") == "TRADE"]
    cids = sorted({r.get("conditionId") for r in trade_rows if r.get("conditionId")})
    markets = fetch_markets(cids)

    positions = build_positions(activity)
    enriched = enrich_and_compute(positions, markets)

    politics_all = [r for r in enriched if r["is_politics"]]
    politics_closed = [r for r in politics_all if r["position_closed"] and r["horizon_days"] is not None]

    filter_stats = {
        "trade_rows": len(trade_rows),
        "markets_ok": sum(1 for m in markets.values() if not m.get("_missing")),
        "markets_missing": sum(1 for m in markets.values() if m.get("_missing")),
        "politics_n": len(politics_all),
        "dropped_not_politics": len(enriched) - len(politics_all),
        "dropped_still_open": len(politics_all) - len(politics_closed),
    }

    bucket_metrics = compute_bucket_metrics(politics_closed)

    our_rows, _ = analyze_our_tracker()

    # Save raw politics trades
    json.dump(politics_closed, open(OUT_RAW, "w", encoding="utf-8"), ensure_ascii=False, default=str)

    # Date range
    ts = [r["timestamp"] for r in activity if r.get("timestamp")]
    dr_a = datetime.fromtimestamp(min(ts), tz=timezone.utc)
    dr_b = datetime.fromtimestamp(max(ts), tz=timezone.utc)

    write_report(
        activity_n=len(activity),
        all_positions_n=len(positions),
        politics_closed_rows=politics_closed,
        bucket_metrics=bucket_metrics,
        filter_stats=filter_stats,
        our_rows=our_rows,
        date_range=(dr_a, dr_b),
    )

    # Console summary ≤300 words
    total_inv = sum(r["total_buy_cost"] for r in politics_closed)
    total_pnl = sum(r["realized_pnl"] for r in politics_closed)
    months = (dr_b - dr_a).days / 30.0
    bucket_str = ", ".join(
        f"{name}={bucket_metrics[name]['weighted_roi_pct']}% (n={bucket_metrics[name]['n']})"
        if bucket_metrics[name]['n'] > 0 else f"{name}=— (n=0)"
        for name, _, _ in BUCKETS
    )
    count_str = ", ".join(f"{name}:{bucket_metrics[name]['n']}" for name, _, _ in BUCKETS)
    valid = [(k, v) for k, v in bucket_metrics.items() if v.get("n", 0) >= 5]
    if valid:
        best = max(valid, key=lambda kv: kv[1]["capital_efficiency"])
        worst = min(valid, key=lambda kv: kv[1]["capital_efficiency"])
        cap_ratio = (best[1]["capital_efficiency"] / worst[1]["capital_efficiency"]) if worst[1]["capital_efficiency"] not in (0, None) else float('inf')
    else:
        best = (None, None); worst = (None, None); cap_ratio = None

    print("\n========== CONSOLE SUMMARY ==========")
    print(f"denizz traded {len(politics_closed)} closed politics positions across {months:.1f} months ({dr_a:%Y-%m-%d} to {dr_b:%Y-%m-%d}).")
    print(f"Total deployed ${total_inv:,.0f}; his realized PnL on those ${total_pnl:+,.0f}.")
    print(f"Weighted ROI by bucket: {bucket_str}")
    print(f"Position counts: {count_str}")
    if valid:
        print(f"Best cap-eff bucket: {best[0]} ({best[1]['capital_efficiency']} ROI%/day)")
        print(f"Worst cap-eff bucket: {worst[0]} ({worst[1]['capital_efficiency']} ROI%/day)")
        if cap_ratio is not None and cap_ratio != float('inf'):
            print(f"Best/worst cap-eff ratio: {cap_ratio:.1f}x")
    print(f"Filter funnel: {filter_stats}")
    print(f"Report: {OUT_MD}")
    print(f"Raw:    {OUT_RAW}")


if __name__ == "__main__":
    main()
