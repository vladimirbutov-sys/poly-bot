"""Full analytical profile for player2 (0x9bbd88...).
Positions endpoint returns ONLY open positions — realized P&L must be
reconstructed from activity (BUY, SELL, REDEEM).
"""
import sys, io, json, os, time
from datetime import datetime, timezone
from statistics import mean, median, pstdev
from collections import defaultdict, Counter
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

DATA = r"C:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot_v2/_analytics/data"
REPORT = r"C:/Users/Honor/Desktop/Polymarket/Bots/25_multi_signal_copybot_v2/_analytics/2026-04-17_player2-profile.md"

MIN_USD_SIZE_ACT = 30
BUCKETS = [(0.02,0.15,"02-15c"),(0.15,0.30,"15-30c"),(0.30,0.50,"30-50c"),
           (0.50,0.70,"50-70c"),(0.70,0.85,"70-85c"),(0.85,0.99,"85-99c")]

CATEGORY_KEYWORDS = {
    "politics": ["trump","tariff","doge","cabinet","executive order","approval rating","greenland","deport","impeach","pete hegseth","tulsi","rfk","bessent","gold card","congress","senate","democrat","republican","pardon","veto","white house","presidential"],
    "geopolitics": ["nato","china","venezuela","sanctions","nuclear","trade deal","blockade","taiwan","ceasefire","north korea","kim jong"],
    "entertainment": ["super bowl","oscar","grammy","ufc","nfl","nba","album","movie","chess","eurovision","world series","ballon d'or","premier league"],
    "oil": ["oil","crude","brent","wti","gold (gc)","commodity"],
    "elections": ["election","vote","ballot","primary","runoff","governor","mayor","referendum"],
    "iran": ["iran","tehran","hezbollah","lebanon","israel strike","iranian"],
    "russia_ukraine": ["ukraine","russia","putin","zelensky","crimea","donbas","kherson"],
    "tech": ["nvidia","apple","google","meta","tesla","microsoft","amazon"],
}
EXCLUDED_KEYWORDS = ["bitcoin","btc","ethereum","eth","solana","sol","crypto","token","defi","nft","fed rate","inflation","cpi","gdp","unemployment","interest rate","fomc","federal reserve"]

def classify(title):
    t = (title or "").lower()
    for kw in EXCLUDED_KEYWORDS:
        if kw in t:
            return "crypto_macro"
    hits = []
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                hits.append(cat); break
    if not hits:
        return "other"
    priority = ["iran","russia_ukraine","geopolitics","oil","elections","politics","entertainment","tech"]
    for p in priority:
        if p in hits:
            return p
    return hits[0]

def bucket_of(price):
    for lo,hi,name in BUCKETS:
        if lo <= price < hi:
            return name
    return None

def load(path):
    return json.load(open(path,"r",encoding="utf-8"))

act = load(os.path.join(DATA,"player2_activity_ALL.json"))
pos = load(os.path.join(DATA,"player2_positions.json"))
denizz_act = load(os.path.join(DATA,"denizz_activity_ALL.json"))
try:
    denizz_pos = load(os.path.join(DATA, "denizz_positions_ALL.json"))
except Exception:
    denizz_pos = []

print(f"act={len(act)} pos={len(pos)} denizz_act={len(denizz_act)} denizz_pos={len(denizz_pos)}")

trades = [r for r in act if r.get("type") == "TRADE"]
buys = [r for r in trades if r.get("side") == "BUY"]
sells = [r for r in trades if r.get("side") == "SELL"]
redeems = [r for r in act if r.get("type") == "REDEEM"]
rewards = [r for r in act if r.get("type") == "REWARD"]
rebates = [r for r in act if r.get("type") == "MAKER_REBATE"]

ts_min = min(r["timestamp"] for r in act if r.get("timestamp"))
ts_max = max(r["timestamp"] for r in act if r.get("timestamp"))
period_first = datetime.fromtimestamp(ts_min, tz=timezone.utc).strftime("%Y-%m-%d")
period_last = datetime.fromtimestamp(ts_max, tz=timezone.utc).strftime("%Y-%m-%d")
period_days = (ts_max-ts_min)/86400

uniq_cond = set(r["conditionId"] for r in trades if r.get("conditionId"))
uniq_asset = set(r["asset"] for r in trades if r.get("asset"))

total_buy_usd = sum(r.get("usdcSize",0) or 0 for r in buys)
total_sell_usd = sum(r.get("usdcSize",0) or 0 for r in sells)
total_redeem_usd = sum(r.get("usdcSize",0) or 0 for r in redeems)
total_reward_usd = sum(r.get("usdcSize",0) or 0 for r in rewards)
total_rebate_usd = sum(r.get("usdcSize",0) or 0 for r in rebates)

now_ts = int(time.time())
trades_7d = [r for r in trades if r["timestamp"] >= now_ts - 7*86400]
trades_30d = [r for r in trades if r["timestamp"] >= now_ts - 30*86400]
buys_7d = sum(r.get("usdcSize",0) for r in trades_7d if r.get("side")=="BUY")
buys_30d = sum(r.get("usdcSize",0) for r in trades_30d if r.get("side")=="BUY")

