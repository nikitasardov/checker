from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.config import TargetConfig
from app.notifier import TelegramNotifier

logger = logging.getLogger(__name__)


@dataclass
class TargetState:
    consecutive_failures: int = 0
    is_down: bool = False


class AvailabilityChecker:
    def __init__(self, notifier: TelegramNotifier, checker_name: str | None = None) -> None:
        self._notifier = notifier
        self._states: dict[str, TargetState] = {}
        self._checker_name = checker_name

    def set_notifier(self, notifier: TelegramNotifier) -> None:
        self._notifier = notifier

    def set_checker_name(self, checker_name: str | None) -> None:
        self._checker_name = checker_name

    def _message_prefix(self) -> str:
        if not self._checker_name:
            return ""
        return f"[{self._checker_name}] "

    async def check_targets(self, targets: list[TargetConfig]) -> None:
        enabled_targets = [target for target in targets if target.enabled]
        if not enabled_targets:
            logger.warning("No enabled targets found in config")
            return

        for target in enabled_targets:
            await self._check_target(target)

    async def _check_target(self, target: TargetConfig) -> None:
        state_key = f"{target.name}|{target.url}"
        state = self._states.setdefault(state_key, TargetState())
        is_ok, reason = await self._request_status(target)

        if is_ok:
            if state.is_down:
                state.is_down = False
                state.consecutive_failures = 0
                message = f"{self._message_prefix()}[RECOVERED] {target.name} is back online: {target.url}"
                logger.info(message)
                await self._notifier.send(message)
            else:
                state.consecutive_failures = 0
            return

        state.consecutive_failures += 1
        logger.warning(
            "[FAIL] %s (%s): %s (failures %s/%s)",
            target.name,
            target.url,
            reason,
            state.consecutive_failures,
            target.failure_threshold,
        )

        if not state.is_down and state.consecutive_failures >= target.failure_threshold:
            state.is_down = True
            response_info = reason if reason.startswith("status_code=") else f"error={reason}"
            message = (
                f"{self._message_prefix()}[DOWN] {target.name} is unavailable: {target.url}. "
                f"Response: {response_info}. Failures: {state.consecutive_failures}/{target.failure_threshold}"
            )
            logger.error(message)
            await self._notifier.send(message)

    async def _request_status(self, target: TargetConfig) -> tuple[bool, str]:
        try:
            async with httpx.AsyncClient(timeout=target.timeout_seconds, follow_redirects=True) as client:
                response = await client.get(target.url)
            if response.status_code == 200:
                return True, "status_code=200"
            return False, f"status_code={response.status_code}"
        except Exception as exc:
            return False, f"{type(exc).__name__}: {exc}"
