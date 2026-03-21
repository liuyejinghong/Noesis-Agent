from __future__ import annotations

from noesis_agent.agent.roles.types import BacktestComparison
from noesis_agent.agent.gates import (
    gate_1_failure_memory,
    gate_2_backtest_comparison,
    gate_3_walk_forward,
    gate_4_testnet_period,
    gate_5_testnet_performance,
)


def make_comparison(*, total_return_pct: float, max_drawdown_pct: float) -> BacktestComparison:
    return BacktestComparison(
        total_return_pct=total_return_pct,
        max_drawdown_pct=max_drawdown_pct,
        win_rate_pct=55.0,
        trade_count=20,
        sharpe_ratio=1.1,
    )


def test_gate_1_failure_memory_passes_when_no_matching_failure_exists() -> None:
    result = gate_1_failure_memory(
        strategy_id="breakout_v1",
        change_type="parameter",
        failure_records=[{"strategy_id": "breakout_v1", "category": "code"}],
    )

    assert result.passed is True
    assert result.gate_name == "gate_1_memory"


def test_gate_1_failure_memory_fails_when_strategy_and_change_type_match() -> None:
    result = gate_1_failure_memory(
        strategy_id="breakout_v1",
        change_type="parameter",
        failure_records=[{"strategy_id": "breakout_v1", "category": "parameter"}],
    )

    assert result.passed is False
    assert "matching failure" in result.reason.lower()


def test_gate_1_failure_memory_ignores_partial_matches() -> None:
    result = gate_1_failure_memory(
        strategy_id="breakout_v2",
        change_type="trade_management",
        failure_records=[
            {"strategy_id": "breakout_v1", "category": "trade_management"},
            {"strategy_id": "breakout_v2", "category": "parameter"},
        ],
    )

    assert result.passed is True


def test_gate_2_backtest_comparison_passes_with_higher_return_and_bounded_drawdown() -> None:
    result = gate_2_backtest_comparison(
        make_comparison(total_return_pct=10.0, max_drawdown_pct=4.0),
        make_comparison(total_return_pct=12.0, max_drawdown_pct=5.5),
    )

    assert result.passed is True


def test_gate_2_backtest_comparison_fails_on_lower_return() -> None:
    result = gate_2_backtest_comparison(
        make_comparison(total_return_pct=10.0, max_drawdown_pct=4.0),
        make_comparison(total_return_pct=9.5, max_drawdown_pct=4.5),
    )

    assert result.passed is False
    assert "return" in result.reason.lower()


def test_gate_2_backtest_comparison_fails_on_excessive_drawdown() -> None:
    result = gate_2_backtest_comparison(
        make_comparison(total_return_pct=10.0, max_drawdown_pct=4.0),
        make_comparison(total_return_pct=10.5, max_drawdown_pct=6.1),
    )

    assert result.passed is False
    assert "drawdown" in result.reason.lower()


def test_gate_2_backtest_comparison_allows_drawdown_at_limit() -> None:
    result = gate_2_backtest_comparison(
        make_comparison(total_return_pct=10.0, max_drawdown_pct=4.0),
        make_comparison(total_return_pct=10.0, max_drawdown_pct=6.0),
    )

    assert result.passed is True


def test_gate_3_walk_forward_passes_below_threshold() -> None:
    result = gate_3_walk_forward(decay_pct=12.5)

    assert result.passed is True


def test_gate_3_walk_forward_fails_above_threshold() -> None:
    result = gate_3_walk_forward(decay_pct=31.0)

    assert result.passed is False
    assert "decay" in result.reason.lower()


def test_gate_3_walk_forward_allows_equal_threshold() -> None:
    result = gate_3_walk_forward(decay_pct=30.0)

    assert result.passed is True


def test_gate_4_testnet_period_passes_when_days_and_trades_meet_minimums() -> None:
    result = gate_4_testnet_period(days_running=14, trade_count=20)

    assert result.passed is True


def test_gate_4_testnet_period_fails_when_days_are_below_minimum() -> None:
    result = gate_4_testnet_period(days_running=13, trade_count=20)

    assert result.passed is False
    assert "days" in result.reason.lower()


def test_gate_4_testnet_period_fails_when_trades_are_below_minimum() -> None:
    result = gate_4_testnet_period(days_running=14, trade_count=19)

    assert result.passed is False
    assert "trade" in result.reason.lower()


def test_gate_5_testnet_performance_passes_when_deviation_is_within_tolerance() -> None:
    result = gate_5_testnet_performance(actual_return_pct=9.0, expected_return_pct=10.0)

    assert result.passed is True


def test_gate_5_testnet_performance_fails_when_deviation_is_below_tolerance() -> None:
    result = gate_5_testnet_performance(actual_return_pct=4.0, expected_return_pct=10.0)

    assert result.passed is False
    assert "deviation" in result.reason.lower()


def test_gate_5_testnet_performance_skips_check_when_expected_return_is_zero() -> None:
    result = gate_5_testnet_performance(actual_return_pct=-3.0, expected_return_pct=0.0)

    assert result.passed is True
