"""Read and write bot configuration files."""
import re
import shutil
import logging
from pathlib import Path

from config import BOTS

log = logging.getLogger("settings_editor")

# Detailed explanations for each parameter (Russian)
PARAM_HELP = {
    # ── 98_sure_bot ──
    "98_sure_bot": {
        "PRICE_THRESHOLD": "Бот покупает только если цена выше этого порога. "
            "Например 0.975 = покупает контракты от 97.5 центов. "
            "Чем выше — тем надёжнее сделки, но меньше прибыль на каждой.",
        "MAX_PRICE": "Максимальная цена покупки. Бот не будет покупать дороже. "
            "Например 0.993 = не дороже 99.3 центов. "
            "Разница между MAX_PRICE и 1.00 — это потенциальная прибыль.",
        "BET_SIZE": "Сколько долларов ставить на одну сделку. "
            "Больше ставка = больше прибыль, но и больше риск.",
        "MIN_LIQUIDITY": "Минимальная ликвидность рынка в USD. "
            "Бот пропускает рынки с маленькой ликвидностью — "
            "там сложно купить/продать без потерь на проскальзывании.",
        "MIN_VOLUME": "Минимальный объём торгов на рынке в USD. "
            "Низкий объём = мало участников = ненадёжный рынок.",
        "SCAN_INTERVAL": "Как часто бот сканирует рынки в поисках новых сделок (в секундах). "
            "300 = раз в 5 минут. Меньше = быстрее реагирует, но больше нагрузка на API.",
        "ORDER_TTL_SECONDS": "Если ордер не исполнился за это время — отменить. "
            "Защита от зависших ордеров. Например 300 = отмена через 5 минут.",
    },
    # ── 20_crock95_bot ──
    "20_crock95_bot": {
        "MIN_BET_USD": "Минимальный размер ставки в долларах. "
            "Бот не будет ставить меньше этой суммы.",
        "RESERVE_USD": "Резерв для повторных входов. Бот откладывает эту сумму, "
            "чтобы усилить позицию если Crock95 докупает. "
            "0 = не резервировать, ставить всё сразу.",
        "MAX_CONCURRENT": "Максимум открытых позиций одновременно. "
            "Защита от чрезмерной диверсификации. "
            "8 = бот держит максимум 8 рынков одновременно.",
        "MAX_SLIPPAGE": "Максимальное проскальзывание цены при покупке. "
            "0.02 = допускается отклонение до 2%. "
            "Если цена ушла дальше — ордер не размещается.",
        "MIN_PLAYER_INVESTED": "Бот копирует Crock95 только если тот вложил минимум "
            "эту сумму в рынок. Фильтрует мелкие \"пробные\" ставки.",
        "MIN_PLAYER_BUYS": "Минимальное количество покупок Crock95 на рынке. "
            "2 = Crock95 должен купить минимум 2 раза, прежде чем бот повторит.",
        "EXIT_SELL_AT_PRICE": "Автоматическая фиксация прибыли: продать когда цена "
            "достигнет этого уровня. 0.90 = продать при цене 90 центов.",
        "EXIT_STOP_LOSS_PCT": "Стоп-лосс: продать если цена упала на этот % от входа. "
            "0.80 = продать если цена упала на 20% от цены покупки.",
        "EXIT_TIME_STOP_DAYS": "Закрыть позицию если она открыта дольше этого количества дней. "
            "Защита от \"застрявших\" сделок, которые не двигаются.",
        "EXIT_TIME_STOP_MAX_LOSS": "При закрытии по времени — закрывать только если убыток "
            "не превышает этот %. 0.15 = закрыть по времени только если потеря < 15%.",
        "EXIT_FOLLOW_CROCK95_HOURS": "Если Crock95 продал свою позицию — продать через "
            "столько часов. Следуем за лидером при выходе.",
        "MAX_DRAWDOWN_PCT": "Максимальная просадка портфеля в %. "
            "Если портфель упал на этот % от максимума — бот останавливается. "
            "0.30 = стоп при просадке 30%.",
        "POLL_INTERVAL": "Как часто бот проверяет активность Crock95 (в секундах). "
            "30 = раз в полминуты.",
        "POSITIONS_CHECK_INTERVAL": "Как часто проверять открытые позиции на условия выхода "
            "(стоп-лосс, тейк-профит, время). В секундах.",
        "ORDER_TTL_SECONDS": "Если ордер не исполнился за это время — отменить. "
            "Защита от зависших ордеров.",
    },
    # ── 10_oil_swing_bot ──
    "10_oil_swing_bot": {
        "MIN_BET_USD": "Минимальный размер ставки в долларах на одну сделку.",
        "MAX_BET_FREE_PCT": "Максимальный % от свободного баланса на одну ставку. "
            "0.10 = не более 10% свободных средств на сделку. "
            "Защита от слишком крупных ставок.",
        "MAX_SLIPPAGE": "Максимальное проскальзывание цены. "
            "0.03 = допуск 3%. Если цена ушла дальше — ордер отменяется.",
        "MAX_YES_ENTRY_PRICE": "Максимальная цена для покупки YES (нефть вырастет). "
            "Бот не покупает YES дороже этой цены.",
        "MAX_NO_ENTRY_PRICE": "Максимальная цена для покупки NO (нефть не вырастет). "
            "Бот не покупает NO дороже этой цены.",
        "YES_PROFIT_TARGET": "Цель по прибыли для YES-позиций. "
            "0.15 = продать когда прибыль достигнет 15%.",
        "WTI_SELL_NO_BELOW": "Продать NO-позиции если цена нефти WTI упала ниже этого уровня. "
            "Логика: если нефть сильно падает, NO (\"нефть не вырастет\") становится выгоднее держать... "
            "но этот порог — для фиксации прибыли.",
        "STOP_CEASEFIRE_WTI": "Аварийный стоп для YES: продать YES если нефть WTI "
            "упала ниже этого уровня. Например $84 = если нефть ниже $84, "
            "шансы на рост малы — фиксируем убыток.",
        "STOP_NO_WTI": "Аварийный стоп для NO: продать NO если нефть WTI "
            "выросла выше этого уровня. Если нефть растёт — NO-позиция теряет.",
        "STOP_THETA_DAYS": "Продать YES если позиция открыта дольше N дней "
            "и нефть не двигается в нужную сторону. Защита от \"замороженного\" капитала.",
        "STOP_THETA_WTI_MOVE": "Минимальное движение цены WTI (в $) чтобы держать YES. "
            "Если за STOP_THETA_DAYS дней нефть не сдвинулась хотя бы на столько — продаём.",
        "STOP_PORTFOLIO_FLOOR": "Полная остановка бота если портфель упал ниже этой суммы. "
            "Последняя линия защиты от потерь.",
        "DEAD_ZONE_START_ET": "Начало \"мёртвой зоны\" (час по ET / Нью-Йорк). "
            "В это время бот не торгует — рынок нефти закрыт.",
        "DEAD_ZONE_END_ET": "Конец \"мёртвой зоны\" (час по ET). "
            "После этого часа бот снова может торговать.",
        "ORDER_TTL_SECONDS": "Отменить неисполненный ордер через это количество секунд.",
        "SCAN_INTERVAL": "Как часто сканировать рынки (в секундах). "
            "60 = раз в минуту.",
    },
    # ── oil_swing_bot2 ──
    "oil_swing_bot2": {
        "BET_USD": "Размер ставки в долларах на одну сделку NO $105.",
        "MAX_POSITIONS": "Максимум открытых NO позиций одновременно.",
        "BANKROLL": "Общий капитал, выделенный на этого бота.",
        "YES_ENTRY_THRESHOLD": "Покупать NO только когда YES выше этого порога. "
            "0.55 = покупать NO когда рынок даёт 55%+ шанс на $105 (переоценка).",
        "WTI_MAX_ENTRY": "Не входить если WTI уже выше этой цены. "
            "$98 = слишком близко к $105, риск стоп-лосса высок.",
        "PROFIT_TARGET": "Цель по прибыли. 0.10 = продать NO при +10% от входа.",
        "WTI_STOP_LOSS": "Стоп-лосс: продать NO если WTI достигнет этой цены. "
            "$103 = слишком близко к $105, NO обесценится.",
        "ORDER_TTL_SECONDS": "Отменить неисполненный ордер через N секунд.",
        "MAX_SLIPPAGE": "Максимальное проскальзывание цены. 0.03 = допуск 3%.",
        "SCAN_INTERVAL_SECONDS": "Как часто проверять рынок (в секундах). 60 = раз в минуту.",
        "DEAD_ZONE_START_ET": "Начало мёртвой зоны (час по ET). Бот не торгует в это время.",
        "DEAD_ZONE_END_ET": "Конец мёртвой зоны (час по ET).",
    },
    # ── 24_iran_daily_trader ──
    "24_iran_daily_trader": {
        "S1_ENTRY_A": "Основная цена входа S1 (60% размера). "
            "0.80 = покупать YES за 80¢. Чем ниже — тем лучше вход, но реже срабатывает.",
        "S1_ENTRY_B": "Вторая цена входа S1 (40% размера). "
            "0.76 = докупить YES за 76¢ если цена просела. Усреднение позиции.",
        "S1_EXIT_A": "Первая цель по прибыли S1. "
            "0.87 = продать 50% при 87¢ (+7¢ от входа).",
        "S1_EXIT_B": "Вторая цель по прибыли S1. "
            "0.92 = продать остаток при 92¢ (+12¢ от входа).",
        "S1_HARD_STOP": "Жёсткий стоп-лосс S1. "
            "0.65 = продать всё при 65¢. Потеря ~19% от входа 80¢.",
        "S2A_TRIGGER_DROP": "Минимальное падение YES для входа в S2A (стратегия NO при панике). "
            "0.10 = -10% от пика за 6ч. Покупаем NO когда рынок резко падает.",
        "S2A_NO_TARGET": "Цель по прибыли для NO-позиции S2A. "
            "0.60 = продать NO при 60¢.",
        "S2A_STOP_LOSS": "Стоп-лосс для NO-позиции S2A. "
            "0.30 = продать NO при убытке -30%.",
        "S2A_TIME_LIMIT_H": "Максимальное время удержания NO-позиции S2A (часов). "
            "8 = если за 8ч NO не достиг цели — закрыть по рынку.",
        "S1_SIZE": "Размер ставки S1 (YES swing) в долларах. "
            "$50 = на каждый daily-рынок.",
        "S2_SIZE": "Размер ставки S2 (NO при панике/перемирии) в долларах. "
            "$25 = на каждый вход.",
        "PRICE_POLL_INTERVAL": "Как часто опрашивать цены (в секундах). "
            "30 = раз в 30 секунд.",
        "STRATEGY_TICK_INTERVAL": "Как часто проверять сигналы на вход/выход (в секундах). "
            "30 = раз в 30 секунд.",
    },
}

