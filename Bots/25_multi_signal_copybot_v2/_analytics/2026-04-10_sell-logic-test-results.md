# Sell Logic Test Results — On-Chain Truth Architecture

**Date:** 2026-04-10
**Result:** 28/28 PASS, 0 FAIL

## Architecture Change

Replaced event-based `sold_pct` (from monitor's `old_size`/`sold_shares`) with **on-chain truth**:

```
Monitor hint → cache lookup → CTF.balanceOf(denizz, token) → actual_sold = cached - current
```

- Player size cache: in-memory, initialized from data-api at startup (451 positions for denizz)
- Periodic refresh: every ~60 seconds for tokens where we have open positions (2-10 RPC calls)
- Fail-safe: if RPC fails → do NOT sell

## Test Scenarios

### Group A: Phantom sells (all BLOCKED ✓)
| ID | Scenario | Cache | OnChain | Result |
|---|---|---|---|---|
| A1 | API pagination drop | 396k | 396k | BLOCKED |
| A2 | Activity replay, old_size=0 | 396k | 396k | BLOCKED |
| A3 | Startup recovery phantom | 396k | 396k | BLOCKED |
| A4 | Snapshot jitter (40/10000=0.4%) | 10k | 9960 | BLOCKED (dust) |
| A5 | Double phantom in 1 second | 396k | 396k | BLOCKED (both) |

### Group B: Real sells (all correct ✓)
| ID | Scenario | Cache | OnChain | Result |
|---|---|---|---|---|
| B1 | Real 100% dump | 5k | 0 | FULL EXIT |
| B2 | Real 100% dump, old_size=0 | 5k | 0 | FULL EXIT |
| B3 | Real 30% partial (player loss) | 10k | 7k | MIRROR 30% |
| B4 | Real 30% partial, old_size=0 | 10k | 7k | MIRROR 30% |
| B5 | Real 80% dump | 10k | 2k | FULL EXIT |
| B6 | Real 5% dust | 10k | 9.5k | BLOCKED (dust) |

### Group C: Edge cases (all correct ✓)
| ID | Scenario | Result |
|---|---|---|
| C1 | RPC error | BLOCKED (fail-safe) |
| C2 | No cache baseline | BLOCKED (cached for next) |
| C3 | Player increased position | BLOCKED (phantom) |
| C4 | Merge event | FULL EXIT (bypass verify) |
| C5 | Dedup 2nd event at 0s | BLOCKED |
| C6 | Dedup expired at 70s | MIRROR 43% (processed) |

### Group D: Decision matrix (all correct ✓)
| ID | Player | Us | Result |
|---|---|---|---|
| D1 | partial 30%, loss | loss | MIRROR 30% (rule 2a) |
| D2 | partial 30%, loss | profit | MIRROR 30% (rule 2a) |
| D3 | partial 30%, profit | profit | MIRROR 30% (rule 2b) |
| D4 | partial 30%, profit | loss | BLOCKED (skip) |
| D5 | big dump 80% | any | FULL EXIT (rule 3) |
| D6 | dust 5% | any | BLOCKED (dust) |

### Group E: Historical incidents (all correct ✓)
| ID | Incident | Result |
|---|---|---|
| E1 | Iran Apr 15 phantom (API pagination, denizz 396k) | BLOCKED |
| E2 | Iranian regime fall phantom (denizz 252k) | BLOCKED |
| E3 | Hezbollah Jun 30 burst (7 events, real 29%) | 1× MIRROR, 6× dedup SKIP |
| E4 | Trump Iran real 100% dump | FULL EXIT |
| E5 | Hezbollah Apr 30 29% profit, we NOT in profit | BLOCKED (skip) |

## Key Protection Layers

1. **On-chain truth**: `actual_sold = cached_size - current_onchain`. If ≤ 0 → phantom.
2. **Dedup guard**: 60s window per (player, cid, token). Burst events → 1 sell.
3. **Fail-safe**: RPC error → do NOT sell.
4. **Monitor verify**: Snapshot diff also checks on-chain before emitting sell event.
5. **Decision matrix**: dust/big-dump/mirror rules unchanged, but fed by reliable data.
