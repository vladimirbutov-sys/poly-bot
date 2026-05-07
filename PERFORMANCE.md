# Performance

## 98_sure_bot (Production Results)

| Metric | Value |
|--------|-------|
| Total trades | 881 |
| Win rate | 96.0% (839 wins / 26 losses) |
| Entry price range | 96–99.5¢ |
| Average trade duration | 1–3 days |
| Scan interval | 5 minutes |
| Markets scanned per cycle | 500+ |
| Fill rate (orders filled / placed) | ~60% |
| Typical ROI per trade | 0.5–4% |

### What a "loss" looks like
A loss occurs when a market resolves against a 96–99¢ position. This happens when:
- An event considered "virtually certain" is cancelled or overturned
- A sports match result is unexpected at the last moment
- A political resolution is delayed past the market expiry date

At 96¢, the maximum loss is 96¢ per share (the full cost). The bot limits single bet sizes to $5–$20 to keep individual losses small.

---

## 25_multi_signal_copybot_v2

Denizz lifetime P&L: **+$447K** on Polymarket.

Our bot's performance mirrors denizz with a small lag discount. Detailed results are in `_analytics/`.

---

## Interpreting Your Own Results

### Key metrics to track

**Win rate** — Wins / Total closed positions. Target: ≥ 85% for `98_sure_bot`.

**ROI per trade** — (P&L / Cost) × 100. For 97¢ entries resolving at $1.00: 3.1% gross.

**Fill rate** — Filled orders / Placed orders. Low fill rate → raise slippage limits or check liquidity filters.

**Capital efficiency** — Total P&L / Average frozen capital. Higher = better use of your money.

**Max drawdown** — Largest peak-to-trough decline. Monitor this — if it exceeds 10% in a month, review filter settings.

### Reading positions.json stats

```python
import json
d = json.load(open('Bots/98_sure_bot/positions.json'))
s = d['stats']
print(f"Trades: {s['total_bets']}")
print(f"Win rate: {s['wins']/s['total_bets']*100:.1f}%")
print(f"Total P&L: ${s['total_pnl']:.2f}")
```

---

## Backtesting

Historical backtest scripts are in each bot's `_analytics/` folder. They simulate the strategy on past market data.

To run the 98_sure_bot backtest:
```bash
cd Bots/98_sure_bot/_analytics
python backtest.py
```

Output includes win rate, P&L, and filter rejection breakdown by category.
