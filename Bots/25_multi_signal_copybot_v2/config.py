"""Configuration for Multi-Signal Copy-Bot.

Strategy:
  - ANY of 3 players buys $500+ → potential signal
  - NONE of the other 2 players have $500+ opposing → entry confirmed
  - Bet size: per-player additive tiers (based on WR/ROI analysis)
  - Price range: per-player (10-82c for Car/aenews2, 15-82c for denizz)
  - Exit: follow the player who gave the signal
"""
import os
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(ENV_PATH, override=True)

# === SIGNAL PLAYERS (3 players monitored for BUY/SELL/MERGE) ===
# Only denizz is actively copied. Car and aenews2 removed 2026-04-09 after
# the Iran April 7 incident where Car's merge-arbitrage trades were misread
# as real signals and triggered cascade sells of denizz positions.
# Root cause analysis:
#   1. Car does merge-prep arbitrage (buys Yes+No, then merges to $1) —
#      we copied the buys as real direction signals and got burned.
#   2. Startup recovery replayed old Car exits as "missed sells" after
#      every restart, repeatedly triggering exit attempts.
#   3. When bot had multiple tracker records (Car + denizz) on the same
#      (cid, token), executing "Car exit" sold denizz shares too.
# Solution: remove Car and aenews2 entirely. denizz is the only proven
# alpha (+$447k lifetime) and his behavior is directional (not merge).
PLAYERS = {
    "denizz":   "0xbaa2bcb5439e985ce4ccf815b4700027d1b92c73",
}

# === LOGARITHMIC BET SIZING (replaces additive tiers) ===
# Formula: our_bet = BET_FORMULA_A * ln(invested) + BET_FORMULA_B
# Anchors: denizz $500 -> $20, denizz $30K -> $150
BET_FORMULA_A = 31.75
BET_FORMULA_B = -177.0
MIN_BET_FORMULA = 15.0      # minimum after all multipliers (V9: lowered from 20 to let PRICE_RISK work)
MAX_BET_USD = 250.0     # cap before multipliers (V9: raised from 200 for $4000 bankroll)
MIN_UPGRADE_USD = 5.0  # minimum increment for tier upgrade (lowered 15→5 on 2026-04-15 to catch smaller denizz top-ups)

# DEPRECATED 2026-04-15: replaced by ratio-based filter in handle_buy.
# The ratio filter uses TOPUP_RATIO_TIERS[0][1] (3%) to classify noise
# top-ups relative to denizz's existing position size. New markets (no
# prior shares) pass everything to the buffer unconditionally.
# Kept for backward compatibility — not used in main.py any more.
MIN_BUY_EVENT_USD = 150.0  # DEPRECATED — see ratio filter
MAX_POSITION_USD = 300.0  # max total in one position (11% of bankroll)

# === TOP-UP DETECTION (on-chain classification) ===
# Added 2026-04-15 (Bugfix #1). Before Path A (new entry), verify denizz's
# ACTUAL pre-event share balance on-chain via CTF.balanceOf. If he already
# holds non-dust shares on this token, treat the buy as a TOP-UP and route
# to the existing tier-upgrade branch, regardless of whether our internal
# _signaled_keys contains the key. Reason: for markets where denizz held a
# position BEFORE our bot ever saw it, _signaled_keys is empty and Path A
# would mis-size the entry with the full log formula at late-conviction
# prices. Rule A+ and TOPUP_RATIO_TIERS inside the tier-upgrade branch
# already handle late-entry sizing correctly.
TOPUP_DUST_SHARES = 5.0          # <= this many shares => treat as "no prior position"
TOPUP_DETECTION_TIMEOUT_SEC = 3.0  # RPC call budget for hot-path top-up check

# Minimum player investment to even consider a signal
MIN_PLAYER_INVESTED = {
    "denizz":   500,
}

# Top-up ratio tiers: multiplier on bet based on new_buy / total_position
# Filters out noise when player adds <3% to existing position
TOPUP_RATIO_TIERS = [
    (0.00, 0.03, 0.0),    # <3%: skip (noise)
    (0.03, 0.10, 0.5),    # 3-10%: half size
    (0.10, 0.30, 0.75),   # 10-30%: 3/4 size
    (0.30, 999.0, 1.0),   # 30%+: full size
]

# === VARIANT 1: on-chain cost as source of truth for tier-upgrade ===
# When True: already_bet = tracker.cost_usd (live) instead of buf.last_tier_bet
# (stale, ignores manual sells). SAFETY: keep False until dry-run validates.
USE_ONCHAIN_COST = True
ONCHAIN_COST_GRACE_SEC = 45      # skip data-api refresh if record_position <N sec ago
TIER_UPGRADE_THROTTLE_SEC = 60   # max 1 upgrade per (cid, token) per N sec

