"""
Asymmetry Deep Dive: Can we trade the YES upside convexity?

Finding: WTI +$1 → YES +1.72pp, WTI -$1 → YES -0.20pp
Question: Is this stable? What's the edge? What's the risk?
"""
import math
import json
import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta

from config import YES_TOKEN_ID, NO_TOKEN_ID

# ── Fetch data ──
print("Fetching data...")

def fetch_prices(token_id):
    resp = requests.get(
        "https://clob.polymarket.com/prices-history",
        params={"market": token_id, "interval": "max", "fidelity": "60"},
        timeout=30,
    )
    data = resp.json()
    if isinstance(data, dict) and "history" in data:
        return [(int(p["t"]), float(p["p"])) for p in data["history"]]
    return [(int(p["t"]), float(p["p"])) for p in data]

yes_raw = fetch_prices(YES_TOKEN_ID)
wti_raw = yf.Ticker("CL=F").history(period="1mo", interval="1h")
wti_data = [(int(t.timestamp()), float(row["Close"])) for t, row in wti_raw.iterrows()]

print(f"YES: {len(yes_raw)} pts, WTI: {len(wti_data)} pts")

# ── Build hourly ──
def to_hourly(data):
    r = {}
    for ts, p in data:
        r[ts // 3600] = p
    return r

wti_h = to_hourly(wti_data)
yes_h = to_hourly(yes_raw)
common = sorted(set(wti_h) & set(yes_h))
now_hour = int(datetime.now(timezone.utc).timestamp()) // 3600

def ols_slope(xs, ys):
    n = len(xs)
    if n < 5: return None
    mx, my = sum(xs)/n, sum(ys)/n
    d = sum((x-mx)**2 for x in xs)
    if d == 0: return None
    return sum((xs[i]-mx)*(ys[i]-my) for i in range(n)) / d

# ═══════════════════════════════════════════════════
#  TEST 1: Is the asymmetry stable across time windows?
# ═══════════════════════════════════════════════════
print("\n" + "="*60)
print("TEST 1: Asymmetry stability across time windows")
print("="*60)

for window_name, hours_back in [("24h", 24), ("48h", 48), ("3d", 72), ("5d", 120), ("7d", 168)]:
    min_h = now_hour - hours_back
    hrs = [h for h in common if h >= min_h]

    up_wti, up_yes = [], []
    down_wti, down_yes = [], []

    for i in range(1, len(hrs)):
        if hrs[i] - hrs[i-1] > 3:
            continue
        dw = wti_h[hrs[i]] - wti_h[hrs[i-1]]
        dy = (yes_h[hrs[i]] - yes_h[hrs[i-1]]) * 100  # pp
        if dw > 0.01:
            up_wti.append(dw)
            up_yes.append(dy)
        elif dw < -0.01:
            down_wti.append(dw)
            down_yes.append(dy)

    up_slope = ols_slope(up_wti, up_yes) if len(up_wti) >= 5 else None
    down_slope = ols_slope(down_wti, down_yes) if len(down_wti) >= 5 else None

    up_s = f"{up_slope:+.3f}" if up_slope else "N/A"
    dn_s = f"{down_slope:+.3f}" if down_slope else "N/A"
    ratio = f"{up_slope/abs(down_slope):.1f}x" if up_slope and down_slope and down_slope != 0 else "N/A"

    print(f"  {window_name:>3}: WTI↑ → YES {up_s} pp/$1 ({len(up_wti)} pts) | "
          f"WTI↓ → YES {dn_s} pp/$1 ({len(down_wti)} pts) | "
          f"Asymmetry: {ratio}")

# ═══════════════════════════════════════════════════
#  TEST 2: Edge per oscillation cycle
# ═══════════════════════════════════════════════════
print("\n" + "="*60)
print("TEST 2: Simulated P&L from oscillation cycles (last 3 days)")
print("="*60)

# Find all WTI oscillation cycles: down then up, or up then down
min_3d = now_hour - 72
hrs_3d = [h for h in common if h >= min_3d]

# Track each swing: buy YES when WTI drops, sell when WTI rises back
cycles = []
i = 0
while i < len(hrs_3d) - 1:
    # Find a dip: WTI drops at least $0.50
    dip_start = i
    while i < len(hrs_3d) - 1:
        if wti_h[hrs_3d[i+1]] < wti_h[hrs_3d[dip_start]] - 0.3:
            break
        i += 1
    if i >= len(hrs_3d) - 1:
        break

    dip_bottom = i
    wti_at_dip = wti_h[hrs_3d[dip_bottom]]
    yes_at_dip = yes_h[hrs_3d[dip_bottom]]

    # Find recovery: WTI rises back at least $0.50 from bottom
    while i < len(hrs_3d) - 1:
        if wti_h[hrs_3d[i+1]] > wti_at_dip + 0.3:
            break
        i += 1
    if i >= len(hrs_3d) - 1:
        break

    recovery_top = i + 1
    wti_at_recovery = wti_h[hrs_3d[recovery_top]]
    yes_at_recovery = yes_h[hrs_3d[recovery_top]]

    wti_drop = wti_at_dip - wti_h[hrs_3d[dip_start]]
    wti_rise = wti_at_recovery - wti_at_dip
    yes_drop = (yes_at_dip - yes_h[hrs_3d[dip_start]]) * 100
    yes_rise = (yes_at_recovery - yes_at_dip) * 100

    duration_hours = (hrs_3d[recovery_top] - hrs_3d[dip_start])

    # P&L: buy $10 of YES at dip, sell at recovery
    if yes_at_dip > 0:
        shares = 10 / yes_at_dip
        revenue = shares * yes_at_recovery
        pnl = revenue - 10
        pnl_pct = pnl / 10 * 100
    else:
        pnl, pnl_pct = 0, 0

    cycles.append({
        "wti_drop": wti_drop,
        "wti_rise": wti_rise,
        "yes_drop_pp": yes_drop,
        "yes_rise_pp": yes_rise,
        "pnl_usd": pnl,
        "pnl_pct": pnl_pct,
        "hours": duration_hours,
        "entry_yes": yes_at_dip,
        "exit_yes": yes_at_recovery,
    })

    i = recovery_top

print(f"\nFound {len(cycles)} oscillation cycles in 3 days:\n")
total_pnl = 0
for j, c in enumerate(cycles):
    total_pnl += c["pnl_usd"]
    print(f"  Cycle {j+1}: WTI dropped ${c['wti_drop']:.2f} (YES {c['yes_drop_pp']:+.1f}pp) "
          f"→ WTI rose ${c['wti_rise']:+.2f} (YES {c['yes_rise_pp']:+.1f}pp) "
          f"| {c['hours']}h | Buy YES @ {c['entry_yes']:.3f} → Sell @ {c['exit_yes']:.3f} "
          f"| $10 bet → P&L: ${c['pnl_usd']:+.2f} ({c['pnl_pct']:+.1f}%)")

print(f"\n  Total P&L on $10 bets: ${total_pnl:+.2f}")
if cycles:
    print(f"  Avg per cycle: ${total_pnl/len(cycles):+.2f}")
    print(f"  Win rate: {sum(1 for c in cycles if c['pnl_usd'] > 0)}/{len(cycles)}")

# ═══════════════════════════════════════════════════
#  TEST 3: What WTI range maximizes asymmetry?
# ═══════════════════════════════════════════════════
print("\n" + "="*60)
print("TEST 3: Asymmetry by WTI price zone")
print("="*60)

# Split common hours by WTI level, measure asymmetry in each zone
zones = [(91, 93), (93, 95), (95, 97), (97, 99), (99, 101)]
for zlo, zhi in zones:
    up_w, up_y, dn_w, dn_y = [], [], [], []
    for i in range(1, len(common)):
        if common[i] - common[i-1] > 3:
            continue
        wti_mid = (wti_h[common[i]] + wti_h[common[i-1]]) / 2
        if not (zlo <= wti_mid < zhi):
            continue
        dw = wti_h[common[i]] - wti_h[common[i-1]]
        dy = (yes_h[common[i]] - yes_h[common[i-1]]) * 100
        if dw > 0.01:
            up_w.append(dw); up_y.append(dy)
        elif dw < -0.01:
            dn_w.append(dw); dn_y.append(dy)

    up_s = ols_slope(up_w, up_y)
    dn_s = ols_slope(dn_w, dn_y)

    up_str = f"{up_s:+.2f}" if up_s else "N/A"
    dn_str = f"{dn_s:+.2f}" if dn_s else "N/A"
    asym = f"{up_s/abs(dn_s):.1f}x" if up_s and dn_s and dn_s != 0 else "—"
    n = len(up_w) + len(dn_w)

    print(f"  WTI ${zlo}-${zhi}: UP {up_str} pp/$1 ({len(up_w)}pts) | "
          f"DOWN {dn_str} pp/$1 ({len(dn_w)}pts) | Asymmetry: {asym} | Total: {n} obs")

# ═══════════════════════════════════════════════════
#  TEST 4: Maximum drawdown risk
# ═══════════════════════════════════════════════════
print("\n" + "="*60)
print("TEST 4: Worst-case scenario for asymmetry trade")
print("="*60)

# What if WTI drops $3 in a row without bouncing?
hrs_7d = [h for h in common if h >= now_hour - 168]
max_consecutive_drop_wti = 0
max_consecutive_drop_yes = 0
current_drop_wti = 0
current_drop_yes = 0

for i in range(1, len(hrs_7d)):
    if hrs_7d[i] - hrs_7d[i-1] > 3:
        current_drop_wti = 0
        current_drop_yes = 0
        continue
    dw = wti_h[hrs_7d[i]] - wti_h[hrs_7d[i-1]]
    dy = (yes_h[hrs_7d[i]] - yes_h[hrs_7d[i-1]]) * 100
    if dw < 0:
        current_drop_wti += abs(dw)
        current_drop_yes += abs(dy)
    else:
        if current_drop_wti > max_consecutive_drop_wti:
            max_consecutive_drop_wti = current_drop_wti
            max_consecutive_drop_yes = current_drop_yes
        current_drop_wti = 0
        current_drop_yes = 0

print(f"  Max consecutive WTI drop (7d): ${max_consecutive_drop_wti:.2f}")
print(f"  YES drop during that: {max_consecutive_drop_yes:.1f}pp")
if max_consecutive_drop_wti > 0:
    print(f"  Ratio: {max_consecutive_drop_yes/max_consecutive_drop_wti:.2f} pp/$1 during max drop")

# Max YES single-day drop
daily_yes_changes = []
for i in range(24, len(hrs_7d)):
    h_now = hrs_7d[i]
    h_24ago = hrs_7d[i-24] if i >= 24 else hrs_7d[0]
    if h_now - h_24ago > 30:
        continue
    change = (yes_h[h_now] - yes_h[h_24ago]) * 100
    daily_yes_changes.append(change)

if daily_yes_changes:
    worst_day = min(daily_yes_changes)
    best_day = max(daily_yes_changes)
    print(f"\n  Worst 24h YES move: {worst_day:+.1f}pp")
    print(f"  Best 24h YES move: {best_day:+.1f}pp")
    print(f"  On $10 bet at 68c: worst loss = ${10 * worst_day / 100 / 0.68:+.2f}, "
          f"best gain = ${10 * best_day / 100 / 0.68:+.2f}")

# ═══════════════════════════════════════════════════
#  SUMMARY
# ═══════════════════════════════════════════════════
print("\n" + "="*60)
print("SUMMARY: Asymmetry Trading Viability")
print("="*60)
