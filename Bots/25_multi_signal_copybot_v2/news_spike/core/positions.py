"""core/positions.py — Load and query user positions from positions.json"""
import json
import logging
from core.config import DATA_DIR

logger = logging.getLogger("positions")

POSITIONS_FILE = DATA_DIR / "positions.json"

_positions: dict = {}


def load_positions() -> dict:
    """Load positions from disk. Returns {slug: {side, size_usd, avg_price, ...}}"""
    global _positions
    try:
        if POSITIONS_FILE.exists():
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _positions = data.get("positions", {})
            logger.info(f"Loaded {len(_positions)} positions")
    except Exception as e:
        logger.warning(f"Positions load failed: {e}")
    return _positions


def get_position(slug: str) -> dict | None:
    """Get position by market slug. Returns None if no position."""
    return _positions.get(slug)


def get_all_positions() -> dict:
    """Get all positions."""
    return _positions


def get_hedge_rules() -> dict:
    """Get hedge rules from positions.json."""
    try:
        if POSITIONS_FILE.exists():
            with open(POSITIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("hedge_rules", {})
    except Exception:
        pass
    return {}
