# Strategy Guide

Overview of all trading strategies implemented in the system, when to use each, and how they work.

---

## Strategy 1 — Sure Bet (`98_sure_bot`)

**Core idea:** Prediction markets are inefficient near resolution. When an outcome is effectively certain, the price often stays below 100¢ due to limited liquidity and information lag. Buy at 96–99.5¢, collect $1.00 at resolution.

**Edge:** The gap between "market price" and "true probability" is systematic and repeatable.

### Entry rules
- Price: 96–99.5¢
- Days to resolution: ≤ 3
- Liquidity: ≥ $500
- Volume: ≥ $500
- Pass all 14 filters (see [DOCS.md](Bots/98_sure_bot/DOCS.md))

### Position sizing
| Market type | Bet size |
|-------------|----------|
| Regular | $20 |
| Neg-risk | $15 |
| Weather | $10 |
| Slow-keyword (test) | $5 |

### Risk controls
- Max total frozen: $1,000
- Max in neg-risk: $350
- Max politics share: 30% of balance
- Order TTL: 5 minutes (cancel if unfilled)

### Historical performance
- **881 trades** in production
- **96% win rate**
- Typical ROI per trade: 0.5–4% over 1–3 days

### When NOT to use
- High-volatility events (elections, breaking news, black swans)
- Markets with < $500 liquidity — low fill probability
- Geopolitical markets with ambiguous resolution criteria

---

## Strategy 2 — Smart Money Copy (`25_multi_signal_copybot_v2`)

**Core idea:** Copy trades from a verified high-conviction wallet (denizz) with a documented edge on Polymarket. Enter proportionally, exit when they exit.

**Why denizz:** Lifetime P&L of +$447K on Polymarket. Trades directionally (not merge-arbitrage). Early entry signals are alpha-generating on a consistent basis.

### Signal detection
- Monitor denizz's on-chain trades via Data API + Polygon RPC
- Signal triggered: denizz buys ≥ $500 in a single market
- No opposing position from signal player required

### Position sizing
Logarithmic formula scaled to denizz's investment:
```
bet = 31.75 × ln(denizz_invested) - 177.0
```
Anchors: denizz $500 → our $20 / denizz $30K → our $150

Plus price-risk multipliers (longshots and near-100¢ get reduced size):
| Price range | Multiplier |
|------------|------------|
| 0–15¢ | 40% |
| 15–30¢ | 70% |
| 30–70¢ | 100% |
| 70–85¢ | 90% |
| 85–99¢ | 80% |

### Exit rules
Follow denizz's sells proportionally:
- Denizz sells 20–30% → we sell 25%
- Denizz sells 50–60% → we sell 55%
- Denizz sells 80%+ → we sell 100%

Additional exits:
- Auto take-profit at 99.5¢
- Stop-loss: -80% (disabled by default during volatile windows)

### Top-up handling
When denizz adds to an existing position:
- < 3% of his total: skip (noise)
- 3–10%: enter at 50% size
- 30%+: enter at full size

### When NOT to use
- During confirmed merge-arbitrage activity (identified by YES+NO simultaneous buys)
- When market horizon > 120 days (position multiplier = 0)

---

## Strategy 3 — YES/NO Arbitrage (`21_arb_scanner`)

**Core idea:** On Polymarket, YES + NO shares for the same outcome = $1.00 exactly. When YES price + NO price < $1.00 (e.g., YES at 60¢ + NO at 38¢ = 98¢), buy both and redeem for $1.00 — risk-free 2¢ profit.

**Edge:** Price dislocations occur during high-volume trading when market makers lag.

### Signal conditions
- YES price + NO price < threshold (e.g., < $0.995)
- Sufficient liquidity on both sides
- Market not near resolution (enough time to fill both legs)

### Execution
1. Buy YES at best ask
2. Buy NO at best ask
3. Both orders must fill within TTL
4. Call `merge()` on NegRiskAdapter contract → receive $1.00 USDC

### Risk
- If one leg fills and the other doesn't: exposed to directional risk
- Mitigation: cancel unfilled leg immediately, small position sizes

---

## Strategy 4 — Oil Swing (`10_oil_swing_bot`)

**Core idea:** Trade Polymarket binary questions on WTI crude oil prices using real-world price triggers. "Will WTI hit $100 by end of month?" — buy YES when WTI is at $92 (cheap), sell when WTI approaches $100 (expensive).

**Edge:** Polymarket oil markets lag spot price by minutes. Gradient entry captures the full move.

### Entry: YES (WTI will hit target)
Gradient entries as WTI drops (cheaper YES):
| WTI trigger | Bet |
|-------------|-----|
| ≤ $92 | $20 (reconnaissance) |
| ≤ $90 | $20 (confirmation) |
| ≤ $88 | $60 (core position) |

Max entry price: 28¢ (limited upside above this)

### Entry: NO (WTI will NOT hit target)
Gradient entries as WTI rises (cheaper NO):
| WTI trigger | Bet | Profit target |
|-------------|-----|--------------|
| ≥ $97 | $20 | +35% |
| ≥ $98 | $20 | +69% |
| ≥ $99 | $40 | +104% |

### Stop-losses
- YES: sell all if WTI < $80 (ceasefire / demand crash)
- NO: sell if WTI > $110
- Theta: sell YES if held > 3 days without $3+ WTI move

### Special rules
- Dead zone: no trading 30 min before/after CME settlement (14:00–15:00 ET)
- Weekend block: no new positions Fri 16:00 ET – Mon 09:00 ET
- Theta scaling: position sizes reduced as deadline approaches

---

## Strategy 5 — Whale Tracking (`26_whale_tracker`)

**Monitoring only — no automatic orders.**

Tracks a curated list of high-performing wallets in real-time. Sends Telegram alerts when:
- Wallet makes a large buy (≥ $1,000)
- Wallet makes a significant sell
- New wallet identified with unusual activity

Use the alerts as manual trading signals or to inform copybot configuration.

**Tracked wallets:** Curated list based on historical P&L analysis of 7,053 wallets across war-market trades (see `Players_DB/`).

---

## Strategy 6 — Dispute Monitor (`22_dispute_monitor`)

**Monitoring only — no automatic orders.**

Monitors the UMA oracle for Polymarket resolution disputes. Sends Telegram alerts when:
- A dispute is opened on a market you hold
- A dispute is resolved (outcome confirmed or overturned)

Disputes create temporary mispricing opportunities: if the market trades as if resolved YES but a dispute is pending, it may revert to 50¢. The alert gives you time to act manually.

---

## Choosing the Right Strategy

| Goal | Strategy |
|------|----------|
| Low-risk consistent income | Sure Bet (98_sure_bot) |
| Higher returns, more risk | Smart Money Copy |
| Exploit pricing dislocations | Arbitrage Scanner |
| Trade macro events (commodities) | Oil Swing Bot |
| Research and signal generation | Whale Tracker |
| Risk management for open positions | Dispute Monitor |

All strategies can run simultaneously. They use separate `positions.json` files and don't interfere with each other.
