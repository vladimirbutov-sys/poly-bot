"""monitors/twitter_monitor.py — Мониторинг Twitter через API v2 polling

Приоритизированный polling (оптимизация расхода API):
  Tier 1: каждый цикл (5 мин)
  Tier 2: каждый 3-й цикл (15 мин)
  Tier 3: каждый 6-й цикл (30 мин)
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx

from monitors.base import BaseMonitor
from core.config import X_BEARER_TOKEN, TWITTER_POLL_INTERVAL, DATA_DIR

logger = logging.getLogger("twitter")

SINCE_FILE = DATA_DIR / "twitter_since.json"

# Частота polling по tier: каждые N циклов (base = 5 мин)
# T1: каждый цикл = 5 мин, T2: каждый 3-й = 15 мин, T3: каждый 6-й = 30 мин
TIER_FREQUENCY = {1: 1, 2: 3, 3: 6}

# Игнорировать твиты старше этой даты
MIN_TWEET_DATE = datetime(2026, 4, 20, 0, 0, 0, tzinfo=timezone.utc)


class TwitterMonitor(BaseMonitor):
    name = "twitter"

    def __init__(self, accounts: dict, on_message=None):
        """
        accounts: {username: {tier, topic}}
        on_message: async callback(text, source_name, meta)
        """
        self.accounts = accounts
        self.on_message = on_message

    async def _run(self):
        if not X_BEARER_TOKEN:
            logger.warning("No X_BEARER_TOKEN, Twitter monitor disabled")
            await asyncio.sleep(999999)
            return

        headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

        # Load since_ids
        since_ids = {}
        try:
            if SINCE_FILE.exists():
                with open(SINCE_FILE, "r") as f:
                    since_ids = json.load(f)
        except Exception:
            pass

        # Resolve usernames → user_ids
        user_ids = {}
        usernames = list(self.accounts.keys())

        async with httpx.AsyncClient(timeout=15, headers=headers) as client:
            for i in range(0, len(usernames), 100):
                batch = usernames[i:i + 100]
                try:
                    resp = await client.get(
                        "https://api.twitter.com/2/users/by",
                        params={"usernames": ",".join(batch)},
                    )
                    if resp.status_code == 200:
                        body = resp.json()
                        for user in body.get("data", []):
                            user_ids[user["id"]] = user["username"]
                            logger.info(f"Resolved @{user['username']} → id {user['id']}")
                        errors = body.get("errors", [])
                        for err in errors:
                            logger.warning(f"Twitter user lookup error: {err.get('detail', err)}")
                    else:
                        logger.error(f"Twitter user lookup HTTP {resp.status_code}: {resp.text[:200]}")
                except Exception as e:
                    logger.error(f"User lookup failed: {e}")

        # Count by tier
        tier_counts = {}
        for uid, uname in user_ids.items():
            t = self.accounts.get(uname, {}).get("tier", 3)
            tier_counts[t] = tier_counts.get(t, 0) + 1

        logger.info(
            f"Twitter monitor: {len(user_ids)} accounts "
            f"(T1={tier_counts.get(1,0)} @5min, T2={tier_counts.get(2,0)} @15min, "
            f"T3={tier_counts.get(3,0)} @30min), base interval {TWITTER_POLL_INTERVAL}s"
        )

        cycle = 0

        # Poll loop
        while True:
            cycle += 1
            polled = 0

            for user_id, username in user_ids.items():
                meta = self.accounts.get(username, {"tier": 3, "topic": "unknown"})
                tier = meta.get("tier", 3)
                freq = TIER_FREQUENCY.get(tier, 4)

                # Skip this account if not its turn
                if cycle % freq != 0:
                    continue

                params = {"max_results": 5, "tweet.fields": "created_at,text"}
                if username in since_ids:
                    params["since_id"] = since_ids[username]

                try:
                    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
                        resp = await client.get(
                            f"https://api.twitter.com/2/users/{user_id}/tweets",
                            params=params,
                        )

                    if resp.status_code == 200:
                        polled += 1
                        tweets = resp.json().get("data", [])
                        skipped_old = 0
                        for tweet in reversed(tweets):
                            text = tweet.get("text", "")
                            tweet_id = tweet.get("id", "")
                            created_at = tweet.get("created_at", "")
                            # Фильтр по дате — отсекаем старые твиты
                            if created_at:
                                try:
                                    tweet_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                                    if tweet_dt < MIN_TWEET_DATE:
                                        skipped_old += 1
                                        continue
                                except Exception:
                                    pass
                            if self.on_message:
                                await self.on_message(
                                    text, f"X @{username}",
                                    {**meta, "lang": "en", "tweet_id": tweet_id, "created_at": created_at},
                                )
                        if skipped_old:
                            logger.info(f"@{username}: skipped {skipped_old} tweets older than {MIN_TWEET_DATE.strftime('%Y-%m-%d')}")
                        if tweets:
                            since_ids[username] = tweets[0]["id"]

                    elif resp.status_code == 429:
                        logger.warning("Twitter rate limit, sleeping 60s")
                        await asyncio.sleep(60)
                        break

                except Exception as e:
                    logger.error(f"@{username}: {e}")

            # Save state
            try:
                with open(SINCE_FILE, "w") as f:
                    json.dump(since_ids, f)
            except Exception:
                pass

            if cycle % 10 == 0:
                logger.debug(f"Twitter cycle {cycle}: polled {polled} accounts")

            await asyncio.sleep(TWITTER_POLL_INTERVAL)
