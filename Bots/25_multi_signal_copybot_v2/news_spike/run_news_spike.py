"""
run_news_spike.py — минимальный orchestrator для copybot-v2.

Запускает:
  🔵 News informer — Telegram (27 каналов) + Twitter (@araghchi) + Truth Social (Трамп)
      → Claude Haiku оценка → Crisis Bypass → дедупликация → Telegram alert
  🟠 Spike detector — мониторинг 21 целевого Iran/US рынка из configs/target_markets_iran.json
      → детект сдвига >= 5 п.п. за 5 мин → Telegram alert

НЕ запускает: auto-hedge, auto-spike-rider (только alerts, без торговли).

Запуск: python run_news_spike.py
"""
import asyncio
import hashlib
import json
import logging
import time as _time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from core.config import (
    DATA_DIR, CONFIGS_DIR, MIN_CONFIDENCE, ANTHROPIC_API_KEY,
    TG_BOT_TOKEN, TG_CHAT_ID,
)
from core.iran_market_cache import MarketCache
from core.iran_evaluator import IranEvaluator
from core.alerter import send_alert, format_news_alert, format_odds_alert, format_opportunity_alert
from core.signal_logger import log_signal

from monitors.telegram_monitor import TelegramMonitor
from monitors.twitter_monitor import TwitterMonitor
from monitors.truth_social_monitor import TruthSocialMonitor
from monitors.rss_monitor import RSSMonitor
from monitors.odds_monitor import OddsMonitor
from monitors.opportunity_monitor import OpportunityMonitor

# =====================================================================
# Логирование
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(DATA_DIR / "news_spike.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("news_spike")

# =====================================================================
# Shared ядро
# =====================================================================
market_cache = MarketCache()
evaluator = IranEvaluator()

# Дедупликация по source+text (персистентная)
SEEN_FILE = DATA_DIR / "seen_hashes.json"
_seen: set[str] = set()


def _load_seen():
    global _seen
    try:
        if SEEN_FILE.exists():
            with open(SEEN_FILE, "r") as f:
                _seen = set(json.load(f))
            logger.info(f"Loaded {len(_seen)} seen hashes")
    except Exception as e:
        logger.warning(f"Seen hashes load failed: {e}")


def _save_seen():
    try:
        to_save = list(_seen)[-5000:]
        with open(SEEN_FILE, "w") as f:
            json.dump(to_save, f)
    except Exception as e:
        logger.warning(f"Seen hashes save failed: {e}")


# Дедупликация по теме (20 минут)
_topic_alert_times: dict[str, float] = {}
TOPIC_DEDUP_WINDOW = 1200

# Crisis bypass keywords
CRISIS_BYPASS_ENABLED = True
CRISIS_KEYWORDS_EN = [
    "ultimatum", "deadline", "power plant", "power grid", "obliterate",
    "blackout", "infrastructure strike", "hormuz open", "hormuz reopen",
    "hormuz clos", "full closure", "desalination", "bandar abbas", "bushehr",
    "neka power", "strikes iran", "struck iran", "bombing iran", "iran retaliates",
    "blockade lifted", "blockade ended", "ceasefire broken", "military action",
]
CRISIS_KEYWORDS_OTHER = [
    "ультиматум", "электростанция", "блэкаут", "бандар-аббас",
    "نیروگاه", "اولتیماتوم", "ضرب‌الاجل", "خاموشی", "قطع برق",
    "محطة كهرباء", "إنذار", "مهلة",
]
ALL_CRISIS_KEYWORDS = [k.lower() for k in CRISIS_KEYWORDS_EN + CRISIS_KEYWORDS_OTHER]


def _crisis_keyword_match(text: str) -> str | None:
    text_lower = text.lower()
    for kw in ALL_CRISIS_KEYWORDS:
        if kw in text_lower:
            return kw
    return None


async def _quick_translate(text: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content":
                        f"Переведи на русский язык. Только перевод, ничего лишнего.\n\n{text[:500]}"}],
                },
            )
            resp.raise_for_status()
            return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        logger.warning(f"Quick translate failed: {e}")
        return text


IRAN_CACHE_INTERVAL = 60

# ====== Safety-net: глобальный cutoff по дате поста ======
# Все сообщения со timestamp < MIN_MESSAGE_DATE отбрасываются (даже если прошли фильтр монитора)
MIN_MESSAGE_DATE_ISO = "2026-04-20T00:00:00+00:00"
from datetime import datetime as _dt
MIN_MESSAGE_DATE = _dt.fromisoformat(MIN_MESSAGE_DATE_ISO)


