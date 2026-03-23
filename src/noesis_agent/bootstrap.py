from __future__ import annotations

from pathlib import Path

from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.models import ModelRouter
from noesis_agent.agent.orchestrator import AgentOrchestrator
from noesis_agent.agent.proposal_manager import ProposalManager
from noesis_agent.agent.skills.registry import SkillRegistry
from noesis_agent.core.config import NoesisSettings
from noesis_agent.core.models import AppContext


class AppBootstrap:
    def __init__(self, root_dir: Path | None = None, config_path: Path | None = None) -> None:
        self.root_dir = root_dir or Path.cwd()

        if config_path is None:
            candidate = self.root_dir / "config" / "config.toml"
            config_path = candidate if candidate.exists() else None

        self.settings = NoesisSettings(
            root_dir=self.root_dir,
            config_path=config_path,
        )

        self.app_context = AppContext(
            root_dir=self.root_dir,
            config_dir=self.root_dir / "config",
            data_dir=self.root_dir / "data",
            state_dir=self.root_dir / "state",
            artifacts_dir=self.root_dir / "artifacts",
            logs_dir=self.root_dir / "logs",
        )

        db_path = self.app_context.state_dir / "memory.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.memory = MemoryStore(db_path)

        self.router = ModelRouter(self.settings.agent_roles)
        self.skill_registry = SkillRegistry()
        self.proposal_manager = ProposalManager(self.memory)
        configured_prompts_dir = self.root_dir / "config" / "prompts"
        prompts_dir = configured_prompts_dir if configured_prompts_dir.exists() else None
        self.orchestrator = AgentOrchestrator(
            router=self.router,
            memory=self.memory,
            proposal_manager=self.proposal_manager,
            skill_registry=self.skill_registry,
            prompts_dir=prompts_dir,
        )
