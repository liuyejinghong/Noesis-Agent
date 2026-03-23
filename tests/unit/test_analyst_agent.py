# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.models import ModelRouter
from noesis_agent.agent.roles.analyst import AnalystDeps
from noesis_agent.agent.roles.types import AnalysisReport
from noesis_agent.agent.skills.registry import SkillRegistry
from noesis_agent.core.config import AgentRoleConfig


def make_router() -> ModelRouter:
    return ModelRouter({"analyst": AgentRoleConfig(model="test")})


def make_deps() -> AnalystDeps:
    return AnalystDeps(memory_store=MemoryStore(":memory:"), skill_registry=SkillRegistry())


def write_prompt_files(base_dir: Path, *, role: str, content: str) -> Path:
    role_dir = base_dir / role
    role_dir.mkdir(parents=True)
    _ = (role_dir / "meta.toml").write_text(
        'active_version = "v1"\n\n[[versions]]\nversion = "v1"\ndate = "2026-03-23"\nchangelog = "initial"\n',
        encoding="utf-8",
    )
    _ = (role_dir / "v1.md").write_text(content + "\n", encoding="utf-8")
    return role_dir


def instruction_text(agent: Agent[Any, Any]) -> str:
    instructions = cast(list[Callable[[], str]], agent._instructions)
    return instructions[0]()


def test_create_analyst_agent_returns_agent() -> None:
    from noesis_agent.agent.roles.analyst import create_analyst_agent

    agent = create_analyst_agent(make_router())

    assert isinstance(agent, Agent)


def test_create_analyst_agent_registers_expected_tools() -> None:
    from noesis_agent.agent.roles.analyst import create_analyst_agent

    agent = create_analyst_agent(make_router())
    test_model = TestModel()

    with agent.override(model=test_model):
        _ = agent.run_sync("列出可用工具", deps=make_deps())

    assert test_model.last_model_request_parameters is not None
    assert {tool.name for tool in test_model.last_model_request_parameters.function_tools} == {
        "get_trade_records",
        "search_related_analysis",
    }


def test_analyst_agent_run_sync_with_test_model_returns_analysis_report() -> None:
    from noesis_agent.agent.roles.analyst import create_analyst_agent

    agent = create_analyst_agent(make_router())

    with agent.override(model=TestModel()):
        result = agent.run_sync("分析 breakout_v1 在 2026-W12 的表现", deps=make_deps())

    assert isinstance(result.output, AnalysisReport)


def test_analyst_agent_output_contains_required_fields() -> None:
    from noesis_agent.agent.roles.analyst import create_analyst_agent

    agent = create_analyst_agent(make_router())

    with agent.override(model=TestModel()):
        result = agent.run_sync("生成结构化分析报告", deps=make_deps())

    output = result.output

    assert output.period
    assert output.strategy_id
    assert output.market_regime
    assert output.performance.trade_count >= 0
    assert output.strengths is not None
    assert output.weaknesses is not None
    assert output.patterns is not None
    assert output.recommendations is not None


def test_create_analyst_agent_uses_fallback_instructions_without_prompts_dir() -> None:
    from noesis_agent.agent.roles.analyst import ANALYST_INSTRUCTIONS, create_analyst_agent

    agent = create_analyst_agent(make_router())

    assert instruction_text(agent) == ANALYST_INSTRUCTIONS


def test_create_analyst_agent_loads_instructions_from_prompt_registry(tmp_path: Path) -> None:
    from noesis_agent.agent.roles.analyst import create_analyst_agent

    prompts_dir = tmp_path / "prompts"
    _ = write_prompt_files(prompts_dir, role="analyst", content="external analyst prompt")

    agent = create_analyst_agent(make_router(), prompts_dir=prompts_dir)

    assert instruction_text(agent) == "external analyst prompt"
