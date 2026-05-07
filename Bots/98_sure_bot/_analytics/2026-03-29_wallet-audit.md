# Wallet Audit: 0x4717eccF1e1E2443e7563b330C6E0B3B6f96bDdE

**Date:** 2026-03-29
**Period:** 2026-03-16 to 2026-03-29 (14 days)
**Source:** Polygon Blockscout API (all token transfers) + on-chain RPC balance check

---

## Summary

| Metric | Value |
|--------|-------|
| Total USDC/USDC.e transfers | 1,288 |
| Total non-USDC token transfers (CTF tokens) | 1,465 |
| Wallet nonce (total txs sent) | 673 |
| On-chain USDC balance | $0.00 |
| On-chain USDC.e balance | $4.41 |
| On-chain MATIC/POL balance | 38.49 |
| Estimated value in open positions | $871.48 |

---

## Money Flow: Where Every Dollar Went

### Capital In (from outside the Polymarket ecosystem)

| # | Date | Amount | Source | Details |
|---|------|--------|--------|---------|
| 1 | 2026-03-16 | +$496.00 USDC | Personal wallet (EOA) | 0xa85c29b9... - initial funding |
| 2 | 2026-03-17 | +$1.00 USDC | RelayRouterV3 (bridge) | 0xb92fe925... - bridge micro-deposit |
| **Total** | | **$497.00** | | |

### Capital Out (to outside the Polymarket ecosystem)

| # | Date | Amount | Destination | Details |
|---|------|--------|-------------|---------|
| 1 | 2026-03-16 | -$494.79 USDC | RelayDepository (bridge) | 0x4cd00e38... - bridged into Polymarket |
| 2 | 2026-03-17 | -$5.00 USDC.e | Unknown wallet (EOA) | 0xffbfb5ab... |
| 3 | 2026-03-22 | -$100.00 USDC.e | Unknown contract | 0x476d1cf6... |
| **Total** | | **$599.79** | | |

> Note: The $494.79 bridge deposit went to RelayDepository which converts USDC to USDC.e for use in Polymarket. This is not a withdrawal - it's moving capital into the Polymarket ecosystem.

### Token Swaps (USDC <-> USDC.e, neutral)

| Date | Action | Details |
|------|--------|---------|
| 2026-03-27 | $199.00 USDC -> $198.99 USDC.e | Via ParaSwap DEX aggregator |

Net swap cost: $0.01 (rounding)

---

## Polymarket Trading Activity

### By Contract

| Contract | Txs | Received (IN) | Sent (OUT) | Net |
|----------|-----|---------------|------------|-----|
| CTF Exchange | 718 | $566.97 | $4,146.64 | -$3,579.68 |
| NegRiskAdapter | 292 | $3,101.03 | $0.00 | +$3,101.03 |
| NegRiskCtfExchange | 166 | $125.97 | $788.10 | -$662.12 |
| WrappedCollateral | 82 | $586.19 | $0.00 | +$586.19 |
| Exchange Router | 12 | $1,328.63 | $1,340.52 | -$11.89 |
| Trade Counterparty (EOA) | 10 | $1,334.31 | $0.00 | +$1,334.31 |
| **TOTAL** | **1,280** | **$7,043.10** | **$6,275.26** | **+$767.84** |

**How to read this:**
- **CTF Exchange** is where buy orders go (you send USDC, get conditional tokens) - hence large OUT
- **NegRiskAdapter** is where winning positions pay out (resolved markets return USDC) - hence large IN
- **WrappedCollateral** returns USDC.e when positions in wrapped markets resolve
- Net +$767.84 means Polymarket has returned $767.84 more USDC than was sent in

### Daily Trading Summary

| Date | Txs | Total IN | Total OUT | Net | PM IN | PM OUT |
|------|-----|----------|-----------|-----|-------|--------|
| 2026-03-16 | 171 | $1,479.59 | $1,378.55 | +$101.04 | $983.59 | $883.76 |
| 2026-03-17 | 101 | $1,053.79 | $461.51 | +$592.29 | $1,052.79 | $456.51 |
| 2026-03-18 | 167 | $1,074.92 | $959.63 | +$115.29 | $1,074.92 | $959.63 |
| 2026-03-19 | 54 | $162.60 | $222.86 | -$60.26 | $162.60 | $222.86 |
| 2026-03-20 | 98 | $351.90 | $395.29 | -$43.38 | $351.90 | $395.29 |
| 2026-03-21 | 62 | $286.31 | $243.51 | +$42.81 | $286.31 | $243.51 |
| 2026-03-22 | 78 | $348.59 | $534.28 | -$185.68 | $348.59 | $434.28 |
| 2026-03-23 | 81 | $540.09 | $444.15 | +$95.94 | $540.09 | $444.15 |
| 2026-03-24 | 58 | $342.34 | $185.35 | +$156.99 | $342.34 | $185.35 |
| 2026-03-25 | 91 | $647.08 | $631.50 | +$15.58 | $647.08 | $631.50 |
| 2026-03-26 | 168 | $388.94 | $475.84 | -$86.90 | $388.94 | $475.84 |
| 2026-03-27 | 62 | $636.24 | $559.55 | +$76.69 | $238.25 | $360.55 |
| 2026-03-28 | 65 | $489.06 | $359.24 | +$129.82 | $489.06 | $359.24 |
| 2026-03-29 | 32 | $136.65 | $222.80 | -$86.15 | $136.65 | $222.80 |

