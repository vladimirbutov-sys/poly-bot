"""
monitors/base.py — Базовый класс монитора с auto-restart

Каждый монитор:
- Работает в бесконечном цикле
- При ошибке — логирует, ждёт backoff, рестартится
- Не роняет другие мониторы
"""
import asyncio
import logging

logger = logging.getLogger("monitor")


class BaseMonitor:
    """
    Базовый класс для всех мониторов.
    Подклассы реализуют _run() — основной цикл.
    """

    name: str = "base"
    restart_delay: float = 10.0   # секунд перед рестартом
    max_restart_delay: float = 300.0  # максимальный backoff

    async def run_forever(self):
        """Запуск с auto-restart при падении."""
        delay = self.restart_delay
        while True:
            try:
                logger.info(f"[{self.name}] Starting...")
                await self._run()
            except asyncio.CancelledError:
                logger.info(f"[{self.name}] Cancelled")
                break
            except Exception as e:
                logger.error(f"[{self.name}] Crashed: {e}", exc_info=True)
                logger.info(f"[{self.name}] Restarting in {delay:.0f}s...")
                await asyncio.sleep(delay)
                delay = min(delay * 1.5, self.max_restart_delay)
            else:
                # Нормальный выход (не должен случаться)
                logger.warning(f"[{self.name}] Exited normally, restarting...")
                delay = self.restart_delay
                await asyncio.sleep(delay)

    async def _run(self):
        """Основной цикл. Реализуется в подклассе."""
        raise NotImplementedError
