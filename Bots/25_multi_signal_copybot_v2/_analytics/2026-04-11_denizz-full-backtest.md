# Denizz Full Backtest: Bet Sizing Ratio Analysis

**Generated:** 2026-04-11 10:25 UTC
**Player:** denizz `0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73`
**Data span:** 2025-07-01 to 2026-04-11 (284 days)
**Total trades fetched:** 3500
**Positions reconstructed:** 465 (Open: 43, Closed: 422)
**Resolution data:** won=178, lost=131, unknown=113

## Comparison with previous analysis

| Metric | Previous (90d, open only) | This (full history) |
|--------|---------------------------|---------------------|
| Positions analyzed | 52 (open only) | 465 (open + closed) |
| Trades processed | ~1,672 | 3500 |
| Data window | 90 days | 284 days |
| Resolution tracking | No (estimated) | Yes (CLOB API) |
| Total PnL | +$504 (sim, $2K bankroll) | $+1,649,908.39 (actual) |

## Summary

| Metric | Value |
|--------|-------|
| Total capital bought | $4,381,913.48 |
| Total capital sold (trades) | $2,084,654.98 |
| Open position value | $1,413,013.19 |
| Resolution payouts | $2,534,153.69 |
| **Net PnL** | **$+1,649,908.39** |
| ROI on deployed | +37.7% |
| Win rate | 281/465 = 60.4% |
| Losers | 184 |
| Breakeven | 0 |
| Peak capital deployed | $3,284,910.95 |

### Closed Positions (known resolution only)

| Metric | Value |
|--------|-------|
| Positions | 309 |
| Won | 178 |
| Lost | 131 |
| WR | 56.0% |
| Avg ROI | -2.5% |
| Total PnL | $+39,150.09 |

## TABLE A: Ratio Buckets vs Outcomes

Ratio = total_bought_for_market / active_portfolio_at_first_buy

| Ratio | Count | WR% | Avg ROI% | Med ROI% | Total PnL |
|-------|-------|-----|----------|----------|-----------|
| < 5% | 433 | 58.9% | +276.1% | +5.3% | $+1,259,009.50 |
| 5-15% | 21 | 81.0% | +65.3% | +18.1% | $+302,654.93 |
| 15-30% | 4 | 100.0% | +55.0% | +43.6% | $+127,276.30 |
| 30-50% | 2 | 100.0% | +43.6% | +43.6% | $+45,545.25 |
| 50-80% | 0 | 0.0% | +0.0% | +0.0% | $+0.00 |
| 80-100% | 1 | 100.0% | +3.7% | +3.7% | $+728.26 |
| > 100% | 4 | 50.0% | -6.5% | -14.8% | $-85,305.85 |

## TABLE B: Portfolio Size at Entry vs Outcomes

Portfolio = total active capital across all markets at time of first buy

| Portfolio | Count | WR% | Avg ROI% | Med ROI% | Total PnL |
|-----------|-------|-----|----------|----------|-----------|
| < $100 | 0 | 0.0% | +0.0% | +0.0% | $+0.00 |
| $100-500 | 0 | 0.0% | +0.0% | +0.0% | $+0.00 |
| $500-2K | 0 | 0.0% | +0.0% | +0.0% | $+0.00 |
| $2K-5K | 1 | 100.0% | +62.8% | +62.8% | $+11,640.14 |
| $5K-20K | 0 | 0.0% | +0.0% | +0.0% | $+0.00 |
| $20K-50K | 7 | 57.1% | +143.6% | +3.7% | $-94,888.23 |
| $50K-100K | 9 | 77.8% | +130.3% | +52.4% | $+113,751.26 |
| $100K+ | 448 | 60.0% | +265.5% | +6.4% | $+1,619,405.22 |

## TABLE C: Buy Price Tier vs Outcomes

| Price | Count | WR% | Avg ROI% | Total PnL |
|-------|-------|-----|----------|-----------|
| 2-15c | 45 | 33.3% | +915.7% | $+73,018.74 |
| 15-50c | 138 | 47.1% | +86.7% | $+1,086,599.81 |
| 50-82c | 154 | 61.7% | +123.8% | $+196,500.77 |
| 82-95c | 84 | 86.9% | +186.3% | $+218,047.51 |
| 95-99c | 27 | 92.6% | +95.9% | $+75,025.68 |

