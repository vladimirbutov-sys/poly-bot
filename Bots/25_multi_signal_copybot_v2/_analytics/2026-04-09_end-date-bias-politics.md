# End-date bias in denizz politics trades — analysis & options

**Generated:** 2026-04-09
**Wallet:** denizz `0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73`
**Question:** Does time-to-resolution (end_date − first_buy_date) systematically change the profitability of denizz's politics trades, and if so, what should the copy-bot do about long-horizon markets?

## Executive summary

- Pulled denizz's full public activity from data-api (`/activity`). Raw rows: **3500**. Date range covered: **2026-03-07 → 2026-04-09**.
- Grouped into **100** unique (conditionId, asset) positions.
- After filtering to **politics category** (broad: US+geopolitics+leadership+diplomacy, excluding strike/attack/sports/crypto) AND **closed / fully-exited**, we have **30** positions with $754,564 total deployed and denizz's own realized P&L of **$-57,955**.
- **Only one bucket reached n≥5** (7-30d, n=14, cap-eff 0.2891 ROI%/day). All other buckets are directional only (n<5). Directional best: **30-90d** (42.085). Directional worst: **180-365d** (-9.0255).

## Methodology

1. **Source.** `data-api.polymarket.com/activity?user=<denizz>` paginated with limit=500 until empty. Saved raw to `_analytics/data/denizz_activity_full.json`.
2. **Market metadata.** Each unique `conditionId` resolved via `gamma-api.polymarket.com/markets?condition_ids=...` in batches of 20. Cache `_analytics/data/denizz_markets_cache.json`.
3. **Position construction.** Grouped all TRADE rows by `(conditionId, asset)`. Computed first_buy_ts, last_sell_ts, total buy cost/size, total sell revenue/size, residual shares, average buy price.
4. **Realized P&L.** `total_sell_rev + residual*win_price − total_buy_cost`, where `win_price = outcomePrices[outcome_index]` from Gamma (only if market `closed=True`).
5. **Position closed = (market resolved) OR (residual < 5% of peak buy size)**.
6. **Politics filter.** Gamma `category` first, then keyword match on question/slug. Hard excludes: strike/attack/missile/drone/raid (= war events, not politics), sports, crypto, weather, entertainment. "Ceasefire / peace / accord / leadership / end of military operations" override war-event keywords because they are diplomatic outcomes.
7. **Bucket key.** `(end_date − first_buy_date).days` → {0-7, 7-30, 30-90, 90-180, 180-365, 365+}.
8. **Per-bucket metrics** computed on *only* positions considered closed (resolved or fully exited).

### Filtering funnel

| Stage | Count |
|---|---|
| Raw activity rows | 3500 |
| TRADE rows | 3408 |
| Unique (cid, asset) positions | 100 |
| Markets returned by Gamma | 83 |
| Markets missing from Gamma | 0 |
| Politics-classified positions | 60 |
| Politics + closed/exited | 30 |
| Dropped: not politics | 34 |
| Dropped: still open, unresolved | 30 |

## Bucket comparison (denizz politics, closed only)

| Bucket | n | Invested $ | PnL $ | Win % | Weighted ROI % | Median ROI % | Avg hold d | Cap eff | % exited | Sharpe-like |
|---|---|---|---|---|---|---|---|---|---|---|
| 0-7d ⚠n<5 | 3 | $13,670 | $2,900 | 66.7% | 21.22% | 8.7% | 4.9 | 4.3437 | 33.3% | — |
| 7-30d | 14 | $480,173 | $8,032 | 64.3% | 1.67% | 5.05% | 5.8 | 0.2891 | 85.7% | 0.038 |
| 30-90d ⚠n<5 | 2 | $1,492 | $945 | 100.0% | 63.28% | 73.04% | 1.5 | 42.085 | 100.0% | — |
| 90-180d ⚠n<5 | 3 | $178 | $-4 | 66.7% | -2.13% | 0.32% | 9.2 | -0.2313 | 100.0% | — |
| 180-365d ⚠n<5 | 4 | $78,612 | $-50,491 | 25.0% | -64.23% | -37.87% | 7.1 | -9.0255 | 100.0% | — |
| 365+d | 0 | — | — | — | — | — | — | — | — | — |


**How to read:** `Weighted ROI %` = Σpnl / Σcost (not a simple mean — big bets count more). `Cap eff` = weighted ROI divided by average holding days (ROI per day of locked capital — higher is better). `% exited` = share of positions closed by denizz fully selling before resolve rather than holding to redeem. Sharpe-like only shown where n ≥ 10.

### Biggest PnL drivers in the long-horizon bucket (180–365d)

