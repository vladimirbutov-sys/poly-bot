# Daily Review — 2026-04-11 06:00 MSK

## WARNINGS
- 1 positions stuck >48h ($15.00 frozen)

## 1. Performance

| Metric | Value |
|--------|-------|
| USDC Balance | $551.39 |
| Open Positions | 1 ($15.00 frozen) |
| Total Assets | $566.39 |
| Realized PnL | $+36.45 |
| W/L (all time) | 830/10 (98.8%) |

### Rolling Windows
| Period | W/L | PnL |
|--------|-----|-----|
| 7d | 297/4 | $+8.84 |
| 30d | 826/10 | $+36.05 |

### By Category (resolved)
| Category | W/L | WR | PnL |
|----------|-----|----|-----|
| Other | 208/5 | 97.7% | $-20.82 |
| Weather | 159/1 | 99.4% | $+12.16 |
| Geopolitics | 157/1 | 99.4% | $+26.68 |
| Sports | 109/0 | 100.0% | $+19.45 |
| Trump say/post | 86/0 | 100.0% | $+19.37 |
| Esports | 53/3 | 94.6% | $-30.88 |
| Politics/Geo | 23/0 | 100.0% | $+5.39 |
| Elections | 18/0 | 100.0% | $+2.80 |
| Shipping | 8/0 | 100.0% | $+1.33 |
| Crypto | 8/0 | 100.0% | $+0.81 |
| Fighting | 1/0 | 100.0% | $+0.16 |

### By Price Bucket
| Bucket | W/L | PnL |
|--------|-----|-----|
| 96.0-97.5c | 111/1 | $+27.14 |
| 97.5-98.0c | 135/5 | $-9.77 |
| 98.0-98.5c | 129/0 | $+25.18 |
| 98.5-99.0c | 243/2 | $+11.43 |
| 99.0-99.5c | 144/1 | $-7.04 |

### Open Positions by Category
| Category | Count | Frozen |
|----------|-------|--------|
| Geopolitics | 1 | $15.00 |

### Resolve Times (7d)
- Median: 11.4h
- Average: 21.7h
- Sample: 297 positions

## 2. Stuck Positions (>48h past end_date)

**Total: 1 positions, $15.00 frozen**

### Geopolitics (1 positions, $15.00)

- [US x Iran ceasefire by April 7?](https://polymarket.com/event/us-x-iran-ceasefire-by-april-7)
  - End: 2026-04-07 | Overdue: 4.1d | $15.00 | neg_risk=False

## Scanner Market Supply (97_scanner)

Total resolved: 42811 | Bot-eligible: 42811
W/L: 42774/37 (99.91% WR)

### Resolve Times by Type
| Type | Median | Count |
|------|--------|-------|
| regular | 1.5h | 25119 |
| neg_risk | 21.6h | 8695 |

### By Category (scanner, bot-eligible)
| Category | Total | Losses | Loss Rate | 
|----------|-------|--------|-----------|
| sports_other | 23414 | 12 | 0.05% |
| other | 7681 | 14 | 0.18% |
| crypto | 5048 | 6 | 0.12% |
| soccer | 2867 | 0 | 0.00% |
| esports | 1860 | 0 | 0.00% |
| politics | 658 | 0 | 0.00% |
| tech | 605 | 5 | 0.83% |
| tennis | 232 | 0 | 0.00% |
| geopolitics | 209 | 0 | 0.00% |
| finance | 94 | 0 | 0.00% |
| american_football | 57 | 0 | 0.00% |
| cricket | 33 | 0 | 0.00% |
| fighting | 32 | 0 | 0.00% |
| basketball | 21 | 0 | 0.00% |

## 3. Config

- BET_SIZE_REGULAR: 20.00
- BET_SIZE_NEG_RISK: 15.00
- MAX_PRICE: 0.995
- MAX_TOTAL_FROZEN: 1000
- MAX_END_DATE_REGULAR: 3
- MAX_END_DATE_NEG_RISK: 3
- MAX_NEG_RISK_FROZEN: 350
- SCAN_INTERVAL: 300

## 4. Active Filters
- Sub-match (map/game/set/KO/TKO/draw/totals)
- Elections (election/mayoral/prime minister/government)
- Slow markets (top/season/most/transit/strait/ships/weekly/monthly)
- Duplicate event (max 1 position per event)
- Max frozen: $1000
