from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from noesis_agent.agent.roles.types import (
    AnalysisReport,
    BacktestComparison,
    GateResult,
    PerformanceSummary,
    Proposal,
    ProposalStatus,
    ValidationReport,
)


def test_proposal_status_values_match_agent_pipeline() -> None:
    assert ProposalStatus.DRAFT.value == "draft"
    assert ProposalStatus.PENDING_APPROVAL.value == "pending_approval"
    assert ProposalStatus.GRADUATED.value == "graduated"


def test_pipeline_status_count_excludes_terminal_states() -> None:
    terminal_statuses = {
        ProposalStatus.REJECTED,
        ProposalStatus.AUTO_ROLLBACK,
        ProposalStatus.GRADUATED,
    }

    pipeline_statuses = [status for status in ProposalStatus if status not in terminal_statuses]

    assert len(pipeline_statuses) == 12


def test_analysis_report_creation_and_frozen_behavior() -> None:
    report = AnalysisReport(
        period="2026-W12",
        strategy_id="breakout_v1",
        performance=PerformanceSummary(
            total_return_pct=12.4,
            max_drawdown_pct=3.1,
            win_rate_pct=58.0,
            trade_count=21,
            sharpe_ratio=1.4,
        ),
        strengths=["captured trend continuation"],
    )

    assert report.market_regime == "unknown"
    assert report.weaknesses == []
    assert report.patterns == []
    assert report.recommendations == []

    with pytest.raises(ValidationError):
        report.market_regime = "trend"


def test_proposal_parameter_change_defaults_to_draft() -> None:
    proposal = Proposal(
        strategy_id="breakout_v1",
        analysis_report_id=42,
        change_type="parameter",
        parameter_changes={"lookback": 30},
        rationale="Longer lookback may reduce chop entries.",
    )

    assert proposal.status is ProposalStatus.DRAFT
    assert proposal.code_changes == ""
    assert proposal.trade_management_changes == {}
    assert proposal.proposal_id.startswith("prop_")
    assert re.fullmatch(r"prop_\d{8}T\d{6}Z_[0-9a-f]{8}", proposal.proposal_id)


def test_proposal_code_change_variant_supports_code_payload() -> None:
    proposal = Proposal(
        strategy_id="breakout_v2",
        analysis_report_id=43,
        change_type="code",
        code_changes="if trend_strength < 2: return None",
        expected_impact="Avoid weak breakouts during chop.",
    )

    assert proposal.change_type == "code"
    assert proposal.parameter_changes == {}
    assert proposal.code_changes == "if trend_strength < 2: return None"


def test_validation_report_creation_defaults_to_pending() -> None:
    report = ValidationReport(
        proposal_id="prop_20260321T000000Z_deadbeef",
        baseline=BacktestComparison(
            total_return_pct=10.0,
            max_drawdown_pct=4.0,
            win_rate_pct=52.0,
            trade_count=30,
        ),
        proposed=BacktestComparison(
            total_return_pct=11.5,
            max_drawdown_pct=3.8,
            win_rate_pct=54.0,
            trade_count=28,
            sharpe_ratio=1.2,
        ),
    )

    assert report.verdict == "pending"
    assert report.concerns == []
    assert report.walk_forward_decay_pct == 0.0


def test_gate_result_supports_pass_and_fail_outcomes() -> None:
    passed = GateResult(gate_name="gate_2_backtest", passed=True, details={"delta": 1.2})
    failed = GateResult(gate_name="gate_3_walkforward", passed=False, reason="Decay exceeded threshold")

    assert passed.reason == ""
    assert passed.details == {"delta": 1.2}
    assert failed.passed is False
    assert failed.reason == "Decay exceeded threshold"
