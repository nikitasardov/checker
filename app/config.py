from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    chat_id: str


@dataclass(frozen=True)
class GlobalDefaults:
    interval_seconds: int = 60
    timeout_seconds: float = 5.0
    failure_threshold: int = 1


@dataclass(frozen=True)
class TargetConfig:
    name: str
    url: str
    enabled: bool = True
    timeout_seconds: float = 5.0
    failure_threshold: int = 1


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    defaults: GlobalDefaults
    targets: list[TargetConfig]


def _validate_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid URL: {value}")
    return value


def _require_positive_number(name: str, value: int | float) -> int | float:
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value}")
    return value


def load_config(path: str | Path = "config.json") -> AppConfig:
    config_path = Path(path)
    raw = json.loads(config_path.read_text(encoding="utf-8"))

    telegram_raw = raw.get("telegram") or {}
    bot_token = str(telegram_raw.get("bot_token", "")).strip()
    chat_id = str(telegram_raw.get("chat_id", "")).strip()
    if not bot_token or not chat_id:
        raise ValueError("telegram.bot_token and telegram.chat_id are required")
    telegram = TelegramConfig(bot_token=bot_token, chat_id=chat_id)

    defaults_raw = raw.get("global_defaults") or {}
    defaults = GlobalDefaults(
        interval_seconds=int(_require_positive_number("interval_seconds", int(defaults_raw.get("interval_seconds", 60)))),
        timeout_seconds=float(_require_positive_number("timeout_seconds", float(defaults_raw.get("timeout_seconds", 5)))),
        failure_threshold=int(
            _require_positive_number("failure_threshold", int(defaults_raw.get("failure_threshold", 1)))
        ),
    )

    targets_raw = raw.get("targets")
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ValueError("targets must be a non-empty list")

    targets: list[TargetConfig] = []
    for index, item in enumerate(targets_raw):
        if not isinstance(item, dict):
            raise ValueError(f"targets[{index}] must be an object")
        name = str(item.get("name", "")).strip() or f"target-{index + 1}"
        url = _validate_url(str(item.get("url", "")).strip())
        enabled = bool(item.get("enabled", True))

        timeout_seconds = float(item.get("timeout_seconds", defaults.timeout_seconds))
        _require_positive_number(f"targets[{index}].timeout_seconds", timeout_seconds)

        failure_threshold = int(item.get("failure_threshold", defaults.failure_threshold))
        _require_positive_number(f"targets[{index}].failure_threshold", failure_threshold)

        targets.append(
            TargetConfig(
                name=name,
                url=url,
                enabled=enabled,
                timeout_seconds=timeout_seconds,
                failure_threshold=failure_threshold,
            )
        )

    return AppConfig(telegram=telegram, defaults=defaults, targets=targets)
