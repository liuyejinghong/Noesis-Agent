from __future__ import annotations

from pathlib import Path

from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.models import ModelRouter
from noesis_agent.agent.roles.proposer import ProposerDeps
from noesis_agent.agent.roles.types import Proposal, ProposalStatus
from noesis_agent.agent.skills.registry import SkillRegistry
from noesis_agent.core.config import AgentRoleConfig


def make_router() -> ModelRouter:
    return ModelRouter({"proposer": AgentRoleConfig(model="test")})


def make_deps() -> ProposerDeps:
    return ProposerDeps(memory_store=MemoryStore(":memory:"), skill_registry=SkillRegistry())


def write_prompt_files(base_dir: Path, *, role: str, content: str) -> Path:
    role_dir = base_dir / role
    role_dir.mkdir(parents=True)
    (role_dir / "meta.toml").write_text(
        'active_version = "v1"\n\n[[versions]]\nversion = "v1"\ndate = "2026-03-23"\nchangelog = "initial"\n',
        encoding="utf-8",
    )
    (role_dir / "v1.md").write_text(content + "\n", encoding="utf-8")
    return role_dir


def test_create_proposer_agent_returns_agent() -> None:
    from noesis_agent.agent.roles.proposer import create_proposer_agent

    agent = create_proposer_agent(make_router())

    assert isinstance(agent, Agent)


def test_create_proposer_agent_registers_expected_tools() -> None:
    from noesis_agent.agent.roles.proposer import create_proposer_agent

    agent = create_proposer_agent(make_router())
    test_model = TestModel()

    with agent.override(model=test_model):
        _ = agent.run_sync("列出改进提案工具", deps=make_deps())

    assert test_model.last_model_request_parameters is not None
    assert {tool.name for tool in test_model.last_model_request_parameters.function_tools} == {
        "query_failure_memory",
        "read_strategy_config",
    }


def test_proposer_agent_run_sync_with_test_model_returns_proposal() -> None:
    from noesis_agent.agent.roles.proposer import create_proposer_agent

    agent = create_proposer_agent(make_router())

    with agent.override(model=TestModel()):
        result = agent.run_sync("根据分析报告提出一个改进提案", deps=make_deps())

    assert isinstance(result.output, Proposal)


def test_proposer_agent_output_uses_proposal_defaults() -> None:
    from noesis_agent.agent.roles.proposer import create_proposer_agent

    agent = create_proposer_agent(make_router())

    with agent.override(model=TestModel()):
        result = agent.run_sync("生成结构化提案", deps=make_deps())

    output = result.output

    assert output.proposal_id.startswith("prop_")
    assert output.status is ProposalStatus.DRAFT
    assert output.parameter_changes == {}
    assert output.trade_management_changes == {}


def test_create_proposer_agent_uses_fallback_instructions_without_prompts_dir() -> None:
    from noesis_agent.agent.roles.proposer import PROPOSER_INSTRUCTIONS, create_proposer_agent

    agent = create_proposer_agent(make_router())

    assert agent._instructions[0]() == PROPOSER_INSTRUCTIONS


def test_create_proposer_agent_loads_instructions_from_prompt_registry(tmp_path: Path) -> None:
    from noesis_agent.agent.roles.proposer import create_proposer_agent

    prompts_dir = tmp_path / "prompts"
    _ = write_prompt_files(prompts_dir, role="proposer", content="external proposer prompt")

    agent = create_proposer_agent(make_router(), prompts_dir=prompts_dir)

    assert agent._instructions[0]() == "external proposer prompt"
