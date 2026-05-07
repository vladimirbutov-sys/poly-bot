"""Auto-refresh Excel positions file every 30 minutes."""
import time
import logging
import os
from datetime import datetime, timezone

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BOT_DIR, "bot.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [EXCEL] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("excel_refresh")

INTERVAL = 30 * 60  # 30 minutes


def main():
    logger.info("Excel auto-refresh started (every 30 min)")
    while True:
        try:
            import gen_excel_positions
            gen_excel_positions.generate()
            logger.info("Excel updated")
        except Exception as e:
            logger.error(f"Excel update failed: {e}")

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
