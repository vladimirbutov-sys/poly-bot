"""Dashboard configuration — paths to all bots and their data files."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Base paths
POLYMARKET_DIR = Path(__file__).parent.parent  # C:\Users\Honor\Desktop\Polymarket
BOTS_DIR = POLYMARKET_DIR / "Bots"
BOTS_DIR_2 = POLYMARKET_DIR / "Polymarket" / "Bots"  # Second bots directory
POLYMARKET_BRAIN_DIR = Path(r"C:\Users\Honor\Desktop\polymarket-brain")
DASHBOARD_DIR = Path(__file__).parent
LOGS_DIR = DASHBOARD_DIR / "logs"
PIDS_FILE = DASHBOARD_DIR / "pids.json"

# Load .env from 98_sure_bot (has wallet keys)
_env_file = BOTS_DIR / "98_sure_bot" / ".env"
if _env_file.exists():
    load_dotenv(_env_file)

# Wallet (for on-chain balance check)
WALLET_ADDRESS = os.getenv("POLYMARKET_WALLET", "")
PRIVATE_KEY = os.getenv("POLYMARKET_PRIVATE_KEY", "")

# CLOB API
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
GAMMA_API = "https://gamma-api.polymarket.com/markets"

# USDC.e (bridged) contract on Polygon — used by Polymarket for trading
USDC_CONTRACT = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
# Native USDC on Polygon — some deposits go here
USDC_NATIVE_CONTRACT = "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359"
POLYGON_RPC = "https://polygon.drpc.org"

# Bot definitions
BOTS = {
    "98_sure_bot": {
        "name": "98% Sure Bot",
        "path": BOTS_DIR / "98_sure_bot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "main.py"],
        "data_file": "positions.json",
        "config_file": "config.py",
        "config_type": "python",
        "type": "trading",
    },
    "20_crock95_bot": {
        "name": "Crock95 Copy Bot",
        "path": BOTS_DIR / "20_crock95_bot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "main.py"],
        "data_file": "positions.json",
        "config_file": "config.py",
        "config_type": "python",
        "type": "trading",
    },
    # v1 removed — migrated to v2 on 2026-04-12
    # "25_multi_signal_copybot": {
    #     "name": "Multi-Signal Copy-Bot",
    #     "path": BOTS_DIR / "25_multi_signal_copybot",
    #     "command": ["py", "-3.12", "-u", "-X", "utf8", "main.py"],
    #     "data_file": "positions.json",
    #     "config_file": "config.py",
    #     "config_type": "python",
    #     "type": "trading",
    # },
    "10_oil_swing_bot": {
        "name": "Oil $100",
        "path": BOTS_DIR / "10_oil_swing_bot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "main.py"],
        "data_file": "positions.json",
        "config_file": "config.py",
        "config_type": "python",
        "type": "trading",
    },
    "oil_swing_bot2": {
        "name": "Oil NO $105",
        "path": BOTS_DIR / "Oil_swing_bot2",
        "command": [str(BOTS_DIR / "Oil_swing_bot2" / ".venv" / "Scripts" / "python.exe"), "-u", "main.py"],
        "data_file": "positions.json",
        "config_file": "config.py",
        "config_type": "python",
        "type": "trading",
    },
"97_scanner": {
        "name": "97% Scanner",
        "path": BOTS_DIR / "97_scanner",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "scanner.py"],
        "data_file": "scanner_data.json",
        "config_file": None,
        "config_type": None,
        "type": "scanner",
    },
    "0_watchdog": {
        "name": "Watchdog",
        "path": BOTS_DIR_2 / "0_watchdog",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "watchdog_bot.py"],
        "data_file": "watchdog_state.json",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "3_gold_audit": {
        "name": "Gold Audit",
        "path": BOTS_DIR_2 / "3_gold_audit",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "gold_monitor.py"],
        "data_file": "bot_state.json",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "5_bestplayers": {
        "name": "Best Players",
        "path": BOTS_DIR_2 / "5_bestplayers",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "tracker.py"],
        "data_file": "tracker_state.json",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "oil_calibrator": {
        "name": "Oil Calibrator",
        "path": BOTS_DIR / "10_oil_swing_bot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "calibrate_loop.py"],
        "data_file": "theta_calibration.json",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "9_iran_signal": {
        "name": "Iran Signal Bot",
        "path": BOTS_DIR_2 / "9_NON_west_signals_to_crash_west_players",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "signal_bot_iran.py"],
        "data_file": "data/signals.jsonl",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "oil_cross_bot": {
        "name": "Oil Cross v2 (June)",
        "path": BOTS_DIR / "oil_cross_bot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "main.py"],
        "data_file": "positions.json",
        "config_file": "config.py",
        "config_type": "python",
        "type": "trading",
    },
    "24_iran_daily_trader": {
        "name": "Iran Daily Trader",
        "path": BOTS_DIR_2 / "24_Iran_Daily_Trader",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "iran_daily_trader.py"],
        "data_file": "data/state.json",
        "config_file": "core/config.py",
        "config_type": "python",
        "type": "trading",
    },
    "arb_bot": {
        "name": "Arb Bot",
        "path": BOTS_DIR / "arb_bot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "main.py"],
        "data_file": "arb_stats.json",
        "config_file": "config.py",
        "config_type": "python",
        "type": "utility",
    },
    "23_strike_collector": {
        "name": "Strike Daily Collector",
        "path": BOTS_DIR_2 / "23_Iran_Strike_Detector",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "daily_collector.py"],
        "data_file": "data/collector_state.json",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "25_spike_monitor": {
        "name": "Spike Monitor",
        "path": BOTS_DIR / "25_spike_monitor",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "spike_monitor.py"],
        "data_file": "data/monitor_state.json",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "26_weather_bot": {
        "name": "Weather Bot",
        "path": BOTS_DIR / "26_weather_bot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "main.py"],
        "data_file": "positions.json",
        "config_file": "config.py",
        "config_type": "python",
        "type": "trading",
    },
    "26_weather_collector": {
        "name": "Weather Collector",
        "path": BOTS_DIR / "26_weather_bot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "collector.py"],
        "data_file": "collected_data/latest.json",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "27_overround_bot": {
        "name": "Overround Bot",
        "path": BOTS_DIR / "27_overround_bot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "main.py", "--execute"],
        "data_file": "positions.json",
        "config_file": "config.py",
        "config_type": "python",
        "type": "trading",
    },
    "25_copybot_metrics": {
        "name": "Copybot Metrics + Report",
        "path": BOTS_DIR / "25_multi_signal_copybot",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "_metrics_loop.py"],
        "data_file": "_analytics/2026-04-08_all-trades-report.md",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "25_copybot_v2": {
        "name": "Copy-Bot v2 [DRY-RUN]",
        "path": BOTS_DIR / "25_multi_signal_copybot_v2",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "main.py"],
        "data_file": "positions.json",
        "config_file": "config.py",
        "config_type": "python",
        "type": "trading",
    },
    "25_news_spike": {
        "name": "News + Spike (Iran/US)",
        "path": BOTS_DIR / "25_multi_signal_copybot_v2" / "news_spike",
        "command": ["py", "-3.12", "-u", "-X", "utf8", "run_news_spike.py"],
        "data_file": "data/signals.jsonl",
        "config_file": None,
        "config_type": None,
        "type": "utility",
    },
    "polymarket_brain": {
        "name": "Brain Signals (Iran War)",
        "path": POLYMARKET_BRAIN_DIR,
        "command": ["py", "-3.12", "-u", "-X", "utf8", "signal_detector.py"],
        "data_file": "_analytics/data/signal_detector.log",
        "config_file": "config.py",
        "config_type": "python",
        "type": "utility",
    },
}
