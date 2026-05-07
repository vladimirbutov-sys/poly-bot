# Glossary

Key terms used across this project.

---

## Polymarket Concepts

**Condition ID**
Unique identifier for a prediction market on Polymarket and the Polygon blockchain. Format: `0x...` (32 bytes hex). Used in smart contract calls.

**Token ID**
Identifier for a specific outcome token (YES or NO) within a market. Each market has two token IDs. Used for `balanceOf()` and `redeemPositions()` calls.

**Outcome token**
An ERC-1155 token representing a position. YES token pays $1.00 if the market resolves YES; NO token pays $1.00 if it resolves NO. Both are worth $0 on the losing side.

**Neg-risk market**
A market structure where YES and NO positions can offset each other across related outcomes in the same event. Buying YES on one team and YES on another team in the same match creates "neg-risk" — if both can't win, you can't lose on both. Slightly more complex risk profile; handled separately in the bot.

**Resolution**
When a Polymarket market closes and the outcome is determined. The contract sets `payoutDenominator > 0`, allowing winners to redeem their tokens for $1.00 USDC.

**Redemption**
The on-chain action of converting winning outcome tokens to USDC. Calls `redeemPositions()` on the CTF Exchange or NegRiskAdapter contract.

**Merge**
Converting a complete set of YES+NO tokens (one of each) back to $1.00 USDC. Used in arbitrage: buy YES at 60¢ + NO at 38¢ = 98¢ total → merge → $1.00 = 2¢ profit.

---

## Trading Concepts

**CLOB (Central Limit Order Book)**
The order matching system used by Polymarket for trading. Buyers post limit bids, sellers post limit asks, the system matches them. Same mechanism used by stock exchanges.

**Limit order**
An order to buy/sell at a specific price or better. Unlike a market order (buy at whatever price), a limit order specifies the maximum price you'll pay. Used by all bots in this system.

**TTL (Time To Live)**
How long an order stays open before being automatically cancelled. Set to 300 seconds (5 minutes) in `98_sure_bot`. After TTL, any unfilled portion is cancelled.

**Slippage**
The difference between the expected price and the actual execution price. At 98¢, 1¢ of slippage costs you 50% of the potential profit (2¢ upside). Slippage rules in config control the maximum allowed.

**Fill rate**
Percentage of placed orders that actually execute (get matched). A limit order at too low a price may never fill if sellers won't come down to it.

**EV (Expected Value)**
The average outcome of a trade if repeated many times. EV = (probability of win × profit) - (probability of loss × loss). Positive EV = profitable strategy on average.

**Sharpe ratio**
Risk-adjusted return: (average return - risk-free rate) / standard deviation of returns. Higher = better return per unit of risk.

**Drawdown**
The peak-to-trough decline in portfolio value. Max drawdown = the largest single decline in history. A key risk metric.

**Kelly Criterion**
A formula for optimal bet sizing: bet = edge / odds. In this system, position sizes are determined empirically based on win rates and average ROI rather than full Kelly (which can be too aggressive).

---

## Blockchain Concepts

**Polygon PoS**
The Layer 2 blockchain where Polymarket operates. Faster and cheaper than Ethereum mainnet. Chain ID: 137.

**RPC (Remote Procedure Call)**
The method for querying blockchain state and sending transactions without running a full node. This project uses `polygon.gateway.tenderly.co` as the RPC endpoint.

**USDC**
USD Coin — a stablecoin pegged 1:1 to USD. All Polymarket positions are denominated in USDC on Polygon. Contract: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`.

**CTF Exchange**
Conditional Token Framework — the smart contract system underlying Polymarket. Manages outcome tokens, resolution, and redemption.

**ECDSA**
Elliptic Curve Digital Signature Algorithm. Used to authenticate CLOB API requests. Every order is signed with the trader's Ethereum private key.

**Gas**
Transaction fee on Polygon. Very cheap (fractions of a cent). Used for redemption transactions.

**Nonce**
A sequential counter on Ethereum/Polygon that prevents replay attacks. Each wallet transaction must have a unique, incrementing nonce. Nonce conflicts occur when two transactions try to use the same number simultaneously.

---

## Bot-Specific Terms

**Smart money / Whale**
A Polymarket trader with a verified high-win-rate and large position sizes. This project tracks wallets like denizz (+$447K lifetime P&L) as alpha signals.

**Follow-sell**
The exit mechanism in the copybot: when denizz (the tracked trader) sells a percentage of their position, the bot sells a proportional percentage of ours.

**Top-up**
When denizz adds to an existing position rather than opening a new one. Sized differently from a fresh entry.

**Merge-arbitrage**
A strategy where a trader buys both YES and NO simultaneously at prices summing to < $1.00, then merges them for guaranteed profit. Not a directional trade — copying it as a direction signal is a mistake (see `25_multi_signal_copybot_v2/DOCS.md`).

**Strike market**
A market where the underlying event (sports match, election) is happening today. Higher confidence in near-term resolution; prioritized by `98_sure_bot`.

**Frozen capital**
Money committed to open positions that can't be used for new trades. The bot tracks this to enforce portfolio limits.

**Neg-risk cap**
A sub-limit on frozen capital allocated to neg-risk markets specifically, separate from the overall cap.

**UMA Oracle**
Universal Market Access — the dispute resolution system for Polymarket. If a market resolution is contested, UMA token holders vote on the outcome.

**Dispute**
When a market resolution is challenged via the UMA oracle. During a dispute, the market is temporarily in limbo. Monitored by `22_dispute_monitor`.