def _confidence_passes(confidence: str) -> bool:
    levels = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
    return levels.get(confidence, 0) >= levels.get(MIN_CONFIDENCE, 2)


# =====================================================================
# Загрузка sources_iran.json
# =====================================================================
def load_iran_sources() -> dict:
    path = CONFIGS_DIR / "sources_iran.json"
    result = {"telegram": {}, "twitter": {}, "keywords": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        result["telegram"] = cfg.get("telegram_channels", {})
        result["twitter"] = cfg.get("twitter_accounts", {})
        result["keywords"] = cfg.get("keywords", {})
        for lang in result["keywords"]:
            result["keywords"][lang] = list(set(result["keywords"][lang]))
        logger.info(
            f"Loaded sources_iran.json: "
            f"{len(result['telegram'])} TG + {len(result['twitter'])} X + "
            f"{sum(len(v) for v in result['keywords'].values())} keywords"
        )
    except Exception as e:
        logger.error(f"Failed to load sources_iran.json: {e}")
    return result


def _keyword_match(text: str, keywords: dict) -> bool:
    text_lower = text.lower()
    for lang_words in keywords.values():
        for kw in lang_words:
            if kw.lower() in text_lower:
                return True
    return False


def _extract_source_url(source_name: str, meta: dict) -> str:
    tweet_id = meta.get("tweet_id", "")
    if tweet_id and source_name.startswith("X @"):
        username = source_name.replace("X @", "")
        return f"https://x.com/{username}/status/{tweet_id}"
    msg_id = meta.get("msg_id", "")
    if msg_id and source_name.startswith("TG @"):
        username = source_name.replace("TG @", "")
        return f"https://t.me/{username}/{msg_id}"
    return meta.get("url", "")


# =====================================================================
# Задача 1: Pipeline обработки новости
# =====================================================================
async def make_process_message(keywords: dict):
    async def process_message(text: str, source_name: str, meta: dict):
        # Safety-net: отсекаем сообщения со timestamp < MIN_MESSAGE_DATE
        msg_ts_str = meta.get("created_at") or meta.get("pub_date") or ""
        if msg_ts_str:
            try:
                msg_ts = _dt.fromisoformat(msg_ts_str.replace("Z", "+00:00"))
                if msg_ts < MIN_MESSAGE_DATE:
                    logger.debug(f"Skip old post {msg_ts.strftime('%Y-%m-%d %H:%M')} from {source_name}")
                    return
            except Exception:
                pass

        h = hashlib.md5(f"{source_name}:{text[:200]}".encode()).hexdigest()
        if h in _seen:
            return
        _seen.add(h)
        if len(_seen) % 50 == 0:
            _save_seen()
        if len(_seen) > 5000:
            recent = list(_seen)[-3000:]
            _seen.clear()
            _seen.update(recent)
            _save_seen()

        if not _keyword_match(text, keywords):
            return

        logger.info(f"🔵 Keyword match [{meta.get('topic', '?')}] {source_name}: {text[:80]}...")

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        source_url = _extract_source_url(source_name, meta)
        tier = meta.get("tier", 3)

        # Crisis Bypass
        crisis_kw = _crisis_keyword_match(text) if CRISIS_BYPASS_ENABLED else None
        if crisis_kw and tier == 1:
            translated = await _quick_translate(text[:500])
            result = {
                "confidence": "HIGH",
                "topic_key": f"crisis_{crisis_kw.replace(' ', '_')}",
                "reasoning": f"⚡ BYPASS: Tier 1 + '{crisis_kw}' — без Claude",
                "summary": translated,
                "_source": source_name,
                "_timestamp": ts,
                "_source_url": source_url,
            }
            logger.info(f"⚡ CRISIS BYPASS: {source_name} + '{crisis_kw}'")
        else:
            result = await evaluator.evaluate(
                text=text, source_name=source_name, tier=tier,
                topic=meta.get("topic", "unknown"),
                lang=meta.get("lang", "en"),
                timestamp=ts, source_url=source_url,
            )
            if result is None:
                return

        confidence = result.get("confidence", "LOW")
        should_send = _confidence_passes(confidence)

        # Topic dedup 20min
        if should_send:
            now_ts = _time.time()
            topic_key = result.get("topic_key", "")
            if topic_key:
                last = _topic_alert_times.get(topic_key, 0)
                if now_ts - last < TOPIC_DEDUP_WINDOW:
                    logger.info(f"Topic dedup skip: {topic_key}")
                    should_send = False

        log_signal(result, sent=should_send, module="news_spike")

        if should_send:
            _topic_alert_times[result.get("topic_key", "")] = _time.time()
            await send_alert(format_news_alert(result))

    return process_message


# =====================================================================
# Задача 2: Callback для odds alerts
# =====================================================================
async def on_odds_alert(alert_data: dict):
    """Вызывается OddsMonitor при движении цены >= 5 п.п. (наши рынки)."""
    logger.info(
        f"🟠 ODDS ALERT: {alert_data['title'][:50]} "
        f"{alert_data['old_pct']}% → {alert_data['current_pct']}% "
        f"({alert_data['direction']}{abs(alert_data['delta_pp'])}pp)"
    )
    await send_alert(format_odds_alert(alert_data))


async def on_opportunity_alert(alert_data: dict):
    """Вызывается OpportunityMonitor при движении >= 7 п.п. на чужих рынках."""
    logger.info(
        f"🟣 OPPORTUNITY: {alert_data['title'][:50]} "
        f"{alert_data['old_pct']}% → {alert_data['current_pct']}% "
        f"({alert_data['direction']}{abs(alert_data['delta_pp'])}pp) "
        f"vol=${alert_data['volume']:,.0f}"
    )
    await send_alert(format_opportunity_alert(alert_data))


# =====================================================================
# MAIN
# =====================================================================
async def run_market_cache_updater():
    """Обновляет MarketCache каждые IRAN_CACHE_INTERVAL секунд."""
    while True:
        try:
            await market_cache.update()
        except Exception as e:
            logger.error(f"Market cache update error: {e}")
        await asyncio.sleep(IRAN_CACHE_INTERVAL)


async def main():
    _load_seen()
    sources = load_iran_sources()

    # Первое обновление кэша (blocking — чтобы OddsMonitor имел данные)
    logger.info("Initial MarketCache update...")
    await market_cache.update()
    logger.info(f"Cached {len(market_cache.markets)} markets")

    process_message = await make_process_message(sources["keywords"])

    # Мониторы
    monitors = []

    # Telegram (27 каналов)
    if sources["telegram"]:
        tg_monitor = TelegramMonitor(channels=sources["telegram"], on_message=process_message)
        monitors.append(tg_monitor)
        logger.info(f"TelegramMonitor: {len(sources['telegram'])} channels")

    # Twitter (@araghchi)
    if sources["twitter"]:
        tw_monitor = TwitterMonitor(accounts=sources["twitter"], on_message=process_message)
        monitors.append(tw_monitor)
        logger.info(f"TwitterMonitor: {len(sources['twitter'])} accounts")

    # Truth Social (Трамп)
    ts_monitor = TruthSocialMonitor(on_message=process_message)
    monitors.append(ts_monitor)
    logger.info("TruthSocialMonitor: @realDonaldTrump")

    # RSS live-blogs (Al Jazeera, Reuters, Axios, BBC, AP, Times of Israel, JPost)
    rss_monitor = RSSMonitor(on_message=process_message)
    monitors.append(rss_monitor)
    logger.info(f"RSSMonitor: {len(rss_monitor.feeds)} feeds")

    # 🟠 Odds Monitor — наши 21 рынок, порог 5 п.п.
    odds = OddsMonitor(iran_cache=market_cache, on_odds_alert=on_odds_alert)
    monitors.append(odds)

    # 🟣 Opportunity Monitor — чужие рынки, порог 7 п.п., мин. $50k объёма
    opportunity = OpportunityMonitor(iran_cache=market_cache, on_opportunity_alert=on_opportunity_alert)
    monitors.append(opportunity)

    # Стартовый алерт
    await send_alert(
        "🚀 <b>news_spike bot started</b>\n"
        f"📰 TG: {len(sources['telegram'])} | X: {len(sources['twitter'])} | Truth Social: 1 | RSS: {len(rss_monitor.feeds)}\n"
        f"🟠 Odds monitor: 21 our markets (>= 5 п.п.)\n"
        f"🟣 Opportunity monitor: all others (>= 7 п.п., vol >= $50k)\n"
        f"⚡ Crisis bypass: ON\n"
        f"🎯 MIN_CONFIDENCE: {MIN_CONFIDENCE}"
    )

    # Запуск параллельно: мониторы (через run_forever с auto-restart) + периодическое обновление кэша
    tasks = [asyncio.create_task(m.run_forever()) for m in monitors]
    tasks.append(asyncio.create_task(run_market_cache_updater()))
    logger.info(f"Started {len(tasks)} tasks (monitors + cache updater)")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        _save_seen()
