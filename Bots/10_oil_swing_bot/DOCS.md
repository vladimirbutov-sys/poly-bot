# 10_oil_swing_bot — Full Documentation

## What It Does

Trades Polymarket binary prediction markets on WTI crude oil prices using real-world spot price as the signal. Enters YES positions when oil is cheap (far from target), enters NO positions when oil is expensive (near target), and exits via gradient steps as price moves in our favor.

---

## The Edge

Polymarket oil price markets lag spot price by minutes. When WTI moves significantly, the YES/NO tokens on Polymarket haven't repriced yet. The bot detects this lag and enters before the market catches up.

**Example:**
- Market: "Will WTI hit $100 by end of March?"
- WTI spot: $89 (far from $100, unlikely to hit target)
- YES token: still at 22¢ (market is slow)
- Action: don't buy YES yet — wait for WTI to drop further
- When WTI drops to $88 → buy YES at ≤ 28¢ → WTI recovers to $97 → sell at 50¢+ → profit

---

## Strategy

### YES entries (WTI will hit target)
Buy YES in gradient steps as WTI drops lower (YES gets cheaper = better risk/reward):

| WTI trigger | Our bet | Purpose |
|-------------|---------|---------|
| ≤ $92 | $20 | Reconnaissance — test the water |
| ≤ $90 | $20 | Confirmation — add to position |
| ≤ $88 | $60 | Core entry — main position |

Maximum YES entry price: **28¢** (above this, upside is too limited).

### NO entries (WTI will NOT hit target)
Buy NO as WTI rises (NO gets cheaper as target looks more achievable):

| WTI trigger | Our bet | Sell at |
|-------------|---------|--------|
| ≥ $97 | $20 | +35% profit |
| ≥ $98 | $20 | +69% profit |
| ≥ $99 | $40 | +104% profit |

Maximum NO entry price: **16¢**.

---

## Exit Rules

### YES exits — WTI rises
| WTI level | Action |
|-----------|--------|
| ≥ $97 | Sell 30% of YES |
| ≥ $99 | Sell 50% of remaining |
| ≥ $100 | Sell 100% (market resolution expected) |
| Profit ≥ 21% | Auto take-profit regardless of WTI |

### YES stop-losses
| Condition | Action |
|-----------|--------|
| WTI < $80 | Sell ALL YES (demand crash / ceasefire) |
| Held > 3 days, WTI moved < $3 | Theta stop — sell (stagnation) |
| Portfolio < $200 | Emergency stop — halt all trading |

### NO exits
| Condition | Action |
|-----------|--------|
| WTI > $110 | Sell NO (runaway price) |
| Per-step profit target hit | Sell that step's position |

---

## Theta Scaling

Position size is reduced as the market deadline approaches (time-value decay):

| Days remaining | Size multiplier |
|---------------|----------------|
| 10+ days | 100% |
| 7–9 days | 80% |
| 5–6 days | 60% |
| 3–4 days | 30% |
| 0–2 days | 0% (no new entries) |

---

## Special Rules

**CME settlement dead zone**
No trading 30 minutes before or after CME crude oil settlement (14:00–15:00 ET). Settlement causes volatility spikes that create false signals.

**Weekend block**
No new entries Friday 16:00 ET through Monday 09:00 ET. Weekend WTI moves are not reflected in Polymarket until Monday open.

**Momentum filter for NO entries**
Don't buy NO if WTI rose > $2 in the last 6 data points (~6 hours). Rising momentum makes NO entries risky.

**Divergence detection**
If the correlation between WTI moves and YES token price changes deviates > 2× the expected ratio, reduce position size to 50% (possible market dislocation).

---

## Technical Setup

The bot fetches WTI spot price from a free data source every 60 seconds and compares to configured triggers. No paid data feed required.

Token IDs for the specific oil market are hardcoded in `config.py` — update them when a new market period begins.

---

## File Structure

```
10_oil_swing_bot/
├── main.py           ← main loop
├── strategy.py       ← entry/exit decision logic
├── executor.py       ← CLOB order placement
├── config.py         ← all parameters including WTI triggers
├── smart_tuner.py    ← auto-calibration of WTI/price ratios
├── requirements.txt
├── .env.example
└── _analytics/       ← backtest results
```