| Horizon (d) | Cost $ | PnL $ | ROI % | Title |
|---|---|---|---|---|
| 298 | $56,560 | **−$45,135** | **−79.8%** | US forces enter Iran by December 31? |
| 297 | $14,496 | −$609 | −4.2% | Will Mojtaba Khamenei be the next Supreme Leader of Iran? |
| 297 | $6,689 | −$4,785 | −71.5% | Will Mojtaba Khamenei be the next Supreme Leader of Iran? |
| 267 | $867 | +$39 | +4.5% | Netanyahu out by end of 2026? |

**⚠️ Interpretation warning.** One position — "US forces enter Iran by December 31?" — accounts for **≈89% of the bucket's total loss and ≈72% of its total cost**. This is arguably a war/invasion-event question that our keyword filter didn't catch ("enter" isn't on the exclude list). Without it, the 180-365d bucket is close to break-even on tiny size. Read this as: **"denizz has one giant long-horizon loser on an Iran invasion market" rather than "all denizz's long-horizon politics trades are bad."** The hypothesis is still supported directionally because concentration risk on long-horizon thin markets *is itself* a relevant signal for copy-trading.

## Signal-loss sensitivity (if we add a hard cutoff on denizz politics signals)

| Cutoff | % signals dropped | $ invested dropped | $ PnL dropped (denizz's own) |
|---|---|---|---|
| > 30d | 30.0% | $80,283 | $-49,550 |
| > 90d | 23.3% | $78,791 | $-50,494 |
| > 180d | 13.3% | $78,612 | $-50,491 |
| > 365d | 0.0% | $0 | $0 |


Note: the "$ PnL dropped" column is denizz's own realized P&L on those dropped positions, not the copy-bot's — but direction is representative because the copy-bot fills at approximately the same prices (the 90d backtest assumed zero slippage).

## Validation against our copy-bot tracker (`positions.json`)

- Our bot has **50** closed positions total, of which **30** we classify as politics by title keywords.
- Combined cost $1,689, realized PnL $+115, win rate 63%, avg hold 0.3 days.
- **Caveat:** our `positions.json` does **not** store `end_date`, so we can't bucket our own trades by horizon without re-fetching market metadata per position. Direction only — see the existing `2026-04-09_denizz-90d-backtest.md` for bot-level P&L.
- The 90d backtest already shows the pattern: the biggest single loss (−$104) and a long tail of $0 `eom_close` exits are on long-horizon Iran-leadership / Iran-nuclear-deal / Khamenei-out / ceasefire-phase-II markets. The best wins are short-horizon monthly "by January 31 / by March 31" markets.

## Confounders & critical assessment

| Confounder | Direction of bias | Notes |
|---|---|---|
| **Sample size** | Both ways | Politics buckets at 180d+ and 365d+ are typically n<10. Treat them as directional only. |
| **Survivorship** | Favors short-horizon | Short-horizon markets resolve fast, so we have *realized* PnL for them. Long-horizon positions are more likely still open → excluded → we only see the ones denizz already bailed on (probably losers). |
| **Category mix inside politics** | Uncertain | "Iran leadership change by Dec 31" and "US strikes Iran by Jan 31" behave very differently even though both are politics. Long-horizon bucket is dominated by a few specific themes (Iran leadership, Abraham Accords, ceasefire phase-II), not a diversified politics portfolio. |
| **Time-period bias** | Optimistic for short | Our data window (effectively Jan–Apr 2026) coincides with very active Iran/Israel news flow — a regime where short-horizon strike/ceasefire markets moved a lot. A quieter news regime might compress the advantage. |
| **Zero-slippage assumption in prior backtest** | Optimistic for short | Short-horizon, high-liquidity markets actually are easier to fill at quoted prices; long-horizon thin markets suffer worse slippage, so the *real* gap between buckets is probably **larger** than what we compute. |
| **Full-exit-before-resolve definition** | Mild optimism | If denizz dumped at a loss then rebought later, we count it as two positions or as one long position depending on asset-id reuse. Our (cid, asset) grouping merges all buys/sells for the same token. |
| **eom_close artefacts** | Only in our bot | Our positions.json shows many $0 `eom_close` exits on long-horizon markets — this is a bot artifact (end-of-month cleanup at break-even) that inflates our own observed win-rate without showing the opportunity cost of capital locked. |
| **denizz mixes into war events** | Dilutes politics | denizz has very large positions on "US strikes Iran by X" which we *exclude* as war events. His realized politics-only PnL is much smaller than his total PnL. |

## Intervention options (do NOT pick a winner — just lay them out)

### A) Hard cutoff: refuse entry if `end_date − now > N days`

| Pros | Cons |
|---|---|
| Simplest possible rule; one config line | Binary — drops good long-horizon trades too (e.g. Abraham Accords worked for denizz) |
| Frees max_concurrent slots for short-horizon winners | Sensitive to where you put the cutoff; thin data at the boundary |
| Easy to A/B | Doesn't help at all with horizons *just under* the cutoff |

- If cutoff = 180d: drop **13%** of denizz politics signals, **$78,612** of historical investment, denizz's own PnL on those = $-50,491.
- If cutoff = 90d: drop **23%** / $78,791 / $-50,494.
- If cutoff = 30d: drop **30%** / $80,283 / $-49,550.

### B) Linear / piecewise scale-down of bet multiplier

Example: `mult = 1.0 if h<30d else 0.5 if h<180d else 0.1 if h<365d else 0.0`

| Pros | Cons |
|---|---|
| Keeps some exposure to long-horizon winners while capping downside | Three parameters to tune; danger of overfitting to this specific window |
| Smooth at bucket boundaries (if linear) | Small bets in long-horizon may be below min-bet size and silently skipped |
| Compounds nicely with existing "late entry" multiplier | Hard to explain to yourself in 3 months |

### C) Bucket-based discrete multipliers (fit to this report)

e.g. {0-7d: 1.2, 7-30d: 1.0, 30-90d: 0.7, 90-180d: 0.4, 180+: 0.15}.

| Pros | Cons |
|---|---|
| Direct mapping from empirical cap-efficiency ranking | Pure overfit to ~30 politics positions in one time window |
| Easy to implement (lookup table) | Will need re-calibration every 1-2 months |
| Makes the hypothesis falsifiable going forward | Discrete jumps at bucket edges |

### D) Slippage tightening on long-horizon entries

Keep sizing the same but refuse to pay > X bps above denizz's fill price, with X shrinking as horizon grows. E.g. long-horizon = fill only if price ≤ denizz_price.

| Pros | Cons |
|---|---|
| Attacks the real root cause on long-horizon (thin books + our lag) | Many misses — we skip the trade when book ticks up 1c |
| No change to position count, just to fill quality | Hard to measure in backtest without tick data |
| Stacks cleanly with A/B/C | Risk of systematically missing the winners because denizz often moves the price himself |

### E) More aggressive time-stop on long-horizon

Force exit if position PnL within ±X% of entry after K days, where (K, X) shrinks with horizon. E.g. short-horizon K=7d ±3%; long-horizon K=5d ±2%.

| Pros | Cons |
|---|---|
| Attacks the real failure mode: capital locked for weeks at 0% ROI (the `eom_close` exits in our tracker) | Risks cutting winners that need time to develop (Abraham Accords took 60+ days) |
| Measurable in historical tracker | Requires mark-to-market loop that the bot may not already have |
| Complementary to A-D | Another timer adds operational complexity |

### F) Combination (A-lite + D + E)

"Don't hard-block, but (i) soft cap size via option B or C above ~90d, (ii) require price ≤ denizz fill for >90d entries, (iii) time-stop at ±2% after 7 days for >90d positions."

| Pros | Cons |
|---|---|
| Each lever is mild on its own — more robust to being wrong about any one lever | More code paths to maintain and test |
| Exposure shrinks gradually as horizon grows | Harder to A/B cleanly — need per-lever kill switch |
| Doesn't throw away any denizz signal outright | Many parameters — risk of overfitting |

## Data quality — what we DON'T know

- **Window is only ~33 days, not "6-12 months".** The data-api `/activity` endpoint returns HTTP 400 beyond `offset=3500`. denizz is a very high-volume trader, so 3500 rows ≈ 2026-03-07 through 2026-04-09 — just one month. This is the single biggest limitation of the analysis. The politics buckets are thin because of this, and the entire analysis reflects the late-March / early-April 2026 regime (Iran tensions at peak) only. To extend the window we would need either (a) a different endpoint that supports date range or (b) historical snapshots saved daily going forward.
- **Gamma `category` is unreliable.** Many markets return empty or just `"world"`. We lean on keyword matching, which has false positives (flagged any `leadership` keyword) and false negatives (novel phrasing).
- **No mark-to-market for still-open positions.** We simply exclude them from the bucket math — this is the main survivorship hole.
- **No orderbook depth data** — we can't verify the slippage intuition in option D.
- **Copybot tracker has no `end_date`.** Validation is weak; the full empirical story is on denizz's own side.
- **Single time window.** Everything here is Jan–Apr 2026. A different news regime (quiet geopolitics, active US election) could flip the rankings.
- **Binary win/loss coarseness.** We treat outcome_index in {0,1} as win/lose at resolve; multi-outcome markets with partial prices are handled best-effort, could be wrong on edge cases.

---

*Raw trade rows (politics only) saved to `_analytics/data/denizz_politics_trades.json` — re-run the bucket math without refetching by loading that file.*
