"""
monitors/whatsapp_monitor.py — Мониторинг WhatsApp Channels

WhatsApp Channels — публичные ленты (как Telegram каналы).
Контент рендерится через JS → нужен headless browser (Playwright).

Требует:
  pip install playwright
  playwright install chromium  (один раз)
"""
import asyncio
import json
import logging
import re
from pathlib import Path

from monitors.base import BaseMonitor
from core.config import DATA_DIR

logger = logging.getLogger("whatsapp")

STATE_FILE = DATA_DIR / "whatsapp_state.json"
POLL_INTERVAL = 30
BATCH_PAUSE = 3


class WhatsAppMonitor(BaseMonitor):
    name = "whatsapp"
    restart_delay = 30  # Playwright is heavier, give more time

    def __init__(self, channels: dict, on_message=None):
        """
        channels: {channel_id: {tier, lang, topic, name}}
          channel_id = the part after whatsapp.com/channel/
        on_message: async callback(text, source_name, meta)
        """
        self.channels = channels
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

    async def _run(self):
        if not self.channels:
            logger.info("No WhatsApp channels configured, sleeping")
            await asyncio.sleep(999999)
            return

        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error(
                "Playwright not installed. Run:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
            await asyncio.sleep(999999)
            return

        logger.info(f"WhatsApp monitor: {len(self.channels)} channels")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                locale="en-US",
            )

            try:
                while True:
                    for channel_id, meta in self.channels.items():
                        await self._poll_channel(context, channel_id, meta)
                        await asyncio.sleep(BATCH_PAUSE)

                    self._save_state()
                    await asyncio.sleep(POLL_INTERVAL)

            finally:
                await browser.close()

    async def _poll_channel(self, context, channel_id: str, meta: dict):
        """Poll one WhatsApp Channel for new messages."""
        url = f"https://www.whatsapp.com/channel/{channel_id}"
        name = meta.get("name", channel_id[:15])

        try:
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=20000)

            # Wait for message content to render
            await page.wait_for_timeout(3000)

            # Extract messages — WhatsApp renders them in span elements
            messages = await page.evaluate("""
                () => {
                    const msgs = [];
                    // WhatsApp channel messages are in specific DOM elements
                    // Look for text content in message containers
                    const elements = document.querySelectorAll(
                        '[role="row"] span, [data-testid="msg-container"] span, ' +
                        '.message-in span, ._amk6 span, [dir="ltr"] span'
                    );
                    const seen = new Set();
                    for (const el of elements) {
                        const text = el.textContent?.trim();
                        if (text && text.length > 20 && text.length < 2000 && !seen.has(text)) {
                            seen.add(text);
                            msgs.push(text);
                        }
                    }
                    return msgs.slice(-20);  // last 20 messages
                }
            """)

            await page.close()

            if not messages:
                return

            last_known = self.state.get(channel_id, "")

            if not last_known:
                # First run — save last message, don't alert
                self.state[channel_id] = messages[-1][:100] if messages else ""
                logger.info(f"WA @{name}: init with {len(messages)} messages")
                return

            # Find new messages (after last known)
            new_msgs = []
            found_last = False
            for msg in messages:
                if msg[:100] == last_known:
                    found_last = True
                    continue
                if found_last:
                    new_msgs.append(msg)

            # If we didn't find last_known, all messages might be new
            # but to avoid spam, just take the last few
            if not found_last and messages:
                new_msgs = messages[-3:]

            if new_msgs:
                self.state[channel_id] = new_msgs[-1][:100]

            for msg in new_msgs:
                logger.info(f"WA @{name}: {msg[:60]}...")
                if self.on_message:
                    source = f"WA @{name}"
                    await self.on_message(msg, source, meta)

        except Exception as e:
            logger.debug(f"WA @{name}: {e}")
            try:
                await page.close()
            except Exception:
                pass