## TABLE D: Ratio x Portfolio Size (Count / Avg ROI%)

| Ratio | < $2K | $2K-10K | $10K-50K | $50K+ |
|-------|-------|-------|-------|-------|
| < 5% | 0n / +0% | 0n / +0% | 2n / +541% | 431n / +275% |
| 5-15% | 0n / +0% | 0n / +0% | 1n / +9% | 20n / +68% |
| 15-30% | 0n / +0% | 0n / +0% | 0n / +0% | 4n / +55% |
| 30-50% | 0n / +0% | 0n / +0% | 0n / +0% | 2n / +44% |
| 50%+ | 0n / +0% | 1n / +63% | 4n / -21% | 0n / +0% |

## TABLE E: Ratio x Price Tier (Count / Avg ROI%)

| Ratio | 2-15c | 15-50c | 50-82c | 82-95c | 95-99c |
|-------|-------|-------|-------|-------|-------|
| < 5% | 45n / +916% | 131n / +89% | 143n / +131% | 73n / +212% | 24n / +71% |
| 5-15% | 0n / +0% | 4n / +38% | 5n / +38% | 10n / +15% | 2n / +438% |
| 15-30% | 0n / +0% | 2n / +92% | 1n / +26% | 1n / +10% | 0n / +0% |
| 30-50% | 0n / +0% | 0n / +0% | 2n / +44% | 0n / +0% | 0n / +0% |
| 50%+ | 0n / +0% | 1n / -53% | 3n / +9% | 0n / +0% | 1n / +4% |

## Top 15 Winners

| # | PnL | ROI | Bought | Avg Price | Ratio | Status | Date | Title |
|---|-----|-----|--------|-----------|-------|--------|------|-------|
| 1 | $+396,361.51 | +337.7% | $117,354.16 | 0.38 | 4% | OPEN | 2026-04-06 | Iran x Israel/US conflict ends by April 7? |
| 2 | $+272,457.57 | +282.3% | $96,515.79 | 0.33 | 4% | WON | 2026-02-28 | Khamenei out as Supreme Leader of Iran by Feb |
| 3 | $+230,016.71 | +538.4% | $42,724.39 | 0.18 | 1% | OPEN | 2026-03-31 | Iran x Israel/US conflict ends by April 15? |
| 4 | $+121,629.58 | +342.4% | $35,525.82 | 0.83 | 3% | UNKNOWN | 2025-12-19 | Will Trump release the Epstein files by Decem |
| 5 | $+105,440.20 | +3168.1% | $3,328.22 | 0.79 | 0% | OPEN | 2026-01-10 | Will the Iranian regime fall by June 30? |
| 6 | $+101,957.67 | +105.4% | $96,738.79 | 0.70 | 7% | OPEN | 2026-01-05 | Will the Iranian regime fall before 2027? |
| 7 | $+85,422.21 | +2975.7% | $2,870.61 | 0.09 | 0% | UNKNOWN | 2025-10-02 | US strikes Yemen by December 31? |
| 8 | $+85,354.74 | +871.0% | $9,800.00 | 0.98 | 14% | UNKNOWN | 2025-07-02 | Will Zelenskyy wear a suit before July? |
| 9 | $+84,969.90 | +122.6% | $69,294.34 | 0.33 | 21% | WON | 2025-09-29 | Israel x Hamas ceasefire by October 10? |
| 10 | $+82,842.22 | +80.5% | $102,954.13 | 0.67 | 4% | OPEN | 2026-03-07 | Will the U.S. invade Iran before 2027? |
| 11 | $+81,638.70 | +870.9% | $9,373.70 | 0.28 | 0% | OPEN | 2026-04-01 | Iran x Israel/US conflict ends by April 30? |
| 12 | $+46,355.88 | +41.9% | $110,736.33 | 0.75 | 8% | WON | 2026-01-05 | US strikes Iran by January 31, 2026? |
| 13 | $+45,717.46 | +129.8% | $35,224.66 | 0.42 | 3% | WON | 2026-01-03 | Maduro out by March 31, 2026? |
| 14 | $+44,829.92 | +50.5% | $88,735.93 | 0.66 | 3% | WON | 2026-03-01 | France, UK, or Germany military action agains |
| 15 | $+40,397.23 | +190.3% | $21,224.27 | 0.93 | 2% | UNKNOWN | 2025-12-15 | US x Venezuela military engagement by Decembe |

