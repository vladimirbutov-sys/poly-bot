"""
monitors/odds_monitor.py — Модуль 2: Мониторинг коэффициентов ставок

Каждые 30 секунд опрашивает MarketCache и сравнивает текущие цены
с ценами 5 минут назад.

Алертит ТОЛЬКО по целевым рынкам Spike Rider (TARGET_MARKETS).
Порог: абсолютный сдвиг >= 5 п.п. за 5 минут.
"""
import asyncio
import logging

from monitors.base import BaseMonitor

logger = logging.getLogger("odds_monitor")

# Единый порог: 5 п.п. за 5 минут
ABS_THRESHOLD = 5.0            # п.п. — минимальный сдвиг для алерта
POLL_INTERVAL = 30             # секунд между проверками
COOLDOWN_SECONDS = 300         # 5 мин между алертами по одному рынку


class OddsMonitor(BaseMonitor):
    """Мониторинг движений цен ТОЛЬКО на целевых рынках Spike Rider."""

    name = "odds_monitor"

    def __init__(self, iran_cache, on_odds_alert=None):
        """
        iran_cache: MarketCache instance
        on_odds_alert: async callback(alert_data: dict)
        """
        self.iran_cache = iran_cache
        self.on_odds_alert = on_odds_alert
        self._last_alert_time: dict[str, float] = {}  # slug → timestamp
        self._last_event_alert_time: dict[str, float] = {}  # event_slug → timestamp

        # Целевые slugs из configs/target_markets_iran.json (наши открытые Iran/US позиции)
        import json
        from pathlib import Path
        cfg_path = Path(__file__).parent.parent / "configs" / "target_markets_iran.json"
        with open(cfg_path, "r", encoding="utf-8") as f:
            tm_cfg = json.load(f)
        self._target_slugs = {tm["event_slug"] for tm in tm_cfg.get("markets", []) if tm.get("event_slug")}
        logger.info(f"Odds monitor tracking {len(self._target_slugs)} target markets")

    async def _run(self):
        logger.info(f"Odds monitor started: poll every {POLL_INTERVAL}s, "
                     f"threshold >= {ABS_THRESHOLD} п.п., "
                     f"{len(self._target_slugs)} target markets")

        while True:
            try:
                await self._check_movements()
            except Exception as e:
                logger.error(f"Odds check error: {e}")

            await asyncio.sleep(POLL_INTERVAL)

    async def _check_movements(self):
        """Проверить целевые рынки на движения >= 5 п.п."""
        import time
        now = time.time()

        for market in self.iran_cache.markets:
            slug = market["slug"]

            # Только целевые рынки Spike Rider
            if slug not in self._target_slugs:
                continue

            if not market.get("tradeable", True):
                continue

            current_pct = round(market["yes_price"] * 100, 1)

            # Получить цену 5 минут назад
            old_pct = self.iran_cache.get_price_5min_ago(slug)
            if old_pct is None:
                continue

            # Единый порог: >= 5 п.п.
            abs_delta = abs(current_pct - old_pct)
            if abs_delta < ABS_THRESHOLD:
                continue

            # Cooldown: не алертить по тому же рынку чаще чем раз в 5 мин
            last_alert = self._last_alert_time.get(slug, 0)
            if now - last_alert < COOLDOWN_SECONDS:
                continue

            # Дедупликация по event
            event_slug = market.get("event_slug", "")
            if event_slug:
                last_event_alert = self._last_event_alert_time.get(event_slug, 0)
                if now - last_event_alert < COOLDOWN_SECONDS:
                    logger.debug(f"Skipped duplicate event alert: {event_slug}")
                    continue
                self._last_event_alert_time[event_slug] = now

            self._last_alert_time[slug] = now

            # Направление
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
                "trigger_reason": f"сдвиг {abs_delta:.1f} п.п. >= {ABS_THRESHOLD}",
            }

            logger.info(
                f"Odds move: {market['title'][:50]} "
                f"{old_pct}% -> {current_pct}% ({direction}{abs_delta:.1f}pp)"
            )

            if self.on_odds_alert:
                await self.on_odds_alert(alert_data)
