# Polymarket Automated Trading System

Production-grade algorithmic trading system for Polymarket — a decentralized prediction market on Polygon blockchain. Built end-to-end as a personal project: product concept → PRD → implementation → live deployment.

**[Live Dashboard →](https://poly-bot-green.vercel.app)** · **[Full PRD →](PRD%20Poly.md)** · **[Roadmap →](ROADMAP.md)**

---

## Results (Production)

| Metric | Value |
|--------|-------|
| Trades executed | 881 |
| Win rate | 96% |
| Markets scanned per cycle | 500+ |
| Scan interval | 5 minutes |
| Redemption latency | < 10 min after resolution |

---

## What It Does

Scans all open Polymarket prediction markets every 5 minutes, identifies mispriced near-certain outcomes trading at 96–99.5¢, places limit orders via CLOB API, and automatically redeems winning positions on-chain. A web dashboard provides real-time portfolio visibility and manual controls.

**The market inefficiency:** Near-resolution markets (end date ≤ 3 days) where the outcome is effectively decided but price hasn't reached $1.00 yet due to limited liquidity and information lag — a systematic, repeatable edge.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     TRADING ENGINE (Python)                      │
│                                                                  │
│   scanner.py          ←──── Gamma API (market data, prices)     │
│       │                                                          │
│       ▼                                                          │
│   filters.py (14x)    ←──── CLOB API (orderbook bid/ask)        │
│       │                                                          │
│       ▼                                                          │
│   executor.py         ────► CLOB API (place/cancel orders)      │
│       │                                                          │
│       ▼                                                          │
│   redeemer.py         ────► Polygon RPC (on-chain redemption)   │
│       │                                                          │
│       ▼                                                          │
│   telegram_notify.py  ────► Telegram Bot API                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
                   │
                   │ reads positions.json
                   ▼
┌──────────────────────────────────────────────────────────────────┐
│              DASHBOARD (Next.js + FastAPI)                       │
│                                                                  │
│  Real-time P&L · Bot controls · Position table · Live logs      │
│  Manual sell · Config editor · SSE log streaming                │
│                                                                  │
│  Deployed: Vercel (frontend) + local FastAPI (backend)          │
└──────────────────────────────────────────────────────────────────┘
```

---

## API Integrations

### Gamma API (Polymarket market data)
- `GET /markets?limit=500&closed=false` — paginated market feed
- Returns: price, liquidity, volume, end_date, neg_risk flag, category

### CLOB API (Central Limit Order Book)
- `GET /book?token_id=` — live orderbook (bid/ask)
- `POST /order` — place limit order
- `GET /order/:id` — poll order status (filled / partial / open)
- `DELETE /order/:id` — cancel order
- Auth: ECDSA signature (L1 Ethereum key)

### Polygon Blockchain (RPC)
- `balanceOf()` on CTF Exchange — verify conditional token balance
- `redeemPositions()` — on-chain settlement after market resolution
- CTF Exchange: `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`
- NegRiskAdapter: `0xd91e80cf2e7be2e162c6513ced06f1dd0da35296`

---

## Risk Filter System (14 Layers)

Every candidate market passes through 14 sequential filters before an order is placed:

| # | Filter | What it blocks |
|---|--------|----------------|
| 1 | Price range | Outside 96–99.5¢ |
| 2 | Liquidity | < $500 market liquidity |
| 3 | Volume | < $500 total traded |
| 4 | Expiry window | > 3 days to resolution |
| 5 | Duplicate | Already have open position |
| 6 | Sub-match | Game 1 / Map 2 style markets |
| 7 | Elections | Binary political outcome markets |
| 8 | Slow keywords | "season", "weekly", "most" |
| 9 | Coin-flip | "odd or even", "first blood" |
| 10 | Price threshold | "close above $X", "reach $Y" |
| 11 | Cancelled events | Match started >6h ago, unresolved |
| 12 | Neg-risk cap | Frozen capital in neg-risk ≥ $350 |
| 13 | Low-liq financials | BTC/ETH markets with vol < $50K |
| 14 | Price divergence | Gamma vs CLOB spread > 3¢ |

---

## Order Lifecycle

```
Market passes all 14 filters
    │
    ▼
Fetch live CLOB orderbook → calculate limit price (ask + slippage)
    │
    ▼
Check portfolio limits (total frozen ≤ $1,000)
    │
    ▼
POST /order → CLOB API (limit BUY, TTL = 5 min)
    │
    ├── MATCHED → record position, Telegram alert
    ├── PARTIAL → record partial, return remainder to balance
    └── TIMEOUT → cancel order, verify on-chain balance
                  (CLOB sometimes fills on-chain without response)
    │
    ▼
[Background thread] Poll every 5 min: is market resolved on-chain?
    │
    ├── payoutDenominator > 0 → call redeemPositions() on Polygon
    └── Not yet → continue polling
```

---

## Position Data Model

```json
{
  "positions": {
    "<order_id>": {
      "condition_id": "0x...",
      "token_id": "12345...",
      "title": "Will ceasefire hold through Sunday?",
      "outcome": "Yes",
      "category": "geopolitics",
      "entry_price": 0.971,
      "size_shares": 20.59,
      "cost_usd": 20.00,
      "status": "open",
      "end_date": "2026-04-30T23:59:59Z",
      "neg_risk": false,
      "pnl": null
    }
  },
  "stats": {
    "total_bets": 881,
    "wins": 839,
    "losses": 26,
    "total_pnl": 457.23
  }
}
```

---

## Bot Ecosystem

| Bot | Strategy | Status |
|-----|----------|--------|
| `98_sure_bot` | Near-certain market scanner (96–99.5¢) | ✅ Production |
| `25_multi_signal_copybot` | Copy top wallets with EV scoring | ✅ Production |
| `10_oil_swing_bot` | WTI oil prediction market swing | ✅ Production |
| `21_arb_scanner` | YES+NO arbitrage detection | ✅ Production |
| `26_whale_tracker` | Smart money real-time tracking | ✅ Production |
| `22_dispute_monitor` | UMA resolution dispute alerts | ✅ Production |

---

## Dashboard

Live at: **[poly-bot-green.vercel.app](https://poly-bot-green.vercel.app)**

Built with Next.js 15 + Tailwind (frontend) and FastAPI (backend). Features:
- Real-time portfolio metrics (P&L, win rate, open positions, frozen capital)
- Position table with live prices fetched in parallel (5 workers)
- Manual sell via CLOB API directly from UI
- Bot start/stop/restart controls
- Live log streaming via Server-Sent Events (SSE)
- Config editor (bet sizes, price thresholds, portfolio limits)

---

## Stack

| Layer | Technology |
|-------|-----------|
| Trading engine | Python · asyncio · concurrent.futures |
| Blockchain | Web3.py · Polygon PoS · Smart Contracts |
| Order management | Polymarket CLOB API (ECDSA auth) |
| Market data | Gamma API · WebSocket |
| Frontend | Next.js 15 · Tailwind CSS |
| Backend API | FastAPI |
| Notifications | Telegram Bot API |
| Deployment | Vercel (frontend) |
| Storage | JSON (positions) · SQLite (history) |

---

## Security

- Private key: stored only in `.env`, never in code or UI
- `.env` is in `.gitignore` and never committed
- Bot runs on localhost only — no external ports exposed
- Nonce conflicts on Polygon: mitigated with 5s delay between transactions + retry

---

## Product Documentation

- [PRD v2.0](PRD%20Poly.md) — full product requirements, architecture decisions, data models, risk matrix
- [Roadmap](ROADMAP.md) — 9 sprints, 11 completed milestones, backlog
- [Backlog](BACKLOG.md) — prioritized P0–P2 feature list

---

## Quick Start

```bash
git clone https://github.com/vladimirbutov/polymarket-trading-system
cd polymarket-trading-system/Bots/98_sure_bot

pip install -r requirements.txt
cp .env.example .env
# Add: PRIVATE_KEY, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

python main.py
```

---

*Built by [Vladimir Butov](https://linkedin.com/in/vladimirbutov) · 2024–2026*
