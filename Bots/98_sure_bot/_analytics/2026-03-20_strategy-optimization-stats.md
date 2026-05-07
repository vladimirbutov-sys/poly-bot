# Trading Strategy Optimization Report — Full Statistics
**Date:** 2026-03-20
**Source:** positions.json (155 positions total)
**Snapshot time:** 2026-03-20T18:00:00Z

---

## A. RESOLVED POSITIONS (won + lost)

| Metric | Value |
|--------|-------|
| Total resolved | 38 |
| Won | 37 |
| Lost | 1 |

### Wins Breakdown

| Metric | Value |
|--------|-------|
| Total PnL from wins | $3.247670 |
| Avg PnL per win | $0.087775 |
| Min PnL | $0.035000 |
| Max PnL | $0.373680 |
| Total cost of wins | $197.752330 |
| Avg entry_price | 0.984973 |
| Median entry_price | 0.987000 |

### Time to Resolve (33 of 37 wins have resolved_at data)

| Metric | Hours |
|--------|-------|
| Avg | 11.9385 |
| Min | 1.8461 |
| Max | 38.1483 |
| Median | 9.8003 |

### The Single Loss

| Field | Value |
|-------|-------|
| Title | US Avellino 1912 vs. FC Sudtirol: O/U 4.5 |
| Entry price | 0.979 |
| Cost USD | $4.895 |
| Size shares | 5.0 |
| PnL | -$4.895 (total loss) |
| Neg risk | false |
| Category | No category field (sports/O-U market) |
| Market type | Over/Under 4.5 goals — Italian football |
| Timestamp | 2026-03-18T19:27:23Z |
| Resolved at | 2026-03-18T23:06:16Z |
| Time to resolve | ~3.65 hours |

---

## B. PRICE BUCKET ANALYSIS (resolved only)

| Bucket | Count | Wins | Losses | Total PnL | Avg PnL/bet | Avg Resolve (h) |
|--------|-------|------|--------|-----------|-------------|-----------------|
| [0.96-0.97) | 2 | 2 | 0 | $0.704560 | $0.352280 | 10.25 |
| [0.97-0.975) | 0 | 0 | 0 | — | — | — |
| [0.975-0.98) | 8 | 7 | 1 | -$4.125000 | -$0.515625 | 13.63 |
| [0.98-0.985) | 2 | 2 | 0 | $0.195390 | $0.097695 | 5.42 |
| [0.985-0.99) | 18 | 18 | 0 | $1.227270 | $0.068182 | 10.56 |
| [0.99-0.993) | 7 | 7 | 0 | $0.315450 | $0.045064 | 14.69 |
| [0.993-0.996) | 1 | 1 | 0 | $0.035000 | $0.035000 | 15.84 |

**Key insight:** The [0.975-0.98) bucket has the only loss, making its total PnL deeply negative (-$4.13). Without that loss, every bucket is profitable. The [0.96-0.97) bucket has the best avg PnL ($0.35) but only 2 data points. The [0.985-0.99) bucket is the sweet spot by volume (18 bets, all wins, $1.23 total PnL).

---

## C. OPEN POSITIONS ANALYSIS

| Metric | Value |
|--------|-------|
| Total open | 92 |
| Total cost frozen | $505.114140 |

### By neg_risk

| neg_risk | Count | Cost |
|----------|-------|------|
| true | 86 | $470.484970 |
| false | 6 | $34.629170 |

### By category

| Category | Count | Cost |
|----------|-------|------|
| N/A (no category field) | 51 | $251.868510 |
| other | 22 | $139.167240 |
| politics | 18 | $109.123500 |
| crypto | 1 | $4.954890 |

### Age Distribution (now = 2026-03-20T18:00:00Z)

| Age | Count |
|-----|-------|
| < 24h | 0 |
| 24-48h | 54 |
| 48-72h | 38 |
| > 72h | 0 |

### Entry Price Distribution (open)

| Bucket | Count |
|--------|-------|
| [0.96-0.97) | 2 |
| [0.97-0.975) | 1 |
| [0.975-0.98) | 12 |
| [0.98-0.985) | 9 |
| [0.985-0.99) | 31 |
| [0.99-0.993) | 22 |
| [0.993-0.996) | 15 |

---

## D. SOLD POSITIONS

### Completed Sells (status=sold): 14

| Metric | Value |
|--------|-------|
| Count | 14 |
| Total cost | $69.080000 |
| Total PnL | -$0.135000 |

#### Individual Sold Positions

| Title | Buy | Sell | PnL |
|-------|-----|------|-----|
| Carlos Eduardo Palenque - La Paz mayoral | 0.987 | 0.98 | -0.035 |
| Manfred Reyes Villa - Cochabamba mayoral | 0.987 | 0.98 | -0.035 |
| G2 Esports win First Stand 2026 | 0.981 | 0.99 | +0.045 |
| Elon Musk 360-379 tweets Mar 13-20 | 0.99 | 0.99 | 0.000 |
| Trump 180-199 Truth Social posts | 0.986 | 0.98 | -0.030 |
| Trump 200+ Truth Social posts | 0.987 | 0.99 | +0.015 |
| 3 earthquakes magnitude 6.5+ | 0.986 | 0.98 | -0.030 |
| Khamenei 80-99 posts | 0.986 | 0.99 | +0.020 |
| White House 100-119 posts | 0.986 | 0.99 | +0.020 |
| 15-19 ships Strait of Hormuz | 0.98 | 0.97 | -0.050 |
| Elon Musk 140-159 tweets Mar 17-24 | 0.993 | 0.99 | -0.015 |
| Elon Musk 160-179 tweets Mar 17-24 | 0.992 | 0.99 | -0.010 |
| Elon Musk 340-359 tweets Mar 13-20 | 0.984 | 0.98 | -0.020 |
| Elon Musk 460-479 tweets Mar 17-24 | 0.992 | 0.99 | -0.010 |

### Pending Sells (status=selling): 11
Total cost: $54.240000

**Why sold?** Pattern: bot sells when duplicate positions exist (rebought at different price) or when market conditions shift. Most sells are at a small loss (sell < buy) — likely risk management exits to free up capital. The one profitable sell (G2 Esports +0.045) was sold at 0.99.

---

## E. OVERALL STATS

### From stats object in file

| Metric | Value |
|--------|-------|
| total_bets | 155 |
| wins | 38 |
| losses | 1 |
| total_pnl | -$1.732340 |
| peak_balance | $500.00 |
| current_balance | $68.712370 |

### Computed

| Metric | Value |
|--------|-------|
| Total capital (balance + open cost) | $573.826510 |
| Win rate (resolved only) | 97.37% (37/38) |
| Total resolved cost | $202.647330 |
| Total resolved PnL | -$1.647330 |
| Average PnL per resolved bet | -$0.043351 |
| ROI % (total PnL / total cost) | -0.8129% |
| Avg ROI % per position | -1.1230% |

### Note on stats discrepancy
The file stats show wins=38 but actual won positions = 37. The file's total_pnl = -$1.7323 includes both resolved and sold PnL. Computed resolved PnL = -$1.6473, sold PnL = -$0.1350, total = -$1.7823 (slight rounding discrepancy from selling positions not yet completed).