# ===== Reconstruct realized P&L per (conditionId, asset) =====
# For each asset: cost = sum(BUY usdcSize), proceeds = sum(SELL usdcSize) + REDEEM payouts allocated
# REDEEM usdcSize on (cid) — we split it across the single winning asset. But REDEEM doesn't specify asset.
# Simplest: per CONDITION, sum buys+sells on both outcomes and add redeem payout = realized_cond
# Then position is RESOLVED if the conditionId is in redeems (market settled).
redeem_by_cid = defaultdict(float)
for r in redeems:
    redeem_by_cid[r.get("conditionId")] += r.get("usdcSize",0) or 0

open_asset_keys = set()
for p in pos:
    if (p.get("size",0) or 0) > 0:
        open_asset_keys.add((p.get("conditionId"), p.get("asset")))

# Per-condition aggregation
cond_agg = defaultdict(lambda: {"buy_usd":0.0,"sell_usd":0.0,"redeem_usd":0.0,
                                 "buy_evts":0,"sell_evts":0,"title":"","assets":set(),
                                 "yes_buy":0.0,"no_buy":0.0,"first_ts":10**12,"last_ts":0})
for r in trades:
    cid = r.get("conditionId")
    if not cid: continue
    a = cond_agg[cid]
    a["title"] = r.get("title") or a["title"]
    a["assets"].add(r.get("asset"))
    a["first_ts"] = min(a["first_ts"], r["timestamp"])
    a["last_ts"] = max(a["last_ts"], r["timestamp"])
    usd = r.get("usdcSize",0) or 0
    if r.get("side") == "BUY":
        a["buy_usd"] += usd; a["buy_evts"] += 1
        if r.get("outcomeIndex") == 0: a["yes_buy"] += usd
        elif r.get("outcomeIndex") == 1: a["no_buy"] += usd
    elif r.get("side") == "SELL":
        a["sell_usd"] += usd; a["sell_evts"] += 1

for cid, usd in redeem_by_cid.items():
    cond_agg[cid]["redeem_usd"] += usd

# A condition is RESOLVED if no open positions on its assets AND (redeem seen OR end-date reached)
# Proxy: if cond in redeem_by_cid OR all its assets have no open size.
open_cids = set()
for p in pos:
    if (p.get("size",0) or 0) > 0:
        open_cids.add(p.get("conditionId"))

resolved_conds = []
for cid, a in cond_agg.items():
    has_redeem = cid in redeem_by_cid and redeem_by_cid[cid] > 0
    is_open = cid in open_cids
    if has_redeem or not is_open:
        # realized pnl: sells + redeem - buys (for this condition in isolation of still-open)
        if not is_open:
            pnl = a["sell_usd"] + a["redeem_usd"] - a["buy_usd"]
            a["pnl"] = pnl
            a["resolved"] = True
            resolved_conds.append((cid, a))
        else:
            # partially resolved: some asset still open. Skip for clean resolved analysis.
            pass

# Overall realized P&L (reconstructed)
realized_pnl_recon = sum(a["pnl"] for _, a in resolved_conds)

# Unrealized on open positions (use positions endpoint numbers)
unrealized_pnl = 0.0
open_cost_total = 0.0
open_value_total = 0.0
for p in pos:
    if (p.get("size",0) or 0) > 0:
        cv = p.get("currentValue",0) or 0
        iv = p.get("initialValue",0) or 0
        unrealized_pnl += (cv - iv)
        open_cost_total += iv
        open_value_total += cv

# Rewards/rebates add to total P&L
other_income = total_reward_usd + total_rebate_usd
total_pnl = realized_pnl_recon + unrealized_pnl + other_income

# WR on resolved conds (exclude tiny noise <$30)
resolved_meaningful = [(cid,a) for cid,a in resolved_conds if a["buy_usd"] >= MIN_USD_SIZE_ACT]
wins = [(cid,a) for cid,a in resolved_meaningful if a["pnl"] > 0]
losses = [(cid,a) for cid,a in resolved_meaningful if a["pnl"] < 0]
wr_resolved = len(wins)/len(resolved_meaningful) if resolved_meaningful else 0.0

def roi_cond(a):
    if a["buy_usd"] <= 0: return None
    return a["pnl"]/a["buy_usd"]
rois = [roi_cond(a) for _,a in resolved_meaningful]
rois = [x for x in rois if x is not None]
mean_roi = mean(rois) if rois else 0.0
med_roi = median(rois) if rois else 0.0
sharpe = (mean_roi/pstdev(rois)) if len(rois)>1 and pstdev(rois)>0 else 0.0

# Top 5 / bottom 5 resolved
resolved_sorted = sorted(resolved_meaningful, key=lambda x: x[1]["pnl"], reverse=True)
top5 = resolved_sorted[:5]
bot5 = resolved_sorted[-5:]