## Bottom 15 Losers

| # | PnL | ROI | Bought | Avg Price | Ratio | Status | Date | Title |
|---|-----|-----|--------|-----------|-------|--------|------|-------|
| 1 | $-81,570.85 | -99.2% | $82,249.35 | 0.84 | 5% | LOST | 2026-01-26 | Will US or Israel strike Iran by February 28, |
| 2 | $-64,535.15 | -59.4% | $108,700.41 | 0.54 | 359% | LOST | 2025-07-03 | Israel x Hamas ceasefire before August? |
| 3 | $-58,375.94 | -86.5% | $67,464.97 | 0.53 | 4% | LOST | 2026-01-09 | Khamenei out as Supreme Leader of Iran in 202 |
| 4 | $-58,120.78 | -88.2% | $65,898.13 | 0.45 | 5% | LOST | 2026-01-05 | US strikes Iran by June 30, 2026? |
| 5 | $-53,539.28 | -81.3% | $65,880.27 | 0.53 | 5% | LOST | 2026-01-05 | US strikes Iran by March 31, 2026? |
| 6 | $-49,478.17 | -97.8% | $50,605.10 | 0.33 | 2% | LOST | 2026-03-01 | US forces enter Iran by December 31? |
| 7 | $-49,030.22 | -99.9% | $49,060.65 | 0.68 | 4% | LOST | 2026-01-05 | Khamenei out as Supreme Leader of Iran by Jun |
| 8 | $-39,167.59 | -53.1% | $73,722.45 | 0.46 | 300% | LOST | 2025-07-02 | Israel x Hamas ceasefire by July 15? |
| 9 | $-38,172.66 | -82.5% | $46,283.16 | 0.96 | 2% | LOST | 2026-04-07 | US x Iran ceasefire by April 7? |
| 10 | $-34,668.34 | -96.0% | $36,125.77 | 0.40 | 2% | LOST | 2026-01-13 | US strikes Iran by January 31, 2026? |
| 11 | $-33,253.19 | -100.0% | $33,253.19 | 0.67 | 1% | LOST | 2026-02-22 | US strikes Iran by March 7, 2026? |
| 12 | $-33,056.09 | -99.6% | $33,178.56 | 0.80 | 3% | LOST | 2025-12-14 | US strike on Syria by December 31? |
| 13 | $-32,347.83 | -50.1% | $64,503.96 | 0.63 | 3% | UNKNOWN | 2026-01-26 | US strikes Iran by February 28, 2026? |
| 14 | $-31,664.80 | -69.2% | $45,764.64 | 0.85 | 14% | LOST | 2025-09-29 | Israel x Hamas ceasefire by October 10? |
| 15 | $-27,820.35 | -63.2% | $44,040.00 | 0.65 | 2% | LOST | 2026-02-28 | Will US or Israel strike Iran first? |

## Key Insights for Copy-Trading Calibration

1. **Best ratio bucket by PnL:** < 5% (433 positions, WR 59%, total PnL $+1,259,009)
2. **Worst ratio bucket by PnL:** > 100% (4 positions, WR 50%, total PnL $-85,306)
3. **Best price tier by PnL:** 15-50c (138 positions, WR 47%, total PnL $+1,086,600)
4. **Best portfolio size by PnL:** $100K+ (448 positions, WR 60%, total PnL $+1,619,405)
5. **Highest WR ratio bucket (n>=5):** 5-15% (21 positions, WR 81%)

### Signal Strength Observations

- **Concentration vs diversification:** Denizz puts the vast majority of bets at <5% ratio. Larger ratio bets (>15%) are rare but tend to underperform.
- **Price tier sweet spot:** Check which price tiers combine high WR with positive total PnL.
- **Resolution data impact:** 178 positions resolved as wins, 131 as losses. 113 closed positions have unknown resolution (API may not track all).

### Caveats

- Trades API capped at 3,500 records. Older trades may be missing.
- Resolution status for some markets could not be determined via CLOB API.
- "Ratio" uses portfolio snapshot at first buy time; DCA adds complicate the true ratio.
- Open position values use current market prices (unrealized PnL).

---
*Analysis based on 465 positions from 3500 trades spanning 284 days.*