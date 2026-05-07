"""Retry loop: sell 100% YES on US x Iran diplomatic meeting by April 21 @ $0.36.

Retries every 60s until the CLOB accepts the order.
"""
import sys, io, time
from datetime import datetime, timezone
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import executor, tracker, filters
from safe_sell import get_wallet_balance
from config import OUR_WALLET

TOKEN = "10825770508982253966577236303666571711538785796333843502583628816512489950358"
LIMIT_PRICE = 0.36
RETRY_INTERVAL = 60       # seconds between attempts
MAX_HOURS = 8             # give up after this

def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def try_place():
    onchain = get_wallet_balance(OUR_WALLET, TOKEN)
    if onchain <= 0.5:
        return ("no_balance", onchain)
    shares = round(onchain - 0.01, 2)
    bid, ask = filters.get_orderbook_prices(TOKEN)
    log(f"Attempt: onchain={onchain:.2f} bid/ask=${bid:.3f}/${ask:.3f} placing {shares} sh @ ${LIMIT_PRICE}")
    result = executor.place_limit_sell(token_id=TOKEN, price=LIMIT_PRICE, shares=shares)
    if result and result.get("order_id"):
        return ("placed", result)
    return ("failed", None)

def record_fill(order_id, matched):
    real = executor.get_actual_fill(order_id)
    actual_price = real["vwap"] if real and real["size"] > 0 else LIMIT_PRICE
    revenue = real["cost_usd"] if real and real["size"] > 0 else matched * LIMIT_PRICE
    data = tracker.load()
    for k, p in (data.get("positions") or {}).items():
        if p.get("token_id") == TOKEN and p.get("status") == "open":
            cs = float(p.get("size_shares", 0))
            cc = float(p.get("cost_usd", 0))
            cost_sold = cc * (matched / cs) if cs > 0 else 0
            pnl = revenue - cost_sold
            p["size_shares"] = round(cs - matched, 4)
            p["cost_usd"] = round(cc - cost_sold, 4)
            p.setdefault("sells", []).append({
                "shares": round(matched, 4),
                "price": round(actual_price, 6),
                "revenue": round(revenue, 4),
                "pnl": round(pnl, 4),
                "reason": "manual_retry_loop_limit36",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            if p["size_shares"] < 0.5:
                p["status"] = "sold"
            tracker.save(data)
            log(f"RECORDED: sold {matched:.2f} sh @ ${actual_price:.4f} revenue ${revenue:.2f} PnL ${pnl:+.2f} status={p['status']}")
            return

start = time.time()
attempt = 0
while time.time() - start < MAX_HOURS * 3600:
    attempt += 1
    try:
        status, payload = try_place()
        if status == "no_balance":
            log(f"no balance ({payload:.4f} sh) — exiting")
            sys.exit(0)
        if status == "placed":
            oid = payload["order_id"]
            log(f"ORDER PLACED: {oid[:24]}... size={payload.get('size_shares')}")
            # watch for fill
            end_watch = time.time() + 120
            last_m = 0.0
            while time.time() < end_watch:
                d = executor.get_order_details(oid)
                st = d.get("status", "?")
                m = float(d.get("size_matched", 0) or 0)
                if m > last_m + 0.01:
                    log(f"  matched {m:.2f} status={st}")
                    last_m = m
                if st == "MATCHED":
                    break
                time.sleep(5)
            d = executor.get_order_details(oid)
            final_m = float(d.get("size_matched", 0) or 0)
            if final_m > 0.5:
                record_fill(oid, final_m)
                if d.get("status") == "MATCHED":
                    log("DONE — fully matched")
                    sys.exit(0)
                log(f"partial {final_m:.2f}; order still LIVE — leaving it")
                sys.exit(0)
            log(f"Order live but 0 filled after 120s — will cancel and retry")
            executor.cancel_order(oid)
        else:
            log(f"place failed attempt #{attempt} — retry in {RETRY_INTERVAL}s")
    except Exception as e:
        log(f"exception attempt #{attempt}: {e} — retry")
    time.sleep(RETRY_INTERVAL)

log(f"Gave up after {MAX_HOURS}h, {attempt} attempts")