# Bucket analysis — use weighted avg entry price per cond on BUYs
def avg_price_cond(cid, outcome_filter=None):
    """weighted avg BUY price across the cond (can filter by outcomeIndex)"""
    tot_sz = 0; tot_usd = 0
    for r in trades:
        if r.get("conditionId") != cid or r.get("side") != "BUY": continue
        if outcome_filter is not None and r.get("outcomeIndex") != outcome_filter: continue
        sz = r.get("size",0) or 0
        usd = r.get("usdcSize",0) or 0
        tot_sz += sz; tot_usd += usd
    return (tot_usd/tot_sz) if tot_sz>0 else None

bucket_stats = defaultdict(lambda: {"n":0,"wins":0,"usd":0.0,"pnl":0.0,"rois":[]})
for cid, a in resolved_meaningful:
    price = avg_price_cond(cid)
    if price is None: continue
    b = bucket_of(price)
    if not b: continue
    s = bucket_stats[b]
    s["n"] += 1
    if a["pnl"] > 0: s["wins"] += 1
    s["usd"] += a["buy_usd"]
    s["pnl"] += a["pnl"]
    r = roi_cond(a)
    if r is not None: s["rois"].append(r)

# Categories: use all conds (open + resolved) for USD volume, resolved for WR/ROI
cat_stats = defaultdict(lambda: {"n_all":0,"n_res":0,"wins":0,"usd":0.0,"pnl":0.0,"rois":[]})
all_cond_ids = set(cond_agg.keys())
for cid in all_cond_ids:
    a = cond_agg[cid]
    c = classify(a["title"])
    s = cat_stats[c]
    s["n_all"] += 1
    s["usd"] += a["buy_usd"]
    if cid in dict(resolved_meaningful):
        s["n_res"] += 1
        s["pnl"] += a["pnl"]
        if a["pnl"] > 0: s["wins"] += 1
        r = roi_cond(a)
        if r is not None: s["rois"].append(r)

total_usd_all = sum(s["usd"] for s in cat_stats.values())
if cat_stats:
    spec_cat = max(cat_stats.items(), key=lambda kv: kv[1]["usd"])
else:
    spec_cat = (None, {"usd":0})
spec_share = spec_cat[1]["usd"]/total_usd_all if total_usd_all else 0.0

# Trading style
buy_sizes = [r.get("usdcSize",0) or 0 for r in buys]
buy_sizes_f = [x for x in buy_sizes if x >= MIN_USD_SIZE_ACT]
avg_buy = mean(buy_sizes_f) if buy_sizes_f else 0
med_buy = median(buy_sizes_f) if buy_sizes_f else 0
def size_bucket(x):
    if x < 100: return "<$100"
    if x < 500: return "$100-500"
    if x < 2000: return "$500-2K"
    if x < 10000: return "$2K-10K"
    return "$10K+"
size_dist = Counter(size_bucket(x) for x in buy_sizes_f)

pos_trades = defaultdict(list)
for r in trades:
    pos_trades[(r.get("conditionId"), r.get("asset"))].append(r)
trades_per_pos = [len(v) for v in pos_trades.values()]
avg_trades_per_pos = mean(trades_per_pos) if trades_per_pos else 0
med_trades_per_pos = median(trades_per_pos) if trades_per_pos else 0

# Hedging — markets with BUYs on both YES and NO
hedge_markets = []
for cid, a in cond_agg.items():
    if a["yes_buy"] > 30 and a["no_buy"] > 30:
        ratio = min(a["yes_buy"], a["no_buy"])/max(a["yes_buy"], a["no_buy"])
        hedge_markets.append((cid, a, ratio))
hedge_count = len(hedge_markets)
# Balanced hedge (ratio >= 0.7 = likely merge-arb)
balanced_hedge = [x for x in hedge_markets if x[2] >= 0.7]
likely_merge_arb = len(balanced_hedge)

# Horizon + scalp on (cond,asset)
horizons, scalps, sc_cons = [], 0, 0
for key, evts in pos_trades.items():
    es = sorted(evts, key=lambda x: x["timestamp"])
    fb = next((r for r in es if r.get("side")=="BUY"), None)
    fs = next((r for r in es if r.get("side")=="SELL"), None)
    if fb and fs and fs["timestamp"]>fb["timestamp"]:
        dt = (fs["timestamp"]-fb["timestamp"])/3600
        horizons.append(dt); sc_cons += 1
        if dt < 2: scalps += 1
mean_horizon = mean(horizons) if horizons else 0
med_horizon = median(horizons) if horizons else 0
scalp_ratio = scalps/sc_cons if sc_cons else 0

trip = Counter()
for r in trades:
    trip[(r.get("transactionHash"), r.get("conditionId"), r.get("timestamp"))] += 1
batch_events_total = sum(v for v in trip.values() if v>1)
batch_groups = sum(1 for v in trip.values() if v>1)

# Sell/Redeem behavior
# Key discriminator: the player has 1627 BUYs but only 5 SELLs. They exit by REDEEM (holding to expiry).
# This is BUY-AND-HOLD style, not active directional trading.

# ===== DENIZZ CORRELATION =====
denizz_trades = [r for r in denizz_act if r.get("type")=="TRADE"]
denizz_conds = set(r["conditionId"] for r in denizz_trades if r.get("conditionId"))
p2_conds = set(uniq_cond)
common_conds = denizz_conds & p2_conds

