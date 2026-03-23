from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from noesis_agent.logging.logger import get_logger
from noesis_agent.orchestration.strategy_catalog import StrategyCatalog

_logger = get_logger("orchestration.batch")


@dataclass
class BatchResult:
    period: str
    strategy_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.strategy_results) + len(self.errors)

    @property
    def succeeded(self) -> int:
        return len(self.strategy_results)

    @property
    def failed(self) -> int:
        return len(self.errors)


class SupportsRunFullCycle(Protocol):
    async def run_full_cycle(self, strategy_id: str, period: str) -> dict[str, Any]: ...


class MonthlyBatchCoordinator:
    def __init__(self, catalog: StrategyCatalog, orchestrator: SupportsRunFullCycle) -> None:
        self._catalog = catalog
        self._orchestrator = orchestrator

    async def run(self, period: str) -> BatchResult:
        strategies = self._catalog.list_active()
        _logger.info(f"Starting monthly batch for {period}: {len(strategies)} active strategies")
        result = BatchResult(period=period)

        for spec in strategies:
            _logger.info(f"Running cycle for {spec.strategy_id}")
            try:
                cycle_result = await self._orchestrator.run_full_cycle(spec.strategy_id, period)
                result.strategy_results[spec.strategy_id] = cycle_result
                _logger.info(f"Completed {spec.strategy_id}: {cycle_result.get('final_status', 'unknown')}")
            except Exception as exc:
                result.errors[spec.strategy_id] = f"{type(exc).__name__}: {exc}"
                _logger.error(f"Failed {spec.strategy_id}: {exc}")

        _logger.info(f"Batch complete: {result.succeeded}/{result.total} succeeded")
        return result
