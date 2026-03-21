from __future__ import annotations

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