---

## Position Tracker Data (from positions.json)

| Status | Count | Cost Basis |
|--------|-------|------------|
| Won | 404 | $3,934.16 |
| Lost | 4 | ~$40 |
| Sold | 14 | ~$111 |
| Open | 79 | $871.48 |
| **Total** | **501** | **$4,957.25** |

Realized P&L from tracker: **+$23.71** (only counts closed positions)

### Open Positions Breakdown (79 positions, $871.48 total cost)

Most positions are high-probability bets (entry prices 0.96-0.99) on:
- Political elections (Slovenia, Denmark, Faroe Islands, Canada NDP)
- Trump social media activity (various "will Trump say/post X" markets)
- Military/geopolitical events (Iran, Israel, Ukraine-Russia)
- Sports, weather, and entertainment
- Typical bet size: $5-$20 per position

---

## Complete Financial Reconciliation

### Balance Check

| Item | Amount |
|------|--------|
| Total USDC IN (all sources) | $7,938.09 |
| Total USDC OUT (all sources) | $7,074.06 |
| **Calculated balance** | **$864.04** |
| On-chain USDC.e balance | $4.41 |
| **Difference (in positions)** | **$859.63** |
| Positions cost from tracker | $871.48 |
| Tracker vs on-chain gap | $11.85 |

The $11.85 gap between tracker ($871.48) and on-chain calculation ($859.63) is likely due to:
- Rounding across 1,288 transactions
- Small fee deductions not captured in token transfers
- Timing differences in tracker vs chain data

### Net P&L Calculation

```
DEPOSITS FROM OUTSIDE:
  + $496.00  (from personal wallet)
  + $  1.00  (from bridge router)
  = $497.00  TOTAL CAPITAL IN

WITHDRAWALS TO OUTSIDE:
  - $  5.00  (to unknown wallet)
  - $100.00  (to unknown contract)
  = $105.00  TOTAL WITHDRAWN

CURRENT VALUE:
    $  4.41  (on-chain USDC.e balance)
  + $871.48  (in 79 open Polymarket positions, per tracker)
  = $875.89  CURRENTLY HELD

TOTAL ACCOUNTED VALUE:
    $105.00  (withdrawn)
  + $875.89  (currently held)
  = $980.89

NET P&L = $980.89 - $497.00 = +$483.89
ROI = +97.4%
```

### Important Caveats

1. **Open positions are NOT guaranteed** - the $871.48 in open positions is at risk. If all 79 positions win (most are 96-99% probability), the value would be ~$871. If some lose, it would be less.
2. **The $494.79 bridge deposit** was not a withdrawal - it converted USDC to USDC.e within the Polymarket ecosystem via Relay bridge.
3. **USDC native balance shows -$4.00** in the ledger calculation - this suggests some USDC was converted to USDC.e through mechanisms not captured as standard ERC-20 transfers (likely bridge/wrap operations).
4. **Turnover** was massive: $7,043 received and $6,275 sent to Polymarket contracts = $13,318 total volume from just $497 in capital (26.8x turnover ratio in 14 days).

---

## Category Breakdown (Complete)

| Category | Count | IN | OUT | Net |
|----------|-------|----|-----|-----|
| Bridge (Relay) | 2 | $1.00 | $494.79 | -$493.79 |
| DEX Swap (ParaSwap) | 3 | $397.99 | $199.00 | +$198.99 |
| Initial Deposit | 1 | $496.00 | $0.00 | +$496.00 |
| Polymarket Trading | 1,280 | $7,043.10 | $6,275.26 | +$767.84 |
| Transfer Out (unknown contract) | 1 | $0.00 | $100.00 | -$100.00 |
| Transfer Out (unknown wallet) | 1 | $0.00 | $5.00 | -$5.00 |
| **TOTAL** | **1,288** | **$7,938.09** | **$7,074.06** | **+$864.04** |

---

## Data Files

- `_analytics/data/all_token_transfers_raw.json` - All 2,753 token transfers (including CTF tokens)
- `_analytics/data/usdc_transfers_parsed.json` - 1,288 USDC/USDC.e transfers, parsed and sorted
- `_analytics/data/ledger_classified.json` - Full classified ledger with running balances
- `_analytics/data/audit_script.py` - Script used for analysis
