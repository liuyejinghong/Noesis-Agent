from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

from noesis_agent.services.scheduler import NoesisScheduler


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_start_and_stop_updates_running_state() -> None:
    scheduler = NoesisScheduler()

    assert scheduler.is_running is False

    run(scheduler.start())

    assert scheduler.is_running is True

    run(scheduler.stop())

    assert scheduler.is_running is False


def test_emit_event_dispatches_sync_handlers() -> None:
    scheduler = NoesisScheduler()
    calls: list[dict[str, Any]] = []

    def handler(payload: dict[str, Any]) -> None:
        calls.append(payload)

    scheduler.on_event("heartbeat", handler)

    run(scheduler.emit_event("heartbeat", {"scope": "minute"}))

    assert calls == [{"scope": "minute"}]


def test_emit_event_dispatches_async_handlers() -> None:
    scheduler = NoesisScheduler()
    calls: list[dict[str, Any]] = []

    async def handler(payload: dict[str, Any]) -> None:
        await asyncio.sleep(0)
        calls.append(payload)

    scheduler.on_event("heartbeat", handler)

    run(scheduler.emit_event("heartbeat", {"scope": "daily"}))

    assert calls == [{"scope": "daily"}]


def test_emit_event_ignores_unknown_event_types() -> None:
    scheduler = NoesisScheduler()

    run(scheduler.emit_event("missing", {"scope": "monthly"}))

    assert scheduler.is_running is False


def test_add_heartbeat_registers_job_on_underlying_scheduler() -> None:
    scheduler = NoesisScheduler()
    mock_scheduler = MagicMock()
    scheduler._scheduler = mock_scheduler

    def heartbeat() -> None:
        return None

    scheduler.add_heartbeat("minute-heartbeat", "interval", heartbeat, minutes=1)

    mock_scheduler.add_job.assert_called_once_with(
        heartbeat,
        "interval",
        id="minute-heartbeat",
        replace_existing=True,
        minutes=1,
    )
