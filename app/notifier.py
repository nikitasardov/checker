from __future__ import annotations

import logging

import httpx

from app.config import TelegramConfig

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, config: TelegramConfig) -> None:
        self._config = config
        self._url = f"https://api.telegram.org/bot{config.bot_token}/sendMessage"

    async def send(self, message: str) -> bool:
        payload = {"chat_id": self._config.chat_id, "text": message}
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(self._url, json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok", False):
                logger.error("Telegram API returned non-ok response: %s", data)
                return False
            return True
        except Exception:
            logger.exception("Failed to send Telegram message")
            return False
