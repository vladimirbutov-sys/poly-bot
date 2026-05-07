# 98_sure_bot — Configuration Guide

All parameters live in `config.py`. Edit them directly or via the dashboard config editor. Restart the bot after saving changes.

---

## Price Parameters

### `PRICE_THRESHOLD_DEFAULT` (default: `0.965`)
Minimum market price for non-politics markets.
- Lower → more markets qualify, more trades, but higher risk of false positives
- Higher → fewer trades, only cleaner opportunities
- Range: 0.960–0.990
- **Recommendation:** Keep at 0.965 unless you want to test lower-probability markets with `BET_SIZE_TEST_LOW`

### `PRICE_THRESHOLD_POLITICS` (default: `0.960`)
Minimum price for politics/geopolitics markets. Lower than default because political outcomes are slightly more ambiguous and need more "buffer" to be truly certain.

### `MAX_PRICE` (default: `0.995`)
Maximum market price. Above 99.5¢, the ROI is < 0.5% — not worth the gas and risk.

---

## Bet Sizes

### `BET_SIZE_REGULAR` (default: `$20`)
Bet per regular market.
- Start with `$5` for testing
- Raise to $20–$50 as you validate performance
- Rule of thumb: no single bet > 2–3% of your total balance

### `BET_SIZE_NEG_RISK` (default: `$15`)
Smaller bet for neg-risk markets — they carry additional complexity and risk.

### `BET_SIZE_WEATHER` (default: `$10`)
Weather markets have higher ambiguity despite high prices.

### `BET_SIZE_SLOW` (default: `$5`)
Test size for slow-keyword markets ("season", "weekly", "top").

### `BET_SIZE_TEST_LOW` (default: `$5`)
Test size for markets in the 96.5–97.5¢ range — monitoring performance before raising.

---

## Portfolio Limits

### `MAX_TOTAL_FROZEN` (default: `$1,000`)
Maximum total capital in open positions at any time.
- Bot stops placing orders when this limit is reached
- Adjust based on your total USDC balance (e.g., 50–80% of balance)

### `MAX_NEG_RISK_FROZEN` (default: `$350`)
Separate sub-limit for neg-risk positions only.

### `MAX_POLITICS_FRACTION` (default: `0.30`)
Max fraction of balance in politics markets (30%). Politics markets have more black-swan risk.

---

## Timing Parameters

### `SCAN_INTERVAL` (default: `300` seconds = 5 min)
How often the bot scans all markets. Reducing this won't help much — Gamma API data refreshes on a similar cadence.

### `ORDER_TTL_SECONDS` (default: `300` = 5 min)
How long to wait for an order to fill before cancelling.
- Tested at 15 min — no improvement, just frozen capital
- Keep at 5 min

### `MAX_END_DATE_REGULAR` (default: `3` days)
Only enter markets resolving within 3 days. The edge shrinks for longer-horizon markets.

---

## Quality Filters

### `MIN_LIQUIDITY` (default: `$500`)
Skip markets with less than $500 in liquidity. Low-liquidity markets have high slippage and poor fill rates.

### `MIN_VOLUME` (default: `$500`)
Skip markets with less than $500 total traded volume. Low volume = low confidence in the price.

### `MAX_PRICE_DIVERGENCE` (default: `0.03` = 3¢)
Maximum allowed gap between Gamma API price and CLOB orderbook price. If they diverge by > 3¢, skip — the price data is stale or inconsistent.

---

## Slippage Rules

Defined as a list of `(min_price, max_price, max_slippage)` tuples:

```python
SLIPPAGE_RULES = [
    (0.960, 0.975, 0.005),  # 96–97.5%: up to 0.5¢ slippage
    (0.975, 0.985, 0.004),  # 97.5–98.5%: up to 0.4¢
    (0.985, 0.990, 0.003),  # 98.5–99.0%: up to 0.3¢
    (0.990, 0.995, 0.003),  # 99.0–99.5%: up to 0.3¢
]
```

Higher-price markets get less slippage tolerance because the upside is smaller and every cent matters.

---

## Example Configurations

### Conservative (low capital, testing)
```python
BET_SIZE_REGULAR = 5.00
BET_SIZE_NEG_RISK = 3.00
BET_SIZE_WEATHER = 2.00
MAX_TOTAL_FROZEN = 100
PRICE_THRESHOLD_DEFAULT = 0.975  # only high-confidence markets
```

### Standard (production)
```python
BET_SIZE_REGULAR = 20.00
BET_SIZE_NEG_RISK = 15.00
MAX_TOTAL_FROZEN = 1000
PRICE_THRESHOLD_DEFAULT = 0.965
```

### Aggressive (high balance, more volume)
```python
BET_SIZE_REGULAR = 50.00
BET_SIZE_NEG_RISK = 30.00
MAX_TOTAL_FROZEN = 3000
PRICE_THRESHOLD_DEFAULT = 0.960  # include more markets
MAX_POLITICS_FRACTION = 0.40
```
