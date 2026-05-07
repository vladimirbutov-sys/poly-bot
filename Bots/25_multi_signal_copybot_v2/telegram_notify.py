"""Telegram notifications for Multi-Signal Copy-Bot."""
import requests
import time
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

_last_send = 0


def send(text: str):
    global _last_send
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        elapsed = time.time() - _last_send
        if elapsed < 0.5:
            time.sleep(0.5 - elapsed)
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=10)
        _last_send = time.time()
    except Exception as e:
        print(f"[TG] Send failed: {e}")


def startup(bankroll):
    send(f"<b>Multi-Signal Copy-Bot started</b>\nBankroll: ${bankroll:.0f}\nPlayers: Car 🚗 | aenews2 📰 | denizz 🔵")


def shutdown():
    send("<b>Multi-Signal Copy-Bot stopped</b>")


def signal_detected(player_name, title, outcome, price, tier, bet_size):
    emoji = {"Car": "🚗", "aenews2": "📰", "denizz": "🔵"}.get(player_name, "👤")
    send(
        f"{emoji} <b>СИГНАЛ {tier} от {player_name}</b>\n"
        f"{title}\n"
        f"{outcome} @ {price:.3f}\n"
        f"Ставка: ${bet_size:.2f}"
    )


def player_buy(player_name: str, title: str, outcome: str, price: float,
               total_usd: float, denizz_status: str = ""):
    """Alert: one of the 4 players just bought $500+.

    denizz_status: '' or brief note about denizz's position on this market.
    """
    emoji = {
        "Car":     "🚗",
        "aenews2": "📰",
        "denizz":  "🔵",
    }.get(player_name, "👤")

    text = (
        f"{emoji} <b>{player_name}</b> купил\n"
        f"{title}\n"
        f"{outcome} @ {price:.3f} | ${total_usd:,.0f}"
    )
    if denizz_status:
        text += f"\n<i>{denizz_status}</i>"
    send(text)


def buy_placed(title, part, price, cost):
    send(f"BUY part {part}: {title}\n@ {price:.3f} | ${cost:.2f}")


def buy_filled(title, part, price, cost):
    send(f"FILLED part {part}: {title}\n@ {price:.3f} | ${cost:.2f}")


def sell_placed(title, reason, price, shares):
    send(f"SELL: {title}\n{reason}\n@ {price:.3f} | {shares:.1f} shares")


def skip(title, reason):
    send(f"SKIP: {title}\n{reason}")


def win(title, pnl):
    send(f"WIN: {title}\n+${pnl:.2f}")


def loss(title, cost):
    send(f"LOSS: {title}\n-${cost:.2f}")


def error(msg):
    send(f"ERROR: {msg}")


def daily_summary(stats):
    send(
        f"<b>Daily Summary</b>\n"
        f"Open: {stats.get('open_count', 0)} | "
        f"W/L: {stats.get('wins', 0)}/{stats.get('losses', 0)}\n"
        f"P&L: ${stats.get('total_pnl', 0):+.2f}\n"
        f"Balance: ${stats.get('current_balance', 0):.2f}"
    )
