from __future__ import annotations

import pandas as pd
import pytest

from noesis_agent.quant.factors.compute import create_default_registry, momentum
from noesis_agent.quant.factors.registry import FactorDefinition, FactorRegistry


def make_ohlcv(n: int = 60) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    close = pd.Series(range(100, 100 + n), index=index, dtype=float)
    return pd.DataFrame(
        {
            "open": close - 0.5,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": pd.Series(range(1000, 1000 + n), index=index, dtype=float),
        },
        index=index,
    )


def test_register_and_list_factors() -> None:
    registry = FactorRegistry()
    definition = FactorDefinition(
        factor_id="momentum_custom",
        name="Custom Momentum",
        category="momentum",
        compute_fn=momentum,
        default_params={"period": 3},
    )

    registry.register(definition)

    assert registry.get("momentum_custom") == definition
    assert registry.list_factors() == [definition]


def test_compute_returns_series() -> None:
    registry = FactorRegistry()
    registry.register(
        FactorDefinition(
            factor_id="momentum_custom",
            name="Custom Momentum",
            category="momentum",
            compute_fn=momentum,
            default_params={"period": 3},
        )
    )

    result = registry.compute("momentum_custom", make_ohlcv())

    assert isinstance(result, pd.Series)
    assert result.name == "close"


def test_create_default_registry_has_seven_factors() -> None:
    registry = create_default_registry()

    assert [definition.factor_id for definition in registry.list_factors()] == [
        "atr_14",
        "direction_eff_20",
        "ma_slope_50_10",
        "momentum_20",
        "momentum_5",
        "volatility_pct_14",
        "volume_zscore_20",
    ]


def test_unknown_factor_raises_key_error() -> None:
    registry = FactorRegistry()

    with pytest.raises(KeyError, match="Unknown factor: missing"):
        registry.get("missing")


def test_list_factors_filters_by_category() -> None:
    registry = create_default_registry()

    assert [definition.factor_id for definition in registry.list_factors(category="volatility")] == [
        "atr_14",
        "volatility_pct_14",
    ]
