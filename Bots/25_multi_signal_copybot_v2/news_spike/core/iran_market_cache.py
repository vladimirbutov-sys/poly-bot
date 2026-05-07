"""
core/iran_market_cache.py — Market cache for Polymarket (Iran + Oil + Gold)

Loads all active markets via Gamma API,
filters by keywords (Iran, oil, gold),
stores price history for OddsMonitor.
"""
import json
import re
import time
import logging
from collections import deque
from datetime import datetime, timezone

import httpx

from core.config import GAMMA_API_BASE, DATA_DIR

logger = logging.getLogger("market_cache")

MARKET_CACHE_FILE = DATA_DIR / "markets.json"
MARKET_HISTORY_FILE = DATA_DIR / "price_history.json"

# Liquidity filters:
# - Resolved markets (0% or 100%) — nowhere to move, alert is pointless
# - Volume < $1,000 — zero liquidity, impossible to enter/exit
MIN_VOLUME = 1_000
MIN_PRICE = 0.005   # > 0.5% — cuts off resolved 0%
MAX_PRICE = 0.995   # < 99.5% — cuts off resolved 100%

# Keywords for filtering relevant markets
_IRAN_PATTERN = (
    r"\biran\b|\btehran\b|\bhormuz\b|persian.gulf|\birgc\b|\bkhamenei\b|\bpahlavi\b|"
    r"strait.of.hormuz|\brouhani\b|\bpezeshkian\b|\braisi\b|"
    r"strike.*\biran\b|\biran\b.*strike|\biran\b.*nuclear|\biran\b.*nuke|"
    r"ceasefire.*\biran\b|\biran\b.*war|\biran\b.*conflict|"
    r"invade.*\biran\b|\biran\b.*invasion|\biran\b.*bomb|"
    r"\biran\b.*enrichment|\biran\b.*uranium|\biran\b.*centrifuge|"
    r"\biran\b.*missile|\biran\b.*drone|\biran\b.*proxy|"
    r"\biran\b.*sanction|\biran\b.*regime|\biran\b.*coup|"
    r"\bhouthi\b.*\biran\b|\biran\b.*\bhouthi\b|\bhezbollah\b.*\biran\b|\biran\b.*\bhezbollah\b"
)

_OIL_PATTERN = r"\boil\b|\bcrude\b|\bwti\b|\bbrent\b|\bpetroleum\b|\bopec\b"

_GOLD_PATTERN = r"\bgold\b|\bxau\b|precious.metal"

MARKET_KEYWORDS = re.compile(
    f"{_IRAN_PATTERN}|{_OIL_PATTERN}|{_GOLD_PATTERN}",
    re.IGNORECASE,
)

# False positives — exclude
FALSE_POSITIVES = re.compile(
    r"^BTS\b|^Arirang|Stephen Miran|^Nothing Ever Happens|"
    r"\bGoldman\s*Sachs\b|\bGold Coast\b|\bGold Cup\b|\bGolden State\b|\bGolden Globe\b|"
    r"\bOil Paint\b|\bOilers\b|\bOil City\b|\bSnake Oil\b|\bOlive Oil\b",
    re.IGNORECASE,
)

# Backward-compatible alias
IranMarketCache = None  # defined after class


