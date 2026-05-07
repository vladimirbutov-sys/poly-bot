"""One-shot sell script for all positions of 98_sure_bot, weather_bot, overround_bot.

Reads each bot's tracker, verifies on-chain balance, fetches live best_bid,
places GTC SELL @ best_bid (instant fill), waits, then updates the tracker.

Skips positions where bid <= 0.01 (nothing to sell, only redeemable).
Skips positions where on-chain balance == 0 (phantoms).

Usage:
    py -3.12 -u -X utf8 _sell_all_bots.py              # dry run
    py -3.12 -u -X utf8 _sell_all_bots.py --execute    # actually sell
"""
import json
import sys
import time
import math
import os
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1, errors='replace')

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from web3 import Web3

from config import CLOB_HOST, CHAIN_ID, OUR_PRIVATE_KEY, OUR_WALLET, POLYGON_RPC

EXECUTE = "--execute" in sys.argv
MIN_BID = 0.015   # skip anything below — not worth selling
FILL_WAIT_SEC = 30  # wait for fill after posting

SURE_TRACKER = Path(r"c:/Users/Honor/Desktop/Polymarket/Bots/98_sure_bot/positions.json")
WEATHER_TRACKER = Path(r"c:/Users/Honor/Desktop/Polymarket/Bots/26_weather_bot/positions.json")
OVERROUND_TRACKER = Path(r"c:/Users/Honor/Desktop/Polymarket/Bots/27_overround_bot/positions.json")

# ERC1155 balanceOf on ConditionalTokens
CTF = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
_w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
_ctf = _w3.eth.contract(
    address=Web3.to_checksum_address(CTF),
    abi=[{"constant": True, "inputs": [{"name": "a", "type": "address"}, {"name": "id", "type": "uint256"}],
          "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}],
          "type": "function", "stateMutability": "view"}],
)


def onchain_shares(token_id: str) -> float:
    try:
        raw = _ctf.functions.balanceOf(
            Web3.to_checksum_address(OUR_WALLET), int(token_id)
        ).call()
        return raw / 1e6
    except Exception as e:
        print(f"[balanceOf err] {token_id[:20]}: {e}")
        return -1.0


_client = None
def clob() -> ClobClient:
    global _client
    if _client is None:
        _client = ClobClient(
            CLOB_HOST,
            key=OUR_PRIVATE_KEY,
            chain_id=CHAIN_ID,
            signature_type=0,
            funder=OUR_WALLET,
        )
        _client.set_api_creds(_client.create_or_derive_api_creds())
    return _client


def best_bid(token_id: str) -> float | None:
    try:
        book = clob().get_order_book(token_id)
        if not book:
            return None
        bids = book.bids if hasattr(book, 'bids') else []
        if not bids:
            return 0.0
        return max(float(b.price) for b in bids)
    except Exception as e:
        print(f"[orderbook err] {token_id[:20]}: {e}")
        return None


def place_sell(token_id: str, shares: float, price: float) -> dict | None:
    """GTC limit sell at `price` for `shares`."""
    try:
        shares = math.floor(shares * 100) / 100
        price = round(price, 3)
        if shares < 1:
            print(f"  too few shares ({shares}) — skip")
            return None
        args = OrderArgs(token_id=token_id, price=price, size=shares, side="SELL")
        signed = clob().create_order(args)
        resp = clob().post_order(signed, OrderType.GTC)
        if resp and resp.get("success"):
            return {
                "order_id": resp.get("orderID", ""),
                "shares": shares,
                "price": price,
            }
        print(f"  REJECTED: {resp}")
        return None
    except Exception as e:
        print(f"  EXC: {e}")
        return None


