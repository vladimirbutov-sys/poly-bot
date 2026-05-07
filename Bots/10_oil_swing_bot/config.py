"""Configuration for Oil Swing Trading Bot."""
import os
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(ENV_PATH)

# === WALLET ===
OUR_WALLET = os.getenv("POLYMARKET_WALLET", "")
OUR_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")

# === TELEGRAM ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ANALYTICS_TELEGRAM_BOT_TOKEN = os.getenv("ANALYTICS_TELEGRAM_BOT_TOKEN", "")
ANALYTICS_TELEGRAM_CHAT_ID = os.getenv("ANALYTICS_TELEGRAM_CHAT_ID", "")

# === POLYMARKET API ===
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137

# === MARKET: Will Crude Oil (CL) hit $100 by end of March? ===
YES_TOKEN_ID = "79605660806991457811890435537160628976099500543939220857753925926896831621219"
NO_TOKEN_ID = "92274168594309301674860132535303917340223623966677593281435938105131107664927"

# === STRATEGY PARAMETERS ===
BANKROLL = 300.0

# Gradient entry: buy YES in 3 steps as WTI drops
# Fixed USD amounts per step
YES_ENTRY_STEPS = [
    # (wti_trigger, bet_usd)
    (92.0, 20.0),   # Step 1: WTI <= $92 -> $20 (разведка)
    (90.0, 20.0),   # Step 2: WTI <= $90 -> $20 (подтверждение)
    (88.0, 60.0),   # Step 3: WTI <= $88 -> $60 (основная позиция)
]

# Gradient exit: sell YES in 3 steps as WTI rises
YES_EXIT_STEPS = [
    # (wti_trigger, pct_of_position)
    (97.0, 0.3),   # Step 1: WTI >= $97 -> sell 30%
    (99.0, 0.5),   # Step 2: WTI >= $99 -> sell 50%
    (100.0, 1.0),   # Step 3: WTI >= $100 -> sell 100%
]

# Gradient entry: buy NO in 3 steps as WTI rises
NO_ENTRY_STEPS = [
    # (wti_trigger, bet_usd, profit_target)
    (97.0, 20.0, 0.35),   # Step 1: WTI >= $97 -> $20, sell at +35%
    (98.0, 20.0, 0.69),   # Step 2: WTI >= $98 -> $20, sell at +69%
    (99.0, 40.0, 1.04),   # Step 3: WTI >= $99 -> $40, sell at +104%
]

# NO exit
WTI_SELL_NO_BELOW = 91.0      # Sell NO when WTI drops below this

# Profit-based exit thresholds (OR condition with WTI-based exits)
YES_PROFIT_TARGET = 0.21  # Sell YES if position profit >= 21%
# NO profit targets are per-step — defined in NO_ENTRY_STEPS above

# Max entry prices — don't buy if token is too expensive (limited upside)
MAX_YES_ENTRY_PRICE = 0.28  # Don't buy YES above 59c
MAX_NO_ENTRY_PRICE = 0.16  # Don't buy NO above 22c (tightened from 26c)

# Position sizing
# Each bet <= 25% of FREE balance (bankroll minus already invested)
# Example: bankroll $300, invested $75 -> free $225 -> max bet $56
MAX_BET_FREE_PCT = 0.25
MIN_BET_USD = 5.0             # Minimum bet size
MIN_SHARES = 5                # Polymarket minimum

# Stop-loss
STOP_CEASEFIRE_WTI = 80.0     # Sell ALL YES if WTI < $80 (was $87, raised to avoid false triggers during escalation crashes)
STOP_NO_WTI = 110.0           # Sell NO if WTI > $110
STOP_THETA_DAYS = 3           # Sell YES if held > 3 days without $3+ WTI move
STOP_THETA_WTI_MOVE = 3.0     # Required WTI move to keep YES position
STOP_PORTFOLIO_FLOOR = 200.0  # Stop bot if portfolio < $200

# Order execution
ORDER_TTL_SECONDS = 600       # Cancel unfilled orders after 10 min
MAX_SLIPPAGE = 0.03           # Max 3pp slippage from mid price

# Dead zone around CME settlement (hours in ET)
DEAD_ZONE_START_ET = 14       # 14:00 ET — stop trading (30 min before settlement)
DEAD_ZONE_END_ET = 15         # 15:00 ET — resume trading (30 min after settlement)

# Global deadline — stop all trading and close positions
DEADLINE_DATE = "2026-03-26"  # 3 trading days before March 31

# Settlement check
SETTLEMENT_TRIGGER = 100.0    # If WTI settlement >= $100, market resolves YES

# Divergence detection
DIVERGENCE_RATIO_NORMAL = -0.23  # expected pp per $1 (measured by Smart Tuner)
DIVERGENCE_ALERT_MULT = 2.0     # alert if actual ratio > 2x expected
DIVERGENCE_WINDOW_HOURS = 4     # measure over 4-hour windows
DIVERGENCE_REDUCE_PCT = 0.50    # reduce position size to 50% during divergence

# Theta: reduce position size as deadline approaches
# (days_remaining, size_multiplier)
THETA_SCALING = [
    (10, 1.00),   # 10+ days: full size
    (7,  0.80),   # 7-9 days: 80%
    (5,  0.60),   # 5-6 days: 60%
    (3,  0.30),   # 3-4 days: 30%
    (0,  0.00),   # 0-2 days: don't enter
]

# Step cooldown — minimum time between gradient steps (seconds)
STEP_COOLDOWN = 1800            # 30 min between gradient steps

# Momentum filter — block NO entry if WTI rose too fast
MOMENTUM_BLOCK = 2.0            # Don't buy NO if WTI rose >$2 in window
MOMENTUM_WINDOW = 6             # Window size in data points (~6 hours)

# Weekend block — no positions over weekend
WEEKEND_BLOCK = True            # Block entries Fri 20 ET - Mon 09 ET
FRIDAY_CLOSE_HOUR_ET = 16       # Close all positions Friday at 16:00 ET

# Scan interval
SCAN_INTERVAL = 60              # Check prices every 60 seconds

# === PATHS ===
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(BOT_DIR, "positions.json")