class MarketCache:
    """Market cache with price history (Iran + Oil + Gold)."""

    def __init__(self):
        self.markets: list[dict] = []
        self.last_update: float = 0
        # Price history: {slug: deque([(timestamp, yes_price), ...], maxlen=120)}
        self.price_history: dict[str, deque] = {}
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
            logger.warning(f"Market cache load failed: {e}")

        try:
            if MARKET_HISTORY_FILE.exists():
                with open(MARKET_HISTORY_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for slug, entries in raw.items():
                    self.price_history[slug] = deque(
                        [(e[0], e[1]) for e in entries], maxlen=120
                    )
                logger.info(f"Loaded price history for {len(self.price_history)} markets")
        except Exception as e:
            logger.warning(f"Price history load failed: {e}")

    def _save_to_disk(self):
        try:
            with open(MARKET_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(
                    {"markets": self.markets, "last_update": self.last_update},
                    f, ensure_ascii=False,
                )
        except Exception as e:
            logger.warning(f"Market cache save failed: {e}")

        try:
            serializable = {
                slug: list(entries) for slug, entries in self.price_history.items()
            }
            with open(MARKET_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Price history save failed: {e}")

    def _is_market_related(self, event: dict) -> bool:
        """Check if event matches Iran/oil/gold keywords."""
        title = event.get("title", "")
        if FALSE_POSITIVES.search(title):
            return False
        slug = event.get("slug", "")
        desc = event.get("description", "")[:500]
        return bool(
            MARKET_KEYWORDS.search(title)
            or MARKET_KEYWORDS.search(slug)
            or MARKET_KEYWORDS.search(desc)
        )

    async def update(self):
        """Load all active markets, filter relevant ones, update price history."""
        logger.info("Updating market cache...")
        all_markets = []
        offset = 0
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        ts = time.time()

        skipped_resolved = 0
        skipped_volume = 0

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
                    logger.error(f"Gamma API error at offset {offset}: {e}")
                    break

                if not events:
                    break

                for event in events:
                    if not self._is_market_related(event):
                        continue

                    for market in event.get("markets", []):
                        try:
                            prices = json.loads(market.get("outcomePrices", "[]"))
                            yes_price = float(prices[0]) if prices else 0
                        except (json.JSONDecodeError, IndexError, ValueError):
                            yes_price = 0

                        volume = float(market.get("volume", 0) or 0)

                        if yes_price <= MIN_PRICE or yes_price >= MAX_PRICE:
                            skipped_resolved += 1
                            continue

                        slug = market.get("slug", "")
                        event_slug = event.get("slug", "")
                        tradeable = volume >= MIN_VOLUME

                        if not tradeable:
                            skipped_volume += 1

                        all_markets.append({
                            "title": market.get("question", event.get("title", "")),
                            "conditionId": market.get("conditionId", ""),
                            "slug": slug,
                            "event_slug": event_slug,
                            "description": market.get("description", "")[:300],
                            "yes_price": round(yes_price, 4),
                            "volume": round(volume),
                            "end_date": market.get("endDate", ""),
                            "created_at": market.get("createdAt", ""),
                            "tradeable": tradeable,
                        })

                offset += 100
                if len(events) < 100:
                    break

        # Detect new markets (slug absent from previous cache)
        old_slugs = {m["slug"] for m in self.markets}
        new_slugs = {m["slug"] for m in all_markets} - old_slugs
        new_markets = [m for m in all_markets if m["slug"] in new_slugs]

        # Update price history
        for m in all_markets:
            slug = m["slug"]
            if slug not in self.price_history:
                self.price_history[slug] = deque(maxlen=120)
            self.price_history[slug].append((ts, m["yes_price"]))

        self.markets = all_markets
        self.last_update = ts
        self._save_to_disk()
        n_tradeable = sum(1 for m in all_markets if m.get("tradeable", True))
        logger.info(
            f"Market cache updated: {n_tradeable} tradeable + {skipped_volume} low-volume "
            f"= {len(self.markets)} total (skipped {skipped_resolved} resolved)"
        )
        if new_markets:
            logger.info(f"New market(s) detected: {len(new_markets)}")

        return new_markets

    def get_summary_for_prompt(self, max_markets: int = 30) -> str:
        """Summary of live markets for Claude prompt (resolved filtered out)."""
        sorted_m = sorted(self.markets, key=lambda m: m["volume"], reverse=True)
        lines = []
        for m in sorted_m[:max_markets]:
            yes_pct = round(m["yes_price"] * 100, 1)
            desc = m.get("description", "")[:150]
            line = (
                f"- [{m['title']}] YES={yes_pct}% | Vol=${m['volume']:,} | "
                f"Ends: {m['end_date'][:10]} | Slug: {m['slug']}"
            )
            if desc:
                line += f"\n  Resolution: {desc}"
            lines.append(line)
        return "\n".join(lines)

    def get_prices_by_slug(self) -> dict[str, float]:
        """Current prices: {slug: yes_pct}."""
        return {m["slug"]: round(m["yes_price"] * 100, 1) for m in self.markets}

    def get_price_5min_ago(self, slug: str) -> float | None:
        """Price ~5 minutes ago (or nearest to 5 min)."""
        history = self.price_history.get(slug)
        if not history or len(history) < 2:
            return None

        now = time.time()
        target = now - 300  # 5 minutes ago

        best = None
        for ts, price in history:
            if ts <= target:
                best = price

        return round(best * 100, 1) if best is not None else None

    def get_market_by_slug(self, slug: str) -> dict | None:
        """Get market by slug."""
        for m in self.markets:
            if m["slug"] == slug:
                return m
        return None


# Backward-compatible alias so existing imports still work
IranMarketCache = MarketCache
