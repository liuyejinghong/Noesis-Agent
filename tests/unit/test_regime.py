# pyright: reportMissingTypeStubs=false

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from noesis_agent.strategy.regime import (
    MarketRegime,
    _compute_atr,  # pyright: ignore[reportPrivateUsage]
    classify_regime,
)


def _build_ohlcv(close: np.ndarray, wick_scale: float = 0.35) -> pd.DataFrame:
    dates = pd.date_range("2025-01-01", periods=len(close), freq="15min", tz="UTC")
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) + wick_scale
    low = np.minimum(open_, close) - wick_scale
    volume = np.full(len(close), 1000.0)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def make_trending_data(
    n: int = 200,
    direction: int = 1,
    base: float = 100.0,
    strength: float = 0.6,
) -> pd.DataFrame:
    np.random.seed(42)
    trend = np.arange(n) * strength * direction
    noise = np.random.randn(n) * 0.15
    close = base + trend + noise
    return _build_ohlcv(close, wick_scale=0.5)


def make_ranging_data(n: int = 200, base: float = 100.0, amplitude: float = 0.4) -> pd.DataFrame:
    angles = np.linspace(0.0, 10.0 * np.pi, n)
    close = base + np.sin(angles) * amplitude
    return _build_ohlcv(close, wick_scale=0.12)


def make_volatile_data(n: int = 200, base: float = 100.0, volatility: float = 6.0) -> pd.DataFrame:
    np.random.seed(7)
    shocks = np.random.randn(n) * volatility
    close = base + np.cumsum(shocks)
    start_offset = float(close[0] - base)  # pyright: ignore[reportAny]
    end_offset = float(close[-1] - base)  # pyright: ignore[reportAny]
    close = close - np.linspace(start_offset, end_offset, n)
    return _build_ohlcv(close, wick_scale=2.5)


def test_trending_up() -> None:
    result = classify_regime(make_trending_data(direction=1))

    assert result.regime is MarketRegime.TRENDING_UP


def test_trending_down() -> None:
    result = classify_regime(make_trending_data(direction=-1, base=250.0))

    assert result.regime is MarketRegime.TRENDING_DOWN


def test_ranging() -> None:
    result = classify_regime(make_ranging_data())

    assert result.regime is MarketRegime.RANGING


def test_volatile() -> None:
    result = classify_regime(make_volatile_data())

    assert result.regime is MarketRegime.VOLATILE


def test_unknown_insufficient_data() -> None:
    result = classify_regime(make_trending_data(n=20), ma_period=50)

    assert result.regime is MarketRegime.UNKNOWN
    assert result.confidence == 0.0


def test_confidence_range() -> None:
    result = classify_regime(make_trending_data())

    assert 0.0 <= result.confidence <= 1.0


def test_atr_percentile_range() -> None:
    result = classify_regime(make_volatile_data())

    assert 0.0 <= result.atr_percentile <= 1.0


def test_details_in_chinese() -> None:
    result = classify_regime(make_trending_data())

    assert re.search(r"[\u4e00-\u9fff]", result.details)


def test_custom_parameters() -> None:
    result = classify_regime(
        make_trending_data(n=120, strength=0.9),
        atr_period=10,
        ma_period=20,
        slope_window=5,
        atr_high_threshold=0.6,
        slope_threshold=0.0005,
    )

    assert result.regime is MarketRegime.TRENDING_UP


def test_compute_atr() -> None:
    data = pd.DataFrame(
        {
            "high": [10.0, 12.0, 13.0],
            "low": [8.0, 9.0, 11.0],
            "close": [9.0, 11.0, 12.0],
        }
    )

    atr = _compute_atr(data, period=2)

    assert atr.iloc[0] != atr.iloc[0]
    assert atr.iloc[1] == 2.5
    assert atr.iloc[2] == 2.5