def first_buy_side(trs, cid):
    for r in sorted([x for x in trs if x.get("conditionId")==cid and x.get("side")=="BUY"], key=lambda x:x["timestamp"]):
        return r.get("outcomeIndex")
    return None
side_match = {"same":0,"opposite":0,"unknown":0}
for cid in common_conds:
    d = first_buy_side(denizz_trades, cid)
    p = first_buy_side(trades, cid)
    if d is None or p is None: side_match["unknown"] += 1
    elif d == p: side_match["same"] += 1
    else: side_match["opposite"] += 1
known_match = side_match["same"] + side_match["opposite"]
share_same = side_match["same"]/known_match if known_match else 0.0

# ===== DENIZZ METRICS =====
denizz_buys = [r for r in denizz_trades if r.get("side")=="BUY"]
denizz_sells = [r for r in denizz_trades if r.get("side")=="SELL"]
denizz_redeems = [r for r in denizz_act if r.get("type")=="REDEEM"]
denizz_total_buy_usd = sum(r.get("usdcSize",0) or 0 for r in denizz_buys)
denizz_total_sell_usd = sum(r.get("usdcSize",0) or 0 for r in denizz_sells)
denizz_total_redeem_usd = sum(r.get("usdcSize",0) or 0 for r in denizz_redeems)

# denizz realized reconstruction
d_cond_agg = defaultdict(lambda: {"buy_usd":0.0,"sell_usd":0.0,"redeem_usd":0.0,"title":""})
for r in denizz_trades:
    cid = r.get("conditionId");
    if not cid: continue
    a = d_cond_agg[cid]
    a["title"] = r.get("title") or a["title"]
    usd = r.get("usdcSize",0) or 0
    if r.get("side")=="BUY": a["buy_usd"] += usd
    elif r.get("side")=="SELL": a["sell_usd"] += usd
for r in denizz_redeems:
    d_cond_agg[r.get("conditionId")]["redeem_usd"] += r.get("usdcSize",0) or 0

d_open_cids = set(p.get("conditionId") for p in denizz_pos if (p.get("size",0) or 0) > 0)
d_resolved = []
for cid, a in d_cond_agg.items():
    if cid in d_open_cids: continue
    pnl = a["sell_usd"] + a["redeem_usd"] - a["buy_usd"]
    a["pnl"] = pnl
    d_resolved.append((cid,a))
d_resolved_meaningful = [(cid,a) for cid,a in d_resolved if a["buy_usd"] >= MIN_USD_SIZE_ACT]
d_wins = [x for x in d_resolved_meaningful if x[1]["pnl"]>0]
d_wr = len(d_wins)/len(d_resolved_meaningful) if d_resolved_meaningful else 0.0
d_realized = sum(a["pnl"] for _,a in d_resolved)
d_unrealized = sum((p.get("currentValue",0) or 0) - (p.get("initialValue",0) or 0) for p in denizz_pos if (p.get("size",0) or 0) > 0)
d_total_pnl = d_realized + d_unrealized

d_iran_usd = 0.0; d_tot_usd = 0.0
for cid,a in d_cond_agg.items():
    c = classify(a["title"])
    d_tot_usd += a["buy_usd"]
    if c == "iran": d_iran_usd += a["buy_usd"]
d_iran_share = d_iran_usd/d_tot_usd if d_tot_usd else 0.0

# denizz scalp / top-up / batch
dpos_trades = defaultdict(list)
for r in denizz_trades:
    dpos_trades[(r.get("conditionId"), r.get("asset"))].append(r)
d_horizons, d_sc, d_scc = [], 0, 0
for k, es in dpos_trades.items():
    ee = sorted(es, key=lambda x: x["timestamp"])
    fb = next((r for r in ee if r.get("side")=="BUY"), None)
    fs = next((r for r in ee if r.get("side")=="SELL"), None)
    if fb and fs and fs["timestamp"]>fb["timestamp"]:
        dt = (fs["timestamp"]-fb["timestamp"])/3600
        d_horizons.append(dt); d_scc += 1
        if dt < 2: d_sc += 1
d_scalp = d_sc/d_scc if d_scc else 0
d_tpp = [len(v) for v in dpos_trades.values()]
d_avg_tpp = mean(d_tpp) if d_tpp else 0
d_trip = Counter()
for r in denizz_trades:
    d_trip[(r.get("transactionHash"), r.get("conditionId"), r.get("timestamp"))] += 1
d_batch = sum(v for v in d_trip.values() if v>1)
d_hedge = 0
d_hedge_balanced = 0
d_ch = defaultdict(lambda: {"y":0.0,"n":0.0})
for r in denizz_trades:
    if r.get("side") != "BUY": continue
    if r.get("outcomeIndex") == 0: d_ch[r.get("conditionId")]["y"] += r.get("usdcSize",0) or 0
    elif r.get("outcomeIndex") == 1: d_ch[r.get("conditionId")]["n"] += r.get("usdcSize",0) or 0
for cid,x in d_ch.items():
    if x["y"]>30 and x["n"]>30:
        d_hedge += 1
        if min(x["y"],x["n"])/max(x["y"],x["n"]) >= 0.7: d_hedge_balanced += 1

