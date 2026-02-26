from __future__ import annotations

import asyncio
import logging
import signal
from glob import glob
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.checker import AvailabilityChecker
from app.config import load_config
from app.notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class DailyLogHandler(TimedRotatingFileHandler):
    def rotation_filename(self, default_name: str) -> str:
        base_path = Path(self.baseFilename)
        default_path = Path(default_name)
        rotated_suffix = default_path.name.replace(f"{base_path.name}.", "", 1)
        return str(base_path.with_name(f"{base_path.stem}-{rotated_suffix}{base_path.suffix}"))

    def getFilesToDelete(self) -> list[str]:
        if self.backupCount <= 0:
            return []
        base_path = Path(self.baseFilename)
        pattern = str(base_path.with_name(f"{base_path.stem}-*{base_path.suffix}"))
        candidates = sorted(glob(pattern))
        if len(candidates) <= self.backupCount:
            return []
        return candidates[: len(candidates) - self.backupCount]


def setup_logging() -> None:
    log_dir = Path("/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = DailyLogHandler(
        log_dir / "site-checker.log",
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8",
    )
    file_handler.suffix = "%Y-%m-%d"
    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_handler.setFormatter(formatter)
    stream_handler.setFormatter(formatter)
    logging.basicConfig(level=logging.INFO, handlers=[stream_handler, file_handler])


async def run_service() -> None:
    config = load_config("config.json")
    notifier = TelegramNotifier(config.telegram)
    checker = AvailabilityChecker(notifier, checker_name=config.checker_name)

    logger.info("Service started. Interval: %s seconds", config.defaults.interval_seconds)

    stop_event = asyncio.Event()

    def _stop_handler() -> None:
        logger.info("Stop signal received. Shutting down...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _stop_handler)

    while not stop_event.is_set():
        try:
            fresh_config = load_config("config.json")
            if fresh_config != config:
                if fresh_config.telegram != config.telegram:
                    checker.set_notifier(TelegramNotifier(fresh_config.telegram))
                    logger.info("Telegram notifier config reloaded")
                if fresh_config.checker_name != config.checker_name:
                    checker.set_checker_name(fresh_config.checker_name)
                    logger.info("Checker name config reloaded")
                config = fresh_config
                logger.info("Config reloaded from config.json")
        except Exception:
            logger.exception("Failed to reload config.json. Using previous valid config.")

        started_at = loop.time()
        await checker.check_targets(config.targets)
        elapsed = loop.time() - started_at
        sleep_for = max(0.0, config.defaults.interval_seconds - elapsed)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_for)
        except TimeoutError:
            pass

    logger.info("Service stopped")


def main() -> None:
    setup_logging()
    try:
        asyncio.run(run_service())
    except Exception:
        logger.exception("Service crashed")
        raise


if __name__ == "__main__":
    main()
