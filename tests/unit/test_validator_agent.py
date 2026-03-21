from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.models import ModelRouter
from noesis_agent.agent.roles.validator import ValidatorDeps
from noesis_agent.agent.roles.types import ValidationReport
from noesis_agent.agent.skills.registry import SkillRegistry
from noesis_agent.core.config import AgentRoleConfig


def make_router() -> ModelRouter:
    return ModelRouter({"validator": AgentRoleConfig(model="test")})


def make_deps() -> ValidatorDeps:
    return ValidatorDeps(memory_store=MemoryStore(":memory:"), skill_registry=SkillRegistry())


def test_create_validator_agent_returns_agent() -> None:
    from noesis_agent.agent.roles.validator import create_validator_agent

    agent = create_validator_agent(make_router())

    assert isinstance(agent, Agent)


def test_create_validator_agent_registers_expected_tools() -> None:
    from noesis_agent.agent.roles.validator import create_validator_agent

    agent = create_validator_agent(make_router())
    test_model = TestModel()

    with agent.override(model=test_model):
        _ = agent.run_sync("列出验证工具", deps=make_deps())

    assert test_model.last_model_request_parameters is not None
    assert {tool.name for tool in test_model.last_model_request_parameters.function_tools} == {
        "run_backtest_comparison",
        "calculate_walk_forward_decay",
    }


def test_validator_agent_run_sync_with_test_model_returns_validation_report() -> None:
    from noesis_agent.agent.roles.validator import create_validator_agent

    agent = create_validator_agent(make_router())

    with agent.override(model=TestModel()):
        result = agent.run_sync("验证这个策略提案", deps=make_deps())

    assert isinstance(result.output, ValidationReport)


def test_validator_agent_output_contains_verdict() -> None:
    from noesis_agent.agent.roles.validator import create_validator_agent

    agent = create_validator_agent(make_router())

    with agent.override(model=TestModel()):
        result = agent.run_sync("生成结构化验证报告", deps=make_deps())

    output = result.output

    assert output.proposal_id
    assert output.verdict
    assert output.concerns is not None
