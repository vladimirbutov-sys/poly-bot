# Daily Strategy Review — 2026-04-10 13:51 UTC

## ALERTS
- CRITICAL: 7-day loss rate 1.31% (4 losses / 305 bets)

## WARNINGS
- 1 positions > 72h ($15.00 frozen)

## 1. Bot Performance

| Metric | Value |
|--------|-------|
| Balance | $1225.30 |
| Open positions | 1 ($15.00 frozen) |
| Selling | 35 ($287.44) |
| Capital (total) | $1527.75 |
| Utilization | 20% |
| Realized PnL | $+37.81 |
| Unrealized PnL | $+0.14 |
| Resolved | 840 (WR: 98.8%) |

### Rolling Windows
| Period | W/L | Loss Rate | PnL |
|--------|-----|-----------|-----|
| 7d | 301/4 | 1.31% | $+9.24 |
| 30d | 830/10 | 1.19% | $+36.45 |
| all | 830/10 | 1.19% | $+36.45 |

### By Market Type (resolved)
| Type | W/L | WR | PnL | Cost |
|------|-----|----|-----|------|
| regular | 501/7 | 98.6% | $+24.17 | $6304.25 |
| neg_risk | 329/3 | 99.1% | $+12.28 | $2539.27 |

### Open Positions by Type
| Type | Count | Frozen |
|------|-------|--------|
| regular | 1 | $15.00 |
| neg_risk | 0 | $0.00 |

### Resolve Times (bot positions)
| Type | Median | Avg | P90 | Count |
|------|--------|-----|-----|-------|
| regular | 4.8h | 20.9h | 60.3h | 504 |
| neg_risk | 20.3h | 37.0h | 100.8h | 332 |

### By Category (bot resolved)
| Category | W/L | WR | PnL |
|----------|-----|----|-----|
| other | 374/6 | 98.4% | $-8.51 |
| politics | 122/0 | 100.0% | $+27.42 |
| esports | 114/3 | 97.4% | $-19.16 |
| sports_other | 105/0 | 100.0% | $+18.61 |
| geopolitics | 89/1 | 98.9% | $+14.33 |
| crypto | 8/0 | 100.0% | $+0.81 |
| soccer | 8/0 | 100.0% | $+1.39 |
| tech | 7/0 | 100.0% | $+0.87 |
| fighting | 2/0 | 100.0% | $+0.47 |
| finance | 1/0 | 100.0% | $+0.21 |

### By Price Bucket
| Bucket | W/L | WR | PnL |
|--------|-----|----|-----|
| 96.0-97.5c | 111/1 | 99.1% | $+27.14 |
| 97.5-98.0c | 135/5 | 96.4% | $-9.77 |
| 98.0-98.5c | 129/0 | 100.0% | $+25.18 |
| 98.5-99.0c | 243/2 | 99.2% | $+11.43 |
| 99.0-99.5c | 144/1 | 99.3% | $-7.04 |

### Stuck Positions (>72h)
- US x Iran ceasefire by April 7? | 134h | $15.00 | neg=False

## 2. Scanner Market Supply

Total resolved in scanner: 42811
Bot-eligible (price threshold): 42690
Win/Loss: 42661/21 (99.95% WR)
Overall median resolve: 2.5h

### By Market Type (scanner)
| Type | Total | W/L | WR | Median Resolve | P90 |
|------|-------|-----|----|----------------|-----|
| regular | 33337 | 33323/6 | 99.96% | 2.2h | 6.1h |
| neg_risk | 9353 | 9338/15 | 99.84% | 19.1h | 107.1h |

### Resolve Time by End-Date Bucket (scanner)
| Bucket | Count | Median | Avg | P90 |
|--------|-------|--------|-----|-----|
| 0-1d | 33013 | 2.2h | 4.4h | 8.1h |
| 1-2d | 1368 | 40.0h | 37.1h | 59.8h |
| 2-3d | 1133 | 67.5h | 63.4h | 83.3h |
| 3-5d | 2077 | 91.9h | 83.1h | 115.4h |
| 5d+ | 5050 | 2.6h | 31.7h | 153.5h |
| no_end_date | 49 | 46.7h | 62.4h | 130.1h |