# Minimum opposing position that blocks entry (from any of the other players)
# Only relevant if more than one player is active; kept for compatibility.
OPPOSITION_MIN_USD = 500.0

# Players whose opposing positions are IGNORED for a given signal player.
# Not used while only denizz is active (nothing to ignore), but kept
# as a structure in case we re-add players later.
OPPOSITION_IGNORE = {
    "denizz":  [],
}

# === TIMESERIES HEDGE ===
MIN_HEDGE_USD = 5.0  # minimum proportional hedge size to execute

# === OUR WALLET ===
OUR_WALLET = os.getenv("POLYMARKET_WALLET", "")
OUR_PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")

# === TELEGRAM ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# === CONTRACTS (Polygon PoS) ===
CTF_CONTRACT = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
NEG_RISK_CTF = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

# === NETWORK ===
POLYGON_RPC = "https://polygon.gateway.tenderly.co"
CHAIN_ID = 137

# === POLYMARKET API ===
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
DATA_API = "https://data-api.polymarket.com"

# === BANKROLL ===
BANKROLL = 4000.0   # V9: raised from 2700

# === РЕЖИМЫ ===
BOT_MODE = "live"   # "test" | "live"
DRY_RUN = False      # LIVE mode — placing real orders (switched 2026-04-12)

TEST_DURATION_HOURS = 3
TEST_MAX_ERRORS = 0

MIN_BET_USD_LIVE = 10.0
MIN_BET_USD_TEST = 3.0
RESERVE_USD_LIVE = 300.0  # V9: raised from 200 for $4000 bankroll (7.5% reserve)
RESERVE_USD_TEST = 15.0

MIN_BET_USD = MIN_BET_USD_TEST if BOT_MODE == "test" else MIN_BET_USD_LIVE
RESERVE_USD = RESERVE_USD_TEST if BOT_MODE == "test" else RESERVE_USD_LIVE

# Conviction tiers (kept for mode_manager compatibility, not used for sizing)
CONVICTION_TIERS_LIVE = [(500, 999999, 0.05, "B")]
CONVICTION_TIERS_TEST = [(500, 999999, 0.03, "B")]
CONVICTION_TIERS = CONVICTION_TIERS_TEST if BOT_MODE == "test" else CONVICTION_TIERS_LIVE
FIXED_BET_MODE = False   # Per-player additive sizing, not fixed
FIXED_BET_LIVE = 40.0
FIXED_BET_TEST = 10.0

# === BET SCALE FACTOR ===
# Multiplier applied to bet formula output.
# Test mode: scale 0.5
# Live mode: scale 1.0
BET_SCALE_TEST = 0.5   # → base bets from ~$10
BET_SCALE_LIVE = 1.0   # → base bets from ~$20 (tiers as defined)
BET_SCALE = BET_SCALE_TEST if BOT_MODE == "test" else BET_SCALE_LIVE

MAX_CONCURRENT = 40  # Phase 1: raised from 20 (backtest showed 680 skipped signals)
MAX_PER_EVENT = 1

# === PRICE FILTER per player (based on backtest analysis) ===
# Rationale:
#   - 0-10c: too illiquid, slippage destroys edge
#   - 82c+: near-zero upside, slippage makes it negative EV for our bot
#   - 10-82c: optimal zone for all 3 players
#   - denizz: 15c floor (conservative, fewer data points below 15c)
PRICE_FILTER = {
    "denizz":  {"min": 0.05, "max": 0.99},  # lowered 0.15→0.05: denizz buys cheap longshots (Iran 0.069 → 0.524)
    "_default": {"min": 0.10, "max": 0.98},
}

# === BOT VARIANT (mode A vs B) ===
# Variant A (default): copy denizz buys across full PRICE_FILTER range (0.05–0.99).
# Variant B: copy only when live best ask of OUR side is in [0.45, 0.99].
# Filter applies to every buy-event path (Path A, top-up/MERGE, rebuy, hedge).
# Sells / follow-sell / stop-loss are never affected by the variant.
#
# Hot-reload: if file `_bot_variant.txt` exists in project root and contains "A"
# or "B" (single letter, case-insensitive), it overrides BOT_VARIANT without
# requiring a restart. The file is re-read at most once every
# VARIANT_RELOAD_INTERVAL_SEC seconds.
BOT_VARIANT = "A"  # "A" | "B"
VARIANT_B_PRICE_FLOOR = 0.45  # inclusive
VARIANT_B_PRICE_CEIL = 0.99   # inclusive
VARIANT_FILE = "_bot_variant.txt"
VARIANT_RELOAD_INTERVAL_SEC = 30

