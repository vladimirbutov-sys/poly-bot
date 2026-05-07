# Backlog

Priority: 🔴 Critical → 🟡 Important → 🟢 Nice to have

---

## 🔴 P0 — Web Dashboard (Sprint 7)

| ID | Feature | Notes |
|----|---------|-------|
| D-1 | War markets live table | price, volume, days-to-resolve, last spike |
| D-2 | Top traders leaderboard | war P&L, ROI, trade count |
| D-3 | Spike history feed | last 50 alerts, strategy, outcome |
| D-4 | Strategy stats panel | A vs B win rate, reversion rate, verdict |
| D-5 | Supabase ETL script | sync spike_bot.db + war DBs → PostgreSQL |
| D-6 | Vercel deployment | CI/CD from GitHub |
| D-7 | Live price refresh | poll Gamma API from frontend every 60s |

---

## 🔴 P0 — Auto Function Calling (Sprint 8)

| ID | Feature | Notes |
|----|---------|-------|
| F-1 | Tool: `get_top_holders(market_id)` | read war_holders.db |
| F-2 | Tool: `get_recent_trades(market_id, minutes)` | CLOB API |
| F-3 | Tool: `get_trader_pnl(wallet)` | lookup good_players table |
| F-4 | Auto-trigger on HIGH tier alerts | skip MED/LOW to save cost |
| F-5 | AI narrative in Telegram message | replaces /analyze manual call |
| F-6 | Structured output with confidence | JSON schema enforcement |

---

## 🟡 P1 — Mobile App (Sprint 9)

| ID | Feature | Notes |
|----|---------|-------|
| M-1 | Alert feed screen | pulls from dashboard API |
| M-2 | Market detail card | price chart, top holders, strategy |
| M-3 | Push notifications | Expo Notifications |
| M-4 | Filter by strategy/tier | A_MOMENTUM / B_FADE / war only |
| M-5 | iOS + Android builds | via Expo Go for demo |

---

## 🟡 P1 — Spike Bot Improvements

| ID | Feature | Notes |
|----|---------|-------|
| S-1 | Update Claude model to `claude-sonnet-4-6` | currently uses old model ID |
| S-2 | Use official Anthropic SDK (not raw httpx) | cleaner, supports tool_use natively |
| S-3 | Auto-close trades at resolution | check end_date, pull resolution price |
| S-4 | `/stats` dashboard link | send URL when user requests stats |
| S-5 | Threshold auto-calibration | adjust if alert rate too high/low |
| S-6 | WebSocket mode for war markets | faster than polling for high-volatility |

---

## 🟡 P1 — Copy Trader Improvements

| ID | Feature | Notes |
|----|---------|-------|
| C-1 | Merge→exit rule re-backtest | initial test: 50% WR, 6 samples — need more data |
| C-2 | Scotty copybot calibration | analyse 67 Trump positions, tune EV weights |
| C-3 | Add ScottyNooo to tracked wallets | +$1.18M P&L, strong on Trump decisions |
| C-4 | Wallet scoring auto-refresh | re-score weekly, remove stale wallets |

---

## 🟢 P2 — Research & Analytics

| ID | Feature | Notes |
|----|---------|-------|
| R-1 | Strategy A/B backtest report | 50+ alerts → statistical significance |
| R-2 | Best entry timing analysis | immediate vs 5-min delay after spike |
| R-3 | War market calendar | known events, expected volatility windows |
| R-4 | Competitor tracker | monitor other Polymarket tools/bots |
| R-5 | PnL attribution by category | war / elections / macro / sports |

---

## 🟢 P2 — Infrastructure

| ID | Feature | Notes |
|----|---------|-------|
| I-1 | GitHub Actions CI | lint + test on push |
| I-2 | Bot health monitoring | alert if bot silent > 30 min |
| I-3 | Log rotation | current logs grow unbounded |
| I-4 | Multi-environment config | dev / staging / prod |
| I-5 | Secrets rotation guide | X API, Telegram, Anthropic |

---

## Completed ✅

- [x] Spike detection with tier system
- [x] Dual strategy classifier (A_MOMENTUM / B_FADE)
- [x] Twitter + News context collection
- [x] Orderbook pattern detection
- [x] Whale wallet tracking
- [x] Claude AI manual review (/analyze)
- [x] War markets database (1.1M trades)
- [x] Copy trader with EV scoring
- [x] Arb scanner (YES+NO merge)
- [x] Oil swing bot
- [x] Dispute monitor
- [x] P&L tracking in SQLite