def wait_fill(order_id: str) -> dict:
    """Poll order until filled or timeout."""
    c = clob()
    start = time.time()
    last = {}
    while time.time() - start < FILL_WAIT_SEC:
        try:
            o = c.get_order(order_id)
            if o:
                last = o
                status = o.get("status", "UNKNOWN")
                matched = float(o.get("size_matched", 0) or 0)
                orig = float(o.get("original_size", 0) or o.get("size", 0) or 0)
                if status == "MATCHED":
                    return {"status": "MATCHED", "matched": matched, "orig": orig}
                if status == "CANCELLED":
                    return {"status": "CANCELLED", "matched": matched, "orig": orig}
        except Exception as e:
            print(f"  poll err: {e}")
        time.sleep(2)
    # timeout — check if partial
    matched = float(last.get("size_matched", 0) or 0)
    orig = float(last.get("original_size", 0) or last.get("size", 0) or 0)
    try:
        clob().cancel(order_id)
    except Exception:
        pass
    if matched > 0:
        return {"status": "PARTIAL", "matched": matched, "orig": orig}
    return {"status": "TIMEOUT", "matched": 0, "orig": orig}


# -----------------------------------------------------------------
# Build sell list from all 3 bots' trackers
# -----------------------------------------------------------------
def load(path: Path):
    return json.load(open(path, "r", encoding="utf-8"))


def build_sell_list():
    items = []

    # 98_sure_bot — dict of dicts
    d = load(SURE_TRACKER)
    for key, p in d.get("positions", {}).items():
        if p.get("status") != "open":
            continue
        tok = str(p.get("token_id", ""))
        if not tok:
            continue
        items.append({
            "bot": "98_sure",
            "tracker_path": SURE_TRACKER,
            "tracker_key": key,
            "title": p.get("title", "?"),
            "token_id": tok,
            "entry": float(p.get("avg_entry") or p.get("entry_price", 0)),
        })

    # 26_weather — flat list
    d = load(WEATHER_TRACKER)
    for i, p in enumerate(d):
        if not isinstance(p, dict) or p.get("status") != "open":
            continue
        tok = str(p.get("token_id", ""))
        if not tok:
            continue
        items.append({
            "bot": "weather",
            "tracker_path": WEATHER_TRACKER,
            "tracker_key": i,  # index in list
            "title": p.get("question", "?"),
            "token_id": tok,
            "entry": float(p.get("entry_price", 0)),
        })

    # 27_overround — dict of dicts
    d = load(OVERROUND_TRACKER)
    for key, p in (d.get("positions") or {}).items():
        if p.get("status") != "open":
            continue
        tok = str(p.get("no_token", ""))
        if not tok:
            continue
        items.append({
            "bot": "overround",
            "tracker_path": OVERROUND_TRACKER,
            "tracker_key": key,
            "title": p.get("question", "?"),
            "token_id": tok,
            "entry": float(p.get("entry_price", 0)),
        })

    return items


