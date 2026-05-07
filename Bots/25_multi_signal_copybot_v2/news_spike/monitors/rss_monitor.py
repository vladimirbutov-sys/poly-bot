"""
monitors/rss_monitor.py — Generic RSS/Atom feed scraper для новостных live-blogs.

Поддерживает Al Jazeera, Reuters, Axios, BBC, AP, Times of Israel, Jerusalem Post и любые
другие RSS/Atom-источники из configs/rss_sources.json.

Опрашивает каждый feed раз в RSS_POLL_INTERVAL секунд (по умолчанию 60).
Фильтр по дате (MIN_POST_DATE) и persistent-дедуп по guid/link.
"""
import asyncio
import hashlib
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

from monitors.base import BaseMonitor
from core.config import DATA_DIR, CONFIGS_DIR

logger = logging.getLogger("rss_monitor")

RSS_POLL_INTERVAL = 60            # секунд между опросами одного feed
BATCH_PAUSE = 1.0                 # пауза между feed'ами в одном цикле
STATE_FILE = DATA_DIR / "rss_seen_guids.json"

# Игнорировать посты старше этой даты
MIN_POST_DATE = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)


class RSSMonitor(BaseMonitor):
    """Generic RSS/Atom scraper для news live-blogs."""

    name = "rss"

    def __init__(self, on_message=None):
        self.on_message = on_message
        self.feeds = self._load_feeds()
        self.seen_guids: dict[str, list[str]] = {}  # per-feed: list of seen guids
        self._load_state()

    def _load_feeds(self) -> list[dict]:
        path = CONFIGS_DIR / "rss_sources.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            feeds = cfg.get("feeds", [])
            logger.info(f"Loaded {len(feeds)} RSS feeds from rss_sources.json")
            return feeds
        except Exception as e:
            logger.error(f"Failed to load rss_sources.json: {e}")
            return []

    def _load_state(self):
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, "r") as f:
                    self.seen_guids = json.load(f)
        except Exception:
            self.seen_guids = {}

    def _save_state(self):
        try:
            # Keep max 500 guids per feed
            trimmed = {url: guids[-500:] for url, guids in self.seen_guids.items()}
            with open(STATE_FILE, "w") as f:
                json.dump(trimmed, f)
        except Exception as e:
            logger.warning(f"rss_seen_guids save failed: {e}")

    async def _run(self):
        if not self.feeds:
            logger.warning("No RSS feeds configured, monitor idle")
            return
        logger.info(
            f"RSS monitor started: {len(self.feeds)} feeds, "
            f"poll every {RSS_POLL_INTERVAL}s, "
            f"min date: {MIN_POST_DATE.strftime('%Y-%m-%d')}"
        )
        async with httpx.AsyncClient(
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; NewsSpikeBot/1.0)"},
            follow_redirects=True,
        ) as client:
            while True:
                for feed in self.feeds:
                    try:
                        await self._poll_feed(feed, client)
                    except Exception as e:
                        logger.warning(f"Feed error [{feed.get('name')}]: {e}")
                    await asyncio.sleep(BATCH_PAUSE)
                self._save_state()
                await asyncio.sleep(RSS_POLL_INTERVAL)

    async def _poll_feed(self, feed: dict, client: httpx.AsyncClient):
        url = feed["url"]
        name = feed.get("name", url)
        tier = feed.get("tier", 2)
        lang = feed.get("lang", "en")
        topic = feed.get("topic", "unknown")

        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.debug(f"{name}: HTTP {resp.status_code}")
                return
        except Exception as e:
            logger.debug(f"{name}: {e}")
            return

        items = self._parse_items(resp.text)
        if not items:
            return

        seen = set(self.seen_guids.get(url, []))
        new_count = 0
        skipped_old = 0

        for item in items:
            guid = item.get("guid") or item.get("link") or ""
            if not guid:
                # fallback: hash of title+content
                guid = hashlib.md5((item.get("title", "") + item.get("content", "")).encode()).hexdigest()

            if guid in seen:
                continue

            # Date filter
            pub_dt = item.get("pub_date")
            if pub_dt and pub_dt < MIN_POST_DATE:
                skipped_old += 1
                seen.add(guid)
                continue

            seen.add(guid)

            title = item.get("title", "").strip()
            content = item.get("content", "").strip()
            # Remove HTML tags from content
            import re
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()

            text = f"{title}\n{content}" if content else title
            if len(text) < 10:
                continue

            source_name = f"RSS {name}"
            link = item.get("link", "")
            pub_iso = pub_dt.isoformat() if pub_dt else ""

            new_count += 1
            logger.info(f"{name}: {title[:80]}...")

            if self.on_message:
                await self.on_message(
                    text, source_name,
                    {
                        "tier": tier, "lang": lang, "topic": topic,
                        "url": link, "created_at": pub_iso,
                    },
                )

        self.seen_guids[url] = list(seen)[-500:]

        if skipped_old:
            logger.debug(f"{name}: skipped {skipped_old} old posts")
        if new_count:
            logger.info(f"{name}: processed {new_count} new item(s)")

    @staticmethod
    def _parse_items(xml_text: str) -> list[dict]:
        """Parse RSS 2.0 or Atom feed, return list of dicts with {title, link, content, guid, pub_date}."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []

        items = []

        # RSS 2.0: channel/item
        channel = root.find("channel")
        if channel is not None:
            for item_el in channel.findall("item"):
                items.append(RSSMonitor._extract_rss_item(item_el))

        # Atom: /entry
        if not items:
            atom_ns = "{http://www.w3.org/2005/Atom}"
            for entry_el in root.findall(f"{atom_ns}entry"):
                items.append(RSSMonitor._extract_atom_entry(entry_el, atom_ns))

        return [i for i in items if i]

    @staticmethod
    def _extract_rss_item(item_el) -> dict:
        def _get(tag):
            c = item_el.find(tag)
            return c.text.strip() if c is not None and c.text else ""

        title = _get("title")
        link = _get("link")
        description = _get("description")
        content = _get("{http://purl.org/rss/1.0/modules/content/}encoded") or description
        guid = _get("guid") or link
        pub_date_str = _get("pubDate") or _get("dc:date")
        pub_dt = None
        if pub_date_str:
            try:
                pub_dt = parsedate_to_datetime(pub_date_str)
                if pub_dt.tzinfo is None:
                    pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            except Exception:
                try:
                    pub_dt = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
                except Exception:
                    pass

        if not title:
            return {}
        return {
            "title": title, "link": link, "content": content,
            "guid": guid, "pub_date": pub_dt,
        }

    @staticmethod
    def _extract_atom_entry(entry_el, atom_ns: str) -> dict:
        def _get(tag):
            c = entry_el.find(f"{atom_ns}{tag}")
            return c.text.strip() if c is not None and c.text else ""

        title = _get("title")
        summary = _get("summary") or _get("content")
        guid = _get("id")
        link_el = entry_el.find(f"{atom_ns}link")
        link = link_el.get("href") if link_el is not None else ""
        pub_date_str = _get("published") or _get("updated")
        pub_dt = None
        if pub_date_str:
            try:
                pub_dt = datetime.fromisoformat(pub_date_str.replace("Z", "+00:00"))
            except Exception:
                pass

        if not title:
            return {}
        return {
            "title": title, "link": link, "content": summary,
            "guid": guid or link, "pub_date": pub_dt,
        }
