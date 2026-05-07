"""Polymarket Dashboard — NiceGUI application."""
import sys
import asyncio
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from nicegui import ui, app
import data_reader
import bot_manager
import price_fetcher
import trade_executor
import settings_editor
import onchain_reality
from config import BOTS, BOTS_DIR

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("dashboard")

# Prevent NiceGUI from crashing when a browser tab disconnects
_original_handle = None

def _safe_handle_exception(e: Exception) -> None:
    if isinstance(e, RuntimeError) and "deleted" in str(e):
        return  # client disconnected, ignore
    if _original_handle:
        _original_handle(e)

@app.on_startup
def _patch_error_handler():
    global _original_handle
    _original_handle = app.handle_exception
    app.handle_exception = _safe_handle_exception

# ── State ──
_prices: dict[str, float | None] = {}
_loading_prices = False
_redeem_running = False
_redeem_last_result = ""


# ── Formatters ──
def _usd(v) -> str:
    if v is None:
        return "—"
    return f"${v:,.2f}"


def _pnl(v) -> str:
    if v is None:
        return "—"
    return f"{'+' if v >= 0 else ''}${v:,.2f}"


def _pct(w, total) -> str:
    if total == 0:
        return "—"
    return f"{w / total * 100:.0f}%"


def _status_color(s: str) -> str:
    return {"running": "positive", "stopped": "grey", "crashed": "negative"}.get(s, "grey")


