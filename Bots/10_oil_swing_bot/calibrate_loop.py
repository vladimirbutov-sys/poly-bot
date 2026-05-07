"""Daemon wrapper: runs calibrate() + smart_tuner every hour."""
import time
import sys
from datetime import datetime
from calibrate import calibrate

INTERVAL = 3600  # 1 hour


def run_tuner_cycle():
    """Run Smart Tuner: analyze market, auto-apply config changes, send Telegram."""
    try:
        from smart_tuner import run_tuner, save_report, format_telegram_summary
        from telegram_notify import send as tg_send
    except ImportError as e:
        print(f"[TUNER] Import error: {e}")
        return

    try:
        report = run_tuner()  # analyze + auto-apply to config.py
        save_report(report)

        # Telegram notification if there are warnings or applied changes
        applied = report.get("auto_applied", {}).get("applied", [])
        warnings = report.get("warnings", [])

        if applied or warnings:
            msg = format_telegram_summary(report)
            if applied:
                msg += f"\n\n✅ Авто-применено: {len(applied)} изменений"
                for a in applied[:5]:
                    msg += f"\n  {a['parameter']}: {a['old']} → {a['new']}"
            try:
                tg_send(msg)
            except Exception as e:
                print(f"[TUNER] Telegram error: {e}")

        print(f"[TUNER] Done. Applied: {len(applied)}, Warnings: {len(warnings)}")
    except Exception as e:
        print(f"[TUNER] Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    print(f"[CALIB LOOP] Started at {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"[CALIB LOOP] Interval: {INTERVAL}s ({INTERVAL // 60} min)")
    print(f"[CALIB LOOP] Smart Tuner: enabled (auto-apply)")
    sys.stdout.flush()

    while True:
        try:
            calibrate()
        except Exception as e:
            print(f"[CALIB LOOP] Calibrate error: {e}")

        # Run Smart Tuner after calibration
        run_tuner_cycle()

        sys.stdout.flush()
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
