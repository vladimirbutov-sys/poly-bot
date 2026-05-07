"""
monitors/telegram_monitor.py — Мониторинг TG-каналов через t.me/s/

Без авторизации. Парсит публичную web-preview страницу.
"""
import asyncio
import json
import logging
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from monitors.base import BaseMonitor
from core.config import DATA_DIR

logger = logging.getLogger("tg_monitor")

STATE_FILE = DATA_DIR / "tg_last_ids.json"
BATCH_PAUSE = 0.5
POLL_INTERVAL = 10.0


class TelegramMonitor(BaseMonitor):
    name = "telegram"

    def __init__(self, channels: dict, on_message=None):
        """
        channels: {username: {tier, lang, topic}}
        on_message: async callback(text, source_name, meta)
        """
        self.channels = channels
        self.on_message = on_message
        self.last_ids: dict[str, int] = {}
        self._load_state()

    def _load_state(self):
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, "r") as f:
                    self.last_ids = json.load(f)
        except Exception:
            pass

    def _save_state(self):
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(self.last_ids, f)
        except Exception:
            pass

    @staticmethod
    def _parse_messages(html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        messages = []
        for widget in soup.select(".tgme_widget_message"):
            data_post = widget.get("data-post", "")
            msg_id_match = re.search(r"/(\d+)$", data_post)
            if not msg_id_match:
                continue
            msg_id = int(msg_id_match.group(1))

            text_el = widget.select_one(".tgme_widget_message_text")
            if not text_el:
                continue
            text = text_el.get_text(separator=" ", strip=True)
            if not text or len(text) < 10:
                continue

            messages.append({"id": msg_id, "text": text})

        messages.sort(key=lambda m: m["id"])
        return messages

    async def _poll_channel(self, username: str, meta: dict, client: httpx.AsyncClient):
        try:
            resp = await client.get(f"https://t.me/s/{username}")
            if resp.status_code != 200:
                return
        except Exception as e:
            logger.debug(f"@{username}: {e}")
            return

        messages = self._parse_messages(resp.text)
        if not messages:
            return

        last_known = self.last_ids.get(username, 0)

        if last_known == 0:
            self.last_ids[username] = messages[-1]["id"]
            logger.info(f"@{username}: init at #{messages[-1]['id']}")
            return

        new_msgs = [m for m in messages if m["id"] > last_known]
        if not new_msgs:
            return

        self.last_ids[username] = new_msgs[-1]["id"]

        for msg in new_msgs:
            logger.info(f"@{username} #{msg['id']}: {msg['text'][:60]}...")
            if self.on_message:
                await self.on_message(
                    msg["text"], f"TG @{username}",
                    {**meta, "msg_id": msg["id"]},
                )

    async def _run(self):
        usernames = list(self.channels.keys())
        logger.info(f"TG monitor: {len(usernames)} channels, poll {POLL_INTERVAL}s")

        async with httpx.AsyncClient(
            timeout=15,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            follow_redirects=True,
        ) as client:
            while True:
                for username in usernames:
                    await self._poll_channel(username, self.channels[username], client)
                    await asyncio.sleep(BATCH_PAUSE)
                self._save_state()
                await asyncio.sleep(POLL_INTERVAL)
