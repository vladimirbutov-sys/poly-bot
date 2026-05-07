"""
monitors/youtube_monitor.py — Мониторинг YouTube Live стримов

Парсит ТВ-эфиры exit poll через автосубтитры.
Уровень 1 в цепочке информации — быстрее журналистов.

Требует: YOUTUBE_API_KEY в .env (бесплатный, Google Cloud Console)
"""
import asyncio
import json
import logging
import re

import httpx

from monitors.base import BaseMonitor
from core.config import DATA_DIR

logger = logging.getLogger("youtube")

STATE_FILE = DATA_DIR / "youtube_state.json"
YT_API = "https://www.googleapis.com/youtube/v3"


class YouTubeMonitor(BaseMonitor):
    name = "youtube"

    def __init__(self, channels: dict, api_key: str, on_message=None):
        """
        channels: {channel_id: {tier, lang, topic, name}}
        api_key: YouTube Data API v3 key
        on_message: async callback(text, source_name, meta)
        """
        self.channels = channels
        self.api_key = api_key
        self.on_message = on_message
        self.state: dict = {}
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

    async def _check_live_streams(self, client: httpx.AsyncClient) -> list[dict]:
        """Find active live streams from monitored channels."""
        live_streams = []

        for channel_id, meta in self.channels.items():
            try:
                resp = await client.get(f"{YT_API}/search", params={
                    "part": "snippet",
                    "channelId": channel_id,
                    "eventType": "live",
                    "type": "video",
                    "key": self.api_key,
                })
                if resp.status_code != 200:
                    continue

                items = resp.json().get("items", [])
                for item in items:
                    video_id = item["id"]["videoId"]
                    title = item["snippet"]["title"]
                    live_streams.append({
                        "video_id": video_id,
                        "title": title,
                        "channel_id": channel_id,
                        "meta": meta,
                    })
            except Exception as e:
                logger.debug(f"YouTube search error {channel_id}: {e}")

            await asyncio.sleep(0.5)

        return live_streams

    async def _get_live_chat_messages(
        self, video_id: str, client: httpx.AsyncClient
    ) -> list[str]:
        """Read live chat messages from a live stream."""
        try:
            # Get live chat ID
            resp = await client.get(f"{YT_API}/videos", params={
                "part": "liveStreamingDetails",
                "id": video_id,
                "key": self.api_key,
            })
            if resp.status_code != 200:
                return []

            items = resp.json().get("items", [])
            if not items:
                return []

            chat_id = items[0].get("liveStreamingDetails", {}).get("activeLiveChatId")
            if not chat_id:
                return []

            # Get chat messages
            page_token = self.state.get(f"chat_{video_id}", "")
            params = {
                "part": "snippet",
                "liveChatId": chat_id,
                "maxResults": 50,
                "key": self.api_key,
            }
            if page_token:
                params["pageToken"] = page_token

            resp = await client.get(f"{YT_API}/liveChat/messages", params=params)
            if resp.status_code != 200:
                return []

            data = resp.json()
            self.state[f"chat_{video_id}"] = data.get("nextPageToken", "")

            messages = []
            for item in data.get("items", []):
                text = item.get("snippet", {}).get("displayMessage", "")
                if text and len(text) > 10:
                    messages.append(text)

            return messages

        except Exception as e:
            logger.debug(f"Live chat error: {e}")
            return []

    async def _get_auto_captions(self, video_id: str) -> list[str]:
        """Get auto-generated captions from a live/recent video."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            # Try to get auto-generated transcript
            ytt_api = YouTubeTranscriptApi()
            transcript = ytt_api.fetch(video_id)

            # Get last N seconds of captions (recent content)
            last_seen = self.state.get(f"caption_{video_id}", 0)
            new_texts = []

            for entry in transcript:
                start = entry.start
                if start > last_seen:
                    new_texts.append(entry.text)
                    last_seen = max(last_seen, start + entry.duration)

            self.state[f"caption_{video_id}"] = last_seen
            return new_texts

        except Exception as e:
            logger.debug(f"Caption error {video_id}: {e}")
            return []

    async def _check_recent_videos(self, client: httpx.AsyncClient):
        """Check recent uploads for breaking news (non-live)."""
        for channel_id, meta in self.channels.items():
            try:
                resp = await client.get(f"{YT_API}/search", params={
                    "part": "snippet",
                    "channelId": channel_id,
                    "order": "date",
                    "maxResults": 3,
                    "type": "video",
                    "key": self.api_key,
                })
                if resp.status_code != 200:
                    continue

                last_seen = self.state.get(f"recent_{channel_id}", "")

                for item in resp.json().get("items", []):
                    video_id = item["id"]["videoId"]
                    if video_id == last_seen:
                        break

                    title = item["snippet"]["title"]
                    description = item["snippet"].get("description", "")[:300]
                    text = f"{title}. {description}"

                    if self.on_message:
                        source = f"YT @{meta.get('name', channel_id)}"
                        await self.on_message(text, source, meta)

                if resp.json().get("items"):
                    self.state[f"recent_{channel_id}"] = resp.json()["items"][0]["id"]["videoId"]

            except Exception as e:
                logger.debug(f"Recent videos error {channel_id}: {e}")

            await asyncio.sleep(0.5)

    async def _run(self):
        if not self.api_key:
            logger.warning("No YOUTUBE_API_KEY, YouTube monitor disabled")
            await asyncio.sleep(999999)
            return

        logger.info(f"YouTube monitor: {len(self.channels)} channels")

        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                # Check for live streams
                live = await self._check_live_streams(client)

                if live:
                    logger.info(f"Live streams: {len(live)}")
                    for stream in live:
                        vid = stream["video_id"]
                        meta = stream["meta"]
                        source = f"YT LIVE @{meta.get('name', stream['channel_id'])}"

                        # Try auto-captions first (fastest)
                        captions = await self._get_auto_captions(vid)
                        if captions and self.on_message:
                            text = " ".join(captions[-5:])  # last 5 segments
                            await self.on_message(text, source, meta)

                        # Also read live chat
                        chat_msgs = await self._get_live_chat_messages(vid, client)
                        # Chat is noisy — combine into one block
                        if chat_msgs and self.on_message:
                            text = " | ".join(chat_msgs[-10:])
                            await self.on_message(text, f"{source} (chat)", {**meta, "tier": 4})

                        await asyncio.sleep(2)

                # Check recent uploads (every cycle)
                await self._check_recent_videos(client)

                self._save_state()

                # Poll faster when live streams are active
                interval = 15 if live else 60
                await asyncio.sleep(interval)
