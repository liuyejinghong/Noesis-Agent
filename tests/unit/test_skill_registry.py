from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from noesis_agent.agent.skills.registry import SkillContext, SkillRegistry, SkillResult
from noesis_agent.core.models import AppContext


def make_app_context() -> AppContext:
    root = Path("fixtures/noesis")
    return AppContext(
        root_dir=root,
        config_dir=root / "config",
        data_dir=root / "data",
        state_dir=root / "state",
        artifacts_dir=root / "artifacts",
        logs_dir=root / "logs",
    )


def test_register_and_get_returns_callable() -> None:
    registry = SkillRegistry()

    def skill(_: SkillContext, **__: Any) -> SkillResult:
        return SkillResult(success=True, data={})

    registry.register("analyze", skill)

    assert registry.get("analyze") is skill


def test_register_duplicate_raises_value_error() -> None:
    registry = SkillRegistry()

    def skill(_: SkillContext, **__: Any) -> SkillResult:
        return SkillResult(success=True, data={})

    registry.register("analyze", skill)

    with pytest.raises(ValueError, match="Skill already registered: analyze"):
        registry.register("analyze", skill)


def test_get_unknown_raises_key_error() -> None:
    registry = SkillRegistry()

    with pytest.raises(KeyError, match="Unknown skill: missing"):
        registry.get("missing")


def test_list_skills_returns_sorted_names() -> None:
    registry = SkillRegistry()

    registry.register(
        "zeta", lambda context: SkillResult(success=True, data={"root": str(context.app_context.root_dir)})
    )
    registry.register(
        "alpha", lambda context: SkillResult(success=True, data={"root": str(context.app_context.root_dir)})
    )

    assert registry.list_skills() == ["alpha", "zeta"]


def test_has_skill_reports_presence() -> None:
    registry = SkillRegistry()

    registry.register(
        "alpha", lambda context: SkillResult(success=True, data={"root": str(context.app_context.root_dir)})
    )

    assert registry.has_skill("alpha") is True
    assert registry.has_skill("beta") is False


def test_end_to_end_registered_skill_returns_skill_result() -> None:
    registry = SkillRegistry()

    def run_backtest(context: SkillContext, *, strategy_id: str) -> SkillResult:
        return SkillResult(
            success=True,
            data={
                "strategy_id": strategy_id,
                "artifacts_dir": str(context.app_context.artifacts_dir),
            },
            message="Backtest scheduled",
        )

    registry.register("run_backtest", run_backtest)
    context = SkillContext(app_context=make_app_context())

    result = registry.get("run_backtest")(context, strategy_id="mean_reversion")

    assert result == SkillResult(
        success=True,
        data={
            "strategy_id": "mean_reversion",
            "artifacts_dir": "fixtures/noesis/artifacts",
        },
        message="Backtest scheduled",
    )
