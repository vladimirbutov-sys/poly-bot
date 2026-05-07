# Roadmap

## ✅ Sprint 1 — Foundation (Complete)
*Goal: first working alert in Telegram*

- [x] Gamma API integration — fetch live market prices
- [x] Basic spike detection (price delta over time window)
- [x] Telegram bot with alert formatting
- [x] SQLite persistence for price snapshots (survive restarts)
- [x] `.env`-based configuration, Docker-ready

**Outcome:** Bot running 24/7, catching spikes, sending alerts.

---

## ✅ Sprint 2 — Context Layer (Complete)
*Goal: alerts with explanation, not just numbers*

- [x] Twitter/X API integration — keyword tiers (Tier1: Reuters/AP, Tier2: analysts)
- [x] Google News RSS — headline collection per spike
- [x] Phrase-based keyword matching (e.g. "US Iran strike" vs "Iran")
- [x] CLOB API — orderbook pattern detection (single_large / series / mixed)
- [x] Whale wallet tracker — correlate smart money to spike direction

**Outcome:** Each alert includes news sources, orderbook pattern, whale activity.

---

## ✅ Sprint 3 — Dual Strategy (Complete)
*Goal: tell the trader what to DO, not just what happened*

- [x] Momentum scoring (0–10): news, sources, trades, whale alignment
- [x] Fade scoring (0–10): no-news, single order, high liquidity
- [x] Strategy A (Momentum): BUY in direction, target +50% of move
- [x] Strategy B (Fade): BUY against direction, target 50% revert
- [x] Entry / Target / Stop price calculation
- [x] Confidence level (HIGH / MEDIUM / LOW)

**Outcome:** Every alert has a clear trade recommendation.

---

## ✅ Sprint 4 — AI Review Layer (Complete)
*Goal: independent second opinion on each signal*

- [x] Claude API integration via `/analyze` command
- [x] System prompt: resolution criteria → strategy eval → probability estimate → EV
- [x] Structured output: agrees/disagrees with bot strategy, independent probability
- [x] Build prompt from all context (alert + strategy + news + orderbook + whale)

**Outcome:** On-demand AI analysis of any alert in ~5 seconds.

---

## ✅ Sprint 5 — War Markets (Complete)
*Goal: dedicated intelligence on high-volatility geopolitical markets*

- [x] War market classifier (Iran, Ukraine, China — 4 keyword tiers)
- [x] Full trade history download: 1,137,500 trades across 7,053 wallets
- [x] Good player scoring: profit > $5K + 10+ war trades
- [x] `war_holders.db` + `war_markets.db` built and indexed
- [x] Top holder pre-load per market for sub-second spike response

**Outcome:** 325 war markets monitored, smart money pre-indexed.

---

## ✅ Sprint 6 — Copy Trader Ecosystem (Complete)
*Goal: follow profitable wallets automatically*

- [x] Multi-signal copy bot (25_multi_signal_copybot)
- [x] EV scoring model: 7 signals, weighted
- [x] Tracks: Domer, 50pence, fhantom, car, theo4, aenews2 + 3 more
- [x] Merge/exit rule backtested
- [x] Oil swing bot, arb scanner, dispute monitor — satellite bots

**Outcome:** Full copy-trading pipeline, multiple strategies running in parallel.

---

## 🚧 Sprint 7 — Web Dashboard (Current)
*Goal: visual interface for the system, deployable and shareable*

- [ ] Next.js frontend — war markets table, top traders, spike feed
- [ ] FastAPI backend — serves SQLite data via REST
- [ ] Supabase PostgreSQL — cloud-hosted data for Vercel deployment
- [ ] ETL script — sync local SQLite → Supabase
- [ ] Vercel deployment — public demo URL

**Target:** 2 weeks

---

## 📋 Sprint 8 — Auto Function Calling (Planned)
*Goal: every spike gets automatic AI explanation, not just on `/analyze`*

- [ ] Claude API tool_use — `get_top_holders`, `get_recent_trades`, `get_trader_pnl`
- [ ] Auto-trigger on every HIGH/MED tier alert
- [ ] Telegram message enriched with AI narrative
- [ ] Cost cap: skip AI if volume < threshold

**Target:** 1 week after Sprint 7

---

## 📋 Sprint 9 — Mobile App (Planned)
*Goal: alerts on your phone, not just Telegram*

- [ ] React Native + Expo app
- [ ] Alert feed screen (pulls from Sprint 7 backend)
- [ ] Market detail screen: price history, top holders
- [ ] Push notifications via Expo
- [ ] iOS + Android

**Target:** 2 weeks after Sprint 8
