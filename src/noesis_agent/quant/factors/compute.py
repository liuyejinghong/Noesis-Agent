from __future__ import annotations

import numpy as np
import pandas as pd

from noesis_agent.quant.factors.registry import FactorDefinition, FactorParams, FactorRegistry


def momentum(data: pd.DataFrame, params: FactorParams) -> pd.Series:
    period = int(params.get("period", 20))
    return data["close"].pct_change(period)


def volatility_atr(data: pd.DataFrame, params: FactorParams) -> pd.Series:
    period = int(params.get("period", 14))
    high = data["high"]
    low = data["low"]
    close = data["close"]
    prev_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(period).mean()


def volatility_pct(data: pd.DataFrame, params: FactorParams) -> pd.Series:
    period = int(params.get("period", 14))
    atr = volatility_atr(data, {"period": period})
    return atr / data["close"]


def volume_zscore(data: pd.DataFrame, params: FactorParams) -> pd.Series:
    period = int(params.get("period", 20))
    volume = data["volume"]
    mean = volume.rolling(period).mean()
    std = volume.rolling(period).std()
    return (volume - mean) / std.replace(0, np.nan)


def direction_efficiency(data: pd.DataFrame, params: FactorParams) -> pd.Series:
    period = int(params.get("period", 20))
    net_move = (data["close"] - data["close"].shift(period)).abs()
    bar_moves = data["close"].diff().abs().rolling(period).sum()
    return net_move / bar_moves.replace(0, np.nan)


def ma_slope(data: pd.DataFrame, params: FactorParams) -> pd.Series:
    ma_period = int(params.get("ma_period", 50))
    slope_window = int(params.get("slope_window", 10))
    moving_average = data["close"].rolling(ma_period).mean()
    return (moving_average - moving_average.shift(slope_window)) / moving_average.shift(slope_window) / slope_window


def create_default_registry() -> FactorRegistry:
    registry = FactorRegistry()
    registry.register(FactorDefinition("momentum_20", "20-period Momentum", "momentum", momentum, {"period": 20}))
    registry.register(FactorDefinition("momentum_5", "5-period Momentum", "momentum", momentum, {"period": 5}))
    registry.register(FactorDefinition("atr_14", "14-period ATR", "volatility", volatility_atr, {"period": 14}))
    registry.register(
        FactorDefinition(
            "volatility_pct_14",
            "14-period Volatility %",
            "volatility",
            volatility_pct,
            {"period": 14},
        )
    )
    registry.register(
        FactorDefinition(
            "volume_zscore_20",
            "20-period Volume Z-Score",
            "volume",
            volume_zscore,
            {"period": 20},
        )
    )
    registry.register(
        FactorDefinition(
            "direction_eff_20",
            "20-period Direction Efficiency",
            "momentum",
            direction_efficiency,
            {"period": 20},
        )
    )
    registry.register(
        FactorDefinition(
            "ma_slope_50_10",
            "MA(50) Slope over 10 bars",
            "momentum",
            ma_slope,
            {"ma_period": 50, "slope_window": 10},
        )
    )
    return registry