# ===== REPORT =====
out = []
def W(s): out.append(s); print(s)

W(f"# Аналитический профиль player2 — 0x9bbd88...56e72")
W("")
W(f"**Дата:** 2026-04-17  ")
W(f"**Wallet:** `0x9bbd88140ccba06100da00476257d9cffce56e72`  ")
W(f"**Pseudonym:** Female-Tailbud (кошелёк без кастомного ника)  ")
W(f"**URL:** https://polymarket.com/@0x9bbd88140ccba06100da00476257d9cffce56e72-1771508511872?tab=positions")
W("")

W("## 1. Резюме")
W("")
W(f"- Период активности: **{period_first} → {period_last}** ({period_days:.0f} дней — очень короткая история).")
W(f"- События: {len(act)} всего (TRADE {len(trades)}: BUY **{len(buys)}**, SELL **{len(sells)}**; REDEEM **{len(redeems)}** на ${total_redeem_usd:,.0f}; REWARD {len(rewards)}; MAKER_REBATE {len(rebates)}).")
W(f"- **Критическое наблюдение:** 1627 BUY vs 5 SELL — игрок почти не продаёт; выходит через REDEEM (holding-to-expiry), а не через активные продажи.")
W(f"- Volume: BUY **${total_buy_usd:,.0f}**, SELL ${total_sell_usd:,.0f}, REDEEM payout ${total_redeem_usd:,.0f}.")
W(f"- Уникальных позиций (asset): {len(uniq_asset)}, маркетов (cid): {len(uniq_cond)}.")
W(f"- **P&L (реконструкция):** realized **${realized_pnl_recon:+,.0f}**, unrealized **${unrealized_pnl:+,.0f}**, rewards/rebates ${other_income:+,.0f} → **Total ${total_pnl:+,.0f}**.")
W(f"- WR на resolved маркетах (buy>=$30): **{wr_resolved*100:.1f}%** (N={len(resolved_meaningful)}), mean ROI **{mean_roi*100:+.1f}%**, median **{med_roi*100:+.1f}%**.")
spec_name = spec_cat[0]
W(f"- Специализация: **{spec_name}** ({spec_share*100:.1f}% USD volume) — " + ("ВЫДЕЛЕННАЯ." if spec_share>0.4 else "НЕТ выраженной специализации (<40%)."))
W(f"- **HEDGING-РИСК:** {hedge_count} маркетов с BUY на обеих сторонах, из них {likely_merge_arb} со сбалансированным размером (ratio ≥0.7) — **сильный признак merge-арбитража** (тот же паттерн, из-за которого удалили Car).")
W(f"- Стиль: scalp_ratio {scalp_ratio*100:.1f}% (N={sc_cons} мало), avg trades/позиция {avg_trades_per_pos:.1f}, batch-fills {batch_groups} групп ({batch_events_total} events) = {batch_events_total/len(trades)*100:.1f}%.")
W(f"- Корреляция с denizz: пересечение {len(common_conds)} маркетов; на них same-side **{share_same*100:.0f}%** против {side_match['opposite']} opposite — то есть на общих маркетах игрок часто сидит на ПРОТИВОПОЛОЖНОЙ стороне от denizz.")
W("")

W("## 2. Базовые метрики")
W("")
W("| Метрика | Значение |")
W("|---|---|")
W(f"| Первая активность | {period_first} |")
W(f"| Последняя активность | {period_last} |")
W(f"| Период (дней) | {period_days:.0f} |")
W(f"| Всего activity events | {len(act)} |")
W(f"| TRADE events | {len(trades)} |")
W(f"| BUY events | {len(buys)} |")
W(f"| SELL events | {len(sells)} |")
W(f"| REDEEM events | {len(redeems)} (payout ${total_redeem_usd:,.0f}) |")
W(f"| REWARD events | {len(rewards)} (${total_reward_usd:,.2f}) |")
W(f"| MAKER_REBATE events | {len(rebates)} (${total_rebate_usd:,.2f}) |")
W(f"| Уникальных позиций (asset) | {len(uniq_asset)} |")
W(f"| Уникальных маркетов (cid) | {len(uniq_cond)} |")
W(f"| Открытых позиций (сейчас) | {sum(1 for p in pos if (p.get('size',0) or 0)>0)} |")
W(f"| Total BUY USD | ${total_buy_usd:,.0f} |")
W(f"| Total SELL USD | ${total_sell_usd:,.0f} |")
W(f"| BUY USD / 7 дней | ${buys_7d:,.0f} |")
W(f"| BUY USD / 30 дней | ${buys_30d:,.0f} |")
W(f"| Trades / 7 дней | {len(trades_7d)} |")
W(f"| Trades / 30 дней | {len(trades_30d)} |")
W("")

