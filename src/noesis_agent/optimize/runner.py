# pyright: reportMissingTypeStubs=false, reportAny=false, reportArgumentType=false, reportCallIssue=false, reportOperatorIssue=false

from __future__ import annotations

import random
from collections.abc import Callable
from itertools import product
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from noesis_agent.backtest.broker import BrokerSimulator
from noesis_agent.backtest.engine import BacktestEngine, BacktestRunResult
from noesis_agent.backtest.metrics import BacktestSummary, calculate_summary
from noesis_agent.core.models import StrategyRuntimeConfig
from noesis_agent.strategy.base import StrategyBase
from noesis_agent.strategy.registry import StrategyRegistry


class OptimizationTrial(BaseModel):
    model_config = ConfigDict(validate_assignment=True)

    rank: int
    timeframe: str
    parameters: dict[str, Any]
    summary: BacktestSummary


class OptimizationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    trials: list[OptimizationTrial] = Field(default_factory=list)
    best: OptimizationTrial | None = None


def build_strategy(strategy_id: str, config: StrategyRuntimeConfig) -> StrategyBase:
    return StrategyRegistry().build_strategy(strategy_id, config=config)


def run_grid_search(
    *,
    strategy_id: str,
    data_by_timeframe: dict[str, pd.DataFrame],
    base_config: StrategyRuntimeConfig,
    parameter_grid: dict[str, list[Any]],
    lookback_days: int = 365,
    initial_cash: float = 10_000.0,
    progress_callback: Callable[[int, int], None] | None = None,
    trial_callback: Callable[[OptimizationTrial, int, int], None] | None = None,
) -> OptimizationResult:
    trials: list[OptimizationTrial] = []
    combinations = _expand_grid(parameter_grid)
    for index, combination in enumerate(combinations, start=1):
        trials.append(
            _run_optimization_trial(
                strategy_id=strategy_id,
                data_by_timeframe=data_by_timeframe,
                base_config=base_config,
                combination=combination,
                lookback_days=lookback_days,
                initial_cash=initial_cash,
            )
        )
        if trial_callback is not None:
            trial_callback(trials[-1], index, len(combinations))
        if progress_callback is not None:
            progress_callback(index, len(combinations))
    _rank_trials(trials)
    return OptimizationResult(strategy_id=strategy_id, trials=trials, best=trials[0] if trials else None)


def run_random_search(
    *,
    strategy_id: str,
    data_by_timeframe: dict[str, pd.DataFrame],
    base_config: StrategyRuntimeConfig,
    parameter_space: dict[str, list[Any]],
    max_trials: int,
    lookback_days: int = 365,
    initial_cash: float = 10_000.0,
    seed: int | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
    trial_callback: Callable[[OptimizationTrial, int, int], None] | None = None,
) -> OptimizationResult:
    rng = random.Random(seed)  # noqa: S311
    combinations = _sample_parameter_combinations(parameter_space, max_trials=max_trials, rng=rng)
    trials: list[OptimizationTrial] = []
    for index, combination in enumerate(combinations, start=1):
        trials.append(
            _run_optimization_trial(
                strategy_id=strategy_id,
                data_by_timeframe=data_by_timeframe,
                base_config=base_config,
                combination=combination,
                lookback_days=lookback_days,
                initial_cash=initial_cash,
            )
        )
        if trial_callback is not None:
            trial_callback(trials[-1], index, len(combinations))
        if progress_callback is not None:
            progress_callback(index, len(combinations))
    _rank_trials(trials)
    return OptimizationResult(strategy_id=strategy_id, trials=trials, best=trials[0] if trials else None)


def split_optimization_parameters(raw_parameters: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    strategy_parameters: dict[str, Any] = {}
    trade_management_parameters: dict[str, Any] = {}
    for key, value in raw_parameters.items():
        if key.startswith("trade_management."):
            trade_management_parameters[key.removeprefix("trade_management.")] = value
        elif key.startswith("strategy."):
            strategy_parameters[key.removeprefix("strategy.")] = value
        else:
            strategy_parameters[key] = value
    return strategy_parameters, trade_management_parameters


def _run_optimization_trial(
    *,
    strategy_id: str,
    data_by_timeframe: dict[str, pd.DataFrame],
    base_config: StrategyRuntimeConfig,
    combination: dict[str, Any],
    lookback_days: int,
    initial_cash: float,
) -> OptimizationTrial:
    timeframe = str(combination.get("timeframe", base_config.timeframe))
    frame = data_by_timeframe[timeframe]
    raw_parameters = {key: value for key, value in combination.items() if key != "timeframe"}
    strategy_parameters, trade_management_parameters = split_optimization_parameters(raw_parameters)
    config = StrategyRuntimeConfig(
        strategy_id=base_config.strategy_id,
        symbol=base_config.symbol,
        timeframe=timeframe,
        mode=base_config.mode,
        parameters={**base_config.parameters, **strategy_parameters},
        risk=dict(base_config.risk),
        trade_management={**base_config.trade_management, **trade_management_parameters},
    )
    strategy = build_strategy(strategy_id, config)
    run_result = _run_backtest_with_window(
        strategy=strategy,
        config=config,
        frame=frame,
        lookback_days=lookback_days,
        initial_cash=initial_cash,
    )
    summary = calculate_summary(run_result, initial_cash=initial_cash)
    return OptimizationTrial(rank=0, timeframe=timeframe, parameters=raw_parameters, summary=summary)


def _run_backtest_with_window(
    *,
    strategy: StrategyBase,
    config: StrategyRuntimeConfig,
    frame: pd.DataFrame,
    lookback_days: int,
    initial_cash: float,
) -> BacktestRunResult:
    if frame.empty:
        engine = BacktestEngine(broker=BrokerSimulator(initial_cash=initial_cash))
        return engine.run(strategy, frame.copy(), config, warmup_bars=0, trading_start_index=0)

    index = pd.DatetimeIndex(frame.index)
    evaluation_end = index.max()
    evaluation_start = max(index.min(), evaluation_end - pd.Timedelta(days=lookback_days))
    trading_start_index = int(index.searchsorted(evaluation_start))
    slice_start_index = max(0, trading_start_index - strategy.warmup_bars)
    sliced_frame = frame.iloc[slice_start_index:].copy()
    sliced_frame.attrs["symbol"] = config.symbol
    adjusted_trading_start = max(0, trading_start_index - slice_start_index)
    engine = BacktestEngine(broker=BrokerSimulator(initial_cash=initial_cash))
    return engine.run(
        strategy,
        sliced_frame,
        config,
        warmup_bars=0,
        trading_start_index=adjusted_trading_start,
    )


def _expand_grid(parameter_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    if not parameter_grid:
        return [{}]
    keys = list(parameter_grid.keys())
    values = [parameter_grid[key] for key in keys]
    return [dict(zip(keys, combo, strict=True)) for combo in product(*values)]


def _rank_trials(trials: list[OptimizationTrial]) -> None:
    trials.sort(
        key=lambda trial: (
            trial.summary.total_return_pct,
            -trial.summary.max_drawdown_pct,
            -trial.summary.fees_paid,
        ),
        reverse=True,
    )
    for index, trial in enumerate(trials, start=1):
        trial.rank = index


def _sample_parameter_combinations(
    parameter_space: dict[str, list[Any]],
    *,
    max_trials: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    if max_trials <= 0:
        raise ValueError("max_trials must be positive")
    for key, values in parameter_space.items():
        if not values:
            raise ValueError(f"parameter space for {key} cannot be empty")
    keys = list(parameter_space.keys())
    return [{key: rng.choice(parameter_space[key]) for key in keys} for _ in range(max_trials)]
