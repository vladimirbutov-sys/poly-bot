"""Telegram notifications — fire-and-forget, never raises.
Sends to both personal bot channel AND shared analytics channel."""
import time
import requests
from config import (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                    ANALYTICS_TELEGRAM_BOT_TOKEN, ANALYTICS_TELEGRAM_CHAT_ID)

_last_send = 0


def _do_send(token: str, chat_id: str, text: str, link_preview: bool = False):
    """Low-level send to a specific bot/chat."""
    if not token or not chat_id:
        return
    try:
        requests.post(
            "https://api.telegram.org/bot%s/sendMessage" % token,
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": not link_preview,
            },
            timeout=10,
        )
    except Exception:
        pass


def send(text: str):
    """Send to personal bot channel."""
    global _last_send
    elapsed = time.time() - _last_send
    if elapsed < 0.5:
        time.sleep(0.5 - elapsed)
    _do_send(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, text)
    _last_send = time.time()


def send_analytics(text: str, link_preview: bool = False):
    """Send to shared analytics channel."""
    _do_send(ANALYTICS_TELEGRAM_BOT_TOKEN, ANALYTICS_TELEGRAM_CHAT_ID, text, link_preview)


def send_both(text: str):
    """Send same message to both channels."""
    send(text)
    send_analytics(text)


def startup(balance: float):
    send(
        "<b>OIL SWING BOT started</b>\n"
        "Balance: $%.2f\n"
        "Strategy: swing YES/NO on WTI $90-100 range\n"
        "Market: Will CL hit $100 by end of March?" % balance
    )


def shutdown():
    send("<b>OIL SWING BOT stopped</b>")


def buy(side: str, price: float, cost: float, wti: float):
    text = (
        "<b>BUY %s</b> [Bot1 $100]\n"
        "Price: %.3f | Cost: $%.2f\n"
        "WTI: $%.2f" % (side, price, cost, wti)
    )
    send_both(text)


def sell(side: str, price: float, revenue: float, pnl: float, reason: str, wti: float):
    emoji = "+" if pnl >= 0 else ""
    text = (
        "<b>SELL %s</b> [Bot1 $100] (%s)\n"
        "Price: %.3f | Revenue: $%.2f\n"
        "P&L: %s$%.2f\n"
        "WTI: $%.2f" % (side, reason, price, revenue, emoji, pnl, wti)
    )
    send_both(text)


def divergence_alert(wti_change_pct: float, yes_change_pp: float,
                     expected_pp: float, wti_price: float, yes_price: float):
    text = (
        "<b>DIVERGENCE ALERT</b> [Bot1 $100]\n"
        "WTI changed %+.1f%%, YES changed %+.1fpp\n"
        "Expected: %+.1fpp\n"
        "WTI: $%.2f | YES: %.1f%%\n"
        "Position size reduced to 50%%" % (
            wti_change_pct, yes_change_pp, expected_pp, wti_price, yes_price)
    )
    send_both(text)


def news_alert(alert_text: str):
    """Send news risk alert to both channels with clickable links."""
    send_both(alert_text)


def deadline_close(side: str, pnl: float):
    send_both("<b>DEADLINE CLOSE %s</b> [Bot1]\nP&L: $%+.2f\nReason: approaching March 31" % (side, pnl))


def settlement_resolved(price: float):
    send_both("<b>MARKET RESOLVED YES</b>\nCME settlement: $%.2f >= $100\nBot stopped." % price)


def dead_zone():
    send("Dead zone 12:00-16:00 ET active. Trading paused.")


def error(msg: str):
    send("ERROR: %s" % msg)
