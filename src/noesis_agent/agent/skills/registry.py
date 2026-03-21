from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from noesis_agent.core.models import AppContext


@dataclass
class SkillResult:
    success: bool
    data: dict[str, Any]
    message: str = ""


@dataclass
class SkillContext:
    app_context: AppContext


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Callable[..., Any]] = {}

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        if name in self._skills:
            raise ValueError(f"Skill already registered: {name}")
        self._skills[name] = fn

    def get(self, name: str) -> Callable[..., Any]:
        fn = self._skills.get(name)
        if fn is None:
            raise KeyError(f"Unknown skill: {name}")
        return fn

    def list_skills(self) -> list[str]:
        return sorted(self._skills.keys())

    def has_skill(self, name: str) -> bool:
        return name in self._skills
