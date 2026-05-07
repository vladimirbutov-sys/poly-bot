# Car Copy-Strategy Analysis
**Date:** 2026-04-10
**EOA Wallet:** `0x8dECBB0645dDD89c905670F2544aA5a9c5624c42`
**Proxy Wallet:** `0x7c3db723f1d4d8cb9c550095203b686cb11e5c6b`
**Position records:** 801 | **Activity rows:** 3500
**WARNING: Activity data hit 3500-row API cap. Incomplete trade-level data.**
**Position date range:** 2024-02-13 to 2026-03-30 (776 days)
**Activity date range:** 2026-03-29 to 2026-04-10 (12 days)

## 1. General Statistics

- **801** position records across **778** unique markets
- **3500** activity rows (trade-level events)
- **Lifetime realized P&L: $667,564**
- Avg P&L per position: $833

### Activity by type
| Type | Count | Volume |
|------|-------|--------|
| MERGE | 26 | $73,255 |
| REDEEM | 53 | $362,593 |
| REFERRAL_REWARD | 2 | $13 |
| REWARD | 26 | $656 |
| TRADE | 3381 | $2,869,357 |
| YIELD | 12 | $18 |

## 2. Trade Classification

| Classification | Count | % | Volume | P&L | Win Rate | Avg ROI |
|---------------|-------|---|--------|-----|----------|---------|
| direction_bet | 757 | 94.5% | $8,845,041 | $588,301 | 64.3% | 110.9% |
| both_sides_no_merge | 44 | 5.5% | $1,979,603 | $79,264 | 65.9% | 149.9% |

**Direction bets: 757 (94.5%) | Merge/both-sides: 44 (5.5%)**

## 3. Direction Bet Analysis

- Count: 757
- Total P&L: $588,301
- Win rate: 64.3%
- Avg ROI: 110.9%

## 4. Copy-Strategy Simulation

Simulated with denizz tiers ($30/$55/$105/$200), 1c slippage both sides,
price filter 10-98c, MIN_INVESTED $500, long-horizon 0.2x.

| Level | Description | Trades | P&L | WR | ROI | Max DD |
|-------|------------|--------|-----|-----|-----|--------|
| 0 | No filter (copy everything incl. merge) | 200 | $+682 | 65.5% | +8.5% | $55 |
| 1 | Filter confirmed merges/both-sides | 183 | $+656 | 66.7% | +9.3% | $66 |
| 2 | Level 1 + politics/geopolitics only | 96 | $+239 | 62.5% | +5.7% | $38 |
| 3 | Level 2 + min $1000 Car invested | 72 | $+193 | 63.9% | +5.4% | $23 |

## 5. Recommendation

### Result: Marginally profitable at all 4 filter levels

| Level | P&L | ROI | Comment |
|-------|-----|-----|---------|
| L0 (no filter) | $+682 | +8.5% | Best absolute P&L |
| L1 (no merge) | $+656 | +9.3% | Best ROI per dollar |
| L2 (politics only) | $+239 | +5.7% | Fewer trades, still positive |
| L3 (politics + $1k min) | $+193 | +5.4% | Most conservative |

### Surprise finding: Car is 94.5% directional

The prior assumption (Car = mostly merge arbitrage) was WRONG. Out of 801 lifetime positions:
- 757 (94.5%) are pure direction bets
- Only 44 (5.5%) involved both-sides buying (and 0 had confirmed MERGE events in our activity window)
- Car's lifetime P&L is $667k -- higher than denizz ($447k)
- Car's direction bet win rate is 64.3% with avg ROI 110.9% (skewed by cheap longshots)

### But the copy profit is tiny: $682 over 200 trades = $3.41 avg

Why the edge is so thin despite Car's strong raw P&L:
1. **Our bet sizing is small** ($30-$200 per trade), so even a 65% WR produces modest absolute P&L
2. **Slippage (2c round-trip)** eats a large fraction of the per-trade edge at our scale
3. **Many of Car's best wins are on sub-10c longshots** (e.g. $33k on Israel/Lebanon at 1.4c) -- our bot's price filter excludes or heavily reduces these
4. **Car trades 778 markets** (very diversified) -- many don't match our category filter

### Risks of re-adding Car

1. **Merge contamination (5.5%)**: While rare, a single merge-prep event on a market where denizz ALSO has a position can trigger a cascade sell (the April 7-9 incident). This happened with only ~5% merge activity.
2. **Shared markets**: If Car and denizz both hold positions on the same conditionId, a Car exit could sell denizz shares (the root cause #3 from config.py comments).
3. **Volume of noise**: Car does ~290 trades/day (3500 in 12 days). At $500 MIN_INVESTED filter only 200 pass, but that's still a lot of signals competing with denizz.
4. **Marginal edge**: $682 profit over 200 trades = $3.41 avg. One bad merge-cascade incident can wipe months of accumulated edge.

### Verdict: DO NOT RE-ADD

The math is clear: Car has genuine alpha ($667k lifetime, 64.3% WR), but the **copy-trading edge after our bot's filters and slippage is only $3.41 per trade**. Meanwhile, the downside risk of a single merge-cascade incident (like April 7-9) is potentially $50-200 in losses -- wiping 15-60 trades of accumulated profit.

The risk-reward ratio is unfavorable:
- **Upside**: ~$3.41/trade x maybe 5-10 trades/week = $17-34/week
- **Downside**: One merge-cascade = -$50 to -$200 (or more if it sells denizz shares)

If you want to revisit, the ONLY safe way would be:
1. Run Car in a SEPARATE bot with a SEPARATE wallet (never share positions with denizz)
2. Implement a hard per-conditionId lock so both bots can never hold the same market
3. Accept the tiny per-trade edge and treat it as a high-frequency low-conviction strategy

## 6. Car vs denizz Comparison

| Metric | Car | denizz |
|--------|-----|--------|
| Activity rows | 3500 | 3500 |
| Unique markets | 778 | 99 |
| Merge events | 26 | 6 |
| Lifetime P&L | $667,564 | $447,000+ |
| Merge % | 5.5% | ~0% |
| Direction % | 94.5% | ~100% |
| Style | Mixed (direction + merge arb) | Pure directional |