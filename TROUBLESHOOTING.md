# Troubleshooting

Common problems and how to fix them.

---

## Bot Isn't Placing Orders

**Check 1: USDC balance**
```bash
# The bot logs balance on startup. Look for:
grep "Balance:" bot_log.txt | tail -5
```
If balance is 0 or below minimum bet size, add USDC to your wallet.

**Check 2: Are markets available?**
The bot needs markets in the 96–99.5¢ range with ≤ 3 days to resolution. These may not exist at all times. Check [polymarket.com](https://polymarket.com) manually and filter by "Closing soon".

**Check 3: Portfolio limit reached**
If `MAX_TOTAL_FROZEN` is hit, the bot stops placing new orders until existing positions resolve. Check positions.json:
```bash
python -c "import json; d=json.load(open('positions.json')); print('Open:', sum(1 for p in d['positions'].values() if p['status']=='open'))"
```

**Check 4: All candidates failing filters**
Look at the log for filter rejection reasons:
```bash
grep "FILTER" bot_log.txt | tail -20
```

---

## Orders Placed But Never Fill

**Most likely cause:** Your limit price is too low — sellers won't come down to it.

Try raising `SLIPPAGE_RULES` values slightly (add 0.1¢ to each tier). The fill rate vs. cost trade-off is calibrated in `_analytics/` — check the backtest files for your price range.

**Check CLOB orderbook manually:**
```python
import httpx
r = httpx.get("https://clob.polymarket.com/book?token_id=YOUR_TOKEN_ID")
print(r.json()["asks"][:3])  # top 3 ask prices
```
If the ask is at 98.5¢ and your limit is at 97.8¢, the order will never fill.

---

## Telegram Notifications Not Arriving

**Check 1: Token and chat ID**
```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getMe"
```
Should return `{"ok": true, ...}`. If not, your token is wrong.

**Check 2: Bot started the conversation**
Send any message to your bot. Then fetch updates:
```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
```
Copy the `chat.id` value — this is your `TELEGRAM_CHAT_ID`.

**Check 3: Rate limiting**
If many messages are sent in short succession, Telegram may temporarily block. The bot has a 0.5s delay between messages — if you modified this, restore it.

---

## Redemption Not Happening

**Check 1: Market actually resolved?**
```python
import httpx
r = httpx.get(f"https://gamma-api.polymarket.com/markets?condition_id=YOUR_CONDITION_ID")
print(r.json()[0]["closed"], r.json()[0]["resolvedBy"])
```

**Check 2: On-chain balance**
The bot verifies balance before redeeming. If it shows 0, your shares may already be redeemed or never filled on-chain.

**Check 3: Gas**
Polygon transactions need a tiny amount of MATIC for gas. Check your wallet has at least 0.1 MATIC. Add via any Polygon bridge.

**Check 4: Nonce conflict**
If two redemptions triggered simultaneously, one may have failed with a nonce error. Check the log:
```bash
grep -i "nonce\|revert\|reverted" bot_log.txt | tail -10
```
The redeemer will retry on the next cycle (every 5 minutes).

---

## Bot Crashed / Not Responding

**Check if process is still running:**
```bash
# Windows
tasklist | findstr python

# Look for "crashed" status in dashboard
```

**Check last log entry:**
```bash
tail -20 bot_log.txt
```

**Common crash causes:**
- `JSONDecodeError` in positions.json — file corrupted, restore from backup
- `ConnectionError` — internet connection or API outage, retry automatically on restart
- `KeyError` in config — a required config value is missing, check config.py

**Restart:**
```bash
python main.py
```
The bot reads positions.json on startup and resumes monitoring all open positions.

---

## Dashboard Shows Wrong Data

**Force refresh:** Click "Refresh Prices" in the dashboard. Prices are cached for 2 minutes.

**positions.json out of sync:** The dashboard reads this file directly. If a bot crashed mid-write, the file may be corrupted:
```bash
python -c "import json; json.load(open('positions.json'))"
```
If this throws an error, restore the last backup from `_analytics/data/` or manually fix the JSON.

---

## CLOB Authentication Errors (`401 Unauthorized`)

Your private key may be formatted incorrectly in `.env`. It must start with `0x`:
```
POLYMARKET_PRIVATE_KEY=0x1234abcd...
```

Also check that your wallet address matches the private key — they must be a pair.

---

## P&L Looks Wrong

**Check:** positions.json may have stale prices. The P&L displayed = (current price - entry price) × shares. Current price updates on dashboard refresh, not in real-time.

**For closed positions:** P&L is recorded at redemption time. If a position was manually closed or redeemed outside the bot, it may not appear in stats. Check `stats.total_pnl` in positions.json.

---

## Getting More Help

1. Check `_analytics/` for historical research on similar issues
2. Search `bot_log.txt` for the error message
3. Open an issue on GitHub with the relevant log lines