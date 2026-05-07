# Deployment

## Local (Default)

The standard setup — bots run as Python processes on your local machine.

```bash
cd Bots/98_sure_bot
python main.py
```

**Keep alive on Windows:** Use Windows Task Scheduler to auto-restart on crash.

1. Open Task Scheduler → Create Basic Task
2. Trigger: At startup / On an event (application error)
3. Action: Start a program → `python` → Arguments: `C:\path\to\Bots\98_sure_bot\main.py`
4. Set working directory to the bot folder

---

## Running Multiple Bots

Each bot is an independent process. Run in separate terminal windows or use the dashboard:

```bash
# Terminal 1
cd Bots/98_sure_bot && python main.py

# Terminal 2
cd Bots/25_multi_signal_copybot_v2 && python main.py

# Or via dashboard (start/stop buttons)
cd dashboard && python app.py
```

---

## Dashboard Deployment

### Local (development)
```bash
cd dashboard
pip install -r requirements.txt
python app.py
# Opens at http://localhost:8080
```

### Vercel (frontend only)
The Next.js frontend is deployed to Vercel. The FastAPI backend stays local.

```bash
cd dashboard/frontend
npx vercel deploy --prod
```

Configure the frontend's API base URL to point to your local FastAPI via a tunnel (see below).

### Remote access via Cloudflare Tunnel
```bash
# Install cloudflared
# https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

cloudflared tunnel --url http://localhost:8000
# Prints a URL like: https://abc123.trycloudflare.com
```

Set this URL as the API base in your frontend `.env`:
```
NEXT_PUBLIC_API_URL=https://abc123.trycloudflare.com
```

---

## Cloud Deployment (Advanced)

To run bots on a cloud VM (AWS EC2, DigitalOcean Droplet, etc.):

**1. Provision a VM**
- Ubuntu 22.04 LTS
- At least 1 GB RAM, 1 vCPU
- Open no inbound ports (bots are outbound-only)

**2. Transfer files securely**
```bash
# Never scp .env — set it manually on the server
scp -r Bots/98_sure_bot user@server:/home/user/bots/
```

**3. Set up environment**
```bash
ssh user@server
cd /home/user/bots/98_sure_bot
pip install -r requirements.txt
nano .env  # Enter secrets manually
```

**4. Run as a systemd service**
```ini
# /etc/systemd/system/98_sure_bot.service
[Unit]
Description=98_sure_bot
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/bots/98_sure_bot
ExecStart=/usr/bin/python3 main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable 98_sure_bot
sudo systemctl start 98_sure_bot
sudo journalctl -u 98_sure_bot -f  # live logs
```

---

## Production Checklist

Before going live with real money:

- [ ] Tested with minimum bet size ($5) for at least 50 trades
- [ ] `MAX_TOTAL_FROZEN` set to ≤ 50% of your balance
- [ ] Telegram alerts confirmed working
- [ ] `.env` not in git (`git status` shows no `.env`)
- [ ] Wallet has both USDC (for trading) and MATIC (for gas, min 0.1)
- [ ] Redemption tested — at least one position has been redeemed successfully
- [ ] Dashboard accessible and showing correct P&L
- [ ] Bot auto-restart configured (Task Scheduler or systemd)
