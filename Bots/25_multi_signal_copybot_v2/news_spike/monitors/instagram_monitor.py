"""
monitors/instagram_monitor.py — Мониторинг Instagram аккаунтов

Instagram агрессивно блокирует скрейпинг. Подходы:
  1. RSS-bridge сервисы (rss.app, bibliogram, rssbridge)
  2. Playwright для публичных профилей (fallback)

Для выборов: кандидаты публикуют заявления в Instagram Stories
раньше, чем где-либо. Особенно важен для Венгрии (Magyar)
и Латинской Америки.
"""
import asyncio
import json
import logging

import httpx
from bs4 import BeautifulSoup

from monitors.base import BaseMonitor
from core.config import DATA_DIR

logger = logging.getLogger("instagram")

STATE_FILE = DATA_DIR / "instagram_state.json"
POLL_INTERVAL = 60  # Instagram is slower, less frequent polling


# List of RSS bridge services to try (in order of reliability)
RSS_BRIDGES = [
    # rss.app — free tier, reliable
    "https://rss.app/feeds/v1.1/{username}.json",
    # rsshub — self-hostable, many instances
    "https://rsshub.app/instagram/user/{username}",
    # Alternative instances
    "https://rss.nixnet.services/instagram/user/{username}",
]


class InstagramMonitor(BaseMonitor):
    name = "instagram"
    restart_delay = 30

    def __init__(self, accounts: dict, on_message=None):
        """
        accounts: {username: {tier, lang, topic, name}}
        on_message: async callback(text, source_name, meta)
        """
        self.accounts = accounts
        self.on_message = on_message
        self.state: dict = {}
        self._working_bridges: dict = {}  # username → working bridge URL
        self._load_state()

    def _load_state(self):
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, "r") as f:
                    self.state = json.load(f)
        except Exception:
            pass

    def _save_state(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.state, f)
        except Exception:
            pass

    async def _try_rss_bridge(
        self, username: str, client: httpx.AsyncClient
    ) -> list[dict] | None:
        """Try RSS bridge services to get Instagram posts."""

        # Use cached working bridge if available
        if username in self._working_bridges:
            url = self._working_bridges[username]
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200:
                    return self._parse_rss(resp.text)
            except Exception:
                del self._working_bridges[username]

        # Try each bridge
        for bridge_template in RSS_BRIDGES:
            url = bridge_template.format(username=username)
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200 and len(resp.text) > 100:
                    posts = self._parse_rss(resp.text)
                    if posts:
                        self._working_bridges[username] = url
                        logger.info(f"IG @{username}: bridge found ({url[:40]}...)")
                        return posts
            except Exception:
                continue

        return None

    @staticmethod
    def _parse_rss(content: str) -> list[dict]:
        """Parse RSS/Atom/JSON feed into list of {title, text, id}."""
        posts = []

        # Try JSON first (rss.app returns JSON)
        if content.strip().startswith("{") or content.strip().startswith("["):
            try:
                data = json.loads(content)
                items = data.get("items", data if isinstance(data, list) else [])
                for item in items[:10]:
                    title = item.get("title", "")
                    text = item.get("content_text", item.get("summary", ""))
                    post_id = item.get("id", item.get("url", ""))
                    if title or text:
                        posts.append({
                            "text": f"{title} {text}".strip(),
                            "id": post_id,
                        })
                return posts
            except json.JSONDecodeError:
                pass

        # Try RSS/Atom XML
        soup = BeautifulSoup(content, "html.parser")
        for item in soup.find_all(["item", "entry"])[:10]:
            title_el = item.find("title")
            desc_el = item.find(["description", "summary", "content"])
            guid_el = item.find(["guid", "id", "link"])

            title = title_el.get_text(strip=True) if title_el else ""
            desc = desc_el.get_text(strip=True) if desc_el else ""
            guid = ""
            if guid_el:
                guid = guid_el.get("href", "") or guid_el.get_text(strip=True)

            if title or desc:
                posts.append({
                    "text": f"{title} {desc}".strip()[:1000],
                    "id": guid,
                })

        return posts

    async def _poll_account(self, username: str, meta: dict, client: httpx.AsyncClient):
        """Poll one Instagram account for new posts."""
        name = meta.get("name", username)

        posts = await self._try_rss_bridge(username, client)
        if not posts:
            return

        last_id = self.state.get(username, "")

        if not last_id:
            # First run
            self.state[username] = posts[0]["id"] if posts else ""
            logger.info(f"IG @{name}: init, {len(posts)} posts")
            return

        # Find new posts
        new_posts = []
        for post in posts:
            if post["id"] == last_id:
                break
            new_posts.append(post)

        if new_posts:
            self.state[username] = new_posts[0]["id"]

        for post in reversed(new_posts):
            text = post["text"]
            if len(text) < 15:
                continue
            logger.info(f"IG @{name}: {text[:60]}...")
            if self.on_message:
                await self.on_message(text, f"IG @{name}", meta)

    async def _run(self):
        if not self.accounts:
            logger.info("No Instagram accounts configured, sleeping")
            await asyncio.sleep(999999)
            return

        logger.info(f"Instagram monitor: {len(self.accounts)} accounts (via RSS bridges)")

        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0"},
            follow_redirects=True,
        ) as client:
            while True:
                for username, meta in self.accounts.items():
                    await self._poll_account(username, meta, client)
                    await asyncio.sleep(2)

                self._save_state()
                await asyncio.sleep(POLL_INTERVAL)