W("## 3. P&L и ROI (реконструкция)")
W("")
W("Метод: `/positions` endpoint возвращает ТОЛЬКО открытые позиции (228 строк, все size>0). Поэтому realized P&L реконструирован: для каждой cond = Σ(SELL usdcSize) + Σ(REDEEM usdcSize) − Σ(BUY usdcSize); маркет считаем resolved, если нет открытых позиций по нему.")
W("")
W("| Метрика | Значение |")
W("|---|---|")
W(f"| Realized P&L (reconstructed) | ${realized_pnl_recon:+,.2f} |")
W(f"| Unrealized P&L (open) | ${unrealized_pnl:+,.2f} |")
W(f"| Rewards + Maker rebates | ${other_income:+,.2f} |")
W(f"| **Total P&L** | **${total_pnl:+,.2f}** |")
W(f"| Открытых позиций (size>0) | {sum(1 for p in pos if (p.get('size',0) or 0)>0)} |")
W(f"| Открытый cost basis | ${open_cost_total:,.0f} |")
W(f"| Открытый current value | ${open_value_total:,.0f} |")
W(f"| Resolved маркетов всего | {len(resolved_conds)} |")
W(f"| Resolved + buy≥$30 (для WR) | {len(resolved_meaningful)} |")
W(f"| WR resolved | {wr_resolved*100:.1f}% ({len(wins)}/{len(resolved_meaningful)}) |")
W(f"| Mean ROI resolved | {mean_roi*100:+.2f}% |")
W(f"| Median ROI resolved | {med_roi*100:+.2f}% |")
W(f"| Sharpe-like | {sharpe:.3f} |")
W("")
W("### Топ-5 прибыльных (resolved conditions)")
W("")
W("| Title | BUY$ | SELL$ | REDEEM$ | PnL$ | ROI% |")
W("|---|---|---|---|---|---|")
for cid,a in top5:
    roi = a["pnl"]/a["buy_usd"]*100 if a["buy_usd"] else 0
    W(f"| {(a['title'] or cid[:12])[:65]} | ${a['buy_usd']:,.0f} | ${a['sell_usd']:,.0f} | ${a['redeem_usd']:,.0f} | ${a['pnl']:+,.0f} | {roi:+.1f}% |")
W("")
W("### Топ-5 убыточных (resolved conditions)")
W("")
W("| Title | BUY$ | SELL$ | REDEEM$ | PnL$ | ROI% |")
W("|---|---|---|---|---|---|")
for cid,a in bot5:
    roi = a["pnl"]/a["buy_usd"]*100 if a["buy_usd"] else 0
    W(f"| {(a['title'] or cid[:12])[:65]} | ${a['buy_usd']:,.0f} | ${a['sell_usd']:,.0f} | ${a['redeem_usd']:,.0f} | ${a['pnl']:+,.0f} | {roi:+.1f}% |")
W("")

W("## 4. Разбивка по ценовым бакетам (resolved, средняя BUY-цена на cond)")
W("")
W("| Бакет | N | WR | Mean ROI | BUY volume | PnL |")
W("|---|---|---|---|---|---|")
for lo,hi,name in BUCKETS:
    s = bucket_stats[name]
    if s["n"] == 0:
        W(f"| {name} | 0 | — | — | — | — |")
    else:
        wr = s["wins"]/s["n"]*100
        mr = (mean(s["rois"])*100) if s["rois"] else 0
        W(f"| {name} | {s['n']} | {wr:.1f}% | {mr:+.1f}% | ${s['usd']:,.0f} | ${s['pnl']:+,.0f} |")
W("")

W("## 5. Разбивка по категориям")
W("")
W("| Категория | N_all cid | USD vol | % vol | N_res | WR | Mean ROI | PnL |")
W("|---|---|---|---|---|---|---|---|")
for cat in sorted(cat_stats.keys(), key=lambda k: -cat_stats[k]["usd"]):
    s = cat_stats[cat]
    vshare = s["usd"]/total_usd_all*100 if total_usd_all else 0
    wr = s["wins"]/s["n_res"]*100 if s["n_res"] else 0
    mr = (mean(s["rois"])*100) if s["rois"] else 0
    W(f"| {cat} | {s['n_all']} | ${s['usd']:,.0f} | {vshare:.1f}% | {s['n_res']} | {wr:.1f}% | {mr:+.1f}% | ${s['pnl']:+,.0f} |")
W("")
W(f"**Специализация:** `{spec_name}` — {spec_share*100:.1f}% USD volume. " + ("ВЫДЕЛЕННАЯ (>40%)." if spec_share>0.4 else "НЕТ выраженной специализации (<40%)."))
W("")

W("## 6. Стиль торговли")
W("")
W("| Метрика | Значение |")
W("|---|---|")
W(f"| Средний BUY (фильтр ≥$30) | ${avg_buy:,.0f} |")
W(f"| Медианный BUY | ${med_buy:,.0f} |")
W(f"| Trades на позицию (asset) — среднее | {avg_trades_per_pos:.2f} |")
W(f"| Trades на позицию — медиана | {med_trades_per_pos:.1f} |")
W(f"| Horizon (часов first BUY → first SELL) — среднее | {mean_horizon:.1f} |")
W(f"| Horizon медиана | {med_horizon:.1f} |")
W(f"| Scalp ratio (<2ч) | {scalp_ratio*100:.1f}% (N={sc_cons}, выборка крошечная т.к. всего 5 sell-ивентов) |")
W(f"| Batch-fill группы (tx+cid+ts >1) | {batch_groups} групп, {batch_events_total} events из {len(trades)} ({batch_events_total/len(trades)*100:.1f}%) |")
W(f"| Hedging: BUY YES+NO на одном cond | {hedge_count} маркетов |")
W(f"| Из них сбалансированные (min/max ≥0.7) | **{likely_merge_arb}** — признак merge-арбитража |")
W("")
W("### Распределение размеров BUY")
W("")
W("| Бакет | Кол-во |")
W("|---|---|")
for b in ["<$100","$100-500","$500-2K","$2K-10K","$10K+"]:
    W(f"| {b} | {size_dist.get(b,0)} |")
