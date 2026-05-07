# Contributing

## Adding a New Bot

Every bot must follow the standard structure. Use the template below.

### Required Files

```
Bots/NN_botname/
├── main.py             ← entry point and main loop
├── config.py           ← ALL parameters (no hardcoded values anywhere)
├── scanner.py          ← market/signal discovery
├── executor.py         ← order placement via CLOB
├── tracker.py          ← positions.json read/write, P&L calculation
├── redeemer.py         ← on-chain redemption after resolution
├── telegram_notify.py  ← alerts
├── requirements.txt    ← dependencies (pinned versions)
├── .env.example        ← template with comments for every variable
├── README.md           ← what the bot does (2–3 paragraphs)
├── DOCS.md             ← full documentation (see template)
└── _analytics/         ← backtest results and research reports
```

### Naming Convention

- Number prefix: next available integer (e.g., `32_my_new_bot`)
- Snake_case for folder and file names
- No spaces in paths

---

## Code Standards

### config.py

All parameters go in `config.py`. No hardcoded values in any other file.

```python
# Good
from config import BET_SIZE_REGULAR
order_size = BET_SIZE_REGULAR

# Bad
order_size = 20.00  # never hardcode
```

Every parameter must have a comment explaining what it controls:

```python
SCAN_INTERVAL = 300    # seconds between market scans
ORDER_TTL_SECONDS = 300  # cancel unfilled orders after this time
MIN_LIQUIDITY = 500    # skip markets with less liquidity (USD)
```

### .env.example

Every secret variable needs a comment:

```
# Your Polygon wallet address (0x...)
POLYMARKET_WALLET=

# Your Polygon private key (0x...) — NEVER commit the actual key
POLYMARKET_PRIVATE_KEY=

# Telegram bot token from @BotFather
TELEGRAM_BOT_TOKEN=

# Your Telegram chat ID (get from api.telegram.org/bot<token>/getUpdates)
TELEGRAM_CHAT_ID=
```

### positions.json format

All bots use the same position schema:

```json
{
  "positions": {
    "<order_id>": {
      "condition_id": "0x...",
      "token_id": "...",
      "title": "Market question text",
      "outcome": "Yes",
      "category": "sports",
      "entry_price": 0.971,
      "size_shares": 20.59,
      "cost_usd": 20.00,
      "status": "open",
      "timestamp": "2026-05-01T14:32:00+00:00",
      "end_date": "2026-05-03T23:59:59Z",
      "neg_risk": false,
      "pnl": null
    }
  },
  "stats": {
    "total_bets": 0,
    "wins": 0,
    "losses": 0,
    "total_pnl": 0.0
  }
}
```

Status values: `open` | `filled` | `won` | `lost` | `cancelled`

### Error handling

- Wrap all API calls in try/except
- Log errors to `bot_log.txt` and send Telegram alert
- Never let an unhandled exception crash the main loop silently

```python
try:
    result = place_order(market)
except Exception as e:
    log(f"ERROR placing order: {e}")
    notify_telegram(f"⚠️ Bot error: {e}")
    # continue to next iteration, don't raise
```

### Secrets

- Never use `os.getenv("KEY", "hardcoded_fallback")`
- If the key is missing, fail loudly at startup:

```python
PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY")
if not PRIVATE_KEY:
    raise ValueError("POLYMARKET_PRIVATE_KEY not set in .env")
```

---

## Backtesting

Before deploying a new bot, run a backtest with at least 100 historical market samples.

Save results to `_analytics/YYYY-MM-DD_backtest-results.md` with:
- Number of trades simulated
- Win rate
- Average ROI
- Worst case drawdown
- Key parameters tested

---

## Analytics Convention

Research reports go in `_analytics/` using the date prefix format:

```
_analytics/
├── 2026-05-01_initial-backtest.md
├── 2026-05-07_filter-optimization.md
└── data/
    ├── backtest_output.csv
    └── market_samples.json
```

---

## Pull Request Checklist

Before submitting:

- [ ] Bot follows the standard folder structure
- [ ] All parameters in `config.py` with comments
- [ ] `.env.example` has every required variable
- [ ] No hardcoded values outside `config.py`
- [ ] No `.env` or `positions.json` committed
- [ ] `README.md` and `DOCS.md` written
- [ ] Backtest results in `_analytics/`
- [ ] `requirements.txt` with pinned versions
