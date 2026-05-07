"""core/market_cache.py — Shared кэш активных рынков Polymarket"""
import json
import time
import logging
from datetime import datetime, timezone

import httpx

from core.config import GAMMA_API_BASE, MIN_MARKET_VOLUME, MARKET_CACHE_FILE

logger = logging.getLogger("market_cache")


class MarketCache:
    def __init__(self):
        self.markets: list[dict] = []
        self.last_update: float = 0
        self._load_from_disk()

    def _load_from_disk(self):
        try:
            if MARKET_CACHE_FILE.exists():
                with open(MARKET_CACHE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.markets = data.get("markets", [])
                self.last_update = data.get("last_update", 0)
                logger.info(f"Loaded {len(self.markets)} markets from disk")
        except Exception as e:
            logger.warning(f"Cache load failed: {e}")

    def _save_to_disk(self):
        try:
            with open(MARKET_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump({"markets": self.markets, "last_update": self.last_update},
                          f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    async def update(self):
        logger.info("Updating market cache...")
        all_markets = []
        offset = 0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                try:
                    resp = await client.get(f"{GAMMA_API_BASE}/events", params={
                        "closed": "false", "active": "true",
                        "end_date_min": now, "limit": 100, "offset": offset,
                    })
                    resp.raise_for_status()
                    events = resp.json()
                except Exception as e:
                    logger.error(f"Gamma API error: {e}")
                    break

                if not events:
                    break

                for event in events:
                    for market in event.get("markets", []):
                        volume = float(market.get("volume", 0) or 0)
                        if volume < MIN_MARKET_VOLUME:
                            continue
                        try:
                            prices = json.loads(market.get("outcomePrices", "[]"))
                            yes_price = float(prices[0]) if prices else 0
                        except (json.JSONDecodeError, IndexError, ValueError):
                            yes_price = 0

                        all_markets.append({
                            "title": market.get("question", event.get("title", "")),
                            "conditionId": market.get("conditionId", ""),
                            "slug": market.get("slug", ""),
                            "event_slug": event.get("slug", ""),
                            "description": market.get("description", "")[:500],
                            "yes_price": round(yes_price, 4),
                            "volume": round(volume),
                            "end_date": market.get("endDate", ""),
                        })

                offset += 100
                if len(events) < 100:
                    break

        self.markets = all_markets
        self.last_update = time.time()
        self._save_to_disk()
        logger.info(f"Cache updated: {len(self.markets)} markets")

    def get_summary_for_prompt(self, max_markets: int = 80) -> str:
        sorted_m = sorted(self.markets, key=lambda m: m["volume"], reverse=True)
        lines = []
        for m in sorted_m[:max_markets]:
            yes_pct = round(m["yes_price"] * 100, 1)
            lines.append(
                f"- [{m['title']}] YES={yes_pct}% | Vol=${m['volume']:,} | "
                f"Ends: {m['end_date'][:10]} | Slug: {m['slug']}"
            )
        return "\n".join(lines)

    def get_prices_by_slug(self) -> dict[str, float]:
        return {m["slug"]: round(m["yes_price"] * 100, 1) for m in self.markets}
