"""
monitors/truth_social_monitor.py — Truth Social monitor via RSS + CNN backup

Polls TrumpsTruth.org RSS feed every 120 seconds for new Trump posts.
Falls back to CNN JSON archive every 300 seconds as a backup source.
Deduplicates by post guid/id to avoid re-processing.
Only processes posts from MIN_POST_DATE onwards.
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from monitors.base import BaseMonitor

logger = logging.getLogger("truth_social")

RSS_URL = "https://www.trumpstruth.org/feed"
CNN_BACKUP_URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"

RSS_POLL_INTERVAL = 15     # seconds (was 120 — accelerated for BIG IDEA spike rider)
CNN_POLL_INTERVAL = 60     # seconds (was 300 — accelerated backup)

BASE_META = {"tier": 1, "topic": "trump", "lang": "en"}
SOURCE_NAME = "Truth Social @realDonaldTrump"

# Игнорировать посты старше этой даты
# 2026-04-20: поднято с 24.03, чтобы не заваливать алертами старыми постами про Iran-блокаду
MIN_POST_DATE = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)


class TruthSocialMonitor(BaseMonitor):
    """Monitor Trump's Truth Social posts via RSS feed + CNN JSON backup."""

    name = "truth_social"

    def __init__(self, on_message=None):
        self.on_message = on_message
        self._seen_ids: set[str] = set()

    async def _run(self):
        logger.info(
            f"Truth Social monitor started: RSS every {RSS_POLL_INTERVAL}s, "
            f"CNN backup every {CNN_POLL_INTERVAL}s, "
            f"min date: {MIN_POST_DATE.strftime('%Y-%m-%d')}"
        )
        rss_task = asyncio.create_task(self._poll_rss_loop())
        cnn_task = asyncio.create_task(self._poll_cnn_loop())
        await asyncio.gather(rss_task, cnn_task)

    # ── RSS feed polling ──────────────────────────────────────────────

    async def _poll_rss_loop(self):
        while True:
            try:
                await self._poll_rss()
            except Exception as e:
                logger.error(f"RSS poll error: {e}")
            await asyncio.sleep(RSS_POLL_INTERVAL)

    async def _poll_rss(self):
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(RSS_URL)
            resp.raise_for_status()

        root = ET.fromstring(resp.text)

        # Standard RSS: root/channel/item
        channel = root.find("channel")
        if channel is None:
            items = root.findall("item") or root.findall(
                "{http://www.w3.org/2005/Atom}entry"
            )
        else:
            items = channel.findall("item")

        new_count = 0
        skipped_old = 0
        for item in items:
            guid = self._get_text(item, "guid") or self._get_text(item, "link") or ""
            if not guid:
                continue
            if guid in self._seen_ids:
                continue

            self._seen_ids.add(guid)

            # Фильтр по дате — пропускаем посты до MIN_POST_DATE
            pub_date_str = self._get_text(item, "pubDate")
            if pub_date_str:
                try:
                    pub_date = parsedate_to_datetime(pub_date_str)
                    if pub_date < MIN_POST_DATE:
                        skipped_old += 1
                        continue
                except Exception:
                    pass

            title = self._get_text(item, "title") or ""
            description = self._get_text(item, "description") or ""
            text = f"{title}\n{description}".strip() if description else title

            if not text:
                continue

            link = self._get_text(item, "link") or guid
            new_count += 1
            logger.info(f"New Truth Social post (RSS): {text[:80]}...")

            if self.on_message:
                meta = {**BASE_META, "url": link}
                await self.on_message(text, SOURCE_NAME, meta)

        if skipped_old:
            logger.info(f"RSS: skipped {skipped_old} posts older than {MIN_POST_DATE.strftime('%Y-%m-%d')}")
        if new_count:
            logger.info(f"Processed {new_count} new Truth Social post(s) from RSS")

    # ── CNN backup polling ────────────────────────────────────────────

    async def _poll_cnn_loop(self):
        # Initial delay so RSS gets first chance
        await asyncio.sleep(30)
        while True:
            try:
                await self._poll_cnn()
            except Exception as e:
                logger.error(f"CNN backup poll error: {e}")
            await asyncio.sleep(CNN_POLL_INTERVAL)

    async def _poll_cnn(self):
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(CNN_BACKUP_URL)
            resp.raise_for_status()

        data = resp.json()

        # CNN archive: list of post objects with created_at field
        posts = data if isinstance(data, list) else data.get("posts", data.get("data", []))
        if not isinstance(posts, list):
            return

        new_count = 0
        skipped_old = 0
        for post in posts:
            # Фильтр по дате ПЕРВЫМ — отсекаем 99% постов до парсинга
            created_at = post.get("created_at", "")
            if created_at:
                try:
                    post_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if post_dt < MIN_POST_DATE:
                        skipped_old += 1
                        continue
                except Exception:
                    pass
            else:
                # Нет даты — пропускаем (не доверяем)
                continue

            post_id = str(post.get("id", ""))
            if not post_id:
                continue

            cnn_key = f"cnn_{post_id}"
            if cnn_key in self._seen_ids:
                continue

            self._seen_ids.add(cnn_key)

            text = post.get("content", "") or post.get("text", "") or post.get("body", "")
            if not text:
                continue

            post_url = post.get("url", "") or f"https://truthsocial.com/@realDonaldTrump/posts/{post_id}"

            new_count += 1
            logger.info(f"New Truth Social post (CNN backup): {text[:80]}...")

            if self.on_message:
                await self.on_message(text, SOURCE_NAME, {**BASE_META, "url": post_url})

        if skipped_old:
            logger.info(f"CNN: skipped {skipped_old} posts older than {MIN_POST_DATE.strftime('%Y-%m-%d')}")
        if new_count:
            logger.info(f"Processed {new_count} new Truth Social post(s) from CNN backup")

        # Limit seen set size
        if len(self._seen_ids) > 10000:
            recent = list(self._seen_ids)[-5000:]
            self._seen_ids.clear()
            self._seen_ids.update(recent)

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _get_text(element, tag: str) -> str:
        """Safely extract text from an XML sub-element."""
        child = element.find(tag)
        if child is not None and child.text:
            return child.text.strip()
        return ""