# === PRICE MULTIPLIER on bet size (82-99c only) ===
# 0-82c: full size (no multiplier needed)
# 82-99c: reduced — small upside, slippage matters more
PRICE_BET_MULTIPLIERS = [
    (0.00, 0.82, 1.0),
    (0.82, 0.99, 0.65),
]

# === PRICE_RISK_TIERS (V9, added 2026-04-17) ===
# Multiplier on bet size based on entry price.
# Cut longshot bets (< 30c) and expensive bets (> 70c) where our historical
# WR is worst. Sweet spot 30-70c gets full size.
PRICE_RISK_TIERS = [
    (0.00, 0.15, 0.40),   # longshot: 40%
    (0.15, 0.30, 0.70),   # cheap: 70%
    (0.30, 0.70, 1.00),   # sweet spot: 100%
    (0.70, 0.85, 0.90),   # expensive: 90%
    (0.85, 0.99, 0.80),   # near-100c: 80%
]

# === REBUY TRIGGER (added 2026-04-17) ===
# Event-based branch for reversal re-entries: when denizz partially sold and
# then buys back, state-based tier-upgrade misses the signal because formula
# target < our cost. This branch fires when state-based returns 0 AND
# denizz made a fresh buy >= MIN_PLAYER_INVESTED.
# Sizing: formula applied to denizz's NEW BUY amount (not net_invested),
# then PRICE_RISK_TIERS, capped by MAX_POSITION_USD.
REBUY_TRIGGER_ENABLED    = True
REBUY_THROTTLE_SEC       = 300       # one rebuy per (cid, token) per 5 min
REBUY_PNL_KILL_SWITCH_USD = -150.0   # disable branch if cumulative PnL < this
REBUY_INITIAL_MAX_USD    = 20.0      # hard cap on first N rebuys after deploy (smoke test)
REBUY_INITIAL_N          = 3         # after N successful rebuys, cap is removed
REBUY_LOG_PATH           = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rebuy_log.jsonl")

# === SLIPPAGE LIMITS (per price range) ===
# Design principle: keep "loss fraction" (slip / upside-to-$1) roughly
# bounded to ~10-12% in every tier. At higher prices upside shrinks, so
# absolute slippage must shrink too, otherwise a single cent can eat
# half of our potential profit. 0.82-0.98 zone was previously a flat
# 1c which gave 50% loss fraction at 0.98 — now graduated.
MAX_SLIPPAGE_TIERS = [
    (0.00, 0.10, 0.020),   # 0-10c:  slip 2.0c
    (0.10, 0.15, 0.020),   # 10-15c: slip 2.0c (tightened from 3.0c)
    (0.15, 0.20, 0.025),   # 15-20c: slip 2.5c (tightened from 3.0c)
    (0.20, 0.82, 0.030),   # 20-82c: slip 3.0c (merged 4 old tiers)
    (0.82, 0.88, 0.020),   # 82-88c: slip 2.0c (was 1.5c)
    (0.88, 0.92, 0.015),   # 88-92c: slip 1.5c (was 1.0c)
    (0.92, 0.95, 0.010),   # 92-95c: slip 1.0c (was 0.6c)
    (0.95, 0.96, 0.0075),  # 95-96c: slip 0.75c (NEW tier)
    (0.96, 0.97, 0.005),   # 96-97c: slip 0.5c (was 0.3c)
    (0.97, 0.98, 0.0035),  # 97-98c: slip 0.35c (NEW tier)
    (0.98, 0.99, 0.002),   # 98-99c: slip 0.2c (unchanged)
]

# === CATEGORY KEYWORDS ===
CATEGORY_KEYWORDS = {
    "politics": [
        "trump", "tariff", "doge", "cabinet", "executive order",
        "approval rating", "greenland", "deport", "impeach",
        "pete hegseth", "tulsi", "rfk", "bessent", "gold card",
        "congress", "senate", "democrat", "republican",
        "pardon", "veto", "white house", "presidential",
    ],
    "geopolitics": [
        "nato", "china", "venezuela", "sanctions", "nuclear",
        "trade deal", "blockade", "taiwan", "ceasefire",
        "north korea", "kim jong",
    ],
    "entertainment": [
        "super bowl", "oscar", "grammy", "ufc", "nfl", "nba",
        "album", "movie", "chess", "eurovision", "world series",
        "ballon d'or", "premier league",
    ],
    "oil": [
        "oil", "crude", "brent", "wti", "gold (gc)", "commodity",
    ],
    "elections": [
        "election", "vote", "ballot", "primary", "runoff",
        "governor", "mayor", "referendum",
    ],
    "iran": [
        "iran", "tehran", "hezbollah", "lebanon",
        "israel strike", "iranian",
    ],
    "russia_ukraine": [
        "ukraine", "russia", "putin", "zelensky",
        "crimea", "donbas", "kherson",
    ],
    "tech": [
        "nvidia", "apple", "google", "meta", "tesla",
        "microsoft", "amazon",
    ],
}