# Editable parameters per bot (param_name, description, value_type, min, max)
EDITABLE_PARAMS = {
    "98_sure_bot": [
        # Prices
        ("PRICE_THRESHOLD", "Min buy price", "float", 0.90, 1.0),
        ("MAX_PRICE", "Max buy price", "float", 0.90, 1.0),
        # Sizing
        ("BET_SIZE", "Bet size USD", "float", 1.0, 100.0),
        # Filters
        ("MIN_LIQUIDITY", "Min market liquidity USD", "float", 0, 50000),
        ("MIN_VOLUME", "Min market volume USD", "float", 0, 100000),
        # Timing
        ("SCAN_INTERVAL", "Scan interval sec", "int", 30, 3600),
        ("ORDER_TTL_SECONDS", "Cancel unfilled after sec", "int", 30, 3600),
    ],
    "20_crock95_bot": [
        # Sizing
        ("MIN_BET_USD", "Min bet USD", "float", 1.0, 500.0),
        ("RESERVE_USD", "Reserve for multi-entry USD", "float", 0, 200.0),
        # Limits
        ("MAX_CONCURRENT", "Max open positions", "int", 1, 50),
        ("MAX_SLIPPAGE", "Max slippage", "float", 0.001, 0.1),
        # Filters
        ("MIN_PLAYER_INVESTED", "Min Crock95 invested USD", "float", 10.0, 5000.0),
        ("MIN_PLAYER_BUYS", "Min Crock95 buys", "int", 1, 20),
        # Exit rules
        ("EXIT_SELL_AT_PRICE", "Auto-sell at price", "float", 0.5, 1.0),
        ("EXIT_STOP_LOSS_PCT", "Stop-loss %", "float", 0.1, 1.0),
        ("EXIT_TIME_STOP_DAYS", "Close stale after days", "int", 1, 90),
        ("EXIT_TIME_STOP_MAX_LOSS", "Max loss % to close stale", "float", 0.05, 1.0),
        ("EXIT_FOLLOW_CROCK95_HOURS", "Sell after Crock95 exits, hours", "int", 1, 48),
        # Risk
        ("MAX_DRAWDOWN_PCT", "Max drawdown %", "float", 0.1, 1.0),
        # Timing
        ("POLL_INTERVAL", "Poll interval sec", "int", 5, 300),
        ("POSITIONS_CHECK_INTERVAL", "Check exits interval sec", "int", 10, 600),
        ("ORDER_TTL_SECONDS", "Cancel unfilled after sec", "int", 60, 7200),
    ],
    "10_oil_swing_bot": [
        # Sizing
        ("MIN_BET_USD", "Min bet USD", "float", 1.0, 100.0),
        ("MAX_BET_FREE_PCT", "Max bet % of free balance", "float", 0.05, 0.50),
        ("MAX_SLIPPAGE", "Max slippage", "float", 0.001, 0.1),
        # Price limits
        ("MAX_YES_ENTRY_PRICE", "Max YES entry price", "float", 0.10, 0.90),
        ("MAX_NO_ENTRY_PRICE", "Max NO entry price", "float", 0.10, 0.90),
        ("YES_PROFIT_TARGET", "YES profit target %", "float", 0.05, 0.50),
        ("WTI_SELL_NO_BELOW", "Sell NO if WTI below", "float", 80.0, 100.0),
        # Stop-losses
        ("STOP_CEASEFIRE_WTI", "Sell YES if WTI below", "float", 50.0, 120.0),
        ("STOP_NO_WTI", "Sell NO if WTI above", "float", 80.0, 150.0),
        ("STOP_THETA_DAYS", "Sell stale YES after days", "int", 1, 30),
        ("STOP_THETA_WTI_MOVE", "Min WTI move to keep YES", "float", 0.5, 10.0),
        ("STOP_PORTFOLIO_FLOOR", "Stop bot if portfolio below", "float", 50.0, 500.0),
        # Dead zone
        ("DEAD_ZONE_START_ET", "Dead zone start hour ET", "int", 0, 23),
        ("DEAD_ZONE_END_ET", "Dead zone end hour ET", "int", 0, 23),
        # Timing
        ("ORDER_TTL_SECONDS", "Cancel unfilled after sec", "int", 60, 3600),
        ("SCAN_INTERVAL", "Scan interval sec", "int", 10, 600),
    ],
    "oil_swing_bot2": [
        # Sizing
        ("BET_USD", "Bet size USD", "float", 1.0, 100.0),
        ("MAX_POSITIONS", "Max open positions", "int", 1, 10),
        ("BANKROLL", "Bankroll USD", "float", 50.0, 1000.0),
        # Entry
        ("YES_ENTRY_THRESHOLD", "Buy NO when YES above", "float", 0.30, 0.90),
        ("WTI_MAX_ENTRY", "Skip entry if WTI above", "float", 90.0, 110.0),
        # Exit
        ("PROFIT_TARGET", "Profit target %", "float", 0.05, 0.50),
        ("WTI_STOP_LOSS", "Stop-loss: sell NO if WTI above", "float", 95.0, 110.0),
        # Order
        ("ORDER_TTL_SECONDS", "Cancel unfilled after sec", "int", 60, 3600),
        ("MAX_SLIPPAGE", "Max slippage", "float", 0.01, 0.10),
        # Timing
        ("SCAN_INTERVAL_SECONDS", "Scan interval sec", "int", 10, 600),
        ("DEAD_ZONE_START_ET", "Dead zone start hour ET", "int", 0, 23),
        ("DEAD_ZONE_END_ET", "Dead zone end hour ET", "int", 0, 23),
    ],
    "24_iran_daily_trader": [
        # S1 YES Swing
        ("S1_ENTRY_A", "S1 entry price (60%)", "float", 0.50, 0.90),
        ("S1_ENTRY_B", "S1 entry price (40%)", "float", 0.50, 0.90),
        ("S1_EXIT_A", "S1 exit target A", "float", 0.80, 1.00),
        ("S1_EXIT_B", "S1 exit target B", "float", 0.80, 1.00),
        ("S1_HARD_STOP", "S1 hard stop-loss", "float", 0.30, 0.80),
        # S2A NO on crash
        ("S2A_TRIGGER_DROP", "S2A crash trigger (%)", "float", 0.05, 0.30),
        ("S2A_NO_TARGET", "S2A NO exit target", "float", 0.30, 0.90),
        ("S2A_STOP_LOSS", "S2A NO stop-loss (%)", "float", 0.10, 0.50),
        ("S2A_TIME_LIMIT_H", "S2A max hold hours", "int", 2, 24),
        # Sizing
        ("S1_SIZE", "S1 bet size USD", "float", 10.0, 200.0),
        ("S2_SIZE", "S2 bet size USD", "float", 5.0, 100.0),
        # Timing
        ("PRICE_POLL_INTERVAL", "Price poll interval sec", "int", 10, 120),
        ("STRATEGY_TICK_INTERVAL", "Strategy tick interval sec", "int", 10, 120),
    ],
}


