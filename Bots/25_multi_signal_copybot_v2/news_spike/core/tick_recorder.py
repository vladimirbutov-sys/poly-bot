"""
core/tick_recorder.py — Запись тиковых данных по целевым рынкам каждые 10 секунд.

Хранит в SQLite: data/tick_history.db
Таблица: ticks (timestamp, slug, yes_price)

Только 10 целевых рынков Spike Rider — экономия места.
~86400 записей/день на рынок × 10 рынков = ~860K строк/день (~25 MB/день).
"""
import asyncio
import logging
import sqlite3
import time

from core.config import DATA_DIR

logger = logging.getLogger("tick_recorder")

DB_PATH = DATA_DIR / "tick_history.db"
TICK_INTERVAL = 10  # секунд между записями


class TickRecorder:
    """Записывает цены целевых рынков каждые 10 секунд в SQLite."""

    def __init__(self, iran_cache, target_slugs: set[str]):
        self.iran_cache = iran_cache
        self.target_slugs = target_slugs
        self._conn = None
        self._init_db()
        self._count = 0

    def _init_db(self):
        self._conn = sqlite3.connect(str(DB_PATH))
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                ts INTEGER NOT NULL,
                slug TEXT NOT NULL,
                yes_price REAL NOT NULL
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ticks_slug_ts ON ticks (slug, ts)
        """)
        self._conn.commit()

        # Сколько записей уже есть
        row = self._conn.execute("SELECT COUNT(*) FROM ticks").fetchone()
        logger.info(f"Tick DB initialized: {DB_PATH.name}, {row[0]} existing records")

    async def run(self):
        logger.info(f"Tick recorder started: {len(self.target_slugs)} markets, every {TICK_INTERVAL}s")

        while True:
            try:
                self._record_tick()
            except Exception as e:
                logger.error(f"Tick record error: {e}")

            await asyncio.sleep(TICK_INTERVAL)

    def _record_tick(self):
        now = int(time.time())
        rows = []

        for market in self.iran_cache.markets:
            slug = market.get("slug", "")
            if slug not in self.target_slugs:
                continue

            yes_price = market.get("yes_price", 0)
            if yes_price > 0:
                rows.append((now, slug, round(yes_price, 4)))

        if rows:
            self._conn.executemany("INSERT INTO ticks (ts, slug, yes_price) VALUES (?, ?, ?)", rows)
            self._conn.commit()

        self._count += len(rows)
        if self._count % 1000 == 0 and self._count > 0:
            logger.info(f"Tick recorder: {self._count} total records written")
