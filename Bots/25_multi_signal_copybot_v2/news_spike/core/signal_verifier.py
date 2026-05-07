"""
core/signal_verifier.py — Верификация сигналов: проверка фактического движения цены

После каждого отправленного алерта (news или odds) записывает фактическую цену
через 15, 30 и 60 минут. Результаты пишутся в data/signal_audit.jsonl.

Позволяет через неделю посчитать:
  - Hit rate (% алертов с движением в правильном направлении)
  - Magnitude accuracy (прогноз vs реальный сдвиг)
  - False positive rate
  - Source quality (какие источники дают лучшие сигналы)
"""
import asyncio
import json
import logging
import time
from collections import deque
from datetime import datetime, timezone

from core.config import DATA_DIR

logger = logging.getLogger("verifier")

AUDIT_FILE = DATA_DIR / "signal_audit.jsonl"

# Через сколько минут проверять цену
CHECK_DELAYS_MIN = [15, 30, 60]


class SignalVerifier:
    """Фоновая верификация: записывает реальную цену после алерта."""

    def __init__(self, iran_cache):
        self.iran_cache = iran_cache
        # Очередь: (check_time, signal_record)
        self._pending: deque[tuple[float, dict]] = deque()

    def register_signal(self, signal: dict):
        """Зарегистрировать отправленный сигнал для верификации.

        signal должен содержать:
          - slug: market slug
          - signal_type: "news" | "odds"
          - confidence: HIGH/MEDIUM/ODDS_MOVE
          - direction: YES_UP / YES_DOWN / ↑ / ↓
          - price_at_signal: текущая цена в момент сигнала (%)
          - expected_price: ожидаемая цена (%) — только для news
          - source: источник
          - timestamp: ISO timestamp
          - summary: краткое описание
        """
        now = time.time()
        record = {
            **signal,
            "_registered_at": now,
            "_checks_done": [],
        }

        for delay_min in CHECK_DELAYS_MIN:
            check_time = now + delay_min * 60
            self._pending.append((check_time, record))

        logger.info(
            f"Registered signal for verification: {signal.get('slug', '?')} "
            f"({signal.get('signal_type', '?')})"
        )

    async def run(self):
        """Фоновый цикл проверки."""
        logger.info("Signal verifier started")
        while True:
            now = time.time()
            to_check = []

            # Собрать все записи, которым пора проверять
            while self._pending and self._pending[0][0] <= now:
                check_time, record = self._pending.popleft()
                to_check.append((check_time, record))

            for check_time, record in to_check:
                delay_min = round((check_time - record["_registered_at"]) / 60)
                # Не дублировать проверку того же интервала
                if delay_min in record["_checks_done"]:
                    continue
                record["_checks_done"].append(delay_min)

                await self._verify(record, delay_min)

            await asyncio.sleep(30)

    async def _verify(self, record: dict, delay_min: int):
        """Проверить фактическую цену и записать результат."""
        slug = record.get("slug", "")
        market = self.iran_cache.get_market_by_slug(slug)

        if not market:
            logger.debug(f"Market {slug} not found for verification")
            return

        actual_price = round(market["yes_price"] * 100, 1)
        price_at_signal = record.get("price_at_signal", 0)
        expected_price = record.get("expected_price")

        # Определить направление
        direction = record.get("direction", "")
        predicted_up = direction in ("YES_UP", "↑")
        predicted_down = direction in ("YES_DOWN", "↓")

        actual_delta = round(actual_price - price_at_signal, 1)
        abs_delta = abs(actual_delta)

        # Hit = цена двинулась в предсказанном направлении на >= 1 п.п.
        if predicted_up:
            hit = actual_delta >= 1.0
        elif predicted_down:
            hit = actual_delta <= -1.0
        else:
            hit = None  # direction not specified

        # Magnitude error (только для news с expected_price)
        magnitude_error = None
        if expected_price is not None and expected_price != 0:
            predicted_delta = abs(expected_price - price_at_signal)
            if predicted_delta > 0:
                magnitude_error = round(abs_delta / predicted_delta, 2)

        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "check_delay_min": delay_min,
            "slug": slug,
            "signal_type": record.get("signal_type", ""),
            "confidence": record.get("confidence", ""),
            "source": record.get("source", ""),
            "direction": direction,
            "price_at_signal": price_at_signal,
            "expected_price": expected_price,
            "actual_price": actual_price,
            "actual_delta_pp": actual_delta,
            "hit": hit,
            "magnitude_ratio": magnitude_error,
            "summary": record.get("summary", ""),
            "signal_timestamp": record.get("timestamp", ""),
        }

        try:
            with open(AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"Audit write failed: {e}")

        status = "HIT" if hit else ("MISS" if hit is False else "N/A")
        logger.info(
            f"Verify [{delay_min}min] {slug}: "
            f"{price_at_signal}% → {actual_price}% (delta {actual_delta:+.1f}pp) "
            f"= {status}"
        )
