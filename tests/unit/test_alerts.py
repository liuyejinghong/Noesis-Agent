from __future__ import annotations

import logging

import pytest

from noesis_agent.logging import alerts
from noesis_agent.logging import logger as logger_module


class FakeChannel:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str, str]] = []

    def send(self, level: str, title: str, detail: str) -> None:
        self.messages.append((level, title, detail))


def test_alert_manager_sends_to_channels() -> None:
    manager = alerts.AlertManager(cooldown_seconds=10.0)
    first = FakeChannel()
    second = FakeChannel()
    manager.register_channel(first)
    manager.register_channel(second)

    sent = manager.alert("ERROR", "Engine stalled", "heartbeat missing")

    assert sent is True
    assert first.messages == [("ERROR", "Engine stalled", "heartbeat missing")]
    assert second.messages == [("ERROR", "Engine stalled", "heartbeat missing")]
    assert manager.channel_count == 2


def test_alert_cooldown_prevents_duplicate() -> None:
    manager = alerts.AlertManager(cooldown_seconds=60.0)
    channel = FakeChannel()
    manager.register_channel(channel)

    assert manager.alert("WARN", "Slow model", "latency high") is True
    assert manager.alert("WARN", "Slow model", "latency high") is False
    assert channel.messages == [("WARN", "Slow model", "latency high")]


def test_alert_after_cooldown_expires(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = alerts.AlertManager(cooldown_seconds=5.0)
    channel = FakeChannel()
    manager.register_channel(channel)
    times = iter([10.0, 12.0, 16.0])
    monkeypatch.setattr("noesis_agent.logging.alerts.time.monotonic", lambda: next(times))

    assert manager.alert("ERROR", "Broker down", "first") is True
    assert manager.alert("ERROR", "Broker down", "second") is False
    assert manager.alert("ERROR", "Broker down", "third") is True
    assert channel.messages == [
        ("ERROR", "Broker down", "first"),
        ("ERROR", "Broker down", "third"),
    ]


def test_log_alert_channel(caplog: pytest.LogCaptureFixture) -> None:
    logger_module.setup_logging(console=False)

    with caplog.at_level(logging.ERROR, logger="noesis.alerts"):
        alerts.LogAlertChannel().send("error", "Disk full", "95 percent used")

    assert len(caplog.records) == 1
    assert caplog.records[0].getMessage() == "[ALERT] Disk full: 95 percent used"


def test_console_alert_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[bool, str]] = []

    class FakeConsole:
        def __init__(self, *, stderr: bool) -> None:
            captured.append((stderr, "__init__"))

        def print(self, message: str) -> None:
            captured.append((True, message))

    monkeypatch.setattr("rich.console.Console", FakeConsole)

    alerts.ConsoleAlertChannel().send("warn", "Gate failed", "drawdown exceeded")

    assert captured[0] == (True, "__init__")
    assert captured[1][1] == "⚠️ [WARN] Gate failed: drawdown exceeded"


def test_channel_error_doesnt_crash() -> None:
    manager = alerts.AlertManager(cooldown_seconds=0.0)

    class BrokenChannel:
        def send(self, level: str, title: str, detail: str) -> None:
            del level, title, detail
            raise RuntimeError("boom")

    channel = FakeChannel()
    manager.register_channel(BrokenChannel())
    manager.register_channel(channel)

    assert manager.alert("CRITICAL", "Order rejected", "risk guard") is True
    assert channel.messages == [("CRITICAL", "Order rejected", "risk guard")]