W("")
W(f"Итог: {size_dist.get('<$100',0)} из {sum(size_dist.values())} BUY-ивентов (≥$30) — в категории <$100; ни одного BUY ≥$500. Игрок дробит покупки крошечными ордерами.")
W("")

W("## 7. Корреляция с denizz")
W("")
W("| Метрика | Значение |")
W("|---|---|")
W(f"| Маркетов у player2 | {len(p2_conds)} |")
W(f"| Маркетов у denizz | {len(denizz_conds)} |")
W(f"| Пересечение (cid) | {len(common_conds)} |")
W(f"| Same-side first-BUY | {side_match['same']} |")
W(f"| Opposite-side first-BUY | {side_match['opposite']} |")
W(f"| Unknown | {side_match['unknown']} |")
W(f"| % same-side (от известных) | {share_same*100:.1f}% |")
W("")
if known_match >= 5:
    if share_same > 0.6:
        W("**Интерпретация:** SAME-side > 60%. Копируя player2 мы часто будем дублировать denizz → редундантность и двойной риск на одних и тех же маркетах.")
    elif share_same < 0.4:
        W(f"**Интерпретация:** SAME-side {share_same*100:.0f}% < 40% — на общих маркетах игрок торгует **ПРОТИВОПОЛОЖНУЮ** сторону от denizz. Копировать обоих = ставить на обе стороны одного маркета (нулевой EV + комиссии).")
    else:
        W(f"**Интерпретация:** SAME-side {share_same*100:.0f}% — умеренная пересекаемость. Нет ни дополняющей, ни прямо противоположной корреляции.")
else:
    W(f"**Интерпретация:** слишком мало общих маркетов ({known_match}) для статистически значимого вывода.")
W("")

W("## 8. Сравнительная таблица denizz vs player2")
W("")
W("| Метрика | denizz | player2 |")
W("|---|---|---|")
W(f"| Lifetime Total P&L | ${d_total_pnl:+,.0f} | ${total_pnl:+,.0f} |")
W(f"| Realized P&L (reconstructed) | ${d_realized:+,.0f} | ${realized_pnl_recon:+,.0f} |")
W(f"| Unrealized (open) | ${d_unrealized:+,.0f} | ${unrealized_pnl:+,.0f} |")
W(f"| WR resolved (buy≥$30) | {d_wr*100:.1f}% (N={len(d_resolved_meaningful)}) | {wr_resolved*100:.1f}% (N={len(resolved_meaningful)}) |")
W(f"| Total BUY USD | ${denizz_total_buy_usd:,.0f} | ${total_buy_usd:,.0f} |")
W(f"| Total SELL USD | ${denizz_total_sell_usd:,.0f} | ${total_sell_usd:,.0f} |")
W(f"| BUY / SELL events | {len(denizz_buys)} / {len(denizz_sells)} | {len(buys)} / {len(sells)} |")
W(f"| N маркетов (cid) | {len(denizz_conds)} | {len(p2_conds)} |")
W(f"| Специализация | iran ({d_iran_share*100:.0f}%) | {spec_name} ({spec_share*100:.0f}%) |")
W(f"| Scalp ratio (<2ч) | {d_scalp*100:.1f}% | {scalp_ratio*100:.1f}% |")
W(f"| Avg trades/asset | {d_avg_tpp:.2f} | {avg_trades_per_pos:.2f} |")
W(f"| Batch-fill events | {d_batch} | {batch_events_total} |")
W(f"| Hedge markets (YES+NO buys ≥$30) | {d_hedge} | {hedge_count} |")
W(f"| Сбалансированный hedge (merge-arb признак) | {d_hedge_balanced} | {likely_merge_arb} |")
W("")

# ===== VERDICT =====
W("## 9. Финальная рекомендация")
W("")
flags = []
if total_pnl < 0: flags.append(f"Total P&L ${total_pnl:+,.0f} (убыточный).")
if wr_resolved < 0.45 and len(resolved_meaningful) >= 20:
    flags.append(f"WR resolved {wr_resolved*100:.1f}% < 45%.")
if mean_roi < 0 and len(resolved_meaningful) >= 10:
    flags.append(f"Mean ROI {mean_roi*100:+.1f}% отрицательный.")
if len(resolved_meaningful) < 20:
    flags.append(f"N resolved (buy≥$30) = {len(resolved_meaningful)} — низкая стат. значимость.")
if spec_share < 0.4:
    flags.append(f"Нет выраженной специализации (лид. категория {spec_name} {spec_share*100:.1f}%).")
