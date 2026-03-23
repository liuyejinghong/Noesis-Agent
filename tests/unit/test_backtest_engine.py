# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportImplicitOverride=false, reportArgumentType=false

from __future__ import annotations

import pandas as pd
import pytest

from noesis_agent.backtest.broker import BrokerSimulator
from noesis_agent.backtest.engine import BacktestEngine
from noesis_agent.backtest.metrics import calculate_summary
from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide
from noesis_agent.core.models import AccountSnapshot, OrderIntent, PositionSnapshot, SignalEvent, StrategyRuntimeConfig
from noesis_agent.strategy.base import StrategyBase


class FakeStrategy(StrategyBase):
    strategy_id = "fake_backtest_strategy"

    def on_bar(
        self,
        data: pd.DataFrame,
        position: PositionSnapshot | None,
        account: AccountSnapshot | None,
    ) -> list[SignalEvent]:
        bar_index = len(data) - 1
        if bar_index == 5 and position is None:
            return [
                SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol="BTCUSDT",
                    side=SignalSide.LONG,
                    timestamp=pd.Timestamp(data.index[-1]).to_pydatetime(),
                    reason="enter_long",
                )
            ]
        if bar_index == 10 and position is not None:
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
                quantity=1.0,
            )
            for signal in signals
        ]


class FakeShortStrategy(StrategyBase):
    strategy_id = "fake_short_backtest_strategy"

    def on_bar(
        self,
        data: pd.DataFrame,
        position: PositionSnapshot | None,
        account: AccountSnapshot | None,
    ) -> list[SignalEvent]:
        bar_index = len(data) - 1
        if bar_index == 5 and position is None:
            return [
                SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol="BTCUSDT",
                    side=SignalSide.SHORT,
                    timestamp=pd.Timestamp(data.index[-1]).to_pydatetime(),
                    reason="enter_short",
                )
            ]
        if bar_index == 10 and position is not None:
            return [
                SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol="BTCUSDT",
                    side=SignalSide.FLAT,
                    timestamp=pd.Timestamp(data.index[-1]).to_pydatetime(),
                    reason="exit_short",
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
                quantity=1.0,
            )
            for signal in signals
        ]


class CooldownStrategy(StrategyBase):
    strategy_id = "fake_cooldown_backtest_strategy"

    def on_bar(
        self,
        data: pd.DataFrame,
        position: PositionSnapshot | None,
        account: AccountSnapshot | None,
    ) -> list[SignalEvent]:
        bar_index = len(data) - 1
        if bar_index == 5 and position is None:
            return [
                SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol="BTCUSDT",
                    side=SignalSide.LONG,
                    timestamp=pd.Timestamp(data.index[-1]).to_pydatetime(),
                    reason="enter_initial_long",
                )
            ]
        if bar_index == 6 and position is not None:
            return [
                SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol="BTCUSDT",
                    side=SignalSide.FLAT,
                    timestamp=pd.Timestamp(data.index[-1]).to_pydatetime(),
                    reason="exit_long",
                )
            ]
        if bar_index >= 7 and position is None:
            return [
                SignalEvent(
                    strategy_id=self.strategy_id,
                    symbol="BTCUSDT",
                    side=SignalSide.LONG,
                    timestamp=pd.Timestamp(data.index[-1]).to_pydatetime(),
                    reason="reenter_long",
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
                quantity=1.0,
            )
            for signal in signals
        ]


