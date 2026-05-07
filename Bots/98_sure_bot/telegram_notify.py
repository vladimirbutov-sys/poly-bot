"""Telegram notifications — fire-and-forget, never raises."""
import logging
import time
import requests

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger("telegram")

_last_send = 0


def send(text: str):
    """Send message to Telegram. Non-blocking, never raises."""
    global _last_send

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    try:
        # Rate limit: 0.5s between messages
        elapsed = time.time() - _last_send
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)

        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        _last_send = time.time()

        if resp.status_code != 200:
            logger.warning("Telegram error %d: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.warning("Telegram send failed: %s", e)


def startup(balance: float, open_positions: int):
    send(
        f"<b>98_sure_bot started</b>\n"
        f"Balance: ${balance:.2f}\n"
        f"Open positions: {open_positions}\n"
        f"Strategy: buy outcomes at 97.5-99.3c"
    )


def shutdown():
    send("<b>98_sure_bot stopped</b>")


def new_bet(title: str, price: float, cost: float, order_id: str):
    send(
        f"<b>NEW BET</b>\n"
        f"{title}\n"
        f"Price: {price:.3f} | Cost: ${cost:.2f}\n"
        f"Order: {order_id[:16]}..."
    )


def bet_filled(title: str, price: float, shares: float, cost: float):
    send(
        f"<b>FILLED</b>\n"
        f"{title}\n"
        f"Price: {price:.3f} | {shares:.2f} shares | ${cost:.2f}"
    )


def bet_partial(title: str, filled: float, total: float):
    send(
        f"<b>PARTIAL FILL</b>\n"
        f"{title}\n"
        f"Filled: {filled:.2f} / {total:.2f} shares"
    )


def bet_cancelled(title: str, reason: str):
    send(f"Cancelled: {title}\n{reason}")


def filter_skip(title: str, reason: str):
    send(f"SKIP: {title}\n{reason}")


def report(report_text: str):
    send(f"<pre>{report_text}</pre>")


def error(msg: str):
    send(f"ERROR: {msg}")
