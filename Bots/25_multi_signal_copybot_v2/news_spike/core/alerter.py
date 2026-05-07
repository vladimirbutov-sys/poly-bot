"""core/alerter.py — Отправка алертов в Telegram (два типа: новости + движения)"""
import logging
import httpx
from core.config import TG_BOT_TOKEN, TG_CHAT_ID
from core.positions import get_position

logger = logging.getLogger("alerter")


# =====================================================================
# Задача 1 — 🔵 Алерт по новости
# =====================================================================
def format_news_alert(evaluation: dict) -> str:
    """Форматирует оценку Claude в 🔵 алерт по новости."""
    conf = evaluation.get("confidence", "?")
    reasoning = evaluation.get("reasoning", "")
    summary = evaluation.get("summary", "")
    source = evaluation.get("_source", "?")
    source_url = evaluation.get("_source_url", "")
    ts = evaluation.get("_timestamp", "")

    source_link = ""
    if source_url:
        source_link = f"\n🌐 {source_url}"

    return (
        f"🔵 <b>НОВОСТЬ | {conf} CONFIDENCE</b>\n"
        f"\n📰 Источник: {source}\n⏱ {ts}\n"
        f"\n📝 {summary}{source_link}\n"
        f"\n💡 {reasoning}"
    )


# =====================================================================
# Задача 2 — 🟠 Алерт по движению рынка
# =====================================================================
def format_odds_alert(alert_data: dict) -> str:
    """Форматирует движение коэффициента в 🟠 алерт."""
    title = alert_data.get("title", "?")
    old_pct = alert_data.get("old_pct", 0)
    current_pct = alert_data.get("current_pct", 0)
    delta_pp = alert_data.get("delta_pp", 0)
    direction = alert_data.get("direction", "")
    volume = alert_data.get("volume", 0)
    event_slug = alert_data.get("event_slug", "")
    slug = alert_data.get("slug", "")
    trigger_reason = alert_data.get("trigger_reason", "")

    sign = "+" if delta_pp > 0 else ""
    link_slug = event_slug or slug
    market_link = ""
    if link_slug:
        market_link = f"\n🔗 https://polymarket.com/event/{link_slug}"

    # Position awareness
    pos = get_position(slug)
    pos_block = ""
    if pos:
        side = pos.get("side", "?")
        size_usd = pos.get("size_usd", 0)
        avg_price = pos.get("avg_price", 0)
        pos_block += f"\n\n📍 Твоя позиция: {side} ${size_usd} (вход {avg_price * 100:.0f}¢)"

        # Determine if movement is FOR or AGAINST the position
        if side == "NO":
            is_against = delta_pp > 0   # YES price went UP → bad for NO holder
        else:
            is_against = delta_pp < 0   # YES price went DOWN → bad for YES holder

        if is_against:
            pos_block += "\n⚠️ Движение ПРОТИВ тебя"
        else:
            pos_block += "\n✅ Движение В ПОЛЬЗУ"

        change = delta_pp / 100 * size_usd
        if side == "NO":
            change = -change  # NO holder gains when YES drops
        pos_block += f"\n💰 Изменение: ~{change:+.0f}$"
    else:
        pos_block = "\n\n📍 Нет позиции — рассмотри вход"

    return (
        f"🟠 <b>ДВИЖЕНИЕ РЫНКА</b>\n"
        f"\n📊 <b>{title}</b>"
        f"\n   Было: {old_pct}% → Стало: {current_pct}% (YES {direction}{abs(delta_pp):.1f} п.п.)"
        f"\n⏱ За последние 5 минут"
        f"\n💰 Объём: ${volume:,}"
        f"\n📐 Порог: {trigger_reason}"
        f"{market_link}"
        f"{pos_block}"
    )


# =====================================================================
# Обратная совместимость: старый формат (для signal_bot.py)
# =====================================================================
def format_signal_alert(evaluation: dict) -> str:
    """Старый формат алерта (обратная совместимость)."""
    return format_news_alert(evaluation)


def format_opportunity_alert(alert_data: dict) -> str:
    """Форматирует движение на 'чужом' рынке в 🟣 алерт (возможность для входа)."""
    title = alert_data.get("title", "?")
    old_pct = alert_data.get("old_pct", 0)
    current_pct = alert_data.get("current_pct", 0)
    delta_pp = alert_data.get("delta_pp", 0)
    direction = alert_data.get("direction", "")
    volume = alert_data.get("volume", 0)
    event_slug = alert_data.get("event_slug", "")
    slug = alert_data.get("slug", "")

    link_slug = event_slug or slug
    market_link = ""
    if link_slug:
        market_link = f"\n🔗 https://polymarket.com/event/{link_slug}"

    # Hint for user — which side to consider
    side_hint = ""
    if delta_pp > 0:
        side_hint = f"\n💡 YES дорожает — возможно, ранний вход на YES, если ожидаете продолжения тренда"
    else:
        side_hint = f"\n💡 YES падает — возможно, ранний вход на NO, если ожидаете продолжения тренда"

    return (
        f"🟣 <b>ВОЗМОЖНОСТЬ (чужой рынок)</b>\n"
        f"\n📊 <b>{title}</b>"
        f"\n   Было: {old_pct}% → Стало: {current_pct}% (YES {direction}{abs(delta_pp):.1f} п.п.)"
        f"\n⏱ За последние 5 минут"
        f"\n💰 Объём: ${volume:,.0f}"
        f"{market_link}"
        f"\n\n📍 У нас нет позиции на этом рынке"
        f"{side_hint}"
    )


def format_new_market_alert(market: dict) -> str:
    """Форматирует алерт о новом рынке 🆕."""
    title = market.get("title", "?")
    yes_pct = round(market.get("yes_price", 0) * 100, 1)
    volume = market.get("volume", 0)
    event_slug = market.get("event_slug", "")
    slug = market.get("slug", "")
    end_date = market.get("end_date", "")[:10]
    created_at = market.get("created_at", "")

    # Форматирование даты создания
    created_str = ""
    if created_at:
        created_str = created_at[:16].replace("T", " ") + " UTC"

    link_slug = event_slug or slug
    market_link = ""
    if link_slug:
        market_link = f"\n🔗 https://polymarket.com/event/{link_slug}"

    return (
        f"🆕 <b>НОВЫЙ РЫНОК</b>\n"
        f"\n📊 <b>{title}</b>"
        f"\n💰 YES: {yes_pct}% | Объём: ${volume:,}"
        f"\n📅 Создан: {created_str}"
        f"\n⏰ Дедлайн: {end_date}"
        f"{market_link}"
    )


async def send_alert(text: str, chat_id: str | None = None):
    """Отправить сообщение в Telegram."""
    target = chat_id or TG_CHAT_ID
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]

    async with httpx.AsyncClient(timeout=10) as client:
        for chunk in chunks:
            try:
                await client.post(url, json={
                    "chat_id": target,
                    "text": chunk,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                })
            except Exception as e:
                logger.error(f"Telegram send failed: {e}")
