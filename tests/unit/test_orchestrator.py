# pyright: reportUnknownParameterType=false

from __future__ import annotations

import asyncio

from noesis_agent.agent.memory.models import FailureRecord
from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.orchestrator import AgentOrchestrator
from noesis_agent.agent.proposal_manager import ProposalManager
from noesis_agent.agent.roles.types import AnalysisReport, Proposal, ProposalStatus
from noesis_agent.agent.skills.registry import SkillRegistry
from noesis_agent.core.config import AgentRoleConfig


def make_orchestrator() -> AgentOrchestrator:
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

    assert result["final_status"] is ProposalStatus.PENDING_APPROVAL
    assert len(result["gates"]) == 3
    assert all(gate.passed for gate in result["gates"])


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

    assert result["final_status"] is ProposalStatus.REJECTED
    assert result["gates"][0].passed is False
