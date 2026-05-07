"""Configuration and constants for the 98_sure_bot."""
import os
from dotenv import load_dotenv

# Load .env from bot directory
ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(ENV_PATH)

# === OUR WALLET ===
OUR_WALLET = os.getenv("POLYMARKET_WALLET", "")
OUR_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")

# === TELEGRAM ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# === CONTRACTS (Polygon PoS) ===
CTF_CONTRACT = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
NEG_RISK_CTF = "0xC5d563A36AE78145C45a50134d48A1215220f80a"  # CTF Exchange (trading)
NEG_RISK_ADAPTER = "0xd91e80cf2e7be2e162c6513ced06f1dd0da35296"  # NegRiskAdapter (resolution + redeem)

# === NETWORK ===
POLYGON_RPC = "https://polygon.gateway.tenderly.co"
CHAIN_ID = 137

# === POLYMARKET API ===
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"

# === TRADING PARAMETERS ===
PRICE_THRESHOLD = 0.96     # minimum outcome price (lowered for politics)
PRICE_THRESHOLD_DEFAULT = 0.965  # non-politics: min price lowered for live test (was 0.975)
PRICE_THRESHOLD_POLITICS = 0.96  # politics/geopolitics: min price 96%
MAX_PRICE = 0.995          # do NOT buy above this price (ROI too small)
MAX_POLITICS_FRACTION = 0.30  # max 30% of balance in politics positions
BET_SIZE_REGULAR = 20.00   # bet per regular market in USD
BET_SIZE_NEG_RISK = 15.00  # bet per neg_risk market in USD
BET_SIZE_SUB_MATCH = 5.00  # bet per game/map/set market (blocked by sub-match filter)
BET_SIZE_WEATHER = 10.00   # weather markets
BET_SIZE_SLOW = 5.00       # slow-keyword markets (was $1)
BET_SIZE_TEST_LOW = 5.00   # live test: non-politics 96.5-97.5% range (min ~$4.85 for 5 shares)
BET_SIZE = BET_SIZE_REGULAR  # backward compat (used in balance checks)
MAX_NEG_RISK_FROZEN = 350  # max $ frozen in neg_risk positions (was 175)
MAX_TOTAL_FROZEN = 1000    # max $ total in all open positions combined
MAX_END_DATE_REGULAR = 3   # max days to end_date for regular markets
MAX_END_DATE_NEG_RISK = 3  # max days to end_date for neg_risk markets
MIN_LIQUIDITY = 500        # minimum market liquidity in USD
MIN_VOLUME = 500            # minimum total market volume in USD (was 3000→1000→500: backtest 0L across all volume buckets)
SCAN_INTERVAL = 300        # seconds between scans (5 minutes)
MIN_SHARES = 5             # Polymarket minimum shares per order
MIN_ASK_DEPTH = 5.0           # minimum ask-side depth in USD to place order
ORDER_CHECK_INTERVAL = 5      # seconds between fill status checks (was 10)
ORDER_TTL_SECONDS = 300    # cancel unfilled orders after 5 min (15 min tested — no improvement, just froze capital)
MAX_PRICE_DIVERGENCE = 0.03  # max allowed difference between Gamma API price and CLOB price (3c)

# === SLIPPAGE TABLE ===
# Price range -> max allowed slippage (added to market price for limit order)
# Raised +0.1c per bucket (2026-03-20 optimization: improve fill rate)
SLIPPAGE_RULES = [
    (0.960, 0.975, 0.005),  # 96-97.5%: wider slippage ok (higher ROI)
    (0.975, 0.985, 0.004),  # (min_price, max_price, max_slippage)
    (0.985, 0.990, 0.003),
    (0.990, 0.995, 0.003),  # EXPERIMENT 2026-03-26: was 0.002, target fill rate >= 10.85% (breakeven). Revert if fill rate stays <= 10%
]

# === ORDERBOOK BUFFER TABLE ===
# When using CLOB best_ask price, add small buffer to account for
# price movement between book check and order placement.
# Buffer is smaller than SLIPPAGE_RULES because we already know the real price.
BUFFER_RULES = [
    (0.960, 0.975, 0.003),  # politics range: +0.3c buffer
    (0.975, 0.985, 0.002),  # +0.2c buffer
    (0.985, 0.990, 0.001),  # +0.1c buffer
    (0.990, 0.995, 0.001),  # +0.1c buffer
]

# === PATHS ===
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(BOT_DIR, "positions.json")
LOG_FILE = os.path.join(BOT_DIR, "bot_log.txt")
