from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

import pandas as pd  # type: ignore


class MarketRegime(StrEnum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RegimeResult:
    regime: MarketRegime
    confidence: float
    atr_percentile: float
    ma_slope: float
    details: str = ""


def _compute_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
    high = cast(pd.Series, data["high"])
    low = cast(pd.Series, data["low"])
    close = cast(pd.Series, data["close"])
    prev_close = cast(pd.Series, close.shift(1))
    tr_components = [
        cast(pd.Series, high - low),
        cast(pd.Series, (high - prev_close).abs()),  # pyright: ignore[reportAny]
        cast(pd.Series, (low - prev_close).abs()),  # pyright: ignore[reportAny]
    ]
    tr_frame = pd.concat(
        tr_components,
        axis=1,
    )
    tr = tr_frame.max(axis=1)
    return cast(pd.Series, tr.rolling(period).mean())


def _compute_ma_slope(data: pd.DataFrame, ma_period: int, slope_window: int) -> float:
    close = cast(pd.Series, data["close"])
    ma = close.rolling(ma_period).mean()
    recent_ma = pd.Series(ma).dropna().iloc[-slope_window:]
    if len(recent_ma) < slope_window:
        return 0.0
    first = float(recent_ma.iloc[0])
    if first == 0.0:
        return 0.0
    last = float(recent_ma.iloc[-1])
    return (last - first) / first / slope_window


def _compute_directional_efficiency(data: pd.DataFrame, window: int) -> float:
    closes = cast(pd.Series, data["close"]).iloc[-window:]
    if len(closes) < window:
        return 0.0
    path_length = float(cast(pd.Series, closes.diff().abs()).sum())
    if path_length == 0.0:
        return 0.0
    net_move = abs(float(closes.iloc[-1] - closes.iloc[0]))
    return max(0.0, min(1.0, net_move / path_length))


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _atr_percentile(atr: pd.Series, lookback: int = 100) -> float:
    history = atr.dropna().tail(lookback)
    if history.empty:
        return 0.0
    latest = float(history.iloc[-1])
    return float((history <= latest).mean())  # pyright: ignore[reportAny]


def _build_details(
    regime: MarketRegime,
    confidence: float,
    atr_percentile: float,
    ma_slope: float,
    efficiency: float,
) -> str:
    regime_text = {
        MarketRegime.TRENDING_UP: "上升趋势",
        MarketRegime.TRENDING_DOWN: "下降趋势",
        MarketRegime.RANGING: "震荡区间",
        MarketRegime.VOLATILE: "高波动",
        MarketRegime.UNKNOWN: "状态未知",
    }[regime]
    return (
        f"市场状态判断为{regime_text}，置信度{confidence:.2f}；"
        f"ATR分位数{atr_percentile:.2f}，均线斜率{ma_slope:.4f}，方向效率{efficiency:.2f}。"
    )


def classify_regime(
    data: pd.DataFrame,
    *,
    atr_period: int = 14,
    ma_period: int = 50,
    slope_window: int = 10,
    atr_high_threshold: float = 0.75,
    slope_threshold: float = 0.001,
) -> RegimeResult:
    required_columns = {"high", "low", "close"}
    if len(data) < ma_period or not required_columns.issubset(data.columns):
        return RegimeResult(
            regime=MarketRegime.UNKNOWN,
            confidence=0.0,
            atr_percentile=0.0,
            ma_slope=0.0,
            details="样本不足，无法判断当前市场状态。",
        )

    atr = _compute_atr(data, period=atr_period)
    atr_percentile = _atr_percentile(atr)
    ma_slope = _compute_ma_slope(data, ma_period=ma_period, slope_window=slope_window)
    efficiency = _compute_directional_efficiency(data, window=max(slope_window, 2))

    if pd.isna(atr.iloc[-1]):
        return RegimeResult(
            regime=MarketRegime.UNKNOWN,
            confidence=0.0,
            atr_percentile=0.0,
            ma_slope=ma_slope,
            details="ATR数据不足，暂时无法识别市场状态。",
        )

    slope_strength = _clamp(abs(ma_slope) / max(slope_threshold, 1e-9))
    volatility_strength = _clamp((atr_percentile - atr_high_threshold) / max(1.0 - atr_high_threshold, 1e-9))
    calm_strength = _clamp((atr_high_threshold - atr_percentile) / max(atr_high_threshold, 1e-9))
    is_steep = abs(ma_slope) >= slope_threshold
    is_high_atr = atr_percentile >= atr_high_threshold

    if is_high_atr and (is_steep or efficiency >= 0.55):
        regime = MarketRegime.TRENDING_UP if ma_slope >= 0.0 else MarketRegime.TRENDING_DOWN
        confidence = _clamp(0.45 + 0.3 * volatility_strength + 0.15 * slope_strength + 0.1 * efficiency)
    elif is_high_atr:
        regime = MarketRegime.VOLATILE
        confidence = _clamp(0.45 + 0.35 * volatility_strength + 0.2 * (1.0 - efficiency))
    elif is_steep:
        regime = MarketRegime.TRENDING_UP if ma_slope >= 0.0 else MarketRegime.TRENDING_DOWN
        confidence = _clamp(0.3 + 0.25 * slope_strength + 0.2 * calm_strength + 0.15 * efficiency)
    else:
        regime = MarketRegime.RANGING
        confidence = _clamp(0.4 + 0.3 * calm_strength + 0.2 * (1.0 - slope_strength) + 0.1 * (1.0 - efficiency))

    return RegimeResult(
        regime=regime,
        confidence=confidence,
        atr_percentile=_clamp(atr_percentile),
        ma_slope=ma_slope,
        details=_build_details(regime, confidence, _clamp(atr_percentile), ma_slope, efficiency),
    )


__all__ = [
    "MarketRegime",
    "RegimeResult",
    "classify_regime",
    "_compute_atr",
    "_compute_ma_slope",
]