### By Category (scanner, bot-eligible)
| Category | Total | Losses | Loss Rate | Median Resolve |
|----------|-------|--------|-----------|----------------|
| sports_other | 23379 | 2 | 0.01% | 2.2h |
| other | 7627 | 11 | 0.14% | 18.7h |
| crypto | 5031 | 4 | 0.08% | 2.2h |
| soccer | 2859 | 0 | 0.00% | 2.6h |
| esports | 1859 | 0 | 0.00% | 2.5h |
| politics | 658 | 0 | 0.00% | 38.0h |
| tech | 599 | 4 | 0.67% | 25.3h |
| tennis | 232 | 0 | 0.00% | 2.4h |
| geopolitics | 209 | 0 | 0.00% | 26.4h |
| finance | 94 | 0 | 0.00% | 13.5h |
| american_football | 57 | 0 | 0.00% | 101.0h |
| cricket | 33 | 0 | 0.00% | 0.4h |
| fighting | 32 | 0 | 0.00% | 2.1h |
| basketball | 21 | 0 | 0.00% | 32.1h |

### Weekly Loss Rate Trend
| Week | W/L | Total | Loss Rate |
|------|-----|-------|-----------|
| 2026-W11 | 26208/5 | 26213 | 0.019% |
| 2026-W12 | 14141/16 | 14157 | 0.113% |
| 2026-W13 | 2311/0 | 2311 | 0.000% |

### Suspicious Keywords (appear in 3+ losing markets)
- `march`: 16 losses
- `highest`: 8 losses
- `temperature`: 8 losses
- `meta`: 6 losses
- `between`: 5 losses
- `week`: 4 losses
- `mar`: 4 losses
- `price`: 3 losses
- `ethereum`: 3 losses
- `above`: 3 losses
- `day`: 3 losses

## 3. Recommendations

### 1. MAX_END_DATE_REGULAR
- **Current**: 3
- **Recommended**: 3
- **Reasoning**: Loosening regular to include 3-5d would add 2077 markets but median resolve 91.9h vs 67.5h. Capital frozen 1.4x longer.
- **Assumption**: Resolve times from scanner are representative
- **Risk**: Slower turnover = less capital for fast markets
- **Pros**: More supply (+2077 markets)
- **Cons**: Slower resolve (91.9h median)

### 2. MAX_END_DATE_NEG_RISK
- **Current**: 3
- **Recommended**: 3
- **Reasoning**: Loosening neg_risk to include 3-5d would add 2077 markets but median resolve 91.9h vs 67.5h. Capital frozen 1.4x longer.
- **Assumption**: Resolve times from scanner are representative
- **Risk**: Slower turnover = less capital for fast markets
- **Pros**: More supply (+2077 markets)
- **Cons**: Slower resolve (91.9h median)

### 3. MAX_NEG_RISK_FROZEN
- **Current**: 350
- **Recommended**: 75
- **Reasoning**: Neg_risk resolves 19.1h (vs reg 2.2h). Efficiency ratio 0.11. Currently $0 frozen in 0 neg positions.
- **Assumption**: Resolve speed difference stays consistent
- **Risk**: If neg_risk markets start resolving faster, cap is too tight
- **Pros**: More capital available for faster-resolving regular markets
- **Cons**: Fewer neg_risk bets = missed opportunities in that segment

### 4. SORT_PRIORITY
- **Current**: end_date ASC, price ASC
- **Recommended**: end_date ASC, price ASC (keep current)
- **Reasoning**: Regular markets are 8.7x more capital-efficient. Current sort (shortest end_date first) naturally favors fast markets.
- **Assumption**: end_date is a reliable proxy for resolve speed
- **Risk**: None — current sort is already optimal for capital efficiency
- **Pros**: Maximizes capital turnover
- **Cons**: May skip higher-ROI slow markets when capital is available

### 5. CATEGORY_TECH
- **Current**: allowed
- **Recommended**: review
- **Reasoning**: tech: 4 losses in 599 markets (loss rate 0.67%). Median resolve: 25.3h.
- **Assumption**: Scanner loss rate reflects bot's actual risk
- **Risk**: Blocking may reduce supply without meaningful safety gain
- **Pros**: Avoid ~0.67% loss rate in this category
- **Cons**: Lose 599 market supply

## 4. Current Config Snapshot
- BET_SIZE_REGULAR: $20.00
- BET_SIZE_NEG_RISK: $15.00
- MAX_END_DATE_REGULAR: 3d
- MAX_END_DATE_NEG_RISK: 3d
- MAX_NEG_RISK_FROZEN: $350
- PRICE_THRESHOLD: 0.96
- MAX_PRICE: 0.995
- SCAN_INTERVAL: 300s
