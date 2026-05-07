"""core/signal_logger.py — Логирование сигналов в JSONL"""
import json
import logging
from datetime import datetime, timezone
from core.config import SIGNALS_LOG

logger = logging.getLogger("signal_logger")


def log_signal(evaluation: dict, sent: bool, module: str = ""):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "module": module,
        "sent": sent,
        **{k: v for k, v in evaluation.items() if not k.startswith("_raw")},
        "source": evaluation.get("_source", ""),
    }
    try:
        with open(SIGNALS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"Log write failed: {e}")
