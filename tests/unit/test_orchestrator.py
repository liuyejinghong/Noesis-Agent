# pyright: reportUnknownParameterType=false

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import cast

import pytest

from noesis_agent.agent.memory.models import FailureRecord
from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.orchestrator import AgentOrchestrator
from noesis_agent.agent.proposal_manager import ProposalManager
from noesis_agent.agent.roles.types import AnalysisReport, GateResult, Proposal, ProposalStatus, ValidationReport
from noesis_agent.agent.skills.registry import SkillRegistry
from noesis_agent.core.config import AgentRoleConfig


def make_orchestrator(prompts_dir: Path | None = None) -> AgentOrchestrator:
    from noesis_agent.agent.models import ModelRouter

    memory = MemoryStore(":memory:")
    router = ModelRouter(
        {
            "analyst": AgentRoleConfig(model="test"),
            "proposer": AgentRoleConfig(model="test"),
            "validator": AgentRoleConfig(model="test"),
        }
    )
    return AgentOrchestrator(
        router=router,
        memory=memory,
        proposal_manager=ProposalManager(memory),
        skill_registry=SkillRegistry(),
        prompts_dir=prompts_dir,
    )


def test_run_analysis_returns_report_and_stores_it() -> None:
    orchestrator = make_orchestrator()

    report = asyncio.run(orchestrator.run_analysis(strategy_id="breakout_v1", period="2026-W12"))

    assert isinstance(report, AnalysisReport)
    assert report.strategy_id == "breakout_v1"
    assert report.period == "2026-W12"
    assert len(orchestrator.memory.get_reports()) == 1


def test_run_proposal_returns_proposal() -> None:
    orchestrator = make_orchestrator()
    analysis = AnalysisReport.model_validate(
        {
            "period": "2026-W12",
            "strategy_id": "breakout_v1",
            "performance": {
                "total_return_pct": 1.0,
                "max_drawdown_pct": 1.0,
                "win_rate_pct": 1.0,
                "trade_count": 1,
                "sharpe_ratio": 1.0,
            },
        }
    )

    proposal = asyncio.run(orchestrator.run_proposal(analysis, report_id=1))

    assert isinstance(proposal, Proposal)
    assert proposal.strategy_id == "breakout_v1"
    assert proposal.analysis_report_id == 1


def test_run_full_cycle_advances_to_pending_approval_when_gates_pass() -> None:
    orchestrator = make_orchestrator()

    result = asyncio.run(orchestrator.run_full_cycle(strategy_id="breakout_v1", period="2026-W12"))
    gates = cast(list[GateResult], result["gates"])

    assert result["final_status"] is ProposalStatus.PENDING_APPROVAL
    assert len(gates) == 3
    assert all(gate.passed for gate in gates)


def test_run_full_cycle_rejects_when_failure_memory_matches() -> None:
    orchestrator = make_orchestrator()
    _ = orchestrator.memory.store_failure(
        FailureRecord(
            strategy_id="breakout_v1",
            category="parameter",
            title="prior failure",
            content="This parameter change already failed.",
        )
    )

    result = asyncio.run(orchestrator.run_full_cycle(strategy_id="breakout_v1", period="2026-W12"))
    gates = cast(list[GateResult], result["gates"])

    assert result["final_status"] is ProposalStatus.REJECTED
    assert gates[0].passed is False