EXCLUDED_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol",
    "crypto", "token", "defi", "nft",
    "fed rate", "inflation", "cpi", "gdp", "unemployment",
    "interest rate", "fomc", "federal reserve",
]

# HP strategy removed in v2 — entire 82-99c zone uses unified system

# === 3-PART ENTRY ===
# Part1 = 100% (disabled split after simulation showed no benefit on fast-closing trades)
ENTRY_PART1_PCT = 1.00
ENTRY_PART2_PCT = 0.00
ENTRY_PART3_PCT = 0.00

ENTRY_PART2_DELAY_H = 2
ENTRY_PART2_MAX_DELAY_H = 4
ENTRY_PART2_MAX_RISE = 0.15

ENTRY_PART3_DIP_PCT = 0.10
ENTRY_PART3_EXPIRY_DAYS = 7

# === EXIT RULES ===
EXIT_SELL_AT_PRICE = 0.995
EXIT_FOLLOW_TARGET_HOURS = 2

# Flat stop-loss 80% for all tiers (relaxed 2026-04-16: previous tiered
# stops at 35-60% triggered false exits on positions that later won).
STOP_LOSS_TIERS = [
    (0.02, 0.99, 0.80),   # all entries: stop at -80%
]
# EXIT_TIME_STOP_DAYS removed — horizon filter at entry makes time-stop unnecessary

# Global stop-loss kill-switch (added 2026-04-18 ahead of high-volatility window).
# When False, ALL stop-loss logic in check_exits is skipped — the bot will not
# auto-sell on price drops regardless of entry price or custom_stop_loss_price.
# Per-position `disable_stop_loss: true` and `custom_stop_loss_price` overrides
# only matter when this flag is True.
# EXIT_SELL_AT_PRICE (target take-profit at 99.5c) is NOT affected by this.
# Follow-sell on player exit and PHANTOM/redemption logic also NOT affected.
STOP_LOSS_ENABLED = False

# === HEDGE DETECTION ===
# A signal is classified as a "hedge" when:
#   player's new buy USD / player's primary position on opposite side ≤ HEDGE_RATIO_MAX
# We only copy a hedge when our primary position has an unrealized gain
#   of at least HEDGE_MIN_GAIN_PCT above our own entry price.
# If we have no matching primary position, the signal is treated as a standalone trade.
HEDGE_RATIO_MAX = 0.12      # new buy < 12% of primary → classified as hedge
HEDGE_MIN_GAIN_PCT = 0.12   # our primary must be ≥ 12% above our entry to copy hedge

# Horizon tiers: multiplier on bet size based on days to market end_date
HORIZON_TIERS = [
    (0, 30, 1.0),
    (30, 60, 0.8),
    (60, 90, 0.7),
    (90, 120, 0.4),
    (120, 99999, 0.0),   # block entry
]

