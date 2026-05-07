"""Deep reconciliation of our open positions vs denizz — with history analysis
per 'only ours' position. Writes JSON + MD report.
"""
import sys, os, json, time, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

BOT = r'C:\Users\Honor\Desktop\Polymarket\Bots\25_multi_signal_copybot_v2'
sys.path.insert(0, BOT)

import httpx
from datetime import datetime, timezone
import tracker
from config import PLAYERS, OUR_WALLET
from safe_sell import get_wallet_balance

DENIZZ = PLAYERS["denizz"]
OUT_JSON = os.path.join(BOT, '_analytics', 'data', 'denizz_deep_recon.json')


def log(msg): print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ============================================================
# 1. Collect all (cid, token) pairs where denizz MIGHT have a position
# ============================================================

def fetch_positions(wallet, limit=500):
    """All /positions entries with minimal filters."""
    r = httpx.get("https://data-api.polymarket.com/positions",
                  params={"user": wallet, "limit": limit}, timeout=30)
    return r.json() if r.status_code == 200 else []


def fetch_activity(wallet, limit=500):
    r = httpx.get("https://data-api.polymarket.com/activity",
                  params={"user": wallet, "limit": limit, "type": "TRADE"},
                  timeout=30)
    return r.json() if r.status_code == 200 else []


log("Step 1: collecting denizz candidates from /positions + /activity")
denizz_positions = fetch_positions(DENIZZ, limit=500)
denizz_activity = fetch_activity(DENIZZ, limit=500)

# Gather unique (cid, token) from both sources
denizz_candidates = {}  # (cid, token) -> {title, event_slug, slug, outcome, ...}
for p in denizz_positions:
    cid = p.get('conditionId')
    tok = str(p.get('asset') or '')
    if not cid or not tok:
        continue
    denizz_candidates[(cid, tok)] = {
        "title": p.get('title'), "outcome": p.get('outcome'),
        "slug": p.get('slug'), "event_slug": p.get('eventSlug'),
        "from_positions_api": True,
    }

for a in denizz_activity:
    cid = a.get('conditionId')
    tok = str(a.get('asset') or '')
    if not cid or not tok:
        continue
    if (cid, tok) not in denizz_candidates:
        denizz_candidates[(cid, tok)] = {
            "title": a.get('title'), "outcome": a.get('outcome'),
            "slug": a.get('slug'), "event_slug": a.get('eventSlug'),
            "from_activity": True,
        }

log(f"Denizz candidates: /positions={len(denizz_positions)}  "
    f"/activity events={len(denizz_activity)}  unique (cid,token)={len(denizz_candidates)}")


# ============================================================
# 2. Collect OUR open positions + all (cid, token) pairs we care about
# ============================================================

log("Step 2: our open positions from tracker")
data = tracker.load()
ours = []
for k, p in (data.get('positions') or {}).items():
    if p.get('status') != 'open':
        continue
    sh = float(p.get('size_shares') or 0)
    if sh < 0.5:
        continue
    ours.append({
        "key": k, "cid": p.get('condition_id'), "token": str(p.get('token_id') or ''),
        "outcome": p.get('outcome'), "title": p.get('title'),
        "event_slug": p.get('event_slug'),
        "size": sh, "cost_usd": float(p.get('cost_usd') or 0),
        "avg_entry": float(p.get('avg_entry') or 0),
        "signal_player": p.get('signal_player'),
    })
log(f"Our open positions: {len(ours)}")


# ============================================================
# 3. On-chain verification for denizz: for EVERY (cid, token) that we're
#    interested in (ours + denizz candidates), read on-chain balance.
# ============================================================

log("Step 3: on-chain verify denizz balances for all relevant tokens")
all_tokens_to_check = set()
for (cid, tok) in denizz_candidates.keys():
    all_tokens_to_check.add(tok)
for our in ours:
    if our['token']:
        all_tokens_to_check.add(our['token'])

denizz_onchain = {}  # token -> balance
count = 0
for tok in all_tokens_to_check:
    try:
        bal = get_wallet_balance(DENIZZ, tok)
        denizz_onchain[tok] = bal
        count += 1
        if count % 20 == 0:
            log(f"  verified {count}/{len(all_tokens_to_check)}...")
    except Exception as e:
        denizz_onchain[tok] = None
        log(f"  ERROR on {tok[:20]}: {e}")

log(f"On-chain verified: {count} tokens")
denizz_holds = {tok: bal for tok, bal in denizz_onchain.items() if bal and bal >= 1.0}
log(f"Denizz currently holds (>=1 sh): {len(denizz_holds)} tokens")


# ============================================================
# 4. Categorize our positions
# ============================================================

log("Step 4: categorize ours")
both_hold = []       # we and denizz both hold
only_ours = []       # we hold, denizz doesn't
for o in ours:
    tok = o['token']
    if tok in denizz_holds:
        o['denizz_sh'] = denizz_holds[tok]
        both_hold.append(o)
    else:
        only_ours.append(o)

log(f"Both hold: {len(both_hold)}  Only ours: {len(only_ours)}")


