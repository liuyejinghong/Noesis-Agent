from __future__ import annotations

import numpy as np
import pandas as pd

from noesis_agent.quant.analysis.factor_analysis import analyze_factor, compute_ic_series


def make_series(values: np.ndarray | list[float]) -> pd.Series:
    index = pd.date_range("2025-01-01", periods=len(values), freq="15min", tz="UTC")
    return pd.Series(values, index=index, dtype=float)


def test_analyze_factor_with_trending_data_has_positive_ic() -> None:
    factor_values = make_series(np.linspace(0.0, 1.0, 80))
    forward_returns = make_series(np.linspace(0.1, 0.9, 80))

    result = analyze_factor("trend_factor", factor_values, forward_returns)

    assert result.factor_id == "trend_factor"
    assert result.ic_mean > 0.9
    assert result.hit_rate == 1.0


def test_analyze_factor_with_random_data_has_near_zero_ic() -> None:
    rng = np.random.default_rng(42)
    factor_values = make_series(rng.normal(size=120))
    forward_returns = make_series(rng.normal(size=120))

    result = analyze_factor("random_factor", factor_values, forward_returns)

    assert abs(result.ic_mean) < 0.35


def test_analyze_factor_with_insufficient_data_returns_zero_result() -> None:
    factor_values = make_series(np.linspace(0.0, 1.0, 20))
    forward_returns = make_series(np.linspace(0.1, 0.9, 20))

    result = analyze_factor("short_factor", factor_values, forward_returns)

    assert result.factor_id == "short_factor"
    assert result.ic_mean == 0
    assert result.ic_std == 1
    assert result.ir == 0
    assert result.hit_rate == 0
    assert result.turnover == 0
    assert result.monotonicity == 0


def test_compute_ic_series_returns_series() -> None:
    factor_values = make_series(np.linspace(0.0, 1.0, 40))
    forward_returns = make_series(np.linspace(0.2, 1.2, 40))

    ic_series = compute_ic_series(factor_values, forward_returns)

    assert isinstance(ic_series, pd.Series)
    assert not ic_series.empty


def test_compute_ic_series_returns_empty_series_below_rolling_window() -> None:
    factor_values = make_series(np.linspace(0.0, 1.0, 15))
    forward_returns = make_series(np.linspace(0.2, 1.2, 15))

    ic_series = compute_ic_series(factor_values, forward_returns)

    assert ic_series.empty
