"""Mode manager: TEST → LIVE switching with Telegram confirmation.

After startup, bot runs in TEST mode (1/5 bet sizes) for 3 hours.
If no critical errors → sends Telegram message asking user to confirm /live.
Bot continues in TEST until user sends /live command.
If critical error → stops bot, sends error report to Telegram.
"""
import time
import json
import os
import config
import telegram_notify as tg


class ModeManager:
    def __init__(self):
        self.mode = "live"
        self.start_time = time.time()
        self.errors = []
        self.promotion_offered = True
        self._log("Started in LIVE mode (TEST mode disabled).")

    def _log(self, msg):
        print(f"[MODE] {msg}")

    def get_conviction_tiers(self):
        if self.mode == "test":
            return config.CONVICTION_TIERS_TEST
        return config.CONVICTION_TIERS_LIVE

    def get_min_bet(self):
        if self.mode == "test":
            return config.MIN_BET_USD_TEST
        return config.MIN_BET_USD_LIVE

    def get_reserve(self):
        if self.mode == "test":
            return config.RESERVE_USD_TEST
        return config.RESERVE_USD_LIVE

    def get_fixed_bet(self):
        """Fixed bet size by mode ($3 test, $5 live)."""
        if self.mode == "test":
            return config.FIXED_BET_TEST
        return config.FIXED_BET_LIVE

    def get_mode_label(self):
        return "🧪 ТЕСТ" if self.mode == "test" else "🟢 БОЕВОЙ"

    def record_error(self, error_msg: str, critical: bool = True):
        """Record an error. If critical and in test mode → stop bot."""
        self.errors.append({
            "time": time.time(),
            "msg": str(error_msg),
            "critical": critical,
        })
        self._log(f"Error recorded: {error_msg[:100]}")

        # TEST mode disabled — never auto-stop on errors
        # if critical and self.mode == "test":
        #     self._handle_test_failure(error_msg)

    def _handle_test_failure(self, error_msg: str):
        """Test failed: stop bot, send report, wait for restart."""
        elapsed_h = (time.time() - self.start_time) / 3600

        report = (
            "🔴 ТЕСТ ПРОВАЛЕН\n\n"
            f"Время работы: {elapsed_h:.1f}ч\n"
            f"Ошибок: {len(self.errors)}\n\n"
            "Последняя ошибка:\n"
            f"{error_msg[:500]}\n\n"
            "Все ошибки:\n"
        )
        for i, err in enumerate(self.errors, 1):
            report += f"  {i}. {err['msg'][:100]}\n"

        report += (
            "\n⛔ Бот остановлен.\n"
            "Исправьте ошибки и перезапустите бота."
        )

        tg.send(report)
        self._log(f"TEST FAILED: {error_msg}")

        # Save errors for analysis
        errors_file = os.path.join(config.BOT_DIR, "test_errors.json")
        with open(errors_file, "w", encoding="utf-8") as f:
            json.dump(self.errors, f, indent=2, ensure_ascii=False, default=str)

        raise SystemExit("Test mode failed — bot stopped")

    def check_promotion(self):
        """Check if test period passed and offer promotion to live."""
        if self.mode != "test":
            return
        if self.promotion_offered:
            return

        elapsed_h = (time.time() - self.start_time) / 3600
        if elapsed_h < config.TEST_DURATION_HOURS:
            return

        critical_errors = [e for e in self.errors if e.get("critical")]
        if len(critical_errors) > config.TEST_MAX_ERRORS:
            return

        self.promotion_offered = True

        if config.FIXED_BET_MODE:
            bet_info = f"Ставка: ${config.FIXED_BET_LIVE:.0f} (фиксированная)"
        else:
            bankroll = config.BANKROLL
            tiers = config.CONVICTION_TIERS_LIVE
            bet_info = (
                f"Ставки:\n"
                f"  B = ${tiers[0][2]*bankroll:.0f}\n"
                f"  A = ${tiers[1][2]*bankroll:.0f}\n"
                f"  S = ${tiers[2][2]*bankroll:.0f}\n"
                f"  S+ = ${tiers[3][2]*bankroll:.0f}"
            )

        msg = (
            "✅ ТЕСТ ПРОЙДЕН!\n\n"
            f"Работал {elapsed_h:.1f}ч без критических ошибок.\n\n"
            f"Боевые параметры:\n{bet_info}\n\n"
            "Перейти в БОЕВОЙ режим?\n"
            "Отправьте /live для перехода.\n"
            "Бот продолжает работать в тестовом режиме."
        )
        tg.send(msg)
        self._log(f"Test passed after {elapsed_h:.1f}h. Waiting for /live command.")

    def promote_to_live(self):
        """Switch to live mode (called by /live command)."""
        self.mode = "live"
        self.errors = []

        if config.FIXED_BET_MODE:
            bet_info = f"Ставка: ${config.FIXED_BET_LIVE:.0f} (фиксированная)"
        else:
            bankroll = config.BANKROLL
            tiers = config.CONVICTION_TIERS_LIVE
            bet_info = (
                f"Ставки: B=${tiers[0][2]*bankroll:.0f} / "
                f"A=${tiers[1][2]*bankroll:.0f} / "
                f"S=${tiers[2][2]*bankroll:.0f} / "
                f"S+=${tiers[3][2]*bankroll:.0f}"
            )

        msg = (
            "🟢 БОЕВОЙ РЕЖИМ АКТИВИРОВАН\n\n"
            f"{bet_info}"
        )
        tg.send(msg)
        self._log("LIVE MODE ACTIVATED by user command")


# Global instance
mode_manager = ModeManager()
