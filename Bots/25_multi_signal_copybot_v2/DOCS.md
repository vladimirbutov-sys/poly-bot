# 25_multi_signal_copybot_v2 — Full Documentation

## What It Does

Monitors the on-chain trading activity of a high-performing Polymarket wallet (denizz) and mirrors their positions proportionally. Enters when they enter, scales up when they add, exits when they exit.

---

## Why denizz

Denizz has a documented lifetime P&L of **+$447K** on Polymarket with directional trading (not arbitrage). His positions are concentrated bets on geopolitical outcomes — war markets, sanctions, diplomatic events. He enters early and sizes up as conviction grows.

The key insight: denizz's entry signal is alpha-generating because he often knows before the market reprices. By copying with a small lag (5–30 seconds), we capture most of the move.

**Why not copy others?**
Previous versions copied Car and aenews2. Car was removed after an incident where his merge-arbitrage activity (buying YES+NO simultaneously) was misread as directional signals, causing cascade losses. Denizz trades directionally only.

---

## Signal Detection

The bot polls denizz's wallet activity every **5 seconds** via the Data API and Polygon RPC.

**Entry signal triggered when:**
- Denizz buys ≥ $500 in a single market
- No opposing trade from other monitored players (compatibility layer — currently only denizz)
- Market passes price filter (5–99¢)
- Market is not in excluded categories (BTC/ETH/crypto, macro indicators)
- Horizon: < 120 days to end_date

**Top-up signal (denizz adds to existing position):**
- New buy / existing position ≥ 3% → scale up our position
- < 3% → skip (noise/dust)

---

## Entry Sizing

### Logarithmic formula
```
our_bet = 31.75 × ln(denizz_invested) - 177.0
```
Anchors:
- Denizz invests $500 → we bet $20
- Denizz invests $5,000 → we bet $88
- Denizz invests $30,000 → we bet $150 (capped at $250)

### Price-risk multipliers
Longshots and near-100¢ get reduced size to protect against low-upside trades:

| Entry price | Multiplier |
|------------|------------|
| 0–15¢ | 40% |
| 15–30¢ | 70% |
| 30–70¢ | 100% (full size) |
| 70–85¢ | 90% |
| 85–99¢ | 80% |

### Horizon multipliers
Position size reduced as market deadline approaches:

| Days to end | Multiplier |
|------------|------------|
| 0–30 days | 100% |
| 30–60 days | 80% |
| 60–90 days | 70% |
| 90–120 days | 40% |
| 120+ days | 0% (no entry) |

---

## Exit Rules

### Follow-sell (primary exit)
When denizz sells, we sell proportionally from our position:

| Denizz sells | We sell (profit position) | We sell (loss position) |
|-------------|--------------------------|------------------------|
| < 5% | 0% (dust) | 0% (dust) |
| 5–10% | 10% | 10% |
| 10–20% | 15% | 15% |
| 30–40% | 35% | 35% |
| 50–60% | 55% | 55% |
| 80%+ | 100% | 100% |

### Auto take-profit
Sell 100% if position price reaches **99.5¢**.

### Stop-loss
Stop at **-80%** (currently disabled globally during volatile windows — set `STOP_LOSS_ENABLED = True` to re-enable).

---

## Top-Up Detection

Before entering on a new denizz buy, the bot checks denizz's on-chain balance via `CTF.balanceOf()`:

- If denizz already holds shares on this token → it's a top-up, not a new entry
- Routes to the tier-upgrade branch instead of fresh entry sizing
- Prevents over-sizing entries on late-conviction top-ups

This required a 3-second RPC call budget (non-blocking, runs in parallel with API calls).

---

## Cumulative Sell Detection

Denizz sometimes exits via many small sells, each below the 5% dust threshold. The bot tracks cumulative sell percentage over a 1-hour rolling window:

- If cumulative sells ≥ 20% within 1 hour → treat as a single 20% sell event
- Counter resets after firing

---

## Slippage-Aware Settlement

When denizz sells in profit, his market sweep compresses the orderbook briefly. Analysis showed ~27.5% of cases have bid recovery within 60 seconds.

Strategy: wait **30 seconds** before placing our sell order (PROFIT positions only). This reads the post-absorption bid — likely better than peak-impact bid.

Loss positions: sell immediately (no settlement wait).

---

## Rebuy Branch

When denizz partially exits and then re-enters the same market, the standard top-up logic misses the signal (formula target < our cost). The rebuy branch handles this:

- Fires when denizz makes a fresh buy ≥ $500 AND we have an existing position below formula target
- Sizes based on denizz's new buy amount (not net invested)
- Throttled: one rebuy per market per 5 minutes
- Kill-switch: disabled if cumulative rebuy P&L < -$150

---

## Telegram Notifications

| Event | What's sent |
|-------|------------|
| New entry | Market, denizz invested, our bet, entry price |
| Top-up | Additional bet, new total position |
| Follow-sell | % sold, reason (profit/loss), P&L |
| Auto take-profit | Price, final P&L |
| Stop-loss | Price, loss amount |
| Redemption | Market resolved, P&L |
| Daily report (13:00 MSK) | Balance, open positions, daily P&L |
| Evening report (19:00 MSK) | Same |

---

## File Structure

```
25_multi_signal_copybot_v2/
├── main.py             ← polling loop and orchestration
├── config.py           ← all parameters
├── monitor.py          ← denizz wallet activity detection
├── entry_manager.py    ← entry decision and sizing
├── exit_manager.py     ← follow-sell and stop-loss logic
├── executor.py         ← CLOB order placement
├── tracker.py          ← positions.json and P&L
├── redeemer.py         ← on-chain redemption
├── telegram_notify.py  ← alerts
├── .env.example
├── positions.json
└── _analytics/         ← backtest results, player analysis
```

---

## Lessons Learned

**Car merge-arbitrage incident (April 2026)**
Car wallet was removed after it was discovered his activity included merge-arbitrage (buying YES+NO simultaneously). Our bot misread these as directional buys, entered on false signals, and suffered losses when the positions resolved flat. Lesson: verify a wallet's trading pattern before copying. Denizz is confirmed directional.

**Startup replay bug**
After a restart, the bot replayed old Car exits as "missed sells" and triggered exit attempts on denizz's positions. Fixed by separating player-specific exit records and clearing stale signals on startup.
