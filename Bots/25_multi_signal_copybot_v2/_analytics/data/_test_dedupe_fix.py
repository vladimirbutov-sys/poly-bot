"""Unit test: dedupe key must treat batch-order records as distinct.

Scenario (real case 2026-04-17, denizz tx 0x2bb739...):
  Polymarket returns two TRADE records with the same
  transactionHash + conditionId + timestamp but different size/price.
  Old key collapses them to one. New key must keep both.

Also: a truly identical record (same everything) must still be deduped.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def make_key_old(trade):
    tx = trade.get("transactionHash", "")
    cond = trade.get("conditionId", "")
    ts_val = trade.get("timestamp", 0)
    return f"{tx}_{cond}_{ts_val}"


def make_key_new(trade):
    tx = trade.get("transactionHash", "")
    cond = trade.get("conditionId", "")
    ts_val = trade.get("timestamp", 0)
    size = trade.get("size", 0)
    price = trade.get("price", 0)
    return f"{tx}_{cond}_{ts_val}_{size}_{price}"


def run_dedupe(events, key_fn):
    seen = set()
    kept = []
    for e in events:
        k = key_fn(e)
        if k in seen:
            continue
        seen.add(k)
        kept.append(e)
    return kept


passed = 0
failed = 0

def check(name, cond):
    global passed, failed
    if cond:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}")
        failed += 1


# === Test 1: real case — two records same tx+cond+ts, different size/price ===
print("[Test 1] Batch-order: same tx+cond+ts, different size/price → both must pass")
event_a = {
    "transactionHash": "0x2bb739b125094ee5452fdf1605baf6945394d2009fab28d71fe5ab6f9142f953",
    "conditionId": "0xFAKE",
    "timestamp": 1776424996,
    "size": 75.7, "price": 0.66, "usdcSize": 49.962, "side": "BUY",
}
event_b = {
    "transactionHash": "0x2bb739b125094ee5452fdf1605baf6945394d2009fab28d71fe5ab6f9142f953",
    "conditionId": "0xFAKE",
    "timestamp": 1776424996,
    "size": 791.75, "price": 0.67, "usdcSize": 530.4725, "side": "BUY",
}
kept_old = run_dedupe([event_a, event_b], make_key_old)
kept_new = run_dedupe([event_a, event_b], make_key_new)
check("old key drops 1 of 2 batch-order records (demonstrates bug)", len(kept_old) == 1)
check("new key keeps BOTH batch-order records", len(kept_new) == 2)
check("new-key total USD seen = $580.43 (was $49.96 under old key)",
      abs(sum(float(e["usdcSize"]) for e in kept_new) - 580.4345) < 0.01)

# === Test 2: true duplicate (exact same record twice) — must still dedupe ===
print("[Test 2] True duplicate (identical record twice) → old AND new must dedupe to 1")
kept_old = run_dedupe([event_a, event_a], make_key_old)
kept_new = run_dedupe([event_a, event_a], make_key_new)
check("old key dedupes true duplicate to 1", len(kept_old) == 1)
check("new key dedupes true duplicate to 1", len(kept_new) == 1)

# === Test 3: same tx+cond+ts+size but different price ===
print("[Test 3] Same tx+cond+ts+size, different price → new key keeps both")
e1 = {"transactionHash":"0xA","conditionId":"0xB","timestamp":100,"size":10.0,"price":0.5}
e2 = {"transactionHash":"0xA","conditionId":"0xB","timestamp":100,"size":10.0,"price":0.6}
check("new key treats as distinct", len(run_dedupe([e1,e2], make_key_new)) == 2)

# === Test 4: same everything except size ===
print("[Test 4] Same tx+cond+ts+price, different size → new key keeps both")
e1 = {"transactionHash":"0xA","conditionId":"0xB","timestamp":100,"size":10.0,"price":0.5}
e2 = {"transactionHash":"0xA","conditionId":"0xB","timestamp":100,"size":11.0,"price":0.5}
check("new key treats as distinct", len(run_dedupe([e1,e2], make_key_new)) == 2)

# === Test 5: stable float string representation across polls ===
print("[Test 5] Float values from JSON round-trip to the same string")
# Simulate: second poll returns the exact same JSON bytes → same Python floats
import json
raw = json.dumps({"transactionHash":"0xA","conditionId":"0xB","timestamp":100,
                  "size":791.75,"price":0.6700000001})
poll1 = json.loads(raw)
poll2 = json.loads(raw)
k1 = make_key_new(poll1)
k2 = make_key_new(poll2)
check("identical JSON bytes → identical key strings", k1 == k2)

# === Test 6: None / 0 edge cases (non-TRADE events) ===
print("[Test 6] Edge cases: size=None, price=0 (MERGE/SPLIT shape)")
e_merge_a = {"transactionHash":"0xM","conditionId":"0xC","timestamp":200,"size":None,"price":0}
e_merge_b = {"transactionHash":"0xM","conditionId":"0xC","timestamp":200,"size":None,"price":0}
# These are truly identical → should dedupe under new key too
check("two identical MERGE-shape rows dedupe to 1",
      len(run_dedupe([e_merge_a,e_merge_b], make_key_new)) == 1)
# Key must not raise on None / 0
k = make_key_new(e_merge_a)
check("new-key does not raise on size=None, price=0", isinstance(k, str))

# === Test 7: replay real sample of denizz live data ===
print("[Test 7] Replay live denizz activity (3000 records)")
import os
live_path = os.path.join(os.path.dirname(__file__), "_dedupe_audit_denizz_live.json")
if os.path.exists(live_path):
    with open(live_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    trades = [e for e in data if (e.get("type","") or "").upper() == "TRADE"]
    kept_old = run_dedupe(trades, make_key_old)
    kept_new = run_dedupe(trades, make_key_new)
    delta = len(kept_new) - len(kept_old)
    check(f"new key keeps MORE records than old ({len(kept_new)} vs {len(kept_old)}, +{delta})",
          len(kept_new) > len(kept_old))
    lost_usd = sum(float(t.get("usdcSize",0) or 0) for t in trades) \
               - sum(float(t.get("usdcSize",0) or 0) for t in kept_old)
    new_lost_usd = sum(float(t.get("usdcSize",0) or 0) for t in trades) \
                   - sum(float(t.get("usdcSize",0) or 0) for t in kept_new)
    print(f"    Old key lost $={lost_usd:,.2f}  |  New key lost $={new_lost_usd:,.2f}")
else:
    print(f"  SKIP  live sample not found at {live_path}")

print()
print("=" * 60)
print(f"Results: {passed} passed, {failed} failed")
print("=" * 60)
sys.exit(0 if failed == 0 else 1)
