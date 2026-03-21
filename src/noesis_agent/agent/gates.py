from __future__ import annotations

from noesis_agent.agent.roles.types import BacktestComparison, GateResult


def gate_1_failure_memory(*, strategy_id: str, change_type: str, failure_records: list[dict]) -> GateResult:
    for record in failure_records:
        if record.get("strategy_id") == strategy_id and record.get("category") == change_type:
            return GateResult(
                gate_name="gate_1_memory",
                passed=False,
                reason="Found matching failure record for strategy and change type.",
                details={"strategy_id": strategy_id, "change_type": change_type},
            )

    return GateResult(
        gate_name="gate_1_memory",
        passed=True,
        details={"strategy_id": strategy_id, "change_type": change_type},
    )


def gate_2_backtest_comparison(baseline: BacktestComparison, proposed: BacktestComparison) -> GateResult:
    if proposed.total_return_pct < baseline.total_return_pct:
        return GateResult(
            gate_name="gate_2_backtest",
            passed=False,
            reason="Proposed backtest return is lower than baseline.",
            details={
                "baseline_total_return_pct": baseline.total_return_pct,
                "proposed_total_return_pct": proposed.total_return_pct,
            },
        )

    drawdown_limit = baseline.max_drawdown_pct * 1.5
    if proposed.max_drawdown_pct > drawdown_limit:
        return GateResult(
            gate_name="gate_2_backtest",
            passed=False,
            reason="Proposed backtest drawdown exceeds allowed threshold.",
            details={
                "baseline_max_drawdown_pct": baseline.max_drawdown_pct,
                "proposed_max_drawdown_pct": proposed.max_drawdown_pct,
                "drawdown_limit_pct": drawdown_limit,
            },
        )

    return GateResult(gate_name="gate_2_backtest", passed=True)


def gate_3_walk_forward(*, decay_pct: float, threshold: float = 30.0) -> GateResult:
    if decay_pct > threshold:
        return GateResult(
            gate_name="gate_3_walkforward",
            passed=False,
            reason="Walk-forward decay exceeded threshold.",
            details={"decay_pct": decay_pct, "threshold": threshold},
        )

    return GateResult(
        gate_name="gate_3_walkforward",
        passed=True,
        details={"decay_pct": decay_pct, "threshold": threshold},
    )


def gate_4_testnet_period(
    *,
    days_running: int,
    trade_count: int,
    min_days: int = 14,
    min_trades: int = 20,
) -> GateResult:
    if days_running < min_days:
        return GateResult(
            gate_name="gate_4_min_period",
            passed=False,
            reason="Days running is below minimum testnet period.",
            details={
                "days_running": days_running,
                "trade_count": trade_count,
                "min_days": min_days,
                "min_trades": min_trades,
            },
        )

    if trade_count < min_trades:
        return GateResult(
            gate_name="gate_4_min_period",
            passed=False,
            reason="Trade count is below minimum testnet requirement.",
            details={
                "days_running": days_running,
                "trade_count": trade_count,
                "min_days": min_days,
                "min_trades": min_trades,
            },
        )

    return GateResult(
        gate_name="gate_4_min_period",
        passed=True,
        details={
            "days_running": days_running,
            "trade_count": trade_count,
            "min_days": min_days,
            "min_trades": min_trades,
        },
    )


def gate_5_testnet_performance(
    *, actual_return_pct: float, expected_return_pct: float, tolerance: float = -0.5
) -> GateResult:
    if expected_return_pct == 0:
        return GateResult(
            gate_name="gate_5_performance",
            passed=True,
            reason="Expected return is zero; skipping deviation check.",
            details={
                "actual_return_pct": actual_return_pct,
                "expected_return_pct": expected_return_pct,
                "tolerance": tolerance,
            },
        )

    deviation = (actual_return_pct - expected_return_pct) / abs(expected_return_pct)
    if deviation < tolerance:
        return GateResult(
            gate_name="gate_5_performance",
            passed=False,
            reason="Actual performance deviation is below tolerance.",
            details={
                "actual_return_pct": actual_return_pct,
                "expected_return_pct": expected_return_pct,
                "deviation": deviation,
                "tolerance": tolerance,
            },
        )

    return GateResult(
        gate_name="gate_5_performance",
        passed=True,
        details={
            "actual_return_pct": actual_return_pct,
            "expected_return_pct": expected_return_pct,
            "deviation": deviation,
            "tolerance": tolerance,
        },
    )
