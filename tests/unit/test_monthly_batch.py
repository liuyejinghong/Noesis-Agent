from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from noesis_agent.orchestration.monthly_batch import BatchResult, MonthlyBatchCoordinator
from noesis_agent.orchestration.strategy_catalog import StrategyCatalog


def write_strategy_file(path: Path, content: str) -> Path:
    _ = path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def test_run_calls_orchestrator_for_each_active_strategy(tmp_path: Path) -> None:
    strategies_dir = tmp_path / "config" / "strategies"
    strategies_dir.mkdir(parents=True)
    _ = write_strategy_file(strategies_dir / "btc.toml", 'strategy_id = "btc_breakout"')
    _ = write_strategy_file(strategies_dir / "eth.toml", 'strategy_id = "eth_reversion"')
    calls: list[tuple[str, str]] = []

    class FakeOrchestrator:
        async def run_full_cycle(self, strategy_id: str, period: str) -> dict[str, Any]:
            calls.append((strategy_id, period))
            return {"final_status": "approved"}

    coordinator = MonthlyBatchCoordinator(StrategyCatalog(strategies_dir), FakeOrchestrator())

    result = asyncio.run(coordinator.run("2026-03"))

    assert calls == [("btc_breakout", "2026-03"), ("eth_reversion", "2026-03")]
    assert result.strategy_results == {
        "btc_breakout": {"final_status": "approved"},
        "eth_reversion": {"final_status": "approved"},
    }
    assert result.errors == {}


def test_run_collects_errors_for_failed_strategies(tmp_path: Path) -> None:
    strategies_dir = tmp_path / "config" / "strategies"
    strategies_dir.mkdir(parents=True)
    _ = write_strategy_file(strategies_dir / "btc.toml", 'strategy_id = "btc_breakout"')
    _ = write_strategy_file(strategies_dir / "eth.toml", 'strategy_id = "eth_reversion"')

    class FakeOrchestrator:
        async def run_full_cycle(self, strategy_id: str, period: str) -> dict[str, Any]:
            if strategy_id == "eth_reversion":
                raise RuntimeError(f"boom for {period}")
            return {"final_status": "approved"}

    coordinator = MonthlyBatchCoordinator(StrategyCatalog(strategies_dir), FakeOrchestrator())

    result = asyncio.run(coordinator.run("2026-03"))

    assert result.strategy_results == {"btc_breakout": {"final_status": "approved"}}
    assert result.errors == {"eth_reversion": "RuntimeError: boom for 2026-03"}


def test_batch_result_properties_report_counts() -> None:
    result = BatchResult(
        period="2026-03",
        strategy_results={"btc_breakout": {"final_status": "approved"}},
        errors={"eth_reversion": "RuntimeError: boom"},
    )

    assert result.total == 2
    assert result.succeeded == 1
    assert result.failed == 1
