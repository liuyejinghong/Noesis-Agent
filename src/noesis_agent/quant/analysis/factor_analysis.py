from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

IC_WINDOW = 20


@dataclass(frozen=True)
class FactorAnalysisResult:
    factor_id: str
    ic_mean: float
    ic_std: float
    ir: float
    hit_rate: float
    turnover: float
    monotonicity: float


def compute_ic_series(factor_values: pd.Series, forward_returns: pd.Series) -> pd.Series:
    aligned = pd.concat([factor_values, forward_returns], axis=1).dropna()
    if len(aligned) < IC_WINDOW:
        return pd.Series(dtype=float)
    aligned.columns = ["factor", "return"]
    return aligned["factor"].rolling(IC_WINDOW).corr(aligned["return"]).dropna()


def analyze_factor(
    factor_id: str,
    factor_values: pd.Series,
    forward_returns: pd.Series,
    n_quantiles: int = 5,
) -> FactorAnalysisResult:
    aligned = pd.concat([factor_values, forward_returns], axis=1).dropna()
    if len(aligned) < 30:
        return FactorAnalysisResult(
            factor_id=factor_id,
            ic_mean=0,
            ic_std=1,
            ir=0,
            hit_rate=0,
            turnover=0,
            monotonicity=0,
        )

    aligned.columns = ["factor", "fwd_return"]

    ic_series = compute_ic_series(aligned["factor"], aligned["fwd_return"])
    ic_mean = float(ic_series.mean()) if len(ic_series) > 0 else 0.0
    ic_std = float(ic_series.std()) if len(ic_series) > 0 else 1.0
    ir = ic_mean / ic_std if ic_std > 0 else 0.0
    hit_rate = float((ic_series > 0).mean()) if len(ic_series) > 0 else 0.0

    factor_rank = aligned["factor"].rank(pct=True)
    turnover = float(factor_rank.diff().abs().mean())

    try:
        quantiles = pd.qcut(aligned["factor"], n_quantiles, labels=False, duplicates="drop")
        quantile_returns = aligned.groupby(quantiles)["fwd_return"].mean()
        if len(quantile_returns) >= 2:
            ranks = quantile_returns.rank()
            ideal = pd.Series(range(1, len(ranks) + 1), index=ranks.index, dtype=float)
            monotonicity = float(ranks.corr(ideal))
        else:
            monotonicity = 0.0
    except ValueError:
        monotonicity = 0.0

    if pd.isna(monotonicity):
        monotonicity = 0.0

    return FactorAnalysisResult(
        factor_id=factor_id,
        ic_mean=round(ic_mean, 6),
        ic_std=round(ic_std, 6),
        ir=round(ir, 4),
        hit_rate=round(hit_rate, 4),
        turnover=round(turnover, 6),
        monotonicity=round(monotonicity, 4),
    )