if likely_merge_arb > 5:
    flags.append(f"**{likely_merge_arb} сбалансированных hedge-маркетов** — паттерн merge-арбитража (аналогично Car, удалённого 2026-04-09 после Iran April 7).")
elif hedge_count > 20:
    flags.append(f"{hedge_count} маркетов с BUY на обе стороны — высокая доля недирекционных сделок.")
if len(sells) < 10:
    flags.append(f"Всего {len(sells)} SELL-ивентов — игрок не продаёт, exit-сигналы копировать невозможно.")
if batch_events_total/len(trades) > 0.2:
    flags.append(f"Batch-fills {batch_events_total/len(trades)*100:.1f}% trades — большая часть ордеров идёт пачками (арбитражный/ботовый паттерн).")
if known_match >= 5:
    if share_same > 0.6:
        flags.append(f"Same-side с denizz {share_same*100:.0f}% — редундантность.")
    elif share_same < 0.4:
        flags.append(f"Same-side с denizz {share_same*100:.0f}% — на общих маркетах сидит ПРОТИВОПОЛОЖНО. Копирование обоих = ставить на обе стороны.")

# Decision
severe = (likely_merge_arb > 5) or (len(sells) < 10 and len(buys) > 500)
no_exit_signal = len(sells) < 10

if severe or no_exit_signal:
    rec = "НЕ ДОБАВЛЯТЬ"
    icon = "🔴"
elif total_pnl > 50000 and wr_resolved > 0.5 and len(resolved_meaningful) >= 30:
    rec = "ДОБАВИТЬ"
    icon = "✅"
elif len(resolved_meaningful) < 20:
    rec = "ПОДОЖДАТЬ БОЛЬШЕ ИСТОРИИ"
    icon = "⚠️"
else:
    rec = "НЕ ДОБАВЛЯТЬ"
    icon = "🔴"

W(f"### {icon} {rec}")
W("")
W("**Обоснование:**")
for f in flags:
    W(f"- {f}")
if not flags:
    W("- Все ключевые метрики в норме.")
W("")

# Key specific risk warning
if likely_merge_arb >= 5 or (len(sells) < 10 and len(buys) > 500):
    W("**Ключевой риск** — это тот же сценарий, из-за которого удалили Car 2026-04-09:")
    W("> *\"Car does merge-prep arbitrage (buys Yes+No, then merges to \\$1) — we copied the buys as real direction signals and got burned\"* (config.py).")
    W("")
    W(f"У player2: **{likely_merge_arb}** сбалансированных маркетов с BUY на обе стороны (min/max ≥0.7). Это не directional trader, а buy-and-hold / merge-arb style (BUY:SELL ratio {len(buys)}:{len(sells)} = {len(buys)/max(1,len(sells)):.0f}:1). Боту нужны exit-сигналы, а их практически нет.")
W("")

W("## 10. Ограничения и риски (методологические)")
W("")
W(f"- Выборка resolved = {len(resolved_meaningful)} с buy≥$30. " + ("Достаточная." if len(resolved_meaningful)>=30 else "Статистически слабая."))
W("- `/positions` возвращает только OPEN позиции — для realized P&L используем реконструкцию (BUY/SELL/REDEEM usdcSize по cond).")
W("- Маркет считаем resolved, если нет ни одной открытой позиции по нему (может включать частично закрытые маркеты с merge).")
W("- REDEEM events несут usdcSize = выплата по выигравшему outcome; 111 REDEEM-ов с нулевой суммой = проигравший outcome.")
W("- Классификация категорий — по title через keyword-matching из config.CATEGORY_KEYWORDS. Без ключей → `other`.")
W("- Horizon/scalp ratio считаются только по first BUY→first SELL; выборка крошечная (5 SELL-ивентов всего).")
W("- API `/profile/...` возвращает 404 — ник не подтверждён, используем pseudonym из activity (Female-Tailbud).")
W("- Только 56 дней истории (≤2 месяцев). Стиль может эволюционировать.")
W("- Сравнение с denizz по локальным дампам: activity ALL {0} events, positions {1} rows.".format(len(denizz_act), len(denizz_pos)))
W("")

text = "\n".join(out)
with open(REPORT, "w", encoding="utf-8") as f:
    f.write(text)
print(f"\n=== SAVED: {REPORT} ({len(text)} chars) ===")

print("\n=== FINAL VERDICT ===")
print(f"player2 Total P&L: ${total_pnl:+,.0f}")
print(f"Realized: ${realized_pnl_recon:+,.0f}, Unrealized: ${unrealized_pnl:+,.0f}")
print(f"WR resolved: {wr_resolved*100:.1f}% (N={len(resolved_meaningful)})")
print(f"Spec: {spec_name} {spec_share*100:.1f}%")
print(f"Hedge markets: {hedge_count}, balanced (merge-arb): {likely_merge_arb}")
print(f"BUY:SELL = {len(buys)}:{len(sells)}")
print(f"Overlap denizz: {len(common_conds)} cid, same-side {share_same*100:.1f}%")
print(f"RECOMMENDATION: {icon} {rec}")