def _parse_python_config(file_path: Path) -> dict[str, str]:
    """Parse Python config file, extract PARAM = value lines."""
    result = {}
    try:
        text = file_path.read_text(encoding="utf-8")
        # Match lines like: PARAM_NAME = 123 or PARAM_NAME = 0.95
        for match in re.finditer(r'^([A-Z_0-9]+)\s*=\s*(.+?)(?:\s*#.*)?$', text, re.MULTILINE):
            name = match.group(1)
            value = match.group(2).strip()
            result[name] = value
    except OSError as e:
        log.warning("Cannot read %s: %s", file_path, e)
    return result


def read_bot_settings(bot_id: str) -> list[dict] | None:
    """Read editable settings for a bot.
    Returns list of {name, description, value, type, min, max}.
    """
    bot_cfg = BOTS.get(bot_id)
    if not bot_cfg:
        return None

    if bot_id not in EDITABLE_PARAMS:
        return None

    config_path = bot_cfg["path"] / bot_cfg["config_file"]
    if not config_path.exists():
        return None

    parsed = _parse_python_config(config_path)
    settings = []

    for param_name, desc, vtype, vmin, vmax in EDITABLE_PARAMS[bot_id]:
        raw = parsed.get(param_name)
        if raw is None:
            continue
        try:
            if vtype == "float":
                value = float(raw)
            elif vtype == "int":
                value = int(float(raw))
            else:
                value = raw
        except (ValueError, TypeError):
            value = raw

        help_text = PARAM_HELP.get(bot_id, {}).get(param_name, "")
        settings.append({
            "name": param_name,
            "description": desc,
            "value": value,
            "type": vtype,
            "min": vmin,
            "max": vmax,
            "help": help_text,
        })

    return settings