def test_orchestrator_stores_prompts_dir(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(prompts_dir=tmp_path / "config" / "prompts")

    assert orchestrator.prompts_dir == tmp_path / "config" / "prompts"


def test_run_analysis_traces_agent_call(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = make_orchestrator()
    trace_calls: list[tuple[str, str, str]] = []

    class FakeTrace:
        def __init__(self, agent_name: str, model: str, strategy_id: str) -> None:
            trace_calls.append((agent_name, model, strategy_id))

        def __enter__(self) -> dict[str, int]:
            return {}

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    class FakeResult:
        output = AnalysisReport.model_validate(
            {
                "period": "ignored",
                "strategy_id": "ignored",
                "performance": {
                    "total_return_pct": 1.0,
                    "max_drawdown_pct": 1.0,
                    "win_rate_pct": 1.0,
                    "trade_count": 10,
                },
            }
        )

    class FakeAgent:
        async def run(self, _prompt: str, *, deps: object) -> FakeResult:
            del deps
            return FakeResult()

    def fake_create_analyst_agent(*_args: object, **_kwargs: object) -> FakeAgent:
        return FakeAgent()

    monkeypatch.setattr("noesis_agent.agent.orchestrator.trace_agent_call", FakeTrace)
    monkeypatch.setattr("noesis_agent.agent.orchestrator.create_analyst_agent", fake_create_analyst_agent)

    report = asyncio.run(orchestrator.run_analysis("breakout_v1", "2026-W12"))

    assert report.strategy_id == "breakout_v1"
    assert report.period == "2026-W12"
    assert trace_calls == [("analyst", "test", "breakout_v1")]


def test_run_proposal_traces_agent_call(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = make_orchestrator()
    trace_calls: list[tuple[str, str, str]] = []

    class FakeTrace:
        def __init__(self, agent_name: str, model: str, strategy_id: str) -> None:
            trace_calls.append((agent_name, model, strategy_id))

        def __enter__(self) -> dict[str, int]:
            return {}

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    class FakeResult:
        output = Proposal.model_validate(
            {
                "proposal_id": "prop_1",
                "strategy_id": "ignored",
                "analysis_report_id": 1,
                "change_type": "parameter",
            }
        )

    class FakeAgent:
        async def run(self, _prompt: str, *, deps: object) -> FakeResult:
            del deps
            return FakeResult()

    def fake_create_proposer_agent(*_args: object, **_kwargs: object) -> FakeAgent:
        return FakeAgent()

    monkeypatch.setattr("noesis_agent.agent.orchestrator.trace_agent_call", FakeTrace)
    monkeypatch.setattr("noesis_agent.agent.orchestrator.create_proposer_agent", fake_create_proposer_agent)

    analysis = AnalysisReport.model_validate(
        {
            "period": "2026-W12",
            "strategy_id": "breakout_v1",
            "performance": {
                "total_return_pct": 1.0,
                "max_drawdown_pct": 1.0,
                "win_rate_pct": 1.0,
                "trade_count": 10,
            },
        }
    )

    proposal = asyncio.run(orchestrator.run_proposal(analysis, 1))

    assert proposal.strategy_id == "breakout_v1"
    assert proposal.analysis_report_id == 1
    assert trace_calls == [("proposer", "test", "breakout_v1")]


def test_run_validation_traces_agent_call(monkeypatch: pytest.MonkeyPatch) -> None:
    orchestrator = make_orchestrator()
    trace_calls: list[tuple[str, str, str]] = []

    class FakeTrace:
        def __init__(self, agent_name: str, model: str, strategy_id: str) -> None:
            trace_calls.append((agent_name, model, strategy_id))

        def __enter__(self) -> dict[str, int]:
            return {}

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    class FakeValidationResult:
        output = ValidationReport.model_validate(
            {
                "proposal_id": "prop_1",
                "baseline": {
                    "total_return_pct": 1.0,
                    "max_drawdown_pct": 1.0,
                    "win_rate_pct": 1.0,
                    "trade_count": 10,
                },
                "proposed": {
                    "total_return_pct": 2.0,
                    "max_drawdown_pct": 1.0,
                    "win_rate_pct": 1.0,
                    "trade_count": 10,
                },
            }
        )

    class FakeAgent:
        async def run(self, _prompt: str, *, deps: object) -> FakeValidationResult:
            del deps
            return FakeValidationResult()

    def fake_create_validator_agent(*_args: object, **_kwargs: object) -> FakeAgent:
        return FakeAgent()

    monkeypatch.setattr("noesis_agent.agent.orchestrator.trace_agent_call", FakeTrace)
    monkeypatch.setattr("noesis_agent.agent.orchestrator.create_validator_agent", fake_create_validator_agent)

    proposal = Proposal.model_validate(
        {
            "proposal_id": "prop_1",
            "strategy_id": "breakout_v1",
            "analysis_report_id": 1,
            "change_type": "parameter",
        }
    )

    report = asyncio.run(orchestrator.run_validation(proposal))

    assert report.proposal_id == "prop_1"
    assert trace_calls == [("validator", "test", "breakout_v1")]
