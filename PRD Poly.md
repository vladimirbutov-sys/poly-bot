# PRD: 98_SURE_BOT + Dashboard
### Product Requirements Document

**Version:** 2.0
**Date:** 2026-05-05
**Author:** Vladimir Butov
**Status:** MVP — in production

---

## Table of Contents

1. [Context and Problem](#1-context-and-problem)
2. [Product Solution](#2-product-solution)
3. [Users and Use Cases](#3-users-and-use-cases)
4. [Goals and Success Metrics](#4-goals-and-success-metrics)
5. [System Architecture](#5-system-architecture)
6. [Component 1 — Trading Bot (98_sure_bot)](#6-component-1--trading-bot-98_sure_bot)
7. [Component 2 — Web Dashboard](#7-component-2--web-dashboard)
8. [Integrations and Infrastructure](#8-integrations-and-infrastructure)
9. [Data Model](#9-data-model)
10. [Non-Functional Requirements](#10-non-functional-requirements)
11. [Security](#11-security)
12. [Roadmap](#12-roadmap)
13. [Risks and Mitigation](#13-risks-and-mitigation)
14. [Open Questions](#14-open-questions)

---

## 1. Context and Problem

### What is Polymarket

Polymarket is a decentralised prediction market where users trade probabilities on real-world events. Each market has a YES/NO outcome, and the share price (1¢ to 99¢) reflects the collective probability estimate. On resolution:
- The winning share pays **$1.00**
- The losing share pays **$0.00**

**Example:** A market "Will peace talks conclude by Friday?" trades at 97¢. If talks conclude — payout is $1.00, profit is 3¢ per share (~3.1% ROI in a few days).

### Market Inefficiency

Markets trading in the 96–99.5¢ range systematically create near-risk-free trading opportunities when two conditions hold:
1. The market is **close to resolution** (end_date ≤ 3 days)
2. The outcome is **effectively decided** — but the market hasn't reached $1.00 yet due to:
   - Limited liquidity
   - Information lag
   - Market makers unwilling to move price all the way to 100%

### Problem

Manually tracking thousands of Polymarket markets, filtering truly certain outcomes from seemingly certain ones, and placing orders before resolution — is physically impossible. Without automation, this opportunity is lost every 5 minutes.

Additionally: without a centralised dashboard, the operator doesn't know the real portfolio state — open positions, P&L, stuck orders — without manually parsing JSON files and logs.

---

## 2. Product Solution

The system consists of two linked components:

**Component A — 98_sure_bot** — a Python trading bot that:
- Scans all open Polymarket markets every 5 minutes
- Applies 14 filters to eliminate risky markets
- Automatically places limit buy orders via the CLOB API
- Automatically redeems (claims) winning positions on the Polygon blockchain
- Notifies the operator via Telegram on every event

**Component B — Dashboard** — a web application for the operator:
- Shows bot and portfolio status in real time
- Allows starting and stopping the bot with one button
- Displays all positions with current prices and P&L
- Allows manual position selling from the interface
- Provides log and settings access without a terminal

---

## 3. Users and Use Cases

### 3.1 Operator (primary user)

A person running the bot on their machine. Trading with their own funds. Technical level: intermediate — able to run a Python script, but doesn't want to constantly watch the terminal.

**Key scenarios:**

| Scenario | Frequency | How the system handles it |
|----------|-----------|--------------------------|
| Check if bot is running | Several times a day | Dashboard: status indicator + last activity time |
| View today's P&L | Daily | Dashboard: portfolio metrics + positions table |
| Get notified of a new bet | At the moment it happens | Telegram notification |
| Sell a position early | As needed | Dashboard: sell button with price input |
| Change bet size | Rarely | Dashboard: config editor |
| Debug why bot isn't betting | As needed | Dashboard: log viewer |

### 3.2 Observer (secondary user)

An investor, HR specialist, or mentor who wants to understand what the system does and evaluate results. Does not interact with the bot — only views the dashboard and reports.

---

## 4. Goals and Success Metrics

### Business Goals

| Goal | Metric | Target |
|------|--------|--------|
| Profitability | Win rate on closed positions | ≥ 85% |
| Capital efficiency | Capital turnover per month | ≥ 5× starting balance |
| Autonomy | Hours of manual intervention per week | ≤ 1 hour |
| Risk control | Maximum drawdown per month | ≤ 10% of balance |
| Fill rate | Share of placed orders that filled | ≥ 60% |

### Product Metrics

| Metric | Target |
|--------|--------|
| Latency from market appearance to order | ≤ 5 minutes |
| Dashboard update latency | ≤ 30 seconds |
| Redemption time after resolution | ≤ 10 minutes |
| Bot uptime (% of running time) | ≥ 95% |

---

## 5. System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     LOCAL MACHINE (Windows 11)                   │
│                                                                  │
│   ┌─────────────────────────────────┐                           │
│   │        98_sure_bot (Python)     │                           │
│   │                                 │                           │
│   │  main.py ──► scanner.py         │ ◄── Gamma API             │
│   │      │       (fetch markets)    │     (markets, prices)     │
│   │      ▼                          │                           │
│   │  filters.py                     │ ◄── CLOB API              │
│   │  (14 filters)                   │     (orderbook, orders)   │
│   │      │                          │                           │
│   │      ▼                          │ ──► Polygon RPC           │
│   │  executor.py                    │     (blockchain, redeem)  │
│   │  (limit orders)                 │                           │
│   │      │                          │ ──► Telegram              │
│   │      ▼                          │     (notifications)       │
│   │  tracker.py                     │                           │
│   │  positions.json ◄──── redeemer.py                          │
│   │  bot_log.txt                    │                           │
│   └─────────────────────────────────┘                           │
│                   │                                              │
│                   │ reads files                                  │
│                   ▼                                              │
│   ┌─────────────────────────────────┐                           │
│   │     Dashboard (Next.js + FastAPI)│                          │
│   │                                 │                           │
│   │  app.py                         │ ◄── Gamma API             │
│   │  bot_manager.py (start/stop)    │     (current prices)      │
│   │  data_reader.py (positions)     │                           │
│   │  price_fetcher.py               │ ──► CLOB API              │
│   │  trade_executor.py (sell)       │     (sell orders)         │
│   │  settings_editor.py             │                           │
│   │                                 │                           │
│   │  http://localhost:8080          │                           │
│   └─────────────────────────────────┘                           │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘

Operator browser ──► http://localhost:8080
```

### Key Architectural Decisions

**Local execution, not cloud.** The wallet private key never leaves the operator's machine. The bot runs as a regular Python process. This sacrifices convenience (no phone access) for security.

**JSON as database.** State is stored in `positions.json`. No DBMS needed, no server — the file is read by the dashboard directly. Simplicity beats scalability at MVP level.

**Next.js for dashboard.** Allows building a modern web interface with a clean API layer. The operator opens one URL and gets a full portfolio view.

---

## 6. Component 1 — Trading Bot (98_sure_bot)

### 6.1 Operating Cycle (every 5 minutes)

```
Start cycle
    │
    ▼
[scanner.py] Load all open Polymarket markets
    │        (Gamma API, paginated by 500 markets)
    │
    ▼
Filter by price range: 96.0¢ – 99.5¢
    │
    ▼
[filters.py] Apply 14 filters to each candidate
    │
    ▼
Sort:
    1. Strike markets today (match/event happening today)
    2. By end_date ASC (nearest to resolution first)
    │
    ▼
For each candidate that passed:
    │
    ├── Check USDC balance
    ├── Fetch current price from CLOB orderbook
    ├── Check price divergence Gamma vs CLOB (≤ 3¢)
    ├── Calculate limit price (price + slippage buffer)
    ├── Check portfolio limits (total_frozen ≤ $1000)
    ├── Calculate bet size (depends on market type)
    └── Place limit BUY order on CLOB
            │
            ▼
    Record position in positions.json (status: open)
    Send Telegram notification
            │
            ▼
    [Background thread] Track order status (every 5 sec)
            │
            ├── MATCHED → update position (status: filled)
            ├── PARTIAL → update size, return difference to balance
            └── TIMEOUT (5 min) → cancel order
                    │
                    └── Check on-chain balance
                        (bot sometimes fills on-chain but CLOB doesn't respond)

[Background redeemer thread] Every 5 minutes:
    For each open position:
        ├── Check if market resolved on-chain (payoutDenominator > 0)
        ├── Check conditional token balance
        └── If resolved → send redeem transaction on Polygon
                │
                ├── Win → update balance, status: won
                └── Loss → record loss, status: lost
```

### 6.2 Filter System (14 filters)

Each filter takes market data and returns `(passed: bool, reason: str)`.

| # | Filter | Block condition |
|---|--------|----------------|
| 1 | **Price range** | Price < 96% (politics) or < 96.5% (others), or > 99.5% |
| 2 | **Liquidity** | Market liquidity < $500 |
| 3 | **Volume** | Total traded volume < $500 |
| 4 | **Resolution date** | end_date > 3 days ahead or expired > 3 days ago |
| 5 | **Duplicate position** | Already have open position with this condition_id |
| 6 | **Sub-match** | Market on specific game/map/set ("game 1", "map 2") |
| 7 | **Elections** | Markets of type "will candidate X win" (binary uncertainty) |
| 8 | **Slow markets** | Keywords: "top", "most", "season", "weekly" |
| 9 | **Coin-flip patterns** | "odd or even", "first blood", "first baron", "coin flip" |
| 10 | **Threshold markets** | "close above $X", "reach $Y", "dip to", "pump to" |
| 11 | **Cancelled sports events** | Match started > 6 hours ago and market not resolved |
| 12 | **Neg-risk limit** | Frozen capital in neg-risk positions ≥ $350 |
| 13 | **Financial assets** | BTC/ETH/stocks with volume < $50K (low liquidity, volatility) |
| 14 | **Price divergence** | Gap between Gamma API price and CLOB price > 3¢ |

**Additional regex blocks:**
- Toxic keywords: "earthquake", "tornado", "number of views", "total goals"
- Non-WIN sports markets: handicap, over/under, spread
- Delayed resolution markets: "not released by Dec 31", "as of Q4"

### 6.3 Trading Parameters

**Bet sizes by market type:**

| Market type | Bet size | Rationale |
|-------------|----------|-----------|
| Regular market | $20 | Base size |
| Neg-risk market | $15 | Reduced (smaller bet) |
| Weather market | $10 | Higher uncertainty |
| Slow-keyword market | $5 | Test size for ambiguous markets |
| Price 96.5–97.5% (test) | $5 | Lower price range under monitoring |

**Slippage table (allowed deviation when placing order):**

| Price range | Max slippage | Logic |
|-------------|-------------|-------|
| 96.0¢ – 97.5¢ | +0.5¢ | Higher ROI covers slippage |
| 97.5¢ – 98.5¢ | +0.4¢ | |
| 98.5¢ – 99.0¢ | +0.3¢ | |
| 99.0¢ – 99.5¢ | +0.3¢ | Minimum ROI — be cautious |

**Portfolio limits:**

| Parameter | Value |
|-----------|-------|
| Maximum frozen capital (total) | $1,000 |
| Maximum in neg-risk positions | $350 |
| Maximum share of politics markets | 30% of balance |
| Minimum USDC remaining | = bet size |

**Order lifecycle:**
- Order TTL (until cancellation): 5 minutes
- Status check interval: every 5 seconds
- On timeout: cancel remainder → check on-chain balance

### 6.4 Telegram Notifications

The bot sends messages on every significant event:

| Event | Contents |
|-------|---------|
| Startup | Balance, number of open positions |
| New bet | Market name, price, amount, order_id |
| Order filled | Name, execution price, number of shares, total cost |
| Partial fill | How many filled out of total shares |
| Order cancelled | Cancellation reason |
| 8-hour report | Balance, P&L, win rate, open positions |
| Error | Exception description |

### 6.5 Modular Bot Structure

```
98_sure_bot/
├── main.py             ← Main loop, orchestration
├── scanner.py          ← Fetch markets from Gamma API
├── filters.py          ← 14 exclusion filters
├── executor.py         ← Order placement and tracking (CLOB)
├── tracker.py          ← Write P&L to positions.json
├── redeemer.py         ← Automatic on-chain win redemption
├── telegram_notify.py  ← Send notifications
├── config.py           ← All trading parameters
├── .env                ← Secrets (key, Telegram token)
├── positions.json      ← Position database
└── bot_log.txt         ← All events log
```

---

## 7. Component 2 — Web Dashboard

### 7.1 Overview

The dashboard is a web application (Next.js) that provides a real-time visual interface without needing to look at the terminal or parse JSON manually.

The dashboard reads `positions.json` from the bot and serves it via a FastAPI backend.

**Live demo:** [poly-bot-green.vercel.app](https://poly-bot-green.vercel.app)

### 7.2 Interface Sections

#### Section 1: Bot Cards

Each bot is displayed as a card with status:
- **Status indicator:** ✓ Running (green) / ✗ Stopped / ⚠ Crashed
- **Process PID** (if running)
- **Last activity time** — when data_file was last updated
- **Buttons:** Start / Stop / Restart

If data_file hasn't updated for > 65 minutes — status is "crashed", even if the process is formally alive. Covers the scenario where the bot is stuck inside a cycle.

#### Section 2: Portfolio Metrics

Four real-time KPI cards:
- **Current USDC balance** — liquid funds
- **Total P&L** — profit/loss across all closed positions
- **Frozen capital** — total in open positions
- **Open positions** — count

#### Section 3: All Positions Table

Unified position table from all bots:

| Column | Contents |
|--------|---------|
| Bot | Bot identifier |
| Market name | Full question title (truncated) |
| Outcome | YES / NO |
| Entry price | Purchase price (¢) |
| Current price | Live price from Gamma API (updated on button click) |
| Shares | Number of shares |
| Invested | Amount in dollars |
| P&L | Difference: (current price - entry price) × shares |
| Status | open / won / lost / cancelled |
| Sell button | Opens manual sell dialog |

#### Section 4: Manual Position Selling

Dialog with fields:
- Sell price (¢) — operator enters target price
- Sell button → places GTC SELL order via CLOB API

Before placing a new order, all existing SELL orders for this token are automatically cancelled.

#### Section 5: Config Editor

Edit bot parameters directly from the UI without opening files:
- `PRICE_THRESHOLD` — minimum price threshold
- `BET_SIZE_*` — bet sizes
- `MAX_*_FROZEN` — capital limits
- Other parameters from `config.py`

After saving, the bot needs to restart for changes to take effect.

#### Section 6: Log Viewer

Displays the last lines of `bot_log.txt` in real time directly in the browser. Allows diagnosing issues without opening a terminal. Implemented via Server-Sent Events (SSE).

### 7.3 Bot Management (bot_manager.py)

```
Start bot:
  subprocess.Popen(["python", "main.py"])
  with CREATE_NEW_PROCESS_GROUP (Windows — for correct kill)
  PID saved in pids.json

Stop bot:
  psutil.Process(pid).terminate()
  If not terminated within 5 sec → kill()

Detecting "crashed":
  Check data_file (positions.json) modification time
  If > 65 minutes → status: crashed
  (65 min: bots with hourly scans shouldn't trigger false crashed)
```

### 7.4 Fetching Current Prices (price_fetcher.py)

- Parallel requests to Gamma API via ThreadPoolExecutor (5 workers)
- 2-minute cache (avoid spamming API on frequent refresh)
- Progress callback: shows how many prices loaded out of total
- Fallback to on-chain balances via Polygon RPC for verification

### 7.5 Dashboard Structure

```
dashboard/
├── app.py                ← Main Next.js / FastAPI application
├── config.py             ← Bot paths and their configs
├── bot_manager.py        ← Process start/stop
├── data_reader.py        ← Read positions.json, normalise
├── price_fetcher.py      ← Fetch current prices from API
├── trade_executor.py     ← Place SELL orders
├── settings_editor.py    ← Edit bot config.py
├── onchain_reality.py    ← Reconcile tracker.json vs on-chain
├── pids.json             ← Saved PIDs of running bots
└── logs/                 ← stdout/stderr of each bot
```

---

## 8. Integrations and Infrastructure

### 8.1 Gamma API (Polymarket)

**Base URL:** `https://gamma-api.polymarket.com`

| Endpoint | Usage |
|----------|-------|
| `GET /markets?limit=500&closed=false` | Fetch all open markets |
| `GET /markets?token_id=...` | Fetch specific market data |

Returns: price, liquidity, volume, category, end_date, game_start_time, neg_risk flag.

### 8.2 CLOB API (Polymarket)

**Base URL:** `https://clob.polymarket.com`

| Endpoint | Usage |
|----------|-------|
| `GET /book?token_id=...` | Fetch orderbook (bid/ask) |
| `POST /order` | Place order |
| `GET /order/:id` | Check order status |
| `DELETE /order/:id` | Cancel order |
| `GET /orders` | List open orders |

Authentication: ECDSA signature (L1 auth via Ethereum private key).

### 8.3 Polygon Blockchain (RPC)

**Network:** Polygon PoS, Chain ID 137
**RPC:** `https://polygon.gateway.tenderly.co`

| Operation | Contract | Purpose |
|-----------|---------|---------|
| `balanceOf(token_id)` | CTF Exchange | Check conditional token balance |
| `redeemPositions()` | CTF Exchange | Claim winnings (regular markets) |
| `redeemPositions()` | NegRiskAdapter | Claim winnings (neg-risk markets) |
| `balanceOf(wallet)` | USDC Contract | Check USDC balance |

**Key addresses:**
- CTF Exchange: `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`
- USDC (Polygon): `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
- NegRiskAdapter: `0xd91e80cf2e7be2e162c6513ced06f1dd0da35296`

### 8.4 Telegram Bot API

Notifications sent via `https://api.telegram.org/bot{token}/sendMessage`.
Rate limit: 0.5 seconds between messages.

---

## 9. Data Model

### 9.1 Position (positions.json)

```json
{
  "positions": {
    "<order_id>": {
      "condition_id": "0x...",
      "token_id": "12345...",
      "title": "Will peace talks conclude by Friday?",
      "outcome": "Yes",
      "category": "geopolitics",
      "entry_price": 0.971,
      "size_shares": 20.59,
      "cost_usd": 20.00,
      "filled_shares": 20.59,
      "status": "open",
      "timestamp": "2026-04-28T14:32:00+00:00",
      "end_date": "2026-04-30T23:59:59Z",
      "pnl": null,
      "neg_risk": false
    }
  },
  "stats": {
    "current_balance": 8750.00,
    "total_bets": 881,
    "wins": 839,
    "losses": 26,
    "total_pnl": 457.23
  }
}
```

**Possible position statuses:**

| Status | Meaning |
|--------|---------|
| `open` | Order open, not yet resolved |
| `won` | Market resolved in our favour, funds received |
| `lost` | Market resolved against us |
| `cancelled` | Order cancelled (unfilled), position voided |

### 9.2 Bot Configuration (config.py)

All trading parameters stored in one file and editable via dashboard or directly:

```python
PRICE_THRESHOLD_DEFAULT   = 0.965  # minimum price (regular markets)
PRICE_THRESHOLD_POLITICS  = 0.960  # minimum price (politics)
MAX_PRICE                 = 0.995  # maximum price (above this ROI too small)

BET_SIZE_REGULAR          = 20.00  # regular markets
BET_SIZE_NEG_RISK         = 15.00  # neg-risk markets
BET_SIZE_WEATHER          = 10.00  # weather markets
BET_SIZE_TEST_LOW         = 5.00   # markets 96.5–97.5%

MAX_TOTAL_FROZEN          = 1000   # frozen capital limit
MAX_NEG_RISK_FROZEN       = 350    # neg-risk cap
MAX_POLITICS_FRACTION     = 0.30   # max 30% of balance in politics

SCAN_INTERVAL             = 300    # seconds between scans (5 min)
ORDER_TTL_SECONDS         = 300    # order TTL (5 min)
MIN_SHARES                = 5      # minimum shares per order
MIN_LIQUIDITY             = 500    # minimum market liquidity
```

---

## 10. Non-Functional Requirements

| Requirement | Target | Details |
|------------|--------|---------|
| Scan latency | ≤ 5 min | Missing a market = lost bet |
| Fill-check latency | ≤ 5 sec | Partial fills need fast detection |
| Redemption latency | ≤ 10 min after resolution | Capital must return quickly |
| Dashboard update | ≤ 30 sec | Poll positions.json |
| Price loading in UI | ≤ 15 sec | Parallel requests (5 workers) |
| Bot uptime | ≥ 95% | Manual restart on crash |
| RAM usage | ≤ 200 MB | Bot + dashboard together |
| Write reliability | 100% | positions.json must always be consistent |

---

## 11. Security

### Secrets Storage
- Wallet private key and Telegram token — **only in `.env`**
- `.env` is in `.gitignore` and **never committed**
- Dashboard does not display the private key in the UI

### Isolation
- Bot and dashboard run on localhost only
- No open ports for external access
- Polygon RPC — public endpoint, no authorisation required

### Minimal Permissions
- Bot runs as a regular Windows user (not administrator)
- Only permission: send transactions from one wallet

### Transaction Risks
- Nonce conflicts during parallel redemption: resolved with 5-second delay between transactions + retry
- Gas price: standard gas used without acceleration (Polygon is cheap)

---

## 12. Roadmap

### Completed (MVP)

| Milestone | Description |
|-----------|-------------|
| ✅ M1 | Basic bot: scan → filter → place order |
| ✅ M2 | Telegram notifications for all events |
| ✅ M3 | Automatic win redemption |
| ✅ M4 | Tracker: P&L recording, statistics |
| ✅ M5 | 14 filters to exclude risky markets |
| ✅ M6 | Dashboard: position view and bot management |
| ✅ M7 | Manual position selling from UI |
| ✅ M8 | Config editor in dashboard |
| ✅ M9 | 8-hour reports + daily strategy analysis |
| ✅ M10 | Web dashboard (Next.js) with Vercel deployment |
| ✅ M11 | Real-time logs via SSE |

### Backlog (v2)

| Priority | Task | Rationale |
|----------|------|-----------|
| P0 | Auto-restart on crash | Currently requires manual intervention |
| P0 | Telegram alert on crash | Operator unaware of issues |
| P1 | SQLite instead of JSON | JSON doesn't reliably support concurrent access |
| P1 | Backtesting UI | Currently backtest = separate Python scripts |
| P1 | Cloud dashboard deployment (with tunnel) | Phone access without VPN |
| P2 | Mobile app / Telegram bot for management | Start/stop from phone |
| P2 | Portfolio analytics by category | Already exists in Next.js dashboard |
| P2 | A/B strategy testing (two bots, different params) | Compare approaches |

---

## 13. Risks and Mitigation

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|-----------|
| 98% market resolves against us | Low | Medium | 14 filters; loss capped at $5–20 |
| CLOB unresponsive, shares already on-chain | Medium | Medium | On-chain balance check after timeout |
| Gamma API returns stale price | Medium | Medium | Cross-check with CLOB; skip if divergence > 3¢ |
| Nonce conflict on redemption | Medium | Low | Delay between transactions + retry |
| Bot hangs in infinite wait | Medium | Medium | ORDER_TTL_SECONDS = 300; health check in dashboard |
| Private key leak | Very Low | Critical | `.env` + `.gitignore`; not in code, not in dashboard |
| Insufficient liquidity to fill | High | Low | Partial fills are normal; remainder returned |
| Polymarket changes API | Medium | High | Modular architecture; update only scanner/executor |

---

## 14. Open Questions

1. **Auto-restart:** Configure Windows Task Scheduler or watchdog process for bot restart on crash. When to implement?

2. **Data scale:** With > 1000 positions, JSON reading will slow down. Switch to SQLite immediately or wait?

3. **Cloud dashboard access:** Cloudflare Tunnel or ngrok would allow opening the dashboard from a phone. Needed?

4. **Multi-wallet:** Run the bot with multiple wallets to increase bet volume?

5. **Tax reporting:** How to export P&L history in a format understandable to an accountant?

---

*Document reflects system state as of 2026-05-05. Current configuration parameters are in the bot's `config.py` file.*
