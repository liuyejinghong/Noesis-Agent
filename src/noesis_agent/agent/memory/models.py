from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryRecord:
    memory_type: str
    category: str = ""
    strategy_id: str | None = None
    title: str = ""
    content: str = ""
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "active"
    id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None


@dataclass
class FailureRecord(MemoryRecord):
    def __init__(
        self,
        *,
        strategy_id: str,
        category: str,
        title: str,
        content: str,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            memory_type="failure",
            strategy_id=strategy_id,
            category=category,
            title=title,
            content=content,
            tags=tags or [],
            **kwargs,
        )
