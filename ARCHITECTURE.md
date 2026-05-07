# System Architecture

## Overview

The system consists of six independent trading bots sharing a common infrastructure layer (APIs, Polygon blockchain, Telegram). Each bot runs as a standalone Python process and manages its own position state.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL SERVICES                           │
│                                                                     │
│  Gamma API          CLOB API          Polygon RPC    Telegram API  │
│  (market data)      (order book,      (blockchain,   (alerts)      │
│                      orders)           redemption)                  │
└────────┬───────────────────┬──────────────────┬──────────┬─────────┘
         │                   │                  │          │
         ▼                   ▼                  ▼          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        TRADING BOTS                                 │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ 98_sure_bot  │  │copybot_v2    │  │oil_swing_bot │              │
│  │ (sure bets)  │  │(copy denizz) │  │(WTI swing)   │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                  │                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ arb_scanner  │  │whale_tracker │  │dispute_monitor│             │
│  │ (YES+NO arb) │  │(smart money) │  │(UMA disputes) │             │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
│         │                 │                  │                      │
└─────────┼─────────────────┼──────────────────┼──────────────────────┘
          │                 │                  │
          ▼                 ▼                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SHARED STATE FILES                             │
│                                                                     │
│   positions.json   signals.json   bot_log.txt   pids.json          │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         DASHBOARD                                   │
│                                                                     │
│   Next.js (Vercel)  ←──►  FastAPI (local)  ←── positions.json     │
│   Real-time P&L · Bot controls · Manual sell · Live logs           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Bots by Category

### Trading Bots (place orders autonomously)

| Bot | Strategy | Entry Range | Cycle |
|-----|----------|------------|-------|
| `98_sure_bot` | Near-certain outcomes | 96–99.5¢ | 5 min |
| `25_multi_signal_copybot_v2` | Copy smart money (denizz) | 5–99¢ | 5 sec poll |
| `10_oil_swing_bot` | WTI crude oil swing | 5–28¢ (YES), 5–16¢ (NO) | 60 sec |
| `21_arb_scanner` | YES+NO arbitrage | Any | On demand |

### Monitoring Bots (alerts only, no orders)

| Bot | Monitors | Alert condition |
|-----|----------|----------------|
| `26_whale_tracker` | Smart money wallets | Large buy/sell detected |
| `22_dispute_monitor` | UMA resolution oracle | Dispute opened/resolved |

---

## Shared Infrastructure

### APIs Used by All Bots

**Gamma API** (`gamma-api.polymarket.com`)
- Market discovery, prices, liquidity, volume, end dates
- Paginated: 500 markets per request

**CLOB API** (`clob.polymarket.com`)
- Live orderbook (bid/ask depth)
- Order placement, cancellation, status polling
- Auth: ECDSA signature with Ethereum private key

**Polygon RPC** (`polygon.gateway.tenderly.co`)
- On-chain token balance verification
- Automatic position redemption after market resolution
- Contract calls: `balanceOf()`, `redeemPositions()`

**Telegram Bot API**
- Trade notifications, 8-hour portfolio reports, error alerts
- Rate limit: 0.5s between messages

### Key Contracts (Polygon PoS, Chain ID 137)

| Contract | Address | Purpose |
|----------|---------|---------|
| CTF Exchange | `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045` | Regular market redemption |
| USDC | `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174` | Balance checks |
| NegRisk CTF | `0xC5d563A36AE78145C45a50134d48A1215220f80a` | Neg-risk trading |
| NegRiskAdapter | `0xd91e80cf2e7be2e162c6513ced06f1dd0da35296` | Neg-risk redemption |

---

## Standard Bot Architecture

Every trading bot follows the same internal structure:

```
main.py              ← orchestration loop
config.py            ← all parameters (no hardcoded values)
scanner.py           ← fetch + filter market candidates
executor.py          ← place and track orders via CLOB
tracker.py           ← record positions, compute P&L
redeemer.py          ← on-chain redemption after resolution
telegram_notify.py   ← send alerts
.env                 ← secrets (never committed)
.env.example         ← template
positions.json       ← position state
requirements.txt     ← dependencies
_analytics/          ← research reports and backtest data
```

---

## Order Lifecycle (all bots)

```
Market/signal identified
    │
    ▼
Check portfolio limits (frozen capital, per-category caps)
    │
    ▼
Fetch live CLOB orderbook → calculate limit price + slippage
    │
    ▼
POST /order → CLOB API (limit BUY, TTL = 5–10 min)
    │
    ├── MATCHED → record in positions.json, Telegram alert
    ├── PARTIAL → record partial fill, return remainder to balance
    └── TIMEOUT → cancel order, verify on-chain balance (CLOB can fill on-chain without ACK)
    │
    ▼
[Background thread, every 5 min]
Check: is market resolved on-chain? (payoutDenominator > 0)
    │
    ├── YES → call redeemPositions() on Polygon → update status: won/lost
    └── NO  → continue polling
```

---

## Dashboard Architecture

```
Browser
  │
  ▼
Next.js (Vercel) ──── REST API ────► FastAPI (localhost:8000)
                                          │
                                    ┌─────┴──────┐
                                    │            │
                              positions.json   CLOB API
                              (read state)    (manual sell)
```

**Key endpoints:**
- `GET /api/positions` — all positions from all bots
- `GET /api/status` — bot process status (PID, last active)
- `POST /api/sell` — place manual sell order
- `GET /api/logs` — SSE stream of bot_log.txt
- `POST /api/bot/start|stop` — process management

---

## Data Flow: 98_sure_bot (example)

```
[Every 5 minutes]

Gamma API → 500+ markets → price filter (96–99.5¢)
    │
    ▼
14 filters (liquidity, volume, expiry, duplicates, risky patterns...)
    │
    ▼
Surviving candidates sorted by: strike today → nearest end_date
    │
    ▼
For each candidate:
  CLOB API → live orderbook → verify price divergence ≤ 3¢
  → calculate limit price (ask + slippage from table)
  → POST /order
  → poll status every 5s for 5 min
  → if filled: record in positions.json
  → [redeemer thread] poll on-chain every 5 min → auto-redeem
```

---

## Design Decisions

**Why JSON instead of a database?**
positions.json is sufficient for MVP scale (hundreds of positions). It's readable, debuggable without tools, and shared directly with the dashboard. Migration to SQLite is in the backlog for when concurrent access becomes a bottleneck.

**Why local execution instead of cloud?**
The Ethereum private key never leaves the operator's machine. A cloud deployment would require a secrets manager and additional attack surface. Trade-off: no mobile access without a tunnel (Cloudflare/ngrok — in backlog).

**Why separate processes per bot?**
Each bot can crash, restart, or be paused independently. The dashboard monitors PIDs and last-activity timestamps to detect crashed bots (threshold: 65 minutes without positions.json update).

**Why Python instead of Go/Rust?**
Rapid iteration: the entire system was built over ~3 months. Python's ecosystem (Web3.py, asyncio, httpx) covers all requirements. Latency is not a constraint — a 5-minute scan cycle has no sub-second SLA.
