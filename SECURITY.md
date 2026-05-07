# Security

## Private Key

The Ethereum private key is the most sensitive piece of data in this system. It controls the wallet and all funds.

**Rules:**
- Stored only in `.env` — never in code, config, comments, or logs
- `.env` is in `.gitignore` — verified before every commit
- The dashboard never displays the private key in any UI
- The private key never appears in Telegram messages

**If your key is compromised:** Move all USDC to a new wallet immediately. Revoke the old wallet from any approvals on Polygon.

---

## Secrets Storage

All secrets in `.env`:
```
POLYMARKET_PRIVATE_KEY   ← Ethereum private key
POLYMARKET_WALLET        ← Wallet address (public, but kept with key for convenience)
TELEGRAM_BOT_TOKEN       ← Controls who can receive alerts
TELEGRAM_CHAT_ID         ← Your personal chat ID
```

**Never:**
- Commit `.env` to git
- Share `.env` in Slack, email, or screenshots
- Use the same key for multiple applications
- Store in cloud storage without encryption

---

## Network Isolation

All bots run on localhost only. The dashboard serves on `localhost:8080` — not accessible from the internet by default.

If you need remote access (e.g., from phone), use a tunnel:
```bash
# Cloudflare Tunnel (recommended — encrypted, no port forwarding)
cloudflared tunnel --url http://localhost:8080

# ngrok (alternative)
ngrok http 8080
```

**Never** configure the bot or dashboard to bind to `0.0.0.0` without authentication — this exposes your controls to the internet.

---

## Git Safety

Before every commit, verify no secrets are staged:
```bash
git diff --cached | grep -i "private_key\|bot_token\|secret"
```

The `.gitignore` excludes:
- `.env` and `*.env`
- `*.db` (databases may contain wallet addresses)
- Large JSON files with trading activity

---

## Transaction Safety

**Minimum required permissions:** The wallet only needs USDC approval for the CTF Exchange contract. It cannot drain itself — it can only place orders up to its USDC balance.

**Nonce management:** Transactions are sent sequentially with 5-second gaps to prevent nonce conflicts. Retries use the same nonce on failure.

**Gas:** Polygon gas fees are < $0.01 per transaction. The wallet needs a small MATIC balance (0.1 MATIC ≈ $0.05) for gas. MATIC is not your trading capital.

---

## Operational Security

- Run the bot as a regular user — not as administrator/root
- Don't run the bot on a shared or public computer
- Lock your screen when leaving the machine
- Use a dedicated wallet for trading — don't mix with personal crypto holdings