def update_tracker_sold(item, result):
    """Mark position as sold in its tracker."""
    path = item["tracker_path"]
    data = load(path)
    now_iso = datetime.now(timezone.utc).isoformat()
    if item["bot"] == "weather":
        # list; mutate by index
        pos = data[item["tracker_key"]]
        pos["status"] = "sold"
        pos["sold_at"] = now_iso
        pos["sell_price"] = result["price"]
        pos["sell_shares"] = result["shares"]
        pos["sell_order_id"] = result["order_id"]
    else:
        pos = data["positions"][item["tracker_key"]]
        pos["status"] = "sold"
        pos["sold_at"] = now_iso
        pos["sell_price"] = result["price"]
        pos["sell_shares"] = result["shares"]
        pos["sell_order_id"] = result["order_id"]
        if item["bot"] == "98_sure":
            pnl = (result["price"] - pos.get("entry_price", 0)) * result["shares"]
            pos["pnl"] = round(pnl, 4)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def update_tracker_phantom(item, reason):
    """Mark a phantom (not on-chain) position as cancelled."""
    path = item["tracker_path"]
    data = load(path)
    now_iso = datetime.now(timezone.utc).isoformat()
    if item["bot"] == "weather":
        pos = data[item["tracker_key"]]
    else:
        pos = data["positions"][item["tracker_key"]]
    pos["status"] = "cancelled"
    pos["cancelled_at"] = now_iso
    pos["cancel_reason"] = reason
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    mode = "EXECUTE" if EXECUTE else "DRY RUN"
    print(f"\n{'='*70}\n>>> {mode} <<<\n{'='*70}\n")

    items = build_sell_list()
    print(f"Tracker-open positions total: {len(items)}\n")

    plan = []
    phantoms = []

    for it in items:
        tok = it["token_id"]
        sh = onchain_shares(tok)
        if sh < 0.01:
            phantoms.append((it, "not on-chain (already sold/redeemed/cancelled)"))
            continue
        bid = best_bid(tok)
        if bid is None:
            phantoms.append((it, "orderbook unavailable"))
            continue
        if bid < MIN_BID:
            phantoms.append((it, f"bid too low ({bid:.4f}) — redeem only"))
            continue
        plan.append({
            **it,
            "onchain_shares": sh,
            "bid": bid,
            "sell_price": bid,
            "revenue": sh * bid,
            "cost": sh * it["entry"],
        })
        time.sleep(0.15)

    # Print phantoms first
    print(f"--- SKIPPED: {len(phantoms)} positions ---")
    for it, reason in phantoms:
        print(f"  [{it['bot']:9}] {it['title'][:60]}  → {reason}")

    # Print plan
    print(f"\n--- SELL PLAN: {len(plan)} positions ---")
    print(f"{'#':>3} {'bot':>9}  {'sh':>8} {'entry':>6} {'bid':>6} {'rev':>8} {'cost':>8} {'pnl':>8}  title")
    tot_rev = tot_cost = 0
    for i, p in enumerate(plan, 1):
        pnl = p["revenue"] - p["cost"]
        tot_rev += p["revenue"]
        tot_cost += p["cost"]
        print(f"{i:3} {p['bot']:>9}  {p['onchain_shares']:8.2f} {p['entry']:6.3f} {p['bid']:6.3f} "
              f"${p['revenue']:7.2f} ${p['cost']:7.2f} {pnl:+7.2f}  {p['title'][:55]}")
    print(f"{'-'*100}")
    print(f"TOTAL: revenue ${tot_rev:.2f}  cost ${tot_cost:.2f}  realized PnL {tot_rev-tot_cost:+.2f}")

    if not EXECUTE:
        print("\n[DRY RUN] nothing posted. Run again with --execute\n")
        return

    # Execute
    print("\n" + "="*70)
    print("PLACING ORDERS...")
    print("="*70)
    sold_ok = 0
    sold_partial = 0
    failed = 0
    total_received = 0

    for i, p in enumerate(plan, 1):
        print(f"\n[{i}/{len(plan)}] {p['bot']} | {p['title'][:55]}")
        print(f"  sell {p['onchain_shares']:.2f} sh @ {p['sell_price']:.3f}")
        result = place_sell(p["token_id"], p["onchain_shares"], p["sell_price"])
        if not result:
            failed += 1
            continue
        print(f"  order_id: {result['order_id'][:20]}... — waiting for fill")
        fill = wait_fill(result["order_id"])
        matched = fill["matched"]
        if fill["status"] == "MATCHED":
            received = matched * p["sell_price"]
            total_received += received
            sold_ok += 1
            print(f"  FILLED: {matched:.2f} sh → ${received:.2f}")
            update_tracker_sold(p, {
                "order_id": result["order_id"],
                "shares": matched,
                "price": p["sell_price"],
            })
        elif fill["status"] == "PARTIAL":
            received = matched * p["sell_price"]
            total_received += received
            sold_partial += 1
            print(f"  PARTIAL: {matched:.2f}/{fill['orig']:.2f} sh → ${received:.2f}")
            update_tracker_sold(p, {
                "order_id": result["order_id"],
                "shares": matched,
                "price": p["sell_price"],
            })
        else:
            failed += 1
            print(f"  {fill['status']}")
        time.sleep(0.5)

    # Phantoms clean-up
    print(f"\n--- cleaning phantoms ({len(phantoms)}) ---")
    for it, reason in phantoms:
        if "not on-chain" in reason or "orderbook unavailable" in reason:
            try:
                update_tracker_phantom(it, reason)
            except Exception as e:
                print(f"  err: {e}")

    print("\n" + "="*70)
    print(f"DONE. matched: {sold_ok}  partial: {sold_partial}  failed: {failed}")
    print(f"Total received: ${total_received:.2f}")
    print("="*70)


if __name__ == "__main__":
    main()
