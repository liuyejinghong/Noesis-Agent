from __future__ import annotations

from typing import cast

import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from noesis_agent.agent.models import ModelRouter
from noesis_agent.core.config import AgentRoleConfig


class SimpleOutput(BaseModel):
    answer: str


def make_router() -> ModelRouter:
    return ModelRouter(
        {
            "researcher": AgentRoleConfig(model="openai:gpt-4.1", fallback="openai:gpt-4o-mini", tools=["search"]),
            "reviewer": AgentRoleConfig(model="anthropic:claude-3-7-sonnet"),
        }
    )


def test_get_model_returns_registered_model_string() -> None:
    router = make_router()

    assert router.get_model("researcher") == "openai:gpt-4.1"


def test_get_fallback_model_returns_value_or_none() -> None:
    router = make_router()

    assert router.get_fallback_model("researcher") == "openai:gpt-4o-mini"
    assert router.get_fallback_model("reviewer") is None


def test_unknown_role_raises_value_error() -> None:
    router = make_router()

    with pytest.raises(ValueError, match="Unknown agent role: executor"):
        _ = router.get_model("executor")


def test_list_roles_returns_all_registered_roles() -> None:
    router = make_router()

    assert router.list_roles() == ["researcher", "reviewer"]


def test_get_role_config_returns_full_agent_role_config() -> None:
    router = make_router()

    config = router.get_role_config("researcher")

    assert isinstance(config, AgentRoleConfig)
    assert config.model == "openai:gpt-4.1"
    assert config.fallback == "openai:gpt-4o-mini"
    assert config.tools == ["search"]


def test_create_agent_returns_pydantic_ai_agent_instance() -> None:
    router = ModelRouter({"analyst": AgentRoleConfig(model="test")})

    agent = router.create_agent("analyst")

    assert isinstance(agent, Agent)


def test_create_agent_with_unknown_role_raises_value_error() -> None:
    router = make_router()

    with pytest.raises(ValueError, match="Unknown agent role: executor"):
        _ = router.create_agent("executor")


def test_create_agent_runs_with_test_model_and_structured_output() -> None:
    router = ModelRouter(
        {
            "analyst": AgentRoleConfig(
                model="test",
                system_prompt="Answer with structured output.",
            )
        }
    )
    agent = router.create_agent("analyst", output_type=SimpleOutput)

    with agent.override(model=TestModel()):
        result = agent.run_sync("Give me an answer.")

    output = cast(SimpleOutput, result.output)

    assert output == SimpleOutput(answer="a")