# ──────────────────────────────────────────────
#  Main page
# ──────────────────────────────────────────────
@ui.page("/")
def main_page():
    ui.dark_mode(True)

    # ── Header ──
    with ui.header().classes("items-center justify-between"):
        ui.label("Polymarket Dashboard").classes("text-h5 text-bold")
        with ui.row().classes("gap-2"):
            ui.button("Обновить", icon="refresh", on_click=lambda: refresh_all()).props("flat color=white")
            async def restart_dashboard():
                ui.notify("Перезапуск дашборда...", type="info")
                import subprocess
                subprocess.Popen(
                    ["py", "-3.12", "_restart_dash.py"],
                    cwd=str(Path(__file__).parent),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            ui.button("Перезапуск", icon="restart_alt", on_click=restart_dashboard).props("flat color=amber")

    # ══════════════════════════════════════════
    #  Section 1: Bot Controls
    # ══════════════════════════════════════════
    with ui.card().classes("w-full"):
        with ui.row().classes("items-center gap-4"):
            ui.label("Боты").classes("text-h6")
            ui.button("Все старт", icon="play_arrow", color="green",
                      on_click=lambda: start_all()).props("dense size=sm")
            ui.button("Все стоп", icon="stop", color="red",
                      on_click=lambda: stop_all()).props("dense size=sm")
        bot_cards_row = ui.row().classes("w-full flex-wrap gap-3 mt-2")

    # ══════════════════════════════════════════
    #  Section 2: Portfolio Header (4 metrics)
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        with ui.row().classes("items-center gap-4"):
            ui.label("Портфель").classes("text-h6")
            portfolio_price_btn = ui.button("Обновить цены", icon="trending_up",
                                            on_click=lambda: load_prices()).props("dense size=sm")
            portfolio_price_label = ui.label("").classes("text-caption text-grey")
        portfolio_row = ui.row().classes("w-full gap-6 flex-wrap items-end")

    # ══════════════════════════════════════════
    #  Section 3: Bots Breakdown Table
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        ui.label("Разбивка по ботам").classes("text-h6")
        bots_table_container = ui.column().classes("w-full")

    # ══════════════════════════════════════════
    #  Section 3a: Oil Calibration Report
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("oil_barrel", size="sm", color="amber")
            ui.label("Нефть WTI ↔ Polymarket").classes("text-h6")
        calibration_container = ui.column().classes("w-full")

    # ══════════════════════════════════════════
    #  Section 3a2: Smart Tuner Report
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("tune", size="sm", color="deep-purple")
            ui.label("Smart Tuner — Квант-советник").classes("text-h6")
        tuner_container = ui.column().classes("w-full")

    # ══════════════════════════════════════════
    #  Section 3b: Scanner
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        ui.label("97% Scanner — Аналитика рынка").classes("text-h6")
        scanner_container = ui.row().classes("w-full gap-4 flex-wrap")

    # ══════════════════════════════════════════
    #  Section 3c: 98% Sure Bot Stats
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        ui.label("98% Sure Bot — Аналитика").classes("text-h6")
        sure_bot_container = ui.row().classes("w-full gap-4 flex-wrap")

    # ══════════════════════════════════════════
    #  Section 3d: Arb Bot
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("swap_horiz", size="sm", color="cyan")
            ui.label("Arb Bot — Арбитраж").classes("text-h6")
        arb_bot_container = ui.column().classes("w-full")

    # ══════════════════════════════════════════
    #  Section 3e: Iran Signal Bot
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("radar", size="sm", color="red")
            ui.label("Iran Signal Bot — Мониторинг").classes("text-h6")
        iran_signal_container = ui.column().classes("w-full")

    # ══════════════════════════════════════════
    #  Section 3f: Iran Daily Trader
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("military_tech", size="sm", color="amber")
            ui.label("Iran Daily Trader — Торговля").classes("text-h6")
        iran_daily_container = ui.column().classes("w-full")

    # ══════════════════════════════════════════
    #  Section 3g: Multi-Signal Copy-Bot
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        with ui.row().classes("items-center gap-2"):
            ui.icon("people", size="sm", color="teal")
            ui.label("Multi-Signal Copy-Bot — Car 🚗 + aenews2 📰 + denizz 🔵").classes("text-h6")
        multi_signal_container = ui.column().classes("w-full")

    # ══════════════════════════════════════════
    #  Section 4: All Positions
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        with ui.row().classes("items-center gap-4"):
            ui.label("Все позиции").classes("text-h6")
            price_btn = ui.button("Обновить цены", icon="trending_up",
                                  on_click=lambda: load_prices())
            price_label = ui.label("").classes("text-caption text-grey")
        with ui.row().classes("gap-2 mt-1"):
            bot_filter = ui.select(
                ["Все"] + [b["name"] for b in BOTS.values() if b["type"] == "trading"],
                value="Все", label="Бот"
            ).classes("w-48")
            status_filter = ui.select(
                ["Все", "open", "filled", "limit_order", "won", "lost", "selling", "sold", "closed"],
                value="Все", label="Статус"
            ).classes("w-40")
        positions_container = ui.column().classes("w-full mt-2")

    # ══════════════════════════════════════════
    #  Section 5: Bot Strategy Descriptions
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        ui.label("Логика ботов").classes("text-h6")
        strategy_container = ui.column().classes("w-full")

    # ══════════════════════════════════════════
    #  Section 5b: Settings
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        ui.label("Настройки ботов").classes("text-h6")
        settings_container = ui.column().classes("w-full")

    # ══════════════════════════════════════════
    #  Section 6: Logs
    # ══════════════════════════════════════════
    with ui.card().classes("w-full mt-3"):
        ui.label("Логи").classes("text-h6")
        with ui.row().classes("gap-2"):
            log_select = ui.select(
                {bid: bcfg["name"] for bid, bcfg in BOTS.items()},
                value=list(BOTS.keys())[0], label="Бот"
            ).classes("w-48")
            ui.button("Показать", icon="description",
                      on_click=lambda: show_log(log_select.value))
        log_output = ui.code("").classes("w-full max-h-64 overflow-auto mt-2")

    # ──────────────────────────────────────────
    #  Render: Bot Cards
    # ──────────────────────────────────────────
    def render_bot_cards(statuses=None):
        bot_cards_row.clear()
        if statuses is None:
            statuses = bot_manager.get_all_statuses()
        with bot_cards_row:
            for bot_id, bot_cfg in BOTS.items():
                st = statuses.get(bot_id, {})
                status = st.get("status", "stopped")
                with ui.card().classes("p-3 min-w-44"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge(status.upper(), color=_status_color(status)).props("dense")
                        ui.label(bot_cfg["name"]).classes("text-bold text-body2")
                    if st.get("pid"):
                        ui.label(f"PID {st['pid']}").classes("text-caption text-grey")
                    # Health indicator: process alive but not doing work
                    if status == "running" and st.get("healthy") is False:
                        ui.badge("STALE", color="orange").props("dense")
                        ui.label("Нет активности >10 мин").classes("text-caption text-orange")
                    with ui.row().classes("gap-1 mt-1"):
                        if status == "running":
                            ui.button("Стоп", icon="stop", color="red",
                                      on_click=lambda bid=bot_id: do_stop(bid)).props("dense size=sm flat")
                            # Pause button — for bots that support PAUSE file
                            # (98_sure_bot and 26_weather_bot both check for PAUSE file)
                            if bot_id in ("98_sure_bot", "26_weather_bot"):
                                paused = _is_paused(bot_id)
                                if paused:
                                    ui.button("Снять паузу", icon="play_circle",
                                              color="green",
                                              on_click=lambda bid=bot_id: do_toggle_pause(bid)
                                              ).props("dense size=sm flat")
                                    ui.badge("ПАУЗА", color="orange").props("dense")
                                else:
                                    ui.button("Пауза ставок", icon="pause_circle",
                                              color="orange",
                                              on_click=lambda bid=bot_id: do_toggle_pause(bid)
                                              ).props("dense size=sm flat")
                        else:
                            ui.button("Старт", icon="play_arrow", color="green",
                                      on_click=lambda bid=bot_id: do_start(bid)).props("dense size=sm flat")
                        # Redeem button — for any bot that has a redeemer.py module
                        bot_path = bot_cfg.get("path")
                        if bot_path and (Path(bot_path) / "redeemer.py").exists():
                            redeem_disabled = _redeem_running
                            ui.button("Redeem", icon="payments", color="blue",
                                      on_click=lambda bid=bot_id: do_redeem(bid)
                                      ).props(f"dense size=sm flat {'disable' if redeem_disabled else ''}")

    # ──────────────────────────────────────────
    #  Render: Portfolio Header
    # ──────────────────────────────────────────
    def render_portfolio(stats=None, usdc=None):
        portfolio_row.clear()
        if stats is None:
            stats = data_reader.read_bot_stats()

        total_invested = sum(s.get("invested", 0) for s in stats.values())
        total_reserved = sum(s.get("reserved", 0) for s in stats.values())
        total_pnl = sum(s.get("total_pnl", 0) for s in stats.values())
        open_count = sum(s.get("open", 0) for s in stats.values())

        # USDC from cache only (no blocking network call)
        if usdc is None:
            usdc = price_fetcher.get_cached_price("__usdc__") or price_fetcher._usdc_cache[0]

        # Unrealized PnL
        unrealized = _calc_unrealized()

        with portfolio_row:
            # USDC
            with ui.column().classes("min-w-36"):
                ui.label("USDC на кошельке").classes("text-caption text-grey")
                ui.label(_usd(usdc)).classes("text-h5 text-bold")
                ui.label("реальный баланс").classes("text-caption text-grey-6")

            # Invested (only filled positions with actual tokens)
            with ui.column().classes("min-w-36"):
                ui.label("Вложено (filled)").classes("text-caption text-grey")
                ui.label(_usd(total_invested)).classes("text-h5 text-bold")
                ui.label(f"{open_count} открытых").classes("text-caption text-grey-6")

            # Reserved in limit orders (not yet filled)
            if total_reserved > 0:
                with ui.column().classes("min-w-36"):
                    ui.label("В ордерах").classes("text-caption text-grey")
                    ui.label(_usd(total_reserved)).classes("text-h5 text-bold text-orange")
                    ui.label("резерв под лимитки").classes("text-caption text-grey-6")

            # Total portfolio
            total = (usdc or 0) + total_invested + total_reserved
            with ui.column().classes("min-w-36"):
                ui.label("Всего").classes("text-caption text-grey")
                ui.label(_usd(total)).classes("text-h5 text-bold")
                ui.label("USDC + позиции").classes("text-caption text-grey-6")

            # Realized PnL
            color = "text-green" if total_pnl >= 0 else "text-red"
            with ui.column().classes("min-w-36"):
                ui.label("Реализованный PnL").classes("text-caption text-grey")
                ui.label(_pnl(total_pnl)).classes(f"text-h5 text-bold {color}")
                ui.label("факт").classes("text-caption text-grey-6")

            # Unrealized PnL (only if prices loaded)
            if unrealized is not None:
                ucolor = "text-green" if unrealized >= 0 else "text-red"
                with ui.column().classes("min-w-36"):
                    ui.label("Нереализованный PnL").classes("text-caption text-grey")
                    ui.label(_pnl(unrealized)).classes(f"text-h5 text-bold {ucolor}")
                    ui.label("по текущим ценам").classes("text-caption text-grey-6")

            # === ON-CHAIN REALITY (from cache only — never blocks render) ===
            try:
                ws = onchain_reality._wallet_cache.get("data")
                lp = onchain_reality._lifetime_cache.get("data")
                if ws is None:
                    # Schedule background refresh, don't block
                    import threading
                    threading.Thread(target=onchain_reality.get_wallet_summary, daemon=True).start()
                    raise ValueError("cache cold")

                # Real total equity (independent from bot states)
                with ui.column().classes("min-w-36 q-pa-sm").style("border-left: 2px solid #4caf50"):
                    ui.label("РЕАЛЬНО (on-chain)").classes("text-caption text-green-7 text-bold")
                    ui.label(_usd(ws["total_equity"])).classes("text-h5 text-bold text-green-9")
                    parts = f"USDC ${ws['usdc']:.0f} + поз ${ws['open_value']:.0f}"
                    if ws["unredeemed_value"] > 0.5:
                        parts += f" + ред ${ws['unredeemed_value']:.0f}"
                    ui.label(parts).classes("text-caption text-grey-6")

                # Lifetime PnL based on net deposit
                if lp.get("lifetime_pnl") is not None:
                    pnl_val = lp["lifetime_pnl"]
                    pcolor = "text-green-9" if pnl_val >= 0 else "text-red-9"
                    with ui.column().classes("min-w-36 q-pa-sm").style("border-left: 2px solid #4caf50"):
                        ui.label("Lifetime PnL (on-chain)").classes("text-caption text-green-7 text-bold")
                        ui.label(_pnl(pnl_val)).classes(f"text-h5 text-bold {pcolor}")
                        deposit = lp.get("net_external_deposit", 0)
                        ui.label(f"вход ${deposit:.0f}").classes("text-caption text-grey-6")

                # Unredeemed alert (red badge if any)
                if ws["unredeemed_count"] > 0:
                    with ui.column().classes("min-w-36 q-pa-sm").style("border-left: 2px solid #ff5722"):
                        ui.label("Незаредимлено").classes("text-caption text-orange-9 text-bold")
                        ui.label(_usd(ws["unredeemed_value"])).classes("text-h5 text-bold text-orange-9")
                        ui.label(f"{ws['unredeemed_count']} позиций").classes("text-caption text-grey-6")
            except Exception as ex:
                log.warning(f"on-chain reality failed: {ex}")

    # ──────────────────────────────────────────
    #  Render: Bots Table (consistent columns + totals)
    # ──────────────────────────────────────────
    def render_bots_table(stats=None):
        bots_table_container.clear()
        if stats is None:
            stats = data_reader.read_bot_stats()

        columns = [
            {"name": "bot", "label": "Бот", "field": "bot", "align": "left"},
            {"name": "invested", "label": "Вложено", "field": "invested", "align": "right"},
            {"name": "open", "label": "Открыто", "field": "open", "align": "right"},
            {"name": "pnl", "label": "PnL", "field": "pnl", "align": "right"},
            {"name": "wins", "label": "W", "field": "wins", "align": "right"},
            {"name": "losses", "label": "L", "field": "losses", "align": "right"},
            {"name": "winrate", "label": "Win Rate", "field": "winrate", "align": "right"},
        ]

        rows = []
        t_invested = 0
        t_open = 0
        t_pnl = 0
        t_wins = 0
        t_losses = 0

        for bot_id, bot_cfg in BOTS.items():
            if bot_cfg["type"] in ("scanner", "utility") and bot_id != "arb_bot":
                continue
            s = stats.get(bot_id, {})
            invested = s.get("invested", 0)
            opens = s.get("open", 0)
            pnl = s.get("total_pnl", 0)
            wins = s.get("wins", 0)
            losses = s.get("losses", 0)
            total_resolved = wins + losses

            t_invested += invested
            t_open += opens
            t_pnl += pnl
            t_wins += wins
            t_losses += losses

            rows.append({
                "bot": bot_cfg["name"],
                "invested": _usd(invested),
                "open": str(opens),
                "pnl": _pnl(pnl),
                "wins": str(wins),
                "losses": str(losses),
                "winrate": _pct(wins, total_resolved),
            })

        # Totals row
        t_total = t_wins + t_losses
        rows.append({
            "bot": "ИТОГО",
            "invested": _usd(t_invested),
            "open": str(t_open),
            "pnl": _pnl(t_pnl),
            "wins": str(t_wins),
            "losses": str(t_losses),
            "winrate": _pct(t_wins, t_total),
        })

        with bots_table_container:
            table = ui.table(columns=columns, rows=rows).classes("w-full")
            # Bold the totals row
            table.add_slot("body-cell-bot", """
                <q-td :props="props">
                    <span :class="props.row.bot === 'ИТОГО' ? 'text-bold text-primary' : ''">
                        {{ props.row.bot }}
                    </span>
                </q-td>
            """)
            for col in ["invested", "open", "pnl", "wins", "losses", "winrate"]:
                table.add_slot(f"body-cell-{col}", f"""
                    <q-td :props="props">
                        <span :class="props.row.bot === 'ИТОГО' ? 'text-bold text-primary' : ''">
                            {{{{ props.row.{col} }}}}
                        </span>
                    </q-td>
                """)

    # ──────────────────────────────────────────
    #  Render: Arb Bot
    # ──────────────────────────────────────────
    def render_arb_bot(arb_data=None):
        arb_bot_container.clear()
        if arb_data is None:
            arb_data = data_reader.read_arb_bot()
        if not arb_data:
            with arb_bot_container:
                ui.label("Нет данных — бот не запущен").classes("text-grey")
            return

        with arb_bot_container:
            # DRY RUN badge
            if arb_data.get("dry_run"):
                ui.badge("DRY RUN", color="orange").classes("mb-2")

            # Row 1: Key metrics — classify by type
            history = arb_data.get("history", [])
            merged = [h for h in history if h.get("type") == "merged" or
                      (not h.get("type") and h.get("merge_tx"))]
            partial = [h for h in history if h.get("type", "").startswith("partial")]
            stuck = [h for h in history if h.get("type") == "partial_stuck"]
            merge_failed = [h for h in history if h.get("type") == "merge_failed"]

            merge_profit = sum(h.get("profit", 0) for h in merged)
            partial_loss = sum(h.get("profit", 0) for h in partial)
            total_pnl = merge_profit + partial_loss
            total_cost = sum(h.get("cost", 0) for h in history)
            total_revenue = sum(h.get("revenue", h.get("profit", 0) + h.get("cost", 0))
                               for h in merged)

            with ui.row().classes("w-full gap-6 flex-wrap items-end"):
                with ui.column().classes("gap-0"):
                    ui.label("Merge (W)").classes("text-caption text-grey")
                    ui.label(str(len(merged))).classes("text-h5 text-bold text-green")

                with ui.column().classes("gap-0"):
                    ui.label("Partial fill (L)").classes("text-caption text-grey")
                    pcolor = "text-red" if partial else ""
                    ui.label(str(len(partial))).classes(f"text-h5 text-bold {pcolor}")

                with ui.column().classes("gap-0"):
                    ui.label("Вложено всего").classes("text-caption text-grey")
                    ui.label(f"${total_cost:.2f}").classes("text-h5 text-bold")

                with ui.column().classes("gap-0"):
                    ui.label("Прибыль merge").classes("text-caption text-grey")
                    ui.label(f"+${merge_profit:.2f}").classes("text-h5 text-bold text-green")

                with ui.column().classes("gap-0"):
                    ui.label("Убыток partial").classes("text-caption text-grey")
                    lcolor = "text-red" if partial_loss < 0 else "text-grey"
                    ui.label(f"${partial_loss:.2f}").classes(f"text-h5 text-bold {lcolor}")

                with ui.column().classes("gap-0"):
                    ui.label("Итого PnL").classes("text-caption text-grey")
                    color = "text-green" if total_pnl > 0 else "text-red" if total_pnl < 0 else "text-grey"
                    ui.label(f"${total_pnl:.2f}").classes(f"text-h5 text-bold {color}")

                if stuck or merge_failed:
                    with ui.column().classes("gap-0"):
                        ui.label("Застряло").classes("text-caption text-grey")
                        ui.label(str(len(stuck) + len(merge_failed))).classes("text-h5 text-bold text-orange")

            # Row 1b: Scan stats
            with ui.row().classes("w-full gap-6 flex-wrap items-end mt-1"):
                with ui.column().classes("gap-0"):
                    ui.label("Сканирований").classes("text-caption text-grey")
                    ui.label(str(arb_data["total_scans"])).classes("text-h5")

                with ui.column().classes("gap-0"):
                    ui.label("Найдено возможностей").classes("text-caption text-grey")
                    ui.label(str(arb_data["scans_with_opps"])).classes("text-h5")

                hit_rate = (arb_data["scans_with_opps"] / arb_data["total_scans"] * 100) if arb_data["total_scans"] > 0 else 0
                with ui.column().classes("gap-0"):
                    ui.label("Hit rate").classes("text-caption text-grey")
                    ui.label(f"{hit_rate:.1f}%").classes("text-h5")

            # Row 2: Time range & skip reasons
            with ui.row().classes("w-full gap-6 mt-2"):
                if arb_data.get("first_scan"):
                    first_t = arb_data["first_scan"][:16].replace("T", " ")
                    last_t = arb_data["last_scan"][:16].replace("T", " ")
                    ui.label(f"Период: {first_t} — {last_t}").classes("text-caption text-grey")

                if arb_data.get("skipped_reasons"):
                    reasons = ", ".join(f"{k}: {v}" for k, v in arb_data["skipped_reasons"].items())
                    ui.label(f"Пропущено: {reasons}").classes("text-caption text-grey")

            # Row 3: Execution history (last 10)
            if history:
                ui.separator().classes("mt-2")
                ui.label("Последние сделки").classes("text-subtitle2 mt-1")
                rows = []
                type_labels = {
                    "merged": "Merged",
                    "partial_sell": "Partial (sold)",
                    "partial_stuck": "Partial (stuck)",
                    "merge_failed": "Merge failed",
                    "cancelled": "Cancelled",
                }
                for h in reversed(history[-15:]):
                    ts = h.get("timestamp", "")[:16].replace("T", " ")
                    cost = h.get("cost", 0)
                    profit = h.get("profit", 0)
                    h_type = h.get("type", "merged" if h.get("merge_tx") else "unknown")
                    status = type_labels.get(h_type, h_type)
                    rows.append({
                        "time": ts,
                        "event": h.get("event", "?")[:50],
                        "cost": f"${cost:.2f}",
                        "profit": f"${profit:+.4f}" if profit != 0 else "$0",
                        "source": h.get("source", "?"),
                        "status": status,
                    })
                columns = [
                    {"name": "time", "label": "Время", "field": "time"},
                    {"name": "event", "label": "Событие", "field": "event"},
                    {"name": "cost", "label": "Вложено", "field": "cost"},
                    {"name": "profit", "label": "P&L", "field": "profit"},
                    {"name": "source", "label": "Источник", "field": "source"},
                    {"name": "status", "label": "Тип", "field": "status"},
                ]
                ui.table(columns=columns, rows=rows).classes("w-full").props("dense flat")

    # ──────────────────────────────────────────
    #  Render: Iran Signal Bot
    # ──────────────────────────────────────────
    def render_iran_signal(iran=None):
        iran_signal_container.clear()
        if iran is None:
            iran = data_reader.read_iran_signal_bot()
        if not iran:
            with iran_signal_container:
                ui.label("Нет данных — бот не запущен").classes("text-grey")
            return

        with iran_signal_container:
            # Row 1: Key metrics
            with ui.row().classes("w-full gap-6 flex-wrap items-end"):
                _mini_metric("Рынков", str(iran["n_markets"]))
                _mini_metric("Позиций", str(iran["n_positions"]))
                _mini_metric("Вложено", _usd(iran["total_invested"]))

                # Signal counters
                h24 = iran["signals_24h"]
                h1 = iran["signals_1h"]
                high = iran["high_24h"]
                med = iran["medium_24h"]
                _mini_metric("Сигналов/24ч", str(h24))
                _mini_metric("Сигналов/1ч", str(h1))
                _mini_metric("🔴 HIGH/24ч", str(high))
                _mini_metric("🟡 MEDIUM/24ч", str(med))

                # Hedge status
                hedge_label = "ВКЛ" if iran["hedge_enabled"] else "ВЫКЛ"
                hedge_color = "positive" if iran["hedge_enabled"] else "grey"
                with ui.column().classes("min-w-20 items-center"):
                    ui.badge(hedge_label, color=hedge_color).classes("text-bold")
                    ui.label("Авто-хедж").classes("text-caption text-grey")

                if iran["hedge_orders_today"] > 0:
                    _mini_metric("Хеджей сегодня", str(iran["hedge_orders_today"]))
                    _mini_metric("Потрачено", _usd(iran["hedge_daily_usd"]))

                if iran["pending_proposals"] > 0:
                    with ui.column().classes("min-w-20 items-center"):
                        ui.badge(str(iran["pending_proposals"]), color="orange").classes("text-bold")
                        ui.label("Ждут подтв.").classes("text-caption text-grey")

            # Row 2: Positions table
            positions = iran.get("positions", {})
            if positions:
                ui.separator().classes("mt-3 mb-2")
                ui.label("Позиции gamehasyou").classes("text-subtitle2 text-grey")
                pos_rows = []
                for slug, pos in positions.items():
                    pos_rows.append({
                        "title": pos.get("title", slug)[:50],
                        "side": pos.get("side", "?"),
                        "size": _usd(pos.get("size_usd", 0)),
                        "entry": f"{pos.get('avg_price', 0) * 100:.0f}¢",
                        "category": pos.get("category", "?"),
                        "risk": pos.get("risk_note", ""),
                    })
                pos_cols = [
                    {"name": "title", "label": "Рынок", "field": "title", "align": "left", "sortable": True},
                    {"name": "side", "label": "Side", "field": "side", "align": "center"},
                    {"name": "size", "label": "Размер", "field": "size", "align": "right", "sortable": True},
                    {"name": "entry", "label": "Вход", "field": "entry", "align": "center"},
                    {"name": "category", "label": "Кат.", "field": "category", "align": "center"},
                    {"name": "risk", "label": "Риск", "field": "risk", "align": "left"},
                ]
                ui.table(columns=pos_cols, rows=pos_rows).classes("w-full").props("dense flat")

            # Row 3: Recent signals
            signals = iran.get("signals_recent", [])
            if signals:
                ui.separator().classes("mt-3 mb-2")
                ui.label("Последние сигналы").classes("text-subtitle2 text-grey")
                sig_rows = []
                for s in signals[:10]:
                    conf = s.get("confidence", "?").upper()
                    icon = "🔴" if conf == "HIGH" else "🟡" if conf == "MEDIUM" else "⚪"
                    ts = s.get("_timestamp", s.get("timestamp", ""))
                    if "T" in str(ts):
                        ts = str(ts)[:16].replace("T", " ")
                    summary = s.get("summary", s.get("reasoning", "—"))
                    if len(summary) > 100:
                        summary = summary[:97] + "..."
                    source = s.get("_source", s.get("source", ""))
                    sig_rows.append({
                        "time": ts,
                        "level": f"{icon} {conf}",
                        "source": source,
                        "summary": summary,
                    })
                sig_cols = [
                    {"name": "time", "label": "Время", "field": "time", "align": "left"},
                    {"name": "level", "label": "Уровень", "field": "level", "align": "center"},
                    {"name": "source", "label": "Источник", "field": "source", "align": "left"},
                    {"name": "summary", "label": "Сигнал", "field": "summary", "align": "left"},
                ]
                ui.table(columns=sig_cols, rows=sig_rows).classes("w-full").props("dense flat")

    # ──────────────────────────────────────────
    #  Render: Iran Daily Trader
    # ──────────────────────────────────────────
    def render_iran_daily(iran_d=None):
        iran_daily_container.clear()
        if iran_d is None:
            iran_d = data_reader.read_iran_daily_trader()
        if not iran_d:
            with iran_daily_container:
                ui.label("Нет данных — бот не запущен").classes("text-grey")
            return

        with iran_daily_container:
            # Dry run badge
            if iran_d.get("dry_run", True):
                ui.badge("DRY RUN", color="orange").classes("text-bold q-mb-sm")

            # Row 1: Key metrics
            with ui.row().classes("w-full gap-6 flex-wrap items-end"):
                _mini_metric("Рынков", str(iran_d.get("active_markets", 0)))
                _mini_metric("Открыто", str(iran_d.get("open_positions", 0)))
                _mini_metric("Вложено", _usd(iran_d.get("total_invested", 0)))
                _mini_metric("P&L", _pnl(iran_d.get("total_pnl", 0)))
                _mini_metric("Win Rate", f"{iran_d.get('win_rate', 0):.0f}%")
                _mini_metric("Сделок", f"{iran_d.get('wins', 0)}W / {iran_d.get('losses', 0)}L")

            # Row 2: Open positions
            all_pos = []
            for p in iran_d.get("s1_positions", []):
                all_pos.append({**p, "_strategy": "S1"})
            for p in iran_d.get("s2a_positions", []):
                all_pos.append({**p, "_strategy": "S2A"})
            for p in iran_d.get("s2b_positions", []):
                all_pos.append({**p, "_strategy": "S2B"})

            if all_pos:
                ui.separator().classes("mt-3 mb-2")
                ui.label("Открытые позиции").classes("text-subtitle2 text-grey")
                pos_rows = []
                for p in all_pos:
                    pos_rows.append({
                        "strategy": p["_strategy"],
                        "side": p.get("side", "?"),
                        "day": str(p.get("day", "?")),
                        "entry": f"{p.get('entry_price', 0) * 100:.0f}c",
                        "current": f"{p.get('current_price', 0) * 100:.0f}c",
                        "size": _usd(p.get("size_usd", 0)),
                    })
                pos_cols = [
                    {"name": "strategy", "label": "Стратегия", "field": "strategy", "align": "center"},
                    {"name": "side", "label": "Side", "field": "side", "align": "center"},
                    {"name": "day", "label": "День", "field": "day", "align": "center"},
                    {"name": "entry", "label": "Вход", "field": "entry", "align": "center"},
                    {"name": "current", "label": "Текущая", "field": "current", "align": "center"},
                    {"name": "size", "label": "Размер", "field": "size", "align": "right"},
                ]
                ui.table(columns=pos_cols, rows=pos_rows).classes("w-full").props("dense flat")

            # Row 3: Recent trades
            recent = iran_d.get("trades_recent", [])
            if recent:
                ui.separator().classes("mt-3 mb-2")
                ui.label("Последние сделки").classes("text-subtitle2 text-grey")
                trade_rows = []
                for t in recent[:10]:
                    ts = t.get("timestamp", "")
                    if "T" in str(ts):
                        ts = str(ts)[:16].replace("T", " ")
                    pnl = t.get("pnl", 0)
                    trade_rows.append({
                        "time": ts,
                        "strategy": t.get("strategy", "?"),
                        "side": t.get("side", "?"),
                        "action": t.get("action", "?"),
                        "price": f"{t.get('price', 0) * 100:.0f}c",
                        "size": _usd(t.get("size_usd", 0)),
                        "pnl": _pnl(pnl) if pnl != 0 else "—",
                    })
                trade_cols = [
                    {"name": "time", "label": "Время", "field": "time", "align": "left"},
                    {"name": "strategy", "label": "Стр.", "field": "strategy", "align": "center"},
                    {"name": "side", "label": "Side", "field": "side", "align": "center"},
                    {"name": "action", "label": "Действие", "field": "action", "align": "center"},
                    {"name": "price", "label": "Цена", "field": "price", "align": "center"},
                    {"name": "size", "label": "Размер", "field": "size", "align": "right"},
                    {"name": "pnl", "label": "P&L", "field": "pnl", "align": "right"},
                ]
                ui.table(columns=trade_cols, rows=trade_rows).classes("w-full").props("dense flat")

    # ──────────────────────────────────────────
    #  Render: Multi-Signal Copy-Bot
    # ──────────────────────────────────────────
    def render_multi_signal_bot(ms=None):
        multi_signal_container.clear()
        if ms is None:
            ms = data_reader.read_multi_signal_bot()
        if not ms:
            with multi_signal_container:
                ui.label("Нет данных — бот не запущен").classes("text-grey")
            return

        with multi_signal_container:
            # Mode badge
            mode = ms.get("mode", "test")
            mode_color = "red" if mode == "live" else "orange"
            mode_label = "LIVE" if mode == "live" else "TEST"
            ui.badge(mode_label, color=mode_color).classes("text-bold q-mb-sm")

            # Row 1: Key metrics
            with ui.row().classes("w-full gap-6 flex-wrap items-end"):
                _mini_metric("Баланс", _usd(ms.get("current_balance", 0)))
                _mini_metric("Открыто", str(ms.get("open", 0)))
                _mini_metric("Вложено", _usd(ms.get("invested", 0)))
                pnl_val = ms.get("total_pnl", 0)
                with ui.column().classes("min-w-20 items-center"):
                    color = "text-green" if pnl_val >= 0 else "text-red"
                    ui.label(_pnl(pnl_val)).classes(f"text-h6 text-bold {color}")
                    ui.label("P&L").classes("text-caption text-grey")
                wins = ms.get("wins", 0)
                losses = ms.get("losses", 0)
                total_resolved = wins + losses
                _mini_metric("Сделок", f"{wins}W / {losses}L")
                _mini_metric("Win Rate", _pct(wins, total_resolved))

            # Row 2: Open positions table
            open_list = ms.get("positions", [])
            if open_list:
                ui.separator().classes("mt-3 mb-2")
                ui.label("Открытые позиции").classes("text-subtitle2 text-grey")
                pos_rows = []
                for p in open_list:
                    ts = p.get("timestamp", "")
                    if "T" in str(ts):
                        ts = str(ts)[:16].replace("T", " ")
                    player = p.get("signal_player", "—")
                    pos_rows.append({
                        "player": player,
                        "side": p.get("side", "YES"),
                        "entry": f"{p.get('entry_price', 0) * 100:.0f}c",
                        "size": _usd(p.get("cost_usd", 0)),
                        "shares": f"{p.get('size_shares', 0):.0f}",
                        "time": ts,
                        "title": p.get("title", "")[:50],
                    })
                pos_cols = [
                    {"name": "player", "label": "Игрок", "field": "player", "align": "left"},
                    {"name": "side", "label": "Side", "field": "side", "align": "center"},
                    {"name": "entry", "label": "Вход", "field": "entry", "align": "center"},
                    {"name": "size", "label": "Размер", "field": "size", "align": "right"},
                    {"name": "shares", "label": "Шеры", "field": "shares", "align": "right"},
                    {"name": "time", "label": "Время", "field": "time", "align": "left"},
                    {"name": "title", "label": "Рынок", "field": "title", "align": "left"},
                ]
                ui.table(columns=pos_cols, rows=pos_rows).classes("w-full").props("dense flat")
            else:
                ui.separator().classes("mt-3 mb-1")
                ui.label("Нет открытых позиций").classes("text-grey text-caption")

    def render_scanner(sc=None):
        scanner_container.clear()
        if sc is None:
            sc = data_reader.read_scanner_stats()
        if not sc:
            with scanner_container:
                ui.label("Нет данных").classes("text-grey")
            return
        with scanner_container:
            _mini_metric("Рынков", str(sc["total_markets"]))
            _mini_metric("Resolved", str(sc["resolved"]))
            _mini_metric("Win Rate", f"{sc['win_rate']:.1f}%")
            _mini_metric("Lost", str(sc["lost"]))
            _mini_metric("Сканов", str(sc["scans"]))

    # ──────────────────────────────────────────
    #  Render: Oil Calibration
    # ──────────────────────────────────────────
    def render_calibration(cal=None):
        calibration_container.clear()
        if cal is None:
            cal = data_reader.read_oil_calibration()
        if not cal:
            with calibration_container:
                ui.label("Нет данных калибровки. Запустите Oil Calibrator.").classes("text-grey")
            return

        # Parse calibrated_at
        cal_at = cal.get("calibrated_at", "")
        try:
            from datetime import datetime as _dt
            dt = _dt.fromisoformat(cal_at)
            time_str = dt.strftime("%d.%m %H:%M")
        except Exception:
            time_str = cal_at[:16] if cal_at else "—"

        # Days remaining
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        now = _dt.now(_tz.utc)
        deadline = _dt(2026, 3, 31, tzinfo=_tz.utc)
        current = now.date()
        end = deadline.date()
        days_left = 0
        while current <= end:
            if current.weekday() < 5:
                days_left += 1
            current += _td(days=1)

        corr = cal.get("correlation", {})
        chart = cal.get("chart", [])
        days_data = cal.get("days", {})
        current_day = days_data.get(str(days_left), {})
        cur_pm = current_day.get("profit_mult", 0)

        with calibration_container:
            # ── Row 1: Correlation metrics ──
            with ui.row().classes("w-full gap-6 flex-wrap items-end"):
                _mini_metric("Дней до дедлайна", str(days_left))

                for label, key in [("24ч", "24h"), ("3 дня", "3d"), ("7 дней", "7d"), ("Всё время", "all")]:
                    r = corr.get(key)
                    if r is not None:
                        if abs(r) >= 0.5:
                            color = "text-green"
                        elif abs(r) >= 0.2:
                            color = "text-orange"
                        else:
                            color = "text-red"
                        with ui.column().classes("min-w-20 items-center"):
                            ui.label(f"{r:.2f}").classes(f"text-h6 text-bold {color}")
                            ui.label(f"Корр. {label}").classes("text-caption text-grey")
                    else:
                        _mini_metric(f"Корр. {label}", "—")

                # WTI last price from chart
                wti_last = None
                if chart:
                    for pt in reversed(chart):
                        if pt.get("wti") is not None:
                            wti_last = pt["wti"]
                            break
                _mini_metric("WTI сейчас", f"${wti_last:.2f}" if wti_last else "—")

                _mini_metric("Обновлено", time_str)

            # ── Row 2: Chart WTI + YES $100 + YES $105 ──
            if chart:
                ui.separator().classes("mt-2 mb-1")

                from datetime import datetime as _dtc, timezone as _tzc
                import plotly.graph_objects as go

                wti_t, wti_v = [], []
                y100_t, y100_v = [], []
                y105_t, y105_v = [], []
                for pt in chart:
                    dt = _dtc.fromtimestamp(pt["t"], tz=_tzc.utc)
                    if pt.get("wti") is not None:
                        wti_t.append(dt)
                        wti_v.append(pt["wti"])
                    if pt.get("yes100") is not None:
                        y100_t.append(dt)
                        y100_v.append(pt["yes100"] * 100)
                    if pt.get("yes105") is not None:
                        y105_t.append(dt)
                        y105_v.append(pt["yes105"] * 100)

                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=wti_t, y=wti_v, name="WTI ($)",
                    line=dict(color="#ffa726", width=2),
                    fill="tozeroy",
                    fillcolor="rgba(255,167,38,0.15)",
                    yaxis="y1",
                ))
                fig.add_trace(go.Scatter(
                    x=y100_t, y=y100_v, name="YES $100 (%)",
                    line=dict(color="#42a5f5", width=2),
                    yaxis="y2",
                ))
                fig.add_trace(go.Scatter(
                    x=y105_t, y=y105_v, name="YES $105 (%)",
                    line=dict(color="#ef5350", width=1.5, dash="dash"),
                    yaxis="y2",
                ))
                fig.update_layout(
                    height=400,
                    margin=dict(l=60, r=60, t=10, b=40),
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#ccc"),
                    legend=dict(orientation="h", y=1.02, x=0.5, xanchor="center"),
                    xaxis=dict(gridcolor="#333", showgrid=True),
                    yaxis=dict(
                        title="WTI ($)", side="left",
                        gridcolor="#333", showgrid=True,
                    ),
                    yaxis2=dict(
                        title="YES (%)", side="right",
                        overlaying="y", range=[0, 100],
                        showgrid=False,
                    ),
                    hovermode="x unified",
                )
                ui.plotly(fig).classes("w-full")

            # ── Row 3: Theta table (collapsible) ──
            with ui.expansion("Theta-множители по дням", icon="table_chart").classes("w-full mt-2"):
                table_rows = []
                sorted_days = sorted(days_data.keys(), key=int, reverse=True)
                for d in sorted_days:
                    day_num = int(d)
                    if day_num < 1 or day_num > 25:
                        continue
                    entry = days_data[d]
                    pm = entry.get("profit_mult", 0)
                    prm = entry.get("price_mult", 0)
                    p90 = entry.get("p90_gain")
                    avg_yes = entry.get("avg_yes")
                    marker = " \u25c0" if day_num == days_left else ""
                    table_rows.append({
                        "day": f"{day_num}{marker}",
                        "profit": f"{pm:.0%}",
                        "price": f"{prm:.0%}",
                        "p90": f"{p90:+.1%}" if p90 is not None else "\u2014",
                        "yes": f"{avg_yes:.1%}" if avg_yes is not None else "\u2014",
                        "_is_current": day_num == days_left,
                    })

                cols = [
                    {"name": "day", "label": "День", "field": "day", "align": "center"},
                    {"name": "profit", "label": "Profit \u00d7", "field": "profit", "align": "center"},
                    {"name": "price", "label": "Price \u00d7", "field": "price", "align": "center"},
                    {"name": "p90", "label": "P90 gain", "field": "p90", "align": "center"},
                    {"name": "yes", "label": "Avg YES", "field": "yes", "align": "center"},
                ]

                t = ui.table(columns=cols, rows=table_rows).classes("w-full").props("dense flat")
                t.add_slot("body-cell-day", """
                    <q-td :props="props">
                        <span :class="props.row._is_current ? 'text-bold text-amber' : ''">
                            {{ props.row.day }}
                        </span>
                    </q-td>
                """)
                for col in ["profit", "price", "p90", "yes"]:
                    t.add_slot(f"body-cell-{col}", f"""
                        <q-td :props="props">
                            <span :class="props.row._is_current ? 'text-bold text-amber' : ''">
                                {{{{ props.row.{col} }}}}
                            </span>
                        </q-td>
                    """)

    # ──────────────────────────────────────────
    #  Render: Smart Tuner
    # ──────────────────────────────────────────
    def render_tuner(report=None):
        tuner_container.clear()
        if report is None:
            report = data_reader.read_tuner_report()
        if not report:
            with tuner_container:
                ui.label("Нет данных Smart Tuner. Запустите Oil Calibrator.").classes("text-grey")
            return

        regime = report.get("regime", {})
        volatility = report.get("volatility", {})
        sensitivity = report.get("sensitivity", {})
        theta = report.get("theta", {})
        warnings = report.get("warnings", [])
        recs = report.get("recommendations", [])
        auto_applied = report.get("auto_applied", {})
        gen_at = report.get("generated_at", "")

        # Parse time
        try:
            from datetime import datetime as _dt2
            dt2 = _dt2.fromisoformat(gen_at)
            tuner_time = dt2.strftime("%d.%m %H:%M")
        except Exception:
            tuner_time = gen_at[:16] if gen_at else "—"

        # Regime badge colors
        regime_colors = {
            "strong": "positive",
            "weak": "warning",
            "decorrelated": "orange",
            "inverted": "negative",
        }
        regime_cls = regime.get("classification", "?")
        regime_labels = {
            "strong": "СИЛЬНАЯ СВЯЗЬ",
            "weak": "СЛАБАЯ СВЯЗЬ",
            "decorrelated": "ДЕКОРРЕЛЯЦИЯ",
            "inverted": "ИНВЕРСИЯ",
        }

        with tuner_container:
            # ── Row 1: regime badge + key metrics ──
            with ui.row().classes("w-full gap-4 flex-wrap items-center"):
                ui.badge(
                    regime_labels.get(regime_cls, regime_cls.upper()),
                    color=regime_colors.get(regime_cls, "grey"),
                ).classes("text-body1 q-pa-sm")

                _mini_metric("Дней", str(report.get("days_remaining", "?")))

                corr_24h = regime.get("correlations", {}).get("24h")
                if corr_24h is not None:
                    color = "text-green" if corr_24h > 0.3 else "text-orange" if corr_24h > -0.1 else "text-red"
                    with ui.column().classes("min-w-20 items-center"):
                        ui.label(f"{corr_24h:.2f}").classes(f"text-h6 text-bold {color}")
                        ui.label("Корр. 24h").classes("text-caption text-grey")

                sens_3d = sensitivity.get("pp_per_dollar_3d")
                if sens_3d is not None:
                    with ui.column().classes("min-w-20 items-center"):
                        ui.label(f"{sens_3d:.2f}").classes("text-h6 text-bold")
                        ui.label("pp/$1 WTI").classes("text-caption text-grey")

                asym = sensitivity.get("asymmetry", {})
                if asym.get("up_slope") and asym.get("down_slope"):
                    with ui.column().classes("min-w-20 items-center"):
                        ratio = abs(asym["up_slope"] / asym["down_slope"]) if asym["down_slope"] != 0 else 0
                        ui.label(f"{ratio:.1f}x").classes("text-h6 text-bold text-purple")
                        ui.label("Асимметрия").classes("text-caption text-grey")

                vol_cls = volatility.get("classification", "?")
                vol_labels = {"high": "Высокая", "normal": "Нормальная", "low": "Низкая"}
                _mini_metric("Волатильность", vol_labels.get(vol_cls, vol_cls))

                _mini_metric("Обновлено", tuner_time)

            # ── Row 2: Warnings ──
            if warnings:
                ui.separator().classes("mt-2 mb-1")
                for w in warnings:
                    sev = w.get("severity", "low")
                    icon_map = {"high": "error", "medium": "warning", "low": "info"}
                    color_map = {"high": "text-red", "medium": "text-orange", "low": "text-blue"}
                    with ui.row().classes("items-center gap-2"):
                        ui.icon(icon_map.get(sev, "info"), color=color_map.get(sev, "grey")[5:])
                        ui.label(w.get("message", "")).classes(f"text-body2 {color_map.get(sev, '')}")

            # ── Row 3: Applied changes ──
            applied_list = auto_applied.get("applied", [])
            if applied_list:
                ui.separator().classes("mt-2 mb-1")
                with ui.row().classes("items-center gap-2"):
                    ui.icon("check_circle", color="green")
                    ui.label(f"Авто-применено {len(applied_list)} изменений в config.py").classes(
                        "text-body2 text-green")

            # ── Row 4: Recommendations table (collapsible) ──
            if recs:
                with ui.expansion("Рекомендации Smart Tuner", icon="analytics").classes("w-full mt-2"):
                    table_rows = []
                    for r in recs:
                        cur = r.get("current", "")
                        rec_val = r.get("recommended", "")
                        conf = r.get("confidence", "?")
                        changed = cur != rec_val

                        # Format values for display
                        cur_str = _format_tuner_value(cur)
                        rec_str = _format_tuner_value(rec_val)
                        conf_icons = {"high": "🟢", "medium": "🟡", "low": "🔴"}

                        table_rows.append({
                            "param": r.get("parameter", ""),
                            "current": cur_str,
                            "recommended": rec_str,
                            "confidence": f"{conf_icons.get(conf, '⚪')} {conf}",
                            "rationale": r.get("rationale", ""),
                            "_changed": changed,
                        })

                    cols = [
                        {"name": "param", "label": "Параметр", "field": "param", "align": "left"},
                        {"name": "current", "label": "Текущее", "field": "current", "align": "center"},
                        {"name": "recommended", "label": "Рекомендация", "field": "recommended", "align": "center"},
                        {"name": "confidence", "label": "Уверенность", "field": "confidence", "align": "center"},
                        {"name": "rationale", "label": "Обоснование", "field": "rationale", "align": "left"},
                    ]

                    t = ui.table(columns=cols, rows=table_rows).classes("w-full").props("dense flat wrap-cells")
                    t.add_slot("body-cell-recommended", """
                        <q-td :props="props">
                            <span :class="props.row._changed ? 'text-bold text-green' : ''">
                                {{ props.row.recommended }}
                            </span>
                        </q-td>
                    """)

    def _format_tuner_value(val) -> str:
        """Format a tuner value for display."""
        if isinstance(val, list):
            parts = []
            for item in val:
                if isinstance(item, (list, tuple)):
                    parts.append("[" + ", ".join(str(round(x, 2)) if isinstance(x, float) else str(x) for x in item) + "]")
                else:
                    parts.append(str(item))
            return " | ".join(parts)
        if isinstance(val, float):
            return f"{val:.2f}" if val < 10 else f"{val:.0f}"
        return str(val)

    # ──────────────────────────────────────────
    #  Render: 98% Sure Bot Stats
    # ──────────────────────────────────────────
    def render_sure_bot(sb=None):
        sure_bot_container.clear()
        if sb is None:
            sb = data_reader.read_sure_bot_stats()
        if not sb:
            with sure_bot_container:
                ui.label("Нет данных").classes("text-grey")
            return
        with sure_bot_container:
            _mini_metric("Ставок", str(sb["total_bets"]))
            _mini_metric("Resolved", str(sb["resolved"]))
            wr_str = f"{sb['win_rate']:.1f}%" if sb["resolved"] > 0 else "—"
            _mini_metric("Win Rate", wr_str)
            pnl_str = f"{'+'if sb['total_pnl']>=0 else ''}${sb['total_pnl']:.2f}"
            _mini_metric("PnL", pnl_str)
            _mini_metric("Открыто", str(sb["open"]))
            _mini_metric("Lost", str(sb["losses"]))
            if sb["avg_redeem_hours"] is not None:
                avg_h = sb["avg_redeem_hours"]
                if avg_h < 1:
                    time_str = f"{avg_h * 60:.0f} мин"
                else:
                    time_str = f"{avg_h:.1f} ч"
                _mini_metric("Ср. до redeem", f"{time_str} ({sb['redeem_count']})")
            else:
                _mini_metric("Ср. до redeem", "—")
            if sb.get("avg_buy_to_end_hours") is not None:
                avg_e = sb["avg_buy_to_end_hours"]
                if avg_e < 1:
                    end_str = f"{avg_e * 60:.0f} мин"
                elif avg_e < 48:
                    end_str = f"{avg_e:.1f} ч"
                else:
                    end_str = f"{avg_e / 24:.1f} дн"
                _mini_metric("Ср. до end_date", f"{end_str} ({sb['buy_to_end_count']})")
            else:
                _mini_metric("Ср. до end_date", "—")

    # ──────────────────────────────────────────
    #  Render: Positions Table
    # ──────────────────────────────────────────
    def render_positions(positions=None):
        positions_container.clear()
        if positions is None:
            positions = data_reader.read_all_positions()

        # Filters
        bf = bot_filter.value
        sf = status_filter.value
        if bf != "Все":
            name_to_id = {bcfg["name"]: bid for bid, bcfg in BOTS.items()}
            sel = name_to_id.get(bf, "")
            positions = [p for p in positions if p["bot"] == sel or
                         (p["bot"].startswith("multi_") and bf == "Multi Bot")]
        if sf != "Все":
            positions = [p for p in positions if p["status"] == sf]

        positions.sort(key=lambda p: str(p.get("timestamp", "")), reverse=True)

        rows = []
        for p in positions:
            bot_name = BOTS.get(p["bot"], {}).get("name", p["bot"])
            cp = _prices.get(p["token_id"])
            delta = (cp - p["entry_price"]) if cp is not None else None
            pnl_val = p.get("pnl")

            # Get market info (end_date, url) from cache
            minfo = data_reader.get_market_info(p["token_id"])
            end_date_raw = p.get("end_date") or minfo.get("end_date") or ""
            end_date_str = end_date_raw[:10] if end_date_raw else "—"
            market_url = minfo.get("url") or ""

            rows.append({
                "bot": bot_name,
                "title": (p["title"] or "")[:50],
                "entry": f"{p['entry_price']:.4f}",
                "current": f"{cp:.4f}" if cp is not None else "—",
                "delta": f"{delta:+.4f}" if delta is not None else "—",
                "shares": f"{p['size_shares']:.2f}",
                "cost": _usd(p["cost_usd"]),
                "pnl": _pnl(pnl_val) if pnl_val is not None else "—",
                "status": p["status"],
                "end_date": end_date_str,
                "market_url": market_url,
                # For sell dialog
                "_token_id": p["token_id"],
                "_size": p["size_shares"],
                "_entry": p["entry_price"],
                "_title": p["title"],
                "_order_id": p.get("order_id", ""),
                "_bot_id": p["bot"],
                "neg_risk": "yes" if p.get("neg_risk", False) else "no",
            })

        columns = [
            {"name": "bot", "label": "Бот", "field": "bot", "align": "left", "sortable": True},
            {"name": "title", "label": "Рынок", "field": "title", "align": "left", "sortable": True},
            {"name": "neg_risk", "label": "NegRisk", "field": "neg_risk", "sortable": True},
            {"name": "entry", "label": "Вход", "field": "entry", "sortable": True},
            {"name": "current", "label": "Текущая", "field": "current", "sortable": True},
            {"name": "delta", "label": "Δ", "field": "delta", "sortable": True},
            {"name": "shares", "label": "Шеры", "field": "shares", "sortable": True},
            {"name": "cost", "label": "Стоимость", "field": "cost", "sortable": True},
            {"name": "pnl", "label": "PnL", "field": "pnl", "sortable": True},
            {"name": "end_date", "label": "End Date", "field": "end_date", "sortable": True},
            {"name": "status", "label": "Статус", "field": "status", "sortable": True},
            {"name": "sell", "label": "", "field": "sell"},
        ]

        with positions_container:
            table = ui.table(
                columns=columns, rows=rows, row_key="_token_id",
                pagination={"rowsPerPage": 25},
            ).classes("w-full")

            table.add_slot("body-cell-title", """
                <q-td :props="props">
                    <a v-if="props.row.market_url"
                       :href="props.row.market_url" target="_blank"
                       style="color: #90caf9; text-decoration: none;"
                       @mouseover="$event.target.style.textDecoration='underline'"
                       @mouseleave="$event.target.style.textDecoration='none'">
                        {{ props.row.title }}
                    </a>
                    <span v-else>{{ props.row.title }}</span>
                </q-td>
            """)

            table.add_slot("body-cell-sell", """
                <q-td :props="props">
                    <q-btn v-if="props.row.status === 'open'"
                           dense flat icon="sell" color="orange" size="sm"
                           @click="$parent.$emit('sell', props.row)" />
                </q-td>
            """)
            table.on("sell", lambda e: open_sell_dialog(e.args))

            table.add_slot("body-cell-status", """
                <q-td :props="props">
                    <q-badge :color="props.row.status === 'won' ? 'green' :
                                     props.row.status === 'lost' ? 'red' :
                                     ['selling','sold'].includes(props.row.status) ? 'blue' : 'grey'"
                             :label="props.row.status" />
                </q-td>
            """)

            table.add_slot("body-cell-delta", """
                <q-td :props="props">
                    <span :style="{color: props.row.delta.startsWith('+') ? '#4caf50' :
                                          props.row.delta.startsWith('-') ? '#f44336' : 'inherit'}">
                        {{ props.row.delta }}
                    </span>
                </q-td>
            """)

    # ──────────────────────────────────────────
    #  Render: Strategy Descriptions
    # ──────────────────────────────────────────
    def render_strategies():
        strategy_container.clear()
        with strategy_container:
            # ── 98% Sure Bot ──
            with ui.expansion("98% Sure Bot", icon="casino").classes("w-full"):
                ui.markdown("""
**Стратегия:** Покупка исходов с вероятностью 97.5–99.3% на Polymarket.
При резолюции каждый шер = $1, профит = разница между ценой покупки и $1.

**Вход:** цена 97.5–99.3¢, ставка $5 на рынок

**Слиппедж:** 0.3¢ (при 97.5–98.5¢), 0.2¢ (при 98.5–99¢), 0.1¢ (при 99–99.3¢)

**Фильтры (блокируют вход):**
- Объём < $3,000
- Ликвидность < $500
- Пороговые рынки ("reach $X", "close above", "hit $X")
- Финансовые активы (крипто, акции, индексы) при объёме < $50K
- Coin-flip (first blood, first kill, rampage, first roshan, odd/even)
- Esports: только "кто победит" (O/U, spread, handicap блокируются)
- Погодные рынки (температура ≥ X°F/C)
- Медленные рынки (top, season, most, transit, strait, ships, weekly, monthly)
- end_date: макс. 1 день (политика 2 дня, спорт 3 дня при game_start)
- Отменённые матчи (game_start > 6ч назад и не разрешён)
- Neg_risk: лимит $300 замороженного капитала
- Уже есть открытая позиция на этот рынок

**Выход:** автоматический redeem при резолюции рынка

**Стоп-лосс:** портфель < $300 — бот останавливается

**Банкролл:** $500 | **Сканирование:** каждые 5 мин
""")

            # ── Multi-Signal Copy-Bot ──
            with ui.expansion("Multi-Signal Copy-Bot (Car 🚗 + aenews2 📰 + denizz 🔵)", icon="people").classes("w-full"):
                ui.markdown("""
**Стратегия:** Копирование сделок 3 игроков одновременно: Car, aenews2, denizz.
Сигнал: ЛЮБОЙ из 3 купил $500+ → вход. Блок: один из других двух имеет $500+ на противоположной стороне.

**Тиры ставки (аддитивные, по игроку):**

| Игрок вложил | Car | aenews2 | denizz |
|-------------|-----|---------|--------|
| $500–$2K | +$20 | +$25 | +$20 |
| $2K–$5K | +$10 | +$20 | +$15 |
| $5K–$10K | +$50 | +$30 | +$35 |
| $10K+ | +$80 | +$75 | +$80 |

Макс. ставка: Car $160 | aenews2 $150 | denizz $150

**Ценовой фильтр:** Car/aenews2: 10–82¢ | denizz: 15–82¢

**3-частный вход:** 60% сразу, 25% через 2ч, 15% на дипе (-10%)

**Выход:**
- Цена достигла 99¢ — продать всё
- Стоп-лосс: цена упала на 75% от входа
- Тайм-стоп: 16 дней (если убыток ≤ 12%)
- Игрок продал — продать в течение 2ч

**Банкролл:** $300 | **Опрос:** каждые 30 сек
""")

            # ── Crock95 Copy Bot ──
            with ui.expansion("Crock95 Copy Bot", icon="people").classes("w-full"):
                ui.markdown("""
**Стратегия:** Копирование сделок трейдера Crock95 (политика, война, теннис).
Размер ставки зависит от conviction Crock95 — чем больше он вложил, тем больше ставим.

**Тиры conviction:**

| Crock95 вложил | Наша ставка (% банкролла) | Тир |
|---------------|--------------------------|-----|
| $150–$500 | 7% (~$35) | C |
| $500–$1,500 | 8% (~$40) | B |
| $1,500–$5,000 | 16% (~$80) | A |
| $5,000+ | 30% (~$150) | S |

**Фильтры входа:**
- Crock95 вложил ≥ $150
- Crock95 сделал ≥ 2 покупки
- Только категории: политика, война, теннис
- Макс. 8 открытых позиций, макс. 1 на событие
- Слиппедж ≤ 2¢ от входа Crock95

**3-частный вход:** 60% сразу, 25% через 2ч, 15% на дипе (-10%)

**Выход:**
- Цена достигла 90¢ — продать всё
- Стоп-лосс: цена упала на 80% от входа
- Тайм-стоп: 20 дней без движения (если убыток ≤ 20%)
- Crock95 продал — продать в течение 2ч

**Банкролл:** $500 | **Опрос:** каждые 30 сек
""")

            # ── Oil Swing Bot ──
            with ui.expansion("Oil Swing Bot", icon="oil_barrel").classes("w-full"):
                ui.markdown("""
**Рынок:** Will Crude Oil (CL) hit $100 by end of March?

⚙️ *Параметры автоматически корректируются Smart Tuner каждый час*

**Стратегия YES (нефть НЕ дойдёт до $100):**

| Шаг | Триггер | Сумма | Выход |
|-----|---------|-------|-------|
| 1 | WTI ≤ $92 | $5 | WTI ≥ $96: продать 30% |
| 2 | WTI ≤ $90 | $5 | WTI ≥ $98: продать 50% |
| 3 | WTI ≤ $88 | $15 | WTI ≥ $100: продать 100% |

Также: продать YES при профите ≥ 30%. Макс. цена YES: 63¢.

**Стратегия NO (нефть дойдёт до $100):**

| Шаг | Триггер | Сумма | Цель профита |
|-----|---------|-------|-------------|
| 1 | WTI ≥ $97 | $5 | +45% |
| 2 | WTI ≥ $98 | $5 | +90% |
| 3 | WTI ≥ $99 | $10 | +136% |

Продать NO при WTI < $91. Макс. цена NO: 28¢.

**Стоп-лоссы:**
- WTI < $87 — продать ВСЕ YES (ceasefire)
- WTI > $110 — продать NO
- YES > 3 дней без движения WTI на $3+ — тета-стоп
- Портфель < $200 — стоп бота

**Дедлайн:** 26 марта | **Мёртвая зона:** 12–16ч ET (расчёт CME)

**Theta-скейлинг:** 10+ дн: 100%, 7–9: 80%, 5–6: 60%, 3–4: 30%, 0–2: не входить

**Банкролл:** $300 | **Сканирование:** каждые 60 сек
""")


            # ── Iran Signal Bot ──
            with ui.expansion("Iran Signal Bot", icon="radar").classes("w-full"):
                ui.markdown("""
**Тип:** Мониторинг + сигналы (не торгует напрямую, только алерты и хедж-предложения)

**Что делает:** Мониторит 29 Telegram-каналов, 3 Twitter-аккаунта, Truth Social RSS.
Фильтрует новости по 100+ ключевым словам (5 языков: EN/FA/AR/HE/RU).
Claude Haiku оценивает важность (HIGH/MEDIUM/LOW). Алерты → Telegram.

**Фокус:** Война США-Иран, нефть (WTI), золото (XAU)

**Мониторинг ставок:** Каждые 30 сек проверяет цены на Polymarket.
Спайк ≥ 3 п.п. или ≥ 30% за 5 мин → алерт.

**Стоп-лосс:** ⚠️ при -30% от входа, 🔴 при -50% (без автопродажи)

**Авто-хедж (требует подтверждения):**
При 🔴 сигнале → предложение BUY противоположной стороны (30% от позиции).
Нужно подтвердить в Telegram: `/hedge confirm <id>`. Автоотмена через 15 мин.

**Дайджест:** 09:00 + 18:00 МСК автоматически + `/digest` по запросу

**Стоимость:** ~$0.20-0.40/день (Haiku API + Twitter API)
""")

            # ── Iran Daily Trader ──
            with ui.expansion("Iran Daily Trader", icon="military_tech").classes("w-full"):
                ui.markdown("""
**Тип:** Автоматическая торговля (3 стратегии)

**Рынок:** "Will Iran conduct a military action against Israel on [date]?" — ежедневные подрынки.

**S1 — YES Swing (основная):**
Покупаем YES за 80¢ (60%) + 76¢ (40%) за 12-48ч до события.
Продаём: 87¢ (50%) + 92¢ (50%). Стоп-лосс: 65¢. Time-stop: 13:00 МСК.

**S2A — NO на панике:**
Если YES падает >10% от пика за 6ч — покупаем NO (2 транша).
Цель NO: 60¢. Стоп: -30%. Таймаут: 8ч.

**S2B — NO на перемирии:**
Срабатывает ТОЛЬКО при двойном подтверждении:
1) Новость о перемирии (Telegram + Twitter)
2) 3+ рынка падают >7% за 4ч

**Фильтры безопасности:**
- Domino: не входить если 3+ рынка падают >7%
- Single drop: не входить если какой-то рынок упал >11% за 6ч
- Max price: не покупать YES дороже 83¢

**Банкролл:** $300 | S1: $50/сделка | S2: $25/сделка
""")

            # ── Arb Bot ──
            with ui.expansion("Arb Bot", icon="swap_horiz").classes("w-full"):
                ui.markdown("""
**Тип:** Арбитраж (автоматическая безрисковая прибыль)

**Что делает:** Мониторит neg-risk рынки на Polymarket.
Если сумма цен YES + NO на один исход < $0.98 — покупает обе стороны и делает merge → получает $1.00.

**Два режима поиска:**
- **Sniper (WebSocket):** Реагирует за 1-2 сек, когда кто-то сбросил токен ниже рыночной цены
- **Batch (каждые 30 сек):** Сканирует все рынки как страховка

**Параметры:**

| Параметр | Значение | Зачем |
|----------|----------|-------|
| ARB_THRESHOLD | 0.98 | Минимальный спред для входа (2%) |
| MAX_BET_PER_ARB | $5 | Лимит на одну операцию |
| MAX_TOTAL_EXPOSURE | $25 | Макс. незамерженных позиций |
| MIN_RESERVE | $50 | Оставить для 98% Sure Bot |
| MIN_LIQUIDITY | $10 | Минимальная ликвидность исхода |

**Контракт:** NegRiskAdapter → mergePositions() → $1.00 USDC

**Общий кошелёк** с 98% Sure Bot. Приоритет у Sure Bot.
""")

            # ── Oil Cross v2 (June) ──
            with ui.expansion("Oil Cross v2 (June)", icon="oil_barrel").classes("w-full"):
                ui.markdown("""
**Стратегия:** Одновременная торговля 3 нефтяными рынками (WTI $100, $120, $150).
Дедлайн: 30 июня 2026.

**Рынки:**

| Рынок | Что торгуем | Ставки | Цель |
|-------|-------------|--------|------|
| $100 | YES + NO (swing) | $10/$10/$30 ступени | YES: +21%, NO: +35-104% |
| $120 | Только NO | $16 | +15% |
| $150 | Только NO | $10 | +10% |

**Общий лимит:** $100 открытых позиций

**Вход YES $100:** WTI ≤ $92 / $90 / $88 (ступени)
**Вход NO $100:** WTI ≥ $96 / $98 / $99 (ступени)
**NO $120/$150:** Покупка когда цена NO ≤ порога

**Сканирование:** каждые 60 сек
""")

            # ── 97% Scanner ──
            with ui.expansion("97% Scanner", icon="radar").classes("w-full"):
                ui.markdown("""
**Тип:** Сканер (не торгует, только собирает данные)

**Что делает:** Сканирует все рынки Polymarket каждый час.
Записывает рынки, где любой исход достиг цены ≥ 97¢.
Отслеживает, как часто 97%+ разрешается в пользу (→ $1) или против (→ $0).

**Фильтр:** объём ≥ $10,000

**Цель:** Собрать статистику для оценки стратегии 98% Sure Bot.

**Интервал:** каждые 60 мин
""")

    # ──────────────────────────────────────────
    #  Render: Settings
    # ──────────────────────────────────────────
    def render_settings():
        settings_container.clear()
        with settings_container:
            editable_bots = {bid: bcfg["name"] for bid, bcfg in BOTS.items()
                             if bcfg.get("config_file") or bcfg.get("config_type") == "multi_json"}
            sel = ui.select(editable_bots, label="Выберите бота").classes("w-64")
            panel = ui.column().classes("w-full mt-2")

            def on_select(bot_id):
                panel.clear()
                if not bot_id:
                    return
                params = settings_editor.read_bot_settings(bot_id)
                if not params:
                    with panel:
                        ui.label("Нет настроек").classes("text-grey")
                    return

                inputs = {}
                with panel:
                    for p in params:
                        with ui.card().classes("w-full q-pa-sm q-mb-xs"):
                            with ui.row().classes("items-center gap-3"):
                                ui.label(p["name"]).classes("w-52 text-bold font-mono text-body2")
                                inp = ui.number(
                                    label=p["description"],
                                    value=p["value"],
                                    min=p["min"], max=p["max"],
                                    step=0.001 if p["type"] == "float" else 1,
                                ).classes("w-48")
                                inputs[p["name"]] = (inp, p["value"])
                            if p.get("help"):
                                ui.label(p["help"]).classes(
                                    "text-caption text-grey-6 q-ml-sm"
                                ).style("line-height: 1.3; max-width: 600px")

                    async def save():
                        changes = {n: inp.value for n, (inp, orig) in inputs.items() if inp.value != orig}
                        if not changes:
                            ui.notify("Ничего не изменилось", type="info")
                            return
                        result = settings_editor.save_bot_settings(bot_id, changes)
                        if result["success"]:
                            ui.notify(f"Сохранено: {list(changes.keys())}", type="positive")
                            with ui.dialog() as dlg, ui.card():
                                ui.label("Перезапустить бота?")
                                with ui.row().classes("gap-2"):
                                    ui.button("Да", color="green",
                                              on_click=lambda: (do_stop(bot_id), do_start(bot_id), dlg.close()))
                                    ui.button("Нет", on_click=dlg.close)
                            dlg.open()
                        else:
                            ui.notify(f"Ошибка: {result.get('error')}", type="negative")

                    ui.button("Сохранить", icon="save", color="primary", on_click=save).classes("mt-3")

            sel.on_value_change(lambda e: on_select(e.value))

    # ──────────────────────────────────────────
    #  Actions
    # ──────────────────────────────────────────
    def _is_paused(bot_id: str) -> bool:
        """Check if a bot has a PAUSE file (bets paused, redeem active)."""
        bot_cfg = BOTS.get(bot_id)
        if not bot_cfg:
            return False
        pause_file = bot_cfg["path"] / "PAUSE"
        return pause_file.exists()

    async def do_toggle_pause(bot_id):
        """Toggle pause on/off for a bot."""
        bot_cfg = BOTS.get(bot_id)
        if not bot_cfg:
            return
        pause_file = bot_cfg["path"] / "PAUSE"
        if pause_file.exists():
            pause_file.unlink()
            ui.notify(f"{bot_cfg['name']}: ставки возобновлены", type="positive")
        else:
            pause_file.touch()
            ui.notify(f"{bot_cfg['name']}: ставки на паузе (redeem работает)", type="warning")
        loop = asyncio.get_event_loop()
        statuses = await loop.run_in_executor(None, bot_manager.get_all_statuses)
        render_bot_cards(statuses)

    async def do_start(bot_id):
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: bot_manager.start_bot(bot_id))
        status = result.get("status", "?")
        if status == "error":
            ui.notify(f"{BOTS[bot_id]['name']}: {result.get('message', 'ошибка')}", type="negative")
        else:
            ui.notify(f"{BOTS[bot_id]['name']}: {status}", type="positive")
        statuses = await loop.run_in_executor(None, bot_manager.get_all_statuses)
        render_bot_cards(statuses)

    async def do_stop(bot_id):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: bot_manager.stop_bot(bot_id))
        ui.notify(f"{BOTS[bot_id]['name']}: остановлен", type="info")
        statuses = await loop.run_in_executor(None, bot_manager.get_all_statuses)
        render_bot_cards(statuses)

    async def do_redeem(bot_id):
        """Run one-shot redeem for a bot (check resolved markets and redeem tokens)."""
        global _redeem_running, _redeem_last_result
        bot_cfg = BOTS.get(bot_id)
        if not bot_cfg:
            return
        if _redeem_running:
            ui.notify("Redeem уже работает...", type="warning")
            return
        _redeem_running = True
        _redeem_last_result = ""
        render_bot_cards()
        ui.notify(f"{bot_cfg['name']}: запуск redeem...", type="info")
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, lambda: _run_redeem(bot_cfg))
            _redeem_running = False
            try:
                if result["success"]:
                    summary = _parse_redeem_output(result.get("output", ""))
                    _redeem_last_result = summary
                    ntype = "info" if summary == "Нечего выкупать" else "positive"
                    ui.notify(f"Redeem: {summary}", type=ntype)
                else:
                    _redeem_last_result = "Ошибка"
                    ui.notify(f"Redeem ошибка — {result['error'][:200]}", type="negative")
            except RuntimeError:
                log.info("Redeem result: %s", result)
        except Exception as e:
            _redeem_running = False
            _redeem_last_result = "Ошибка"
            try:
                ui.notify(f"Redeem ошибка: {e}", type="negative")
            except RuntimeError:
                log.error("Redeem error: %s", e)
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, _collect_all_data)
            render_bot_cards(data["statuses"])
            render_portfolio(data["bot_stats"], data["usdc"])
            render_bots_table(data["bot_stats"])
            render_positions(data["positions"])
        except RuntimeError:
            pass

    async def start_all():
        loop = asyncio.get_event_loop()
        def _start_all_sync():
            for bid in BOTS:
                if bot_manager.get_status(bid)["status"] != "running":
                    bot_manager.start_bot(bid)
            return bot_manager.get_all_statuses()
        statuses = await loop.run_in_executor(None, _start_all_sync)
        ui.notify("Все боты запущены", type="positive")
        render_bot_cards(statuses)

    async def stop_all():
        loop = asyncio.get_event_loop()
        def _stop_all_sync():
            for bid in BOTS:
                bot_manager.stop_bot(bid)
            return bot_manager.get_all_statuses()
        statuses = await loop.run_in_executor(None, _stop_all_sync)
        ui.notify("Все боты остановлены", type="info")
        render_bot_cards(statuses)

    async def load_prices():
        global _loading_prices
        if _loading_prices:
            ui.notify("Уже загружается...", type="warning")
            return

        _loading_prices = True
        price_btn.disable()
        portfolio_price_btn.disable()
        price_label.set_text("Загрузка...")
        portfolio_price_label.set_text("Загрузка...")

        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(None, data_reader.read_all_positions)
        token_ids = list({p["token_id"] for p in positions if p["token_id"] and p["status"] == "open"})

        if not token_ids:
            price_label.set_text("Нет открытых позиций")
            portfolio_price_label.set_text("Нет открытых позиций")
            _loading_prices = False
            price_btn.enable()
            portfolio_price_btn.enable()
            return

        prices = await loop.run_in_executor(
            None, lambda: price_fetcher.fetch_prices(token_ids)
        )
        _prices.update(prices)
        loaded = sum(1 for v in prices.values() if v is not None)
        status_text = f"{loaded}/{len(token_ids)} цен загружено"
        price_label.set_text(status_text)
        portfolio_price_label.set_text(status_text)

        _loading_prices = False
        price_btn.enable()
        portfolio_price_btn.enable()
        render_portfolio()
        render_positions()

    def open_sell_dialog(row):
        token_id = row.get("_token_id", "")
        shares = row.get("_size", 0)
        entry = row.get("_entry", 0)
        title = row.get("_title", "")
        order_id = row.get("_order_id", "")
        bot_id = row.get("_bot_id", "")
        current = _prices.get(token_id)

        # Check real on-chain balance and existing sell orders
        real_balance = trade_executor.get_token_balance(token_id)
        sell_shares = real_balance if real_balance >= 0 else shares
        existing_sells = trade_executor.get_open_sell_orders(token_id)

        with ui.dialog() as dlg, ui.card().classes("min-w-96"):
            ui.label("Продажа").classes("text-h6")
            ui.label(title).classes("text-bold")
            ui.separator()
            ui.label(f"Вход: {entry:.4f}")
            if current:
                ui.label(f"Текущая: {current:.4f}")
            ui.label(f"Шеры (positions.json): {shares:.2f}")
            if real_balance >= 0:
                color = "text-green" if real_balance >= shares else "text-orange"
                ui.label(f"Шеры (на кошельке): {real_balance:.2f}").classes(f"text-bold {color}")
                if real_balance == 0:
                    ui.label("На кошельке 0 шеров — продажа невозможна").classes("text-red text-bold")
            else:
                ui.label("Не удалось проверить баланс на кошельке").classes("text-orange")
            if existing_sells:
                ui.label(f"Уже есть {len(existing_sells)} ордер(ов) на продажу — будут отменены").classes("text-orange")

            sell_price = ui.number("Цена", value=current or entry, min=0.01, max=0.99, step=0.01).classes("w-full")
            confirm = ui.checkbox("Подтверждаю продажу")

            async def do_sell():
                if not confirm.value:
                    ui.notify("Подтвердите", type="warning")
                    return
                loop = asyncio.get_event_loop()
                r = await loop.run_in_executor(
                    None, lambda: trade_executor.sell_position(token_id, sell_price.value, sell_shares)
                )
                if r["success"]:
                    # Mark position as "selling" in bot's positions.json
                    if order_id and bot_id:
                        await loop.run_in_executor(
                            None, lambda: data_reader.mark_position_selling(
                                bot_id, order_id, r["order_id"],
                                r["price"], r["shares"],
                            )
                        )
                    ui.notify(f"Ордер на продажу: {r['order_id'][:16]}", type="positive")
                    dlg.close()
                    # Refresh positions table and portfolio
                    data = await loop.run_in_executor(None, _collect_all_data)
                    render_portfolio(data["bot_stats"], data["usdc"])
                    render_bots_table(data["bot_stats"])
                    render_positions(data["positions"])
                else:
                    ui.notify(f"Ошибка: {r['error']}", type="negative")

            with ui.row().classes("gap-2 mt-3"):
                sell_btn = ui.button("Продать", icon="sell", color="orange", on_click=do_sell)
                if real_balance == 0:
                    sell_btn.disable()
                ui.button("Отмена", on_click=dlg.close)
        dlg.open()

    def show_log(bot_id):
        text = bot_manager.get_bot_log(bot_id)
        log_output.set_content(text)

    def _collect_all_data():
        """Collect all data synchronously — runs in a background thread."""
        return {
            "statuses": bot_manager.get_all_statuses(),
            "bot_stats": data_reader.read_bot_stats(),
            "positions": data_reader.read_all_positions(),
            "scanner": data_reader.read_scanner_stats(),
            "sure_bot": data_reader.read_sure_bot_stats(),
            "calibration": data_reader.read_oil_calibration(),
            "tuner": data_reader.read_tuner_report(),
            "iran_signal": data_reader.read_iran_signal_bot(),
            "iran_daily": data_reader.read_iran_daily_trader(),
            "arb_bot": data_reader.read_arb_bot(),
            "multi_signal": data_reader.read_multi_signal_bot(),
            "usdc": price_fetcher.fetch_usdc_balance(),
        }

    async def refresh_all(silent=False):
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _collect_all_data)
        render_bot_cards(data["statuses"])
        render_portfolio(data["bot_stats"], data["usdc"])
        render_bots_table(data["bot_stats"])
        render_calibration(data["calibration"])
        render_tuner(data["tuner"])
        render_scanner(data["scanner"])
        render_sure_bot(data["sure_bot"])
        render_arb_bot(data["arb_bot"])
        render_iran_signal(data["iran_signal"])
        render_iran_daily(data["iran_daily"])
        render_multi_signal_bot(data["multi_signal"])
        render_positions(data["positions"])
        if not silent:
            ui.notify("Обновлено", type="positive")

    async def _filter_changed(_):
        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(None, data_reader.read_all_positions)
        render_positions(positions)

    bot_filter.on_value_change(_filter_changed)
    status_filter.on_value_change(_filter_changed)

    # ── Static sections (no I/O) — render immediately ──
    render_strategies()
    render_settings()

    # ── Data-driven sections — load in background, then render ──
    async def _initial_load():
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _collect_all_data)
        render_bot_cards(data["statuses"])
        render_portfolio(data["bot_stats"], data["usdc"])
        render_bots_table(data["bot_stats"])
        render_calibration(data["calibration"])
        render_tuner(data["tuner"])
        render_scanner(data["scanner"])
        render_sure_bot(data["sure_bot"])
        render_arb_bot(data["arb_bot"])
        render_iran_signal(data["iran_signal"])
        render_iran_daily(data["iran_daily"])
        render_multi_signal_bot(data["multi_signal"])
        render_positions(data["positions"])
        # Load prices after initial render
        await load_prices()

    ui.timer(0.1, _initial_load, once=True)

    # ── Auto-refresh every 30 sec (data collected in background thread) ──
    async def _auto_refresh():
        try:
            await refresh_all(silent=True)
        except RuntimeError:
            pass  # client disconnected, ignore
    ui.timer(30, _auto_refresh)


