"""
monitors/facebook_monitor.py — Мониторинг публичных Facebook Pages

Два режима:
  1. Graph API (рекомендуется) — надёжно, быстро, без бана
     Требует: FACEBOOK_ACCESS_TOKEN в .env
     Получить: developers.facebook.com → Create App → Get Page Access Token
  
  2. Playwright fallback — если нет токена, парсит через headless browser
     Медленнее и менее надёжно, но работает без регистрации

Facebook — #1 соцсеть в Венгрии (97%) и #2 в Колумбии.
Журналисты и партии постят сюда раньше, чем на Twitter.
"""
import asyncio
import json
import logging

import httpx

from monitors.base import BaseMonitor
from core.config import DATA_DIR

logger = logging.getLogger("facebook")

STATE_FILE = DATA_DIR / "facebook_state.json"
GRAPH_API = "https://graph.facebook.com/v19.0"
POLL_INTERVAL = 30


class FacebookMonitor(BaseMonitor):
    name = "facebook"

    def __init__(self, pages: dict, access_token: str = "", on_message=None):
        """
        pages: {page_id_or_name: {tier, lang, topic, name}}
        access_token: Facebook Graph API access token
        on_message: async callback(text, source_name, meta)
        """
        self.pages = pages
        self.access_token = access_token
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

    # ======================== Graph API mode ========================

    async def _poll_page_graph_api(
        self, page_id: str, meta: dict, client: httpx.AsyncClient
    ):
        """Poll a Facebook page via Graph API."""
        name = meta.get("name", page_id)
        since_ts = self.state.get(f"graph_{page_id}", "")

        params = {
            "fields": "message,created_time,id",
            "limit": 5,
            "access_token": self.access_token,
        }
        if since_ts:
            params["since"] = since_ts

        try:
            resp = await client.get(f"{GRAPH_API}/{page_id}/feed", params=params)

            if resp.status_code == 200:
                posts = resp.json().get("data", [])

                if not since_ts and posts:
                    # First run — just save timestamp
                    self.state[f"graph_{page_id}"] = posts[0].get("created_time", "")
                    logger.info(f"FB @{name}: init (Graph API)")
                    return

                for post in reversed(posts):  # oldest first
                    message = post.get("message", "")
                    if not message or len(message) < 20:
                        continue

                    logger.info(f"FB @{name}: {message[:60]}...")
                    if self.on_message:
                        await self.on_message(message, f"FB @{name}", meta)

                if posts:
                    self.state[f"graph_{page_id}"] = posts[0].get("created_time", "")

            elif resp.status_code == 190:
                logger.error(f"Facebook token expired! Renew FACEBOOK_ACCESS_TOKEN in .env")
            else:
                logger.debug(f"FB @{name}: HTTP {resp.status_code}")

        except Exception as e:
            logger.debug(f"FB @{name}: {e}")

    async def _run_graph_api(self):
        """Main loop using Graph API."""
        logger.info(f"Facebook monitor (Graph API): {len(self.pages)} pages")

        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                for page_id, meta in self.pages.items():
                    await self._poll_page_graph_api(page_id, meta, client)
                    await asyncio.sleep(1)

                self._save_state()
                await asyncio.sleep(POLL_INTERVAL)

    # ======================== Playwright mode ========================

    async def _run_playwright(self):
        """Fallback: use headless browser to scrape public Facebook pages."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            logger.error("Playwright not installed and no FACEBOOK_ACCESS_TOKEN. Facebook monitor disabled.")
            await asyncio.sleep(999999)
            return

        logger.info(f"Facebook monitor (Playwright): {len(self.pages)} pages")

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                locale="en-US",
            )

            try:
                while True:
                    for page_id, meta in self.pages.items():
                        await self._poll_page_playwright(context, page_id, meta)
                        await asyncio.sleep(5)

                    self._save_state()
                    await asyncio.sleep(POLL_INTERVAL)
            finally:
                await browser.close()

    async def _poll_page_playwright(self, context, page_id: str, meta: dict):
        """Scrape a Facebook page using Playwright."""
        name = meta.get("name", page_id)
        url = f"https://www.facebook.com/{page_id}"

        try:
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=25000)
            await page.wait_for_timeout(3000)

            # Close cookie/login popups if present
            try:
                close_btn = page.locator('[aria-label="Close"], [data-testid="cookie-policy-manage-dialog-accept-button"]')
                if await close_btn.count() > 0:
                    await close_btn.first.click()
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Extract post texts
            posts = await page.evaluate("""
                () => {
                    const texts = [];
                    const seen = new Set();
                    // Facebook renders posts in div[data-ad-comet-preview] or similar
                    const candidates = document.querySelectorAll(
                        '[data-ad-comet-preview="message"] span, ' +
                        '[data-ad-preview="message"] span, ' +
                        'div[dir="auto"] span'
                    );
                    for (const el of candidates) {
                        const text = el.textContent?.trim();
                        if (text && text.length > 30 && text.length < 3000 && !seen.has(text)) {
                            seen.add(text);
                            texts.push(text);
                        }
                    }
                    return texts.slice(0, 10);
                }
            """)

            await page.close()

            if not posts:
                return

            last_known = self.state.get(f"pw_{page_id}", "")

            if not last_known:
                self.state[f"pw_{page_id}"] = posts[0][:100] if posts else ""
                logger.info(f"FB @{name}: init (Playwright), {len(posts)} posts")
                return

            # Find new posts
            new_posts = []
            for post in posts:
                if post[:100] == last_known:
                    break
                new_posts.append(post)

            if new_posts:
                self.state[f"pw_{page_id}"] = new_posts[0][:100]

            for post in reversed(new_posts):
                logger.info(f"FB @{name}: {post[:60]}...")
                if self.on_message:
                    await self.on_message(post, f"FB @{name}", meta)

        except Exception as e:
            logger.debug(f"FB @{name} (PW): {e}")
            try:
                await page.close()
            except Exception:
                pass

    # ======================== Main ========================

    async def _run(self):
        if not self.pages:
            logger.info("No Facebook pages configured, sleeping")
            await asyncio.sleep(999999)
            return

        if self.access_token:
            await self._run_graph_api()
        else:
            logger.warning(
                "No FACEBOOK_ACCESS_TOKEN. Using Playwright fallback. "
                "For reliable monitoring, get a token at developers.facebook.com"
            )
            await self._run_playwright()
