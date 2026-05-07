# Quick Start

Get the main trading bot (`98_sure_bot`) running in under 10 minutes.

---

## Prerequisites

- Python 3.10+
- A Polygon wallet with USDC balance (see Step 1)
- A Telegram bot (see Step 2)

---

## Step 1 — Set Up a Polygon Wallet

You need a wallet with USDC on Polygon PoS to place trades.

**Option A: MetaMask (recommended)**
1. Install MetaMask browser extension
2. Switch network to **Polygon PoS** (Chain ID: 137)
3. Bridge USDC to Polygon via [app.across.to](https://app.across.to) or buy directly
4. Export your private key: MetaMask → Account Details → Export Private Key

**Option B: Generate a new wallet**
```bash
python -c "from eth_account import Account; a = Account.create(); print('Address:', a.address); print('Key:', a.key.hex())"
```

> **Security:** Never share your private key. Never commit it to git. Store it only in `.env`.

---

## Step 2 — Create a Telegram Bot

1. Open Telegram, find **@BotFather**
2. Send `/newbot` → follow prompts → copy the **token**
3. Start a chat with your new bot
4. Get your chat ID: open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` after sending any message

---

## Step 3 — Install and Configure

```bash
# Clone the repository
git clone https://github.com/vladimirbutov/polymarket-trading-system
cd polymarket-trading-system/Bots/98_sure_bot

# Install dependencies
pip install -r requirements.txt

# Create your .env file
cp .env.example .env
```

Edit `.env`:
```
POLYMARKET_WALLET=0xYourWalletAddress
POLYMARKET_PRIVATE_KEY=0xYourPrivateKey
TELEGRAM_BOT_TOKEN=123456:ABC-yourtoken
TELEGRAM_CHAT_ID=123456789
```

---

## Step 4 — Review Parameters

Open `config.py` and check the key trading parameters:

```python
BET_SIZE_REGULAR = 20.00   # $ per trade — start with $5 to test
MAX_TOTAL_FROZEN = 1000    # max $ in open positions at once
PRICE_THRESHOLD_DEFAULT = 0.965  # min market price (96.5¢)
MAX_PRICE = 0.995          # max market price (99.5¢)
```

**For a first test run**, reduce `BET_SIZE_REGULAR` to `5.00` and `MAX_TOTAL_FROZEN` to `100`.

---

## Step 5 — Run the Bot

```bash
python main.py
```

You'll see log output like:
```
[14:32:01] Scan #1: fetching markets...
[14:32:03] Found 847 open markets
[14:32:04] 14 candidates passed price filter
[14:32:05] 2 candidates passed all 14 filters
[14:32:06] ORDER PLACED: "Will ceasefire hold through Sunday?" @ 97.1¢, $20.00
[14:32:11] ORDER FILLED: 20.59 shares @ 97.1¢
```

Telegram will receive a notification for each trade.

---

## Step 6 — Monitor via Dashboard

The web dashboard shows real-time P&L, open positions, and bot status.

**Live dashboard:** [poly-bot-green.vercel.app](https://poly-bot-green.vercel.app)

To run locally:
```bash
cd ../../dashboard
pip install -r requirements.txt
python app.py
# Open http://localhost:8080
```

---

## What Happens Automatically

Once running, the bot handles everything:

| Action | When |
|--------|------|
| Scan markets | Every 5 minutes |
| Place limit orders | When a qualifying market is found |
| Cancel unfilled orders | After 5 minutes (TTL) |
| Redeem winning positions | Within 10 minutes of market resolution |
| Send Telegram alerts | On every trade event |
| 8-hour portfolio report | At 13:00 and 19:00 Moscow time |

---

## Stopping the Bot

Press `Ctrl+C`. The bot gracefully stops after the current scan cycle completes. Open positions remain in `positions.json` and will be monitored when you restart.

---

## Next Steps

- Read [STRATEGY_GUIDE.md](STRATEGY_GUIDE.md) to understand how the bot selects markets
- See [CONFIG_GUIDE.md](Bots/98_sure_bot/CONFIG_GUIDE.md) for all tunable parameters
- Check [TROUBLESHOOTING.md](TROUBLESHOOTING.md) if something doesn't work