def save_bot_settings(bot_id: str, changes: dict[str, any]) -> dict:
    """Save changed settings to bot config.
    changes: {param_name: new_value}
    Returns {"success": True} or {"success": False, "error": ...}.
    """
    bot_cfg = BOTS.get(bot_id)
    if not bot_cfg:
        return {"success": False, "error": f"Unknown bot: {bot_id}"}

    config_path = bot_cfg["path"] / bot_cfg["config_file"]
    if not config_path.exists():
        return {"success": False, "error": "Config file not found"}

    # Validate
    params_map = {p[0]: p for p in EDITABLE_PARAMS.get(bot_id, [])}
    for name, value in changes.items():
        if name not in params_map:
            return {"success": False, "error": f"Unknown parameter: {name}"}
        _, _, vtype, vmin, vmax = params_map[name]
        try:
            if vtype == "float":
                value = float(value)
            elif vtype == "int":
                value = int(float(value))
        except (ValueError, TypeError):
            return {"success": False, "error": f"Invalid value for {name}: {value}"}
        if value < vmin or value > vmax:
            return {"success": False, "error": f"{name} must be between {vmin} and {vmax}"}

    # Backup
    backup_path = config_path.with_suffix(".py.bak")
    shutil.copy2(config_path, backup_path)

    # Read and replace
    text = config_path.read_text(encoding="utf-8")
    for name, value in changes.items():
        _, _, vtype, _, _ = params_map[name]
        if vtype == "int":
            new_val = str(int(float(value)))
        else:
            new_val = str(value)

        # Replace the value in the line
        pattern = rf'^({re.escape(name)}\s*=\s*)(.+?)(\s*#.*)?$'
        replacement = rf'\g<1>{new_val}\3'
        text, count = re.subn(pattern, replacement, text, flags=re.MULTILINE)
        if count == 0:
            return {"success": False, "error": f"Could not find {name} in config"}

    config_path.write_text(text, encoding="utf-8")
    log.info("Saved settings for %s: %s", bot_id, changes)
    return {"success": True}


