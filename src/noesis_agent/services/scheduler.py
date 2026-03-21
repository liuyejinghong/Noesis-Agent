# pyright: reportMissingTypeStubs=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportAny=false, reportUnusedImport=false, reportUnusedCallResult=false

from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, cast

from apscheduler.schedulers.asyncio import AsyncIOScheduler

EventHandler = Callable[[dict[str, Any]], Any]


class NoesisScheduler:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._event_handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._running = False

    async def start(self) -> None:
        if self._running:
            return

        self._scheduler = AsyncIOScheduler()
        self.add_heartbeat("heartbeat-minute", "interval", self._emit_heartbeat("minute"), minutes=1)
        self.add_heartbeat("heartbeat-daily", "cron", self._emit_heartbeat("daily"), hour=0, minute=0)
        self.add_heartbeat("heartbeat-monthly", "cron", self._emit_heartbeat("monthly"), day=1, hour=0, minute=0)
        self._scheduler.start()
        self._running = True

    async def stop(self) -> None:
        if self._scheduler is not None:
            try:
                self._scheduler.shutdown(wait=False)
            except RuntimeError:
                pass
            self._scheduler = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def on_event(self, event_type: str, handler: EventHandler) -> None:
        self._event_handlers[event_type].append(handler)

    async def emit_event(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        for handler in self._event_handlers.get(event_type, []):
            result = handler(payload or {})
            if inspect.isawaitable(result):
                await cast(Awaitable[object], result)

    def add_heartbeat(self, name: str, trigger: str, func: Callable[[], Any], **trigger_args: Any) -> None:
        if self._scheduler is not None:
            _ = self._scheduler.add_job(func, trigger, id=name, replace_existing=True, **trigger_args)

    def _emit_heartbeat(self, scope: str) -> Callable[[], Awaitable[None]]:
        async def heartbeat() -> None:
            await self.emit_event("heartbeat", {"scope": scope})

        return heartbeat
