from __future__ import annotations

import logging
import time
from typing import Protocol

from noesis_agent.logging.logger import get_logger

_logger = get_logger("alerts")


class AlertChannel(Protocol):
    def send(self, level: str, title: str, detail: str) -> None: ...


class LogAlertChannel:
    def send(self, level: str, title: str, detail: str) -> None:
        _logger.log(
            getattr(logging, level.upper(), logging.ERROR),
            "[ALERT] %s: %s",
            title,
            detail,
        )


class ConsoleAlertChannel:
    ICONS = {"INFO": "ℹ️", "WARN": "⚠️", "ERROR": "❌", "CRITICAL": "🚨"}

    def send(self, level: str, title: str, detail: str) -> None:
        from rich.console import Console

        label = self.ICONS.get(level.upper(), level.upper())
        Console(stderr=True).print(f"{label} [{level.upper()}] {title}: {detail}")


class AlertManager:
    def __init__(self, cooldown_seconds: float = 300.0) -> None:
        self._channels: list[AlertChannel] = []
        self._cooldowns: dict[str, float] = {}
        self._cooldown_seconds = cooldown_seconds

    def register_channel(self, channel: AlertChannel) -> None:
        self._channels.append(channel)

    def alert(self, level: str, title: str, detail: str = "") -> bool:
        key = f"{level}:{title}"
        now = time.monotonic()
        last = self._cooldowns.get(key, 0.0)
        if now - last < self._cooldown_seconds:
            return False
        self._cooldowns[key] = now
        for channel in self._channels:
            try:
                channel.send(level, title, detail)
            except Exception:
                _logger.exception("alert channel send failed")
        return True

    @property
    def channel_count(self) -> int:
        return len(self._channels)