# ── Helpers ──
def _calc_unrealized() -> float | None:
    positions = data_reader.read_all_positions()
    total = 0
    has_any = False
    for p in positions:
        if p["status"] == "open" and p["token_id"] in _prices:
            cp = _prices[p["token_id"]]
            if cp is not None:
                total += (cp - p["entry_price"]) * p["size_shares"]
                has_any = True
    return total if has_any else None


def _mini_metric(label: str, value: str):
    with ui.column().classes("min-w-20 items-center"):
        ui.label(value).classes("text-h6 text-bold")
        ui.label(label).classes("text-caption text-grey")


def _run_redeem(bot_cfg: dict) -> dict:
    """Run check_and_redeem() from a bot's redeemer module as a subprocess.
    Forces logger to write to stdout so dashboard can capture output.
    """
    import subprocess as _sp
    bot_path = bot_cfg["path"]
    # Configure root logger to stdout BEFORE importing redeemer
    code = (
        "import logging, sys; "
        "logging.basicConfig(level=logging.INFO, "
        "format='%(message)s', "
        "stream=sys.stdout, force=True); "
        "import redeemer; "
        "redeemer.check_and_redeem()"
    )
    try:
        proc = _sp.run(
            ["py", "-3.12", "-X", "utf8", "-c", code],
            cwd=str(bot_path),
            capture_output=True, text=True, timeout=300,
        )
        # Combine stdout + stderr because some libs write to stderr
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            return {"success": True, "output": combined}
        else:
            return {"success": False, "error": (proc.stderr or proc.stdout or "unknown")[-500:]}
    except _sp.TimeoutExpired:
        return {"success": False, "error": "timeout (300s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def _parse_redeem_output(output: str) -> str:
    """Parse redeem subprocess output into a short summary."""
    if not output.strip():
        return "Нечего выкупать"
    import re
    # Count all WON/LOST markers (any sibling/already-redeemed/no-tokens variant)
    total_won = len(re.findall(r"\[REDEEM\] WON", output))
    total_lost = len(re.findall(r"\[REDEEM\] LOST", output))
    # Also count older bot's markers
    total_lost += output.count("No tokens for")
    # Parse profit/loss amounts
    profit = sum(float(m) for m in re.findall(r'\+\$(\d+\.\d+)', output))
    loss = sum(float(m) for m in re.findall(r'-\$(\d+\.\d+)', output))
    parts = []
    if total_won:
        parts.append(f"WIN {total_won} (+${profit:.2f})")
    if total_lost:
        parts.append(f"LOST {total_lost} (-${loss:.2f})")
    # Also catch summary line if present
    summary_match = re.search(r"Redeem summary: (\d+) redeemed, (\d+) already-resolved, (\d+) skipped", output)
    if summary_match and not parts:
        r, a, s = summary_match.groups()
        if int(r) + int(a) > 0:
            parts.append(f"обработано {int(r)+int(a)}")
    if not parts:
        return "Нечего выкупать"
    return " | ".join(parts)


# ── Run ──
if __name__ in {"__main__", "__mp_main__"}:
    data_reader.warm_cache_background()
    ui.run(
        title="DASHBOARD",
        host="127.0.0.1",
        port=8083,
        reload=False,
        show=False,             # don't auto-open browser (prevents exit when no display)
        reconnect_timeout=60,   # client has 60 sec to reconnect
    )