def _build_ohlcv(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-03-01T00:00:00Z", periods=len(closes), freq="1h")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [price + 1.0 for price in closes],
            "low": [price - 1.0 for price in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=index,
    )


def _build_config(**trade_management: float | int) -> StrategyRuntimeConfig:
    return StrategyRuntimeConfig(
        strategy_id=FakeStrategy.strategy_id,
        symbol="BTCUSDT",
        timeframe="1h",
        mode=RuntimeMode.BACKTEST,
        trade_management=trade_management,
    )


def test_backtest_engine_runs_and_produces_fills() -> None:
    data = _build_ohlcv(
        [
            100.0,
            101.0,
            102.0,
            103.0,
            104.0,
            105.0,
            107.0,
            109.0,
            111.0,
            112.0,
            110.0,
            109.0,
            108.0,
            107.0,
            106.0,
            105.0,
            104.0,
            103.0,
            102.0,
            101.0,
        ]
    )
    engine = BacktestEngine(broker=BrokerSimulator(initial_cash=10_000.0))

    result = engine.run(FakeStrategy(), data, _build_config())

    assert result.bars_processed == len(data)
    assert len(result.fills) == 2
    assert result.final_equity != 10_000.0
    assert result.fills[0].side is SignalSide.LONG
    assert result.fills[1].side is SignalSide.FLAT


def test_backtest_engine_exits_via_stop_loss_trade_management() -> None:
    data = _build_ohlcv(
        [
            100.0,
            101.0,
            102.0,
            103.0,
            104.0,
            105.0,
            103.0,
            102.0,
            101.0,
            100.0,
            99.0,
            98.0,
            97.0,
            96.0,
            95.0,
            94.0,
            93.0,
            92.0,
            91.0,
            90.0,
        ]
    )
    engine = BacktestEngine(broker=BrokerSimulator(initial_cash=10_000.0))

    result = engine.run(FakeStrategy(), data, _build_config(stop_loss_pct=0.01))

    exit_fill = result.fills[1]
    assert exit_fill.metadata["exit_reason"] == "stop_loss_pct_hit"


def test_backtest_engine_exits_via_take_profit_trade_management() -> None:
    data = _build_ohlcv(
        [
            100.0,
            101.0,
            102.0,
            103.0,
            104.0,
            105.0,
            107.0,
            108.0,
            109.0,
            110.0,
            111.0,
            112.0,
        ]
    )
    engine = BacktestEngine(broker=BrokerSimulator(initial_cash=10_000.0))

    result = engine.run(FakeStrategy(), data, _build_config(take_profit_pct=0.02))

    exit_fill = result.fills[1]
    assert exit_fill.metadata["exit_reason"] == "take_profit_pct_hit"


def test_backtest_engine_exits_via_trailing_stop_trade_management() -> None:
    data = _build_ohlcv(
        [
            100.0,
            101.0,
            102.0,
            103.0,
            104.0,
            105.0,
            108.0,
            110.0,
            108.0,
            107.0,
            106.0,
            105.0,
        ]
    )
    engine = BacktestEngine(broker=BrokerSimulator(initial_cash=10_000.0))

    result = engine.run(FakeStrategy(), data, _build_config(trailing_stop_pct=0.01))

    exit_fill = result.fills[1]
    assert exit_fill.metadata["exit_reason"] == "trailing_stop_pct_hit"


def test_backtest_engine_supports_profitable_short_trades() -> None:
    data = _build_ohlcv(
        [
            112.0,
            111.0,
            110.0,
            109.0,
            108.0,
            107.0,
            105.0,
            103.0,
            101.0,
            100.0,
            99.0,
            98.0,
        ]
    )
    engine = BacktestEngine(broker=BrokerSimulator(initial_cash=10_000.0))

    result = engine.run(FakeShortStrategy(), data, _build_config(take_profit_pct=0.02))

    assert result.fills[0].side is SignalSide.SHORT
    assert result.fills[1].side is SignalSide.LONG
    assert result.fills[1].metadata["exit_reason"] == "take_profit_pct_hit"
    assert result.fills[1].metadata["realized_pnl"] > 0


def test_backtest_engine_respects_cooldown_bars_before_reentry() -> None:
    data = _build_ohlcv(
        [
            100.0,
            101.0,
            102.0,
            103.0,
            104.0,
            105.0,
            106.0,
            107.0,
            108.0,
            109.0,
            110.0,
            111.0,
        ]
    )
    engine = BacktestEngine(broker=BrokerSimulator(initial_cash=10_000.0))

    result = engine.run(CooldownStrategy(), data, _build_config(cooldown_bars=2))

    assert [fill.side for fill in result.fills] == [SignalSide.LONG, SignalSide.FLAT, SignalSide.LONG]
    assert result.fills[2].metadata["entry_bar_index"] == 9


def test_broker_maker_taker_fees() -> None:
    broker = BrokerSimulator(initial_cash=10_000.0, maker_fee_rate=0.0, taker_fee_rate=0.0005)
    bar = {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0}

    limit_fill = broker.execute_order(
        OrderIntent(
            strategy_id="test",
            symbol="BTCUSDT",
            side=SignalSide.LONG,
            order_type=OrderType.LIMIT,
            quantity=1.0,
            limit_price=100.0,
        ),
        bar,
    )
    market_fill = broker.execute_order(
        OrderIntent(
            strategy_id="test",
            symbol="BTCUSDT",
            side=SignalSide.FLAT,
            order_type=OrderType.MARKET,
            quantity=1.0,
        ),
        bar,
    )

    assert limit_fill is not None
    assert limit_fill.fee == 0.0
    assert market_fill is not None
    assert market_fill.fee == pytest.approx(market_fill.executed_price * 0.0005)


def test_broker_backward_compat() -> None:
    broker = BrokerSimulator(fee_rate=0.001)

    assert broker.maker_fee_rate == 0.001
    assert broker.taker_fee_rate == 0.001


def test_calculate_summary_reports_trade_count_and_win_rate() -> None:
    data = _build_ohlcv(
        [
            100.0,
            101.0,
            102.0,
            103.0,
            104.0,
            105.0,
            107.0,
            109.0,
            111.0,
            112.0,
            110.0,
            109.0,
            108.0,
            107.0,
            106.0,
            105.0,
            104.0,
            103.0,
            102.0,
            101.0,
        ]
    )
    engine = BacktestEngine(broker=BrokerSimulator(initial_cash=10_000.0))

    result = engine.run(FakeStrategy(), data, _build_config())
    summary = calculate_summary(result, initial_cash=10_000.0)

    assert summary.trade_count == 2
    assert summary.win_rate_pct == 100.0