# Follow-sell tiers: how much of OUR position to sell based on player's sell %.
# Separate tables for profit vs loss positions.
# 2026-04-17 (heightened sensitivity for Apr 21-22 peace deadline window):
#   PROFIT dust threshold lowered 10% → 5% (catch earlier exits)
#   LOSS dust threshold lowered 20% → 10% (don't tolerate loss positions as long)
#   Both tables get an intermediate 5-10% / 10-20% tier with 10/15% sell %.
FOLLOW_SELL_TIERS_PROFIT = [
    (0.00, 0.05, 0.00),   # <5%: dust (lowered from 10%)
    (0.05, 0.10, 0.10),   # 5-10%: sell 10% (NEW intermediate tier)
    (0.10, 0.20, 0.15),   # 10-20%: sell 15%
    (0.20, 0.30, 0.25),   # 20-30%: sell 25%
    (0.30, 0.40, 0.35),   # 30-40%: sell 35%
    (0.40, 0.50, 0.45),   # 40-50%: sell 45%
    (0.50, 0.60, 0.55),   # 50-60%: sell 55%
    (0.60, 0.70, 0.75),   # 60-70%: sell 75%
    (0.70, 0.80, 0.90),   # 70-80%: sell 90%
    (0.80, 1.01, 1.00),   # 80%+: sell 100%
]
FOLLOW_SELL_TIERS_LOSS = [
    (0.00, 0.05, 0.00),   # <5%: dust (lowered from 10% on 2026-04-21 — denizz fragmenting sells)
    (0.05, 0.10, 0.10),   # 5-10%: sell 10% (NEW — catch fragmented sells)
    (0.10, 0.20, 0.15),   # 10-20%: sell 15%
    (0.20, 0.30, 0.25),   # 20-30%: sell 25%
    (0.30, 0.40, 0.35),   # 30-40%: sell 35%
    (0.40, 0.50, 0.45),   # 40-50%: sell 45%
    (0.50, 0.60, 0.55),   # 50-60%: sell 55%
    (0.60, 0.70, 0.75),   # 60-70%: sell 75%
    (0.70, 0.80, 0.90),   # 70-80%: sell 90%
    (0.80, 1.01, 1.00),   # 80%+: sell 100%
]
# DEPRECATED: FOLLOW_SELL_LOSS_THRESHOLD removed — loss positions now use
# graduated tiers (FOLLOW_SELL_TIERS_LOSS) instead of a single 60% gate.

# === SLIPPAGE-AWARE SETTLE WAIT (added 2026-04-17 after empirical bimodal analysis) ===
# When denizz sells in HIS PROFIT, the orderbook is briefly compressed by his
# market sweep. Empirically (price-history backtest on 9 days, 40 events) the
# bid recovers within ~1 minute in 27.5% of cases — these are the "fast
# recovery" events where waiting yields better fill. The other 60% don't
# recover at all in any useful timeframe.
# Strategy: wait briefly (settle window) before placing OUR sell, so we read
# the post-absorption bid (likely higher than peak-impact bid). Only applies
# to PROFIT-mode events; LOSS-mode keeps the urgent immediate-sell path.
SLIPPAGE_SETTLE_ENABLED  = True
SLIPPAGE_SETTLE_WAIT_SEC = 30      # short wait — book recovers fast or not at all

# === CUMULATIVE SELL DETECTION (added 2026-04-17) ===
# Protects against denizz draining position via many small sells, each
# individually below dust threshold. If sum of sold_pct events within
# rolling window crosses CUMULATIVE_SELL_THRESHOLD, treat as if denizz
# made a single sell of cumulative size — fires tier matrix accordingly.
# Counter resets after firing (allows re-fire if denizz keeps dribbling).
CUMULATIVE_SELL_WINDOW_SEC = 3600    # 1 hour rolling window
CUMULATIVE_SELL_THRESHOLD  = 0.20    # ≥20% cumulative within window → fire

# === EXECUTION ===
MIN_SHARES = 5
ORDER_TTL_SECONDS = 600  # was 1800 — shorter to avoid stale-price stuck orders
MAX_DRAWDOWN_PCT = 0.80

# === PRECISION-SAFE SELLING (added 2026-04-15 after Hezbollah-April-15 miss) ===
# positions.json rounds to 2 decimals (59.51), on-chain has 6 decimals
# (59.509092). Subtract this margin before placing a sell, so we never
# request more than actually exists on-chain.
SAFETY_MARGIN_SHARES = 0.001             # default: ~1000 micro-shares
RETRY_SAFETY_MARGIN_MULT = 5.0           # on retry, 5× the margin (5×0.001 = 0.005)

# === RETRY-ON-FAIL (for exit_manager) ===
# When a sell order fails, record _pending_exit_retry on the position so
# later cycles keep trying within this window. Prevents silent loss of the
# exit signal after a transient error (network blip, API flake).
RETRY_WINDOW_MIN = 30                    # minutes to keep retrying after first failure
RETRY_MAX_ATTEMPTS = 6                   # cap attempts (≈every 5 min × 6 = 30 min)
RETRY_MIN_SPACING_SEC = 60               # minimum seconds between retry attempts

# === POLLING ===
POLL_INTERVAL = 5  # was 30 — faster reaction to player signals
POSITIONS_CHECK_INTERVAL = 60
REDEEM_CHECK_INTERVAL = 300

# === DAILY REPORTS ===
REPORT_SCHEDULE = [
    {"hour_msk": 13, "type": "daily",   "name": "Дневной отчёт"},
    {"hour_msk": 19, "type": "evening", "name": "Вечерний отчёт"},
]

# === PATHS ===
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
POSITIONS_FILE = os.path.join(BOT_DIR, "positions.json")
SIGNALS_FILE = os.path.join(BOT_DIR, "signals.json")
