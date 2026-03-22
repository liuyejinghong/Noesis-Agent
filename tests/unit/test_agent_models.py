from __future__ import annotations

from typing import cast

import httpx
import pytest
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.openai import OpenAIProvider

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


def test_create_agent_with_base_url_builds_openai_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("AIPAIBOX_CLAUDE_API_KEY", "relay-secret")

    router = ModelRouter(
        {
            "analyst": AgentRoleConfig(
                model="claude-sonnet-4-6",
                base_url="https://api.aipaibox.com/v1",
                api_key_env="AIPAIBOX_CLAUDE_API_KEY",
            )
        }
    )

    agent = router.create_agent("analyst")
    model = cast(OpenAIChatModel, agent.__dict__["_model"])

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "claude-sonnet-4-6"
    assert str(model.client.base_url) == "https://api.aipaibox.com/v1/"
    assert model.client.api_key == "relay-secret"


def test_create_agent_without_base_url_keeps_string_shortcut_behavior() -> None:
    router = ModelRouter({"analyst": AgentRoleConfig(model="test")})

    agent = router.create_agent("analyst")

    assert isinstance(agent.__dict__["_model"], TestModel)


def test_create_agent_with_oauth_auth_type_builds_openai_chat_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeAuthManager:
        def make_provider(self) -> OpenAIProvider:
            return OpenAIProvider(
                base_url="https://chatgpt.com/backend-api/wham",
                api_key="oauth-token",
                http_client=httpx.AsyncClient(trust_env=False),
            )

    monkeypatch.setattr("noesis_agent.agent.models.OpenAIAuthManager", FakeAuthManager)

    router = ModelRouter(
        {
            "analyst": AgentRoleConfig(
                model="gpt-4o",
                auth_type="oauth_openai",
            )
        }
    )

    agent = router.create_agent("analyst")
    model = cast(OpenAIChatModel, agent.__dict__["_model"])

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "gpt-4o"
    assert str(model.client.base_url).rstrip("/") == "https://chatgpt.com/backend-api/wham"
    assert model.client.api_key == "oauth-token"
