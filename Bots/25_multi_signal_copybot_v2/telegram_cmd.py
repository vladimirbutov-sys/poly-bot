"""Receive commands from Telegram (/live, /status, /stop).

Uses getUpdates long polling to check for new messages.
"""
import time
import requests
import config
import tracker
import telegram_notify as tg


_last_update_id = 0


def _get_updates():
    """Fetch new messages from Telegram."""
    global _last_update_id
    if not config.TELEGRAM_BOT_TOKEN:
        return []

    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates",
            params={
                "offset": _last_update_id + 1,
                "timeout": 1,
                "allowed_updates": '["message"]',
            },
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("result", [])
            if results:
                _last_update_id = max(r["update_id"] for r in results)
            return results
    except Exception as e:
        print(f"[TG_CMD] getUpdates error: {e}")
    return []


def _is_from_owner(update: dict) -> bool:
    """Check if message is from the bot owner."""
    msg = update.get("message", {})
    chat_id = str(msg.get("chat", {}).get("id", ""))
    return chat_id == str(config.TELEGRAM_CHAT_ID)


def check_commands(mode_manager):
    """Check for incoming Telegram commands. Call this in the main loop."""
    updates = _get_updates()
    for update in updates:
        if not _is_from_owner(update):
            continue

        text = update.get("message", {}).get("text", "").strip().lower()
        print(f"[TG_CMD] Command received: '{text}'", flush=True)

        if text == "/live":
            if mode_manager.mode == "live":
                tg.send("Уже в боевом режиме.")
            else:
                mode_manager.promote_to_live()

        elif text == "/status":
            _send_status(mode_manager)

        elif text == "/stop":
            tg.send("⛔ Бот остановлен по команде /stop.")
            print("[TG_CMD] Stopped by user command /stop")
            raise SystemExit("Stopped by user command /stop")

        elif text == "/help":
            tg.send(
                "Команды:\n"
                "/live — переход в боевой режим\n"
                "/status — текущий статус бота\n"
                "/stop — остановить бота"
            )


def _send_status(mode_manager):
    """Send current bot status to Telegram."""
    data = tracker.load()
    stats = data["stats"]
    open_count = tracker.count_open(data)
    elapsed_h = (time.time() - mode_manager.start_time) / 3600

    mode_label = mode_manager.get_mode_label()
    tiers = mode_manager.get_conviction_tiers()
    bankroll = config.BANKROLL

    from config import BET_FORMULA_A, BET_FORMULA_B, MAX_BET_USD, BET_SCALE
    import math
    # Show formula-based max bet for display
    sizing_lines = []
    for player in config.PLAYERS:
        max_bet = MAX_BET_USD * BET_SCALE
        sizing_lines.append(f"{player}: max ${max_bet:.0f} (log formula)")

    msg = (
        f"📊 СТАТУС БОТА\n\n"
        f"Режим: {mode_label}\n"
        f"Работает: {elapsed_h:.1f}ч\n"
        f"Ошибок: {len(mode_manager.errors)}\n\n"
        f"Банкролл: ${stats['current_balance']:.2f}\n"
        f"Открыто позиций: {open_count}/{config.MAX_CONCURRENT}\n"
        f"Всего сделок: {stats['total_bets']}\n"
        f"P&L: ${stats['total_pnl']:+.2f}\n\n"
        f"Макс. ставки:\n" + "\n".join(sizing_lines)
    )
    tg.send(msg)


def init():
    """Initialize: skip old messages, but process /live if it's the last one."""
    global _last_update_id
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"offset": -1, "timeout": 1},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json()
            results = data.get("result", [])
            if results:
                last = results[-1]
                last_msg = last.get("message", {})
                last_text = last_msg.get("text", "").strip().lower()
                last_chat = str(last_msg.get("chat", {}).get("id", ""))
                if last_text == "/live" and last_chat == str(config.TELEGRAM_CHAT_ID):
                    _last_update_id = last["update_id"] - 1
                    print(f"[TG_CMD] Found pending /live, will process on first cycle")
                else:
                    _last_update_id = last["update_id"]
    except Exception:
        pass
