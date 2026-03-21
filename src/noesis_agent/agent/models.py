# pyright: reportAny=false

from __future__ import annotations

from typing import Any

from pydantic_ai import Agent

from noesis_agent.core.config import AgentRoleConfig


class ModelRouter:
    def __init__(self, agent_roles: dict[str, AgentRoleConfig]):
        self._roles = agent_roles

    def get_model(self, role: str) -> str:
        config = self._roles.get(role)
        if config is None:
            raise ValueError(f"Unknown agent role: {role}")
        return config.model

    def get_fallback_model(self, role: str) -> str | None:
        config = self._roles.get(role)
        return config.fallback if config else None

    def list_roles(self) -> list[str]:
        return list(self._roles.keys())

    def get_role_config(self, role: str) -> AgentRoleConfig:
        config = self._roles.get(role)
        if config is None:
            raise ValueError(f"Unknown agent role: {role}")
        return config

    def create_agent(
        self,
        role: str,
        *,
        output_type: type | None = None,
        tools: list[Any] | None = None,
        deps_type: type | None = None,
    ) -> Agent[Any, Any]:
        config = self.get_role_config(role)
        model: str | object

        if config.base_url:
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            provider = OpenAIProvider(
                base_url=config.base_url,
                api_key=config.resolve_api_key(),
            )
            model = OpenAIChatModel(config.model, provider=provider)
        else:
            model = config.model

        if config.fallback:
            from pydantic_ai.models.fallback import FallbackModel

            model = FallbackModel(model, config.fallback)

        kwargs: dict[str, Any] = {}
        if output_type is not None:
            kwargs["output_type"] = output_type
        if deps_type is not None:
            kwargs["deps_type"] = deps_type

        return Agent(
            model,
            instructions=config.system_prompt or None,
            tools=tools or [],
            **kwargs,
        )
