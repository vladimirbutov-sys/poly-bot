"""
monitors/opportunity_monitor.py — Модуль 3: Детектор движений на "чужих" рынках.

Мониторит ВСЕ рынки из MarketCache, ИСКЛЮЧАЯ наши target_markets_iran.json.
Порог выше чем у OddsMonitor: >= 7 п.п. за 5 мин (меньше шума).
Фильтр по объёму: >= $50k (иначе мелочь будет спамить).

Цель: ловить возможности для новых входов, где мы ещё не в позиции.
"""
import asyncio
import logging
import time

from monitors.base import BaseMonitor

logger = logging.getLogger("opportunity_monitor")

ABS_THRESHOLD = 7.0            # п.п. — выше чем у OddsMonitor (5 п.п.)
POLL_INTERVAL = 30             # секунд между проверками
COOLDOWN_SECONDS = 300         # 5 мин между алертами по одному рынку
MIN_VOLUME_USD = 50_000        # фильтр по ликвидности


class OpportunityMonitor(BaseMonitor):
    """Мониторинг движений на 'чужих' рынках (где у нас нет позиций)."""

    name = "opportunity_monitor"

    def __init__(self, iran_cache, on_opportunity_alert=None):
        """
        iran_cache: MarketCache instance
        on_opportunity_alert: async callback(alert_data: dict)
        """
        self.iran_cache = iran_cache
        self.on_opportunity_alert = on_opportunity_alert
        self._last_alert_time: dict[str, float] = {}
        self._last_event_alert_time: dict[str, float] = {}

        # Загружаем наши target slugs — чтобы исключить их
        import json
        from pathlib import Path
        cfg_path = Path(__file__).parent.parent / "configs" / "target_markets_iran.json"
        with open(cfg_path, "r", encoding="utf-8") as f:
            tm_cfg = json.load(f)
        self._excluded_slugs = {tm["event_slug"] for tm in tm_cfg.get("markets", []) if tm.get("event_slug")}
        logger.info(
            f"Opportunity monitor: threshold >= {ABS_THRESHOLD} п.п., "
            f"min volume ${MIN_VOLUME_USD:,}, "
            f"excluding {len(self._excluded_slugs)} our markets"
        )

    async def _run(self):
        logger.info(f"Opportunity monitor started (poll every {POLL_INTERVAL}s)")

        while True:
            try:
                await self._check_movements()
            except Exception as e:
                logger.error(f"Opportunity check error: {e}")

            await asyncio.sleep(POLL_INTERVAL)

    async def _check_movements(self):
        """Проверить все рынки кроме наших на движения >= 7 п.п."""
        now = time.time()

        for market in self.iran_cache.markets:
            slug = market["slug"]
            event_slug = market.get("event_slug", "")

            # Исключить наши target markets
            if event_slug in self._excluded_slugs:
                continue

            # Фильтр: только торгуемые рынки с достаточной ликвидностью
            if not market.get("tradeable", True):
                continue
            if market.get("volume", 0) < MIN_VOLUME_USD:
                continue

            current_pct = round(market["yes_price"] * 100, 1)
            old_pct = self.iran_cache.get_price_5min_ago(slug)
            if old_pct is None:
                continue

            abs_delta = abs(current_pct - old_pct)
            if abs_delta < ABS_THRESHOLD:
                continue

            # Cooldown
            last_alert = self._last_alert_time.get(slug, 0)
            if now - last_alert < COOLDOWN_SECONDS:
                continue

            # Event-level dedup
            if event_slug:
                last_event = self._last_event_alert_time.get(event_slug, 0)
                if now - last_event < COOLDOWN_SECONDS:
                    continue
                self._last_event_alert_time[event_slug] = now

            self._last_alert_time[slug] = now

            direction = "\u2191" if current_pct > old_pct else "\u2193"
            delta_pp = round(current_pct - old_pct, 1)

            alert_data = {
                "slug": slug,
                "event_slug": event_slug,
                "title": market["title"],
                "old_pct": old_pct,
                "current_pct": current_pct,
                "delta_pp": delta_pp,
                "direction": direction,
                "volume": market.get("volume", 0),
                "trigger_reason": f"сдвиг {abs_delta:.1f} п.п. >= {ABS_THRESHOLD} (opportunity)",
            }

            logger.info(
                f"Opportunity: {market['title'][:50]} "
                f"{old_pct}% -> {current_pct}% ({direction}{abs_delta:.1f}pp) "
                f"vol=${market.get('volume', 0):,.0f}"
            )

            if self.on_opportunity_alert:
                await self.on_opportunity_alert(alert_data)
