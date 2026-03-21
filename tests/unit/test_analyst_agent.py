from __future__ import annotations

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
