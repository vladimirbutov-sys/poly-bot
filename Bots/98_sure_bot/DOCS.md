# 98_sure_bot — Full Documentation

## What It Does

Scans all open Polymarket markets every 5 minutes. Identifies markets where the outcome is effectively certain but the price hasn't reached $1.00 yet. Places limit buy orders at 96–99.5¢ and automatically redeems positions after resolution on the Polygon blockchain.

**Live results:** 881 trades, 96% win rate.

---

## The Edge

Prediction markets near resolution (1–3 days to end date) are systematically mispriced:

- Market makers don't push prices to 100¢ because it eliminates their spread
- Retail participants are slow to react to resolved information
- Limited liquidity means small buyers can't move the price

The result: a market trading at 97¢ where the outcome is already decided pays a guaranteed 3¢ ($3 per $97 invested = 3.1% in 1–3 days).

---

## How It Works

### Scan Cycle (every 5 minutes)

```
1. Fetch all open markets from Gamma API (paginated, 500 per page)
2. Filter by price range: 96.0–99.5¢
3. Apply 14 filters to each candidate
4. Sort: strike markets today first → nearest end_date
5. For each survivor:
   a. Check USDC balance
   b. Fetch live CLOB orderbook (bid/ask)
   c. Verify price divergence ≤ 3¢ (Gamma vs CLOB)
   d. Check portfolio limits
   e. Calculate limit price (ask + slippage from table)
   f. Place BUY limit order
6. Monitor each order (every 5 sec, TTL = 5 min)
7. [Background] Check on-chain resolution every 5 min → auto-redeem
```

---

## 14 Filters

| # | Name | Blocks |
|---|------|--------|
| 1 | Price range | Outside 96–99.5¢ |
| 2 | Liquidity | Market liquidity < $500 |
| 3 | Volume | Total traded volume < $500 |
| 4 | Expiry window | > 3 days to resolution OR already expired > 3 days |
| 5 | Duplicate | Already have open position on this condition_id |
| 6 | Sub-match | "game 1", "map 2", "set 3" markets |
| 7 | Elections | Binary political candidate markets |
| 8 | Slow keywords | "top", "most", "season", "weekly" |
| 9 | Coin-flip patterns | "odd or even", "first blood", "first baron" |
| 10 | Threshold markets | "close above $X", "reach $Y", "pump to" |
| 11 | Cancelled events | Match started > 6h ago, market unresolved |
| 12 | Neg-risk cap | Frozen capital in neg-risk positions ≥ $350 |
| 13 | Low-liquidity financials | BTC/ETH/stocks with volume < $50K |
| 14 | Price divergence | Gamma API price vs CLOB price gap > 3¢ |

Additional regex blocks: earthquake/tornado markets, sports over/under/handicap, delayed-resolution keywords ("not released by Q4", "as of Dec 31").

---

## Slippage Table

Limit order price = CLOB ask + slippage. Slippage scales with price to protect ROI:

| Price range | Max slippage |
|------------|-------------|
| 96.0–97.5¢ | +0.5¢ |
| 97.5–98.5¢ | +0.4¢ |
| 98.5–99.0¢ | +0.3¢ |
| 99.0–99.5¢ | +0.3¢ |

---

## Position Sizing

| Market type | Bet size |
|-------------|----------|
| Regular | $20 |
| Neg-risk | $15 |
| Weather | $10 |
| Slow-keyword test | $5 |
| Price 96.5–97.5¢ test | $5 |

---

## Portfolio Limits

| Limit | Value |
|-------|-------|
| Max total frozen capital | $1,000 |
| Max in neg-risk positions | $350 |
| Max politics/geopolitics share | 30% of balance |
| Min USDC remaining | = bet size |

---

## Order Lifecycle

```
POST /order (limit BUY, TTL 5 min)
    │
    ├── MATCHED → record in positions.json, Telegram: "Order filled"
    ├── PARTIAL FILL → record partial, return remainder to balance
    └── TIMEOUT (5 min) → DELETE /order
                          Check on-chain balance (sometimes fills on-chain without CLOB ACK)
    │
    ▼
[redeemer.py, every 5 min]
    Check: CTF.payoutDenominator > 0?
    │
    ├── YES, won → redeemPositions() → USDC returned → status: won
    ├── YES, lost → record loss → status: lost
    └── NO → continue polling
```

---

## Telegram Notifications

| Event | Message includes |
|-------|-----------------|
| Bot start | Balance, open positions count |
| Order placed | Market title, price, amount, order_id |
| Order filled | Shares acquired, execution price, total cost |
| Partial fill | Shares filled / total, remaining |
| Order cancelled | Reason |
| Position redeemed | P&L, win/loss |
| 8-hour report | Balance, total P&L, win rate, open positions |
| Error | Exception details |

---

## File Structure

```
98_sure_bot/
├── main.py             ← main loop, orchestration
├── scanner.py          ← Gamma API fetch + price filter
├── filters.py          ← 14 filter functions
├── executor.py         ← CLOB order placement and tracking
├── tracker.py          ← positions.json read/write, P&L
├── redeemer.py         ← on-chain balance check and redemption
├── telegram_notify.py  ← message formatting and delivery
├── config.py           ← all parameters
├── .env.example        ← secrets template
├── positions.json      ← live position state
├── bot_log.txt         ← execution log
└── _analytics/         ← backtest results and research
```

---

## Known Edge Cases

**CLOB fills on-chain without API acknowledgement**
The CLOB API sometimes fails to report a fill, but the transaction lands on Polygon. The executor checks on-chain balance after TTL timeout — if shares exist, the position is recorded as filled.

**Neg-risk markets**
Some Polymarket markets use a "neg-risk" structure where buying YES on one outcome implicitly creates risk on related outcomes. These are detected via the `neg_risk` flag in the Gamma API response and use a smaller bet size ($15 vs $20) with a separate frozen capital cap ($350).

**Nonce conflicts on redemption**
If multiple positions resolve simultaneously, `redeemPositions()` calls can conflict. The redeemer adds a 5-second delay between transactions and retries failed calls.
