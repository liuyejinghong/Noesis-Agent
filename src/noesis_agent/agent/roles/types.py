from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from noesis_agent.core.models import generate_run_id


class ProposalStatus(str, Enum):
    DRAFT = "draft"
    GATE_1_MEMORY = "gate_1_memory"
    GATE_2_BACKTEST = "gate_2_backtest"
    GATE_3_WALKFORWARD = "gate_3_walkforward"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    TESTNET_DEPLOYED = "testnet_deployed"
    GATE_4_MIN_PERIOD = "gate_4_min_period"
    GATE_5_PERFORMANCE = "gate_5_performance"
    PENDING_LIVE_APPROVAL = "pending_live_approval"
    LIVE_DEPLOYED = "live_deployed"
    MONITORING = "monitoring"
    REJECTED = "rejected"
    AUTO_ROLLBACK = "auto_rollback"
    GRADUATED = "graduated"


class PerformanceSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int
    sharpe_ratio: float | None = None


class AnalysisReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    period: str
    strategy_id: str
    performance: PerformanceSummary
    market_regime: str = "unknown"
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class Proposal(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: str = Field(default_factory=lambda: generate_run_id("prop"))
    strategy_id: str
    analysis_report_id: int
    change_type: str
    parameter_changes: dict[str, Any] = Field(default_factory=dict)
    code_changes: str = ""
    trade_management_changes: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""
    expected_impact: str = ""
    status: ProposalStatus = ProposalStatus.DRAFT


class BacktestComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    total_return_pct: float
    max_drawdown_pct: float
    win_rate_pct: float
    trade_count: int
    sharpe_ratio: float | None = None


class ValidationReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: str
    baseline: BacktestComparison
    proposed: BacktestComparison
    walk_forward_decay_pct: float = 0.0
    verdict: str = "pending"
    concerns: list[str] = Field(default_factory=list)


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    gate_name: str
    passed: bool
    reason: str = ""
    details: dict[str, Any] = Field(default_factory=dict)
