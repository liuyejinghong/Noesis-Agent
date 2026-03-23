from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.models import ModelRouter
from noesis_agent.agent.orchestrator import AgentOrchestrator
from noesis_agent.agent.proposal_manager import ProposalManager
from noesis_agent.agent.skills.registry import SkillRegistry
from noesis_agent.core.config import NoesisSettings
from noesis_agent.core.models import AppContext
from noesis_agent.logging.alerts import AlertManager, ConsoleAlertChannel, LogAlertChannel
from noesis_agent.logging.logger import get_logger, setup_logging
from noesis_agent.orchestration.monthly_batch import MonthlyBatchCoordinator
from noesis_agent.orchestration.strategy_catalog import StrategyCatalog
from noesis_agent.services.scheduler import NoesisScheduler

_logger = get_logger("bootstrap")


class AppBootstrap:
    def __init__(self, root_dir: Path | None = None, config_path: Path | None = None) -> None:
        self.root_dir = root_dir or Path.cwd()
        setup_logging(log_dir=self.root_dir / "logs")

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
        self.alert_manager = AlertManager()
        self.alert_manager.register_channel(LogAlertChannel())
        self.alert_manager.register_channel(ConsoleAlertChannel())
        configured_prompts_dir = self.root_dir / "config" / "prompts"
        prompts_dir = configured_prompts_dir if configured_prompts_dir.exists() else None
        self.orchestrator = AgentOrchestrator(
            router=self.router,
            memory=self.memory,
            proposal_manager=self.proposal_manager,
            skill_registry=self.skill_registry,
            prompts_dir=prompts_dir,
        )
        self.strategy_catalog = StrategyCatalog(self.root_dir / "config" / "strategies")
        self.batch_coordinator = MonthlyBatchCoordinator(self.strategy_catalog, self.orchestrator)
        self.scheduler = NoesisScheduler()
        self.scheduler.on_event("heartbeat", self._handle_heartbeat)

    async def _handle_heartbeat(self, payload: dict[str, object]) -> None:
        if payload.get("scope") != "monthly":
            return

        period = self._monthly_period_for(datetime.now(UTC))
        _logger.info(f"Monthly heartbeat triggered batch run for period {period}")
        _ = await self.batch_coordinator.run(period)

    @staticmethod
    def _monthly_period_for(current_time: datetime) -> str:
        previous_month = current_time.replace(day=1) - timedelta(days=1)
        return previous_month.strftime("%Y-%m")
