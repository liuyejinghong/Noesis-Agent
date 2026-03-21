# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportImplicitOverride=false, reportArgumentType=false, reportAny=false

from __future__ import annotations

import pandas as pd
import pytest

from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide
from noesis_agent.core.models import AccountSnapshot, OrderIntent, PositionSnapshot, SignalEvent, StrategyRuntimeConfig
from noesis_agent.optimize.runner import run_grid_search, run_random_search
from noesis_agent.strategy.base import StrategyBase


class OptimizeFakeStrategy(StrategyBase):
    strategy_id = "optimize_fake_strategy"

    def configure(self, config: StrategyRuntimeConfig) -> None:
        super().configure(config)
        self.hold_bars = int(config.parameters.get("hold_bars", 1))
        self.quantity = float(config.parameters.get("quantity", 1.0))

    def on_bar(
        self,
        data: pd.DataFrame,
        position: PositionSnapshot | None,
        account: AccountSnapshot | None,
    ) -> list[SignalEvent]:
        bar_index = len(data) - 1
        if bar_index == 1 and position is None:
            return [
                SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol="BTCUSDT",
                    side=SignalSide.LONG,
                    timestamp=pd.Timestamp(data.index[-1]).to_pydatetime(),
                    reason="enter_long",
                )
            ]
        if (
            position is not None
            and position.entry_bar_index is not None
            and bar_index >= position.entry_bar_index + self.hold_bars
        ):
            return [
                SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol="BTCUSDT",
                    side=SignalSide.FLAT,
                    timestamp=pd.Timestamp(data.index[-1]).to_pydatetime(),
                    reason="exit_long",
                )
            ]
        return []

    def build_order_intents(
        self,
        signals: list[SignalEvent],
        config: StrategyRuntimeConfig,
    ) -> list[OrderIntent]:
        return [
            OrderIntent(
                strategy_id=self.strategy_id,
                symbol=config.symbol,
                side=signal.side,
                order_type=OrderType.MARKET,
                quantity=self.quantity,
            )
            for signal in signals
        ]


def _build_frame() -> pd.DataFrame:
    closes = [100.0, 102.0, 104.0, 107.0, 111.0, 116.0, 122.0, 129.0]
    index = pd.date_range("2026-03-01T00:00:00Z", periods=len(closes), freq="1h")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [price + 0.5 for price in closes],
            "low": [price - 0.5 for price in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=index,
    )


def _build_config() -> StrategyRuntimeConfig:
    return StrategyRuntimeConfig(
        strategy_id=OptimizeFakeStrategy.strategy_id,
        symbol="BTCUSDT",
        timeframe="1h",
        mode=RuntimeMode.BACKTEST,
    )


def _build_fake_strategy(strategy_id: str, config: StrategyRuntimeConfig) -> OptimizeFakeStrategy:
    del strategy_id
    strategy = OptimizeFakeStrategy()
    strategy.configure(config)
    return strategy


def test_run_grid_search_produces_all_trials_and_ranks_best(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("noesis_agent.optimize.runner.build_strategy", _build_fake_strategy)
    data_by_timeframe = {"1h": _build_frame()}

    result = run_grid_search(
        strategy_id=OptimizeFakeStrategy.strategy_id,
        data_by_timeframe=data_by_timeframe,
        base_config=_build_config(),
        parameter_grid={"hold_bars": [1, 2], "quantity": [1.0, 2.0]},
    )

    assert len(result.trials) == 4
    assert result.best is not None
    assert result.best.summary.total_return_pct == max(trial.summary.total_return_pct for trial in result.trials)


def test_run_random_search_respects_max_trials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("noesis_agent.optimize.runner.build_strategy", _build_fake_strategy)
    data_by_timeframe = {"1h": _build_frame()}

    result = run_random_search(
        strategy_id=OptimizeFakeStrategy.strategy_id,
        data_by_timeframe=data_by_timeframe,
        base_config=_build_config(),
        parameter_space={"hold_bars": [1, 2], "quantity": [1.0, 2.0]},
        max_trials=3,
        seed=7,
    )

    assert len(result.trials) == 3
