"""
monitors/election_monitor.py — Мониторинг выборов

Загружает конфиги из configs/election_*.json
Следит за появлением новых конфигов без перезапуска.
"""
import asyncio
import json
import logging
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from monitors.base import BaseMonitor
from core.config import CONFIGS_DIR, DATA_DIR

logger = logging.getLogger("election")

ELECTION_STATE_FILE = DATA_DIR / "election_state.json"


class ElectionMonitor(BaseMonitor):
    name = "election"

    def __init__(self, get_market_prices=None, on_signal=None):
        """
        get_market_prices: callable() -> dict[slug, price_pct]
        on_signal: async callback(alert_text: str)
        """
        self.get_market_prices = get_market_prices
        self.on_signal = on_signal
        self.state: dict = {}
        self._load_state()

    def _load_state(self):
        try:
            if ELECTION_STATE_FILE.exists():
                with open(ELECTION_STATE_FILE, "r", encoding="utf-8") as f:
                    self.state = json.load(f)
        except Exception:
            pass

    def _save_state(self):
        try:
            with open(ELECTION_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_configs(self) -> list[dict]:
        """Загрузить все активные election_*.json из configs/."""
        configs = []
        for path in sorted(CONFIGS_DIR.glob("election_*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if cfg.get("active"):
                    cfg["_file"] = path.name
                    configs.append(cfg)
            except Exception as e:
                logger.warning(f"Bad config {path.name}: {e}")
        return configs

    def _extract_percentages(self, text: str) -> dict[str, float]:
        results = {}
        patterns = [
            r'([A-ZÁ-Ž][a-zá-ž]+(?:\s+[A-ZÁ-Ž][a-zá-ž]+)*)\s*[-–:]\s*(\d+[.,]\d+)\s*%',
            r'([A-ZÁ-Ž][a-zá-ž]+(?:\s+[A-ZÁ-Ž][a-zá-ž]+)*)\s+(\d+[.,]\d+)\s*%',
            r'([A-ZÁ-Ž]{2,})\s*[-–:]\s*(\d+[.,]\d+)\s*%',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                name = match.group(1).strip()
                pct = float(match.group(2).replace(",", "."))
                if 0.1 < pct < 100 and name not in results:
                    results[name] = pct
        return results

    def _match_to_markets(
        self, parsed_data: dict[str, float], market_prices: dict[str, float], cfg: dict
    ) -> list[dict]:
        threshold = cfg.get("alert_threshold_pp", 10)
        signals = []

        for market_name, minfo in cfg.get("candidate_markets", {}).items():
            slug = minfo.get("slug", "")
            current_price = market_prices.get(slug)
            if current_price is None:
                continue

            # Ищем данные для этого кандидата
            data_pct = None
            for candidate, pct in parsed_data.items():
                if (market_name.lower() in candidate.lower() or
                        candidate.lower() in market_name.lower()):
                    data_pct = pct
                    break

            if data_pct is None:
                continue

            diff = abs(data_pct - current_price)
            if diff >= threshold:
                signals.append({
                    "candidate": market_name,
                    "data_pct": round(data_pct, 1),
                    "market_price_pct": round(current_price, 1),
                    "diff_pp": round(diff, 1),
                    "direction": "YES_UP" if data_pct > current_price else "YES_DOWN",
                    "market_title": minfo.get("market_title", slug),
                    "slug": slug,
                })

        return signals

    def _format_alert(
        self, signals: list[dict], source_name: str, raw_data: dict[str, float], cfg: dict
    ) -> str:
        election_name = cfg.get("name", "Выборы")
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        lines = [
            f"🗳 <b>ELECTION SIGNAL</b>",
            f"",
            f"📰 {election_name}",
            f"📡 Источник: {source_name}",
            f"⏱ {ts}",
            f"",
            f"📊 <b>Данные:</b>",
        ]
        for name, pct in sorted(raw_data.items(), key=lambda x: -x[1]):
            lines.append(f"   {name}: {pct:.1f}%")
        lines.append("")
        lines.append("⚡ <b>Расхождения с Polymarket:</b>")
        for sig in signals:
            arrow = "↑" if sig["direction"] == "YES_UP" else "↓"
            lines.append(
                f"   <b>{sig['candidate']}</b>: данные {sig['data_pct']}% "
                f"vs рынок {sig['market_price_pct']}% "
                f"(Δ {sig['diff_pp']}пп {arrow})"
            )
            if sig.get("slug"):
                lines.append(f"   🔗 https://polymarket.com/event/{sig['slug']}")
        lines.append("")
        lines.append("⏳ Окно: типично 2-6ч")

        return "\n".join(lines)

    async def _check_source(self, source: dict, cfg: dict, client: httpx.AsyncClient):
        url = source.get("url", "")
        name = source.get("name", url)
        keywords = source.get("keywords", [])

        try:
            resp = await client.get(url, follow_redirects=True)
            if resp.status_code != 200:
                return
        except Exception as e:
            logger.debug(f"{name}: {e}")
            return

        html = resp.text

        # Парсинг
        if source.get("type") == "rss":
            soup = BeautifulSoup(html, "html.parser")
            texts = []
            for item in soup.find_all(["item", "entry"]):
                title = item.find("title")
                desc = item.find(["description", "summary"])
                t = (title.get_text(strip=True) if title else "") + " " + \
                    (desc.get_text(strip=True) if desc else "")
                if any(kw.lower() in t.lower() for kw in keywords):
                    texts.append(t)
            full_text = " ".join(texts)
        else:
            if keywords:
                soup = BeautifulSoup(html, "html.parser")
                hits = []
                for el in soup.find_all(["p", "h1", "h2", "h3", "li", "span", "div"]):
                    t = el.get_text(strip=True)
                    if len(t) > 20 and any(kw.lower() in t.lower() for kw in keywords):
                        hits.append(t)
                full_text = " ".join(hits[:10])
            else:
                soup = BeautifulSoup(html, "html.parser")
                full_text = soup.get_text(separator=" ", strip=True)

        parsed_data = self._extract_percentages(full_text)
        if not parsed_data:
            return

        # Дедупликация
        state_key = f"{cfg.get('_file', '')}:{name}"
        if self.state.get(state_key) == parsed_data:
            return
        self.state[state_key] = parsed_data

        logger.info(f"[{cfg.get('name', '?')}] {name}: {parsed_data}")

        # Матчинг
        market_prices = self.get_market_prices() if self.get_market_prices else {}
        signals = self._match_to_markets(parsed_data, market_prices, cfg)
        if not signals:
            return

        logger.info(f"Election signals: {len(signals)} discrepancies")
        if self.on_signal:
            alert = self._format_alert(signals, name, parsed_data, cfg)
            await self.on_signal(alert)

    async def _run(self):
        logger.info("Election monitor started, watching configs/election_*.json")

        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        ) as client:
            while True:
                configs = self._load_configs()

                if not configs:
                    await asyncio.sleep(120)
                    continue

                for cfg in configs:
                    interval = cfg.get("poll_interval", 60)
                    for source in cfg.get("sources", []):
                        await self._check_source(source, cfg, client)
                        await asyncio.sleep(1)

                    self._save_state()

                await asyncio.sleep(min(c.get("poll_interval", 60) for c in configs))
