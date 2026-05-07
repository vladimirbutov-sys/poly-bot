"""core/config.py — Общая конфигурация"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent.parent
load_dotenv(ROOT_DIR / ".env")

# Telegram Bot (алерты)
TG_BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TG_CHAT_ID", "")

# Twitter
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "")
TWITTER_POLL_INTERVAL = int(os.getenv("TWITTER_POLL_INTERVAL", "300"))

# Anthropic
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# YouTube Data API v3
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# Facebook Graph API
FACEBOOK_ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN", "")

# Polymarket
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
MARKET_CACHE_INTERVAL = int(os.getenv("MARKET_CACHE_INTERVAL", "300"))
MIN_MARKET_VOLUME = float(os.getenv("MIN_MARKET_VOLUME", "10000"))

# CLOB API (for auto-hedge)
POLYMARKET_WALLET = os.getenv("POLYMARKET_WALLET", "")
POLYMARKET_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137

# Пороги
MIN_CONFIDENCE = os.getenv("MIN_CONFIDENCE", "MEDIUM")

# Spike Rider (BIG IDEA)
SPIKE_RIDER_ENABLED = os.getenv("SPIKE_RIDER_ENABLED", "false").lower() == "true"
SPIKE_BET_SIZE_USD = float(os.getenv("SPIKE_BET_SIZE_USD", "5"))
SPIKE_MAX_PER_SIGNAL_USD = float(os.getenv("SPIKE_MAX_PER_SIGNAL_USD", "50"))
SPIKE_DAILY_LIMIT_USD = float(os.getenv("SPIKE_DAILY_LIMIT_USD", "100"))
SPIKE_TAKE_PROFIT_PCT = float(os.getenv("SPIKE_TAKE_PROFIT_PCT", "15"))
SPIKE_TIMEOUT_MIN = int(os.getenv("SPIKE_TIMEOUT_MIN", "60"))
SPIKE_CONFIRM_TIMEOUT_SEC = int(os.getenv("SPIKE_CONFIRM_TIMEOUT_SEC", "120"))  # 2 min to confirm

# Пути
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
CONFIGS_DIR = ROOT_DIR / "configs"
SIGNALS_LOG = DATA_DIR / "signals.jsonl"
MARKET_CACHE_FILE = DATA_DIR / "markets.json"
