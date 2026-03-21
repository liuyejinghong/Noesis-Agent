# pyright: reportPrivateUsage=false, reportUnknownMemberType=false, reportAttributeAccessIssue=false

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from noesis_agent.services.scheduler import NoesisScheduler

T = TypeVar("T")


def run(coro: Coroutine[Any, Any, T]) -> T:
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
    calls: list[tuple[object, str, dict[str, object]]] = []

    class FakeScheduler:
        def add_job(self, func: object, trigger: str, **kwargs: object) -> None:
            calls.append((func, trigger, kwargs))

    scheduler._scheduler = FakeScheduler()

    def heartbeat() -> None:
        return None

    scheduler.add_heartbeat("minute-heartbeat", "interval", heartbeat, minutes=1)

    assert calls == [
        (
            heartbeat,
            "interval",
            {"id": "minute-heartbeat", "replace_existing": True, "minutes": 1},
        )
    ]