# ============================================================
# 5. For each ONLY-OURS — denizz history check
# ============================================================

log("Step 5: denizz historical activity per only-ours position")


def denizz_history_on_market(cid):
    """Return list of trades (BUY/SELL) by denizz on this condition_id."""
    try:
        r = httpx.get("https://data-api.polymarket.com/activity",
                      params={"user": DENIZZ, "market": cid, "limit": 200, "type": "TRADE"},
                      timeout=15)
        return r.json() if r.status_code == 200 else []
    except Exception:
        return []


for o in only_ours:
    tok = o['token']
    cid = o['cid']
    history = denizz_history_on_market(cid)
    # Filter to same-token trades only (YES vs NO separation)
    same_token = [t for t in history if str(t.get('asset') or '') == tok]
    total_buy_usd = sum(float(t.get('usdcSize') or 0) for t in same_token if t.get('side') == 'BUY')
    total_sell_usd = sum(float(t.get('usdcSize') or 0) for t in same_token if t.get('side') == 'SELL')
    buys = [t for t in same_token if t.get('side') == 'BUY']
    sells = [t for t in same_token if t.get('side') == 'SELL']

    first_buy_ts = min((int(t['timestamp']) for t in buys), default=None)
    last_sell_ts = max((int(t['timestamp']) for t in sells), default=None)
    last_buy_ts = max((int(t['timestamp']) for t in buys), default=None)

    if not buys and not sells:
        denizz_status = "never_held"
    elif buys and not sells:
        denizz_status = "still_accumulating_or_small"
    elif sells and (last_sell_ts or 0) > (last_buy_ts or 0):
        denizz_status = "held_and_exited"
    elif sells and (last_buy_ts or 0) >= (last_sell_ts or 0):
        denizz_status = "held_partially_sold"
    else:
        denizz_status = "inconclusive"

    o['denizz_history'] = {
        "status": denizz_status,
        "buy_count": len(buys), "sell_count": len(sells),
        "buy_usd": total_buy_usd, "sell_usd": total_sell_usd,
        "first_buy_iso": datetime.fromtimestamp(first_buy_ts, tz=timezone.utc).isoformat() if first_buy_ts else None,
        "last_sell_iso": datetime.fromtimestamp(last_sell_ts, tz=timezone.utc).isoformat() if last_sell_ts else None,
        "onchain_now": denizz_onchain.get(tok, None),
    }
    log(f"  {o['title'][:50]:50s} | {denizz_status:30s} | buys=${total_buy_usd:.0f} sells=${total_sell_usd:.0f}")


# ============================================================
# 6. Resolve Polymarket URLs via gamma-api (batch by cid)
# ============================================================

log("Step 6: resolve polymarket URLs")

def resolve_url(cid):
    try:
        r = httpx.get("https://gamma-api.polymarket.com/markets",
                      params={"condition_ids": cid}, timeout=10)
        d = r.json()
        if isinstance(d, list) and d:
            m = d[0]
            slug = m.get('slug') or ''
            # Also need event slug — query events
            eid = m.get('events', [{}])[0].get('id') if m.get('events') else None
            event_slug = None
            try:
                # Fetch event by id
                if eid:
                    r2 = httpx.get(f"https://gamma-api.polymarket.com/events/{eid}", timeout=10)
                    if r2.status_code == 200:
                        event_slug = r2.json().get('slug')
            except Exception:
                pass
            if event_slug:
                return f"https://polymarket.com/event/{event_slug}/{slug}"
            return f"https://polymarket.com/event/{slug}" if slug else None
    except Exception as e:
        return None
    return None


for o in only_ours + both_hold:
    o['url'] = resolve_url(o['cid']) or (
        f"https://polymarket.com/event/{o['event_slug']}" if o.get('event_slug') else ""
    )


# ============================================================
# 7. Save JSON + write MD report
# ============================================================

os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
with open(OUT_JSON, 'w', encoding='utf-8') as f:
    json.dump({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "denizz_total_onchain_tokens": len(denizz_holds),
        "our_open_positions": len(ours),
        "both_hold": both_hold,
        "only_ours": only_ours,
    }, f, ensure_ascii=False, indent=2)
log(f"JSON saved: {OUT_JSON}")

# Summary categories
cat_never = [o for o in only_ours if o['denizz_history']['status'] == 'never_held']
cat_exited = [o for o in only_ours if o['denizz_history']['status'] == 'held_and_exited']
cat_partial = [o for o in only_ours if o['denizz_history']['status'] == 'held_partially_sold']
cat_other = [o for o in only_ours if o['denizz_history']['status'] not in
             ('never_held', 'held_and_exited', 'held_partially_sold')]

log(f"\nSummary:")
log(f"  Total ours: {len(ours)}")
log(f"  Both hold: {len(both_hold)}")
log(f"  Only ours: {len(only_ours)}")
log(f"    denizz never held:   {len(cat_never)}")
log(f"    denizz held & exited: {len(cat_exited)}")
log(f"    denizz held & partial sold: {len(cat_partial)}")
log(f"    other/inconclusive: {len(cat_other)}")
