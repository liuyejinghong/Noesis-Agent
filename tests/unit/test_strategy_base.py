# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide
from noesis_agent.core.models import (
    AccountSnapshot,
    OrderIntent,
    PositionSnapshot,
    SignalEvent,
    StrategyRuntimeConfig,
)
from noesis_agent.strategy.base import StrategyBase
from noesis_agent.strategy.registry import StrategyRegistry


class FakeStrategy(StrategyBase):
    strategy_id = "fake_strategy"
    version = "1.0.0"
    warmup_bars = 5

    def on_bar(
        self,
        data: pd.DataFrame,
        position: PositionSnapshot | None,
        account: AccountSnapshot | None,
    ) -> list[SignalEvent]:
        if len(data) < self.warmup_bars:
            return []
        return [
            SignalEvent(
                strategy_id=self.strategy_id,
                symbol="BTCUSDT",
                side=SignalSide.LONG,
                timestamp=datetime.now(tz=UTC),
                reason="test_signal",
            )
        ]

    def build_order_intents(
        self,
        signals: list[SignalEvent],
        config: StrategyRuntimeConfig,
    ) -> list[OrderIntent]:
        return [
            OrderIntent(
                strategy_id=self.strategy_id,
                symbol=config.symbol,
                side=s.side,
                order_type=OrderType.MARKET,
                quantity=0.01,
            )
            for s in signals
        ]


def test_strategy_base_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        StrategyBase()  # type: ignore[abstract]


def test_fake_strategy_has_required_attributes() -> None:
    strategy = FakeStrategy()

    assert strategy.strategy_id == "fake_strategy"
    assert strategy.version == "1.0.0"
    assert strategy.warmup_bars == 5


def test_strategy_base_default_version() -> None:
    class MinimalStrategy(StrategyBase):
        strategy_id = "minimal"

        def on_bar(self, data, position, account):
            return []

        def build_order_intents(self, signals, config):
            return []

    strategy = MinimalStrategy()

    assert strategy.version == "0.1.0"


def test_strategy_base_default_warmup_bars() -> None:
    class MinimalStrategy(StrategyBase):
        strategy_id = "minimal"

        def on_bar(self, data, position, account):
            return []

        def build_order_intents(self, signals, config):
            return []

    strategy = MinimalStrategy()

    assert strategy.warmup_bars == 0


def test_configure_clamps_negative_warmup_bars() -> None:
    class NegativeWarmup(StrategyBase):
        strategy_id = "neg_warmup"
        warmup_bars = -5

        def on_bar(self, data, position, account):
            return []

        def build_order_intents(self, signals, config):
            return []

    strategy = NegativeWarmup()
    config = StrategyRuntimeConfig(
        strategy_id="neg_warmup",
        symbol="BTCUSDT",
        timeframe="15m",
        mode=RuntimeMode.BACKTEST,
    )
    strategy.configure(config)

    assert strategy.warmup_bars == 0


def test_on_bar_returns_signals() -> None:
    strategy = FakeStrategy()
    index = pd.to_datetime([f"2026-03-{21 + i}T00:00:00Z" for i in range(6)], utc=True)
    data = pd.DataFrame(
        {
            "open": [100.0] * 6,
            "high": [105.0] * 6,
            "low": [95.0] * 6,
            "close": [101.0] * 6,
            "volume": [1000.0] * 6,
        },
        index=index,
    )

    signals = strategy.on_bar(data, position=None, account=None)

    assert len(signals) == 1
    assert signals[0].side is SignalSide.LONG
    assert signals[0].reason == "test_signal"


def test_build_order_intents_returns_intents_from_signals() -> None:
    strategy = FakeStrategy()
    config = StrategyRuntimeConfig(
        strategy_id="fake_strategy",
        symbol="ETHUSDT",
        timeframe="1h",
        mode=RuntimeMode.BACKTEST,
    )
    signals = [
        SignalEvent(
            strategy_id="fake_strategy",
            symbol="ETHUSDT",
            side=SignalSide.SHORT,
            timestamp=datetime.now(tz=UTC),
            reason="test",
        )
    ]

    intents = strategy.build_order_intents(signals, config)

    assert len(intents) == 1
    assert intents[0].symbol == "ETHUSDT"
    assert intents[0].side is SignalSide.SHORT
    assert intents[0].order_type is OrderType.MARKET
    assert intents[0].quantity == 0.01


def test_registry_register_and_get() -> None:
    registry = StrategyRegistry()
    registry.register(FakeStrategy)

    assert registry.get("fake_strategy") is FakeStrategy


def test_registry_get_unknown_returns_none() -> None:
    registry = StrategyRegistry()

    assert registry.get("nonexistent") is None


def test_registry_list_strategies() -> None:
    registry = StrategyRegistry()
    registry.register(FakeStrategy)

    assert "fake_strategy" in registry.list_strategies()


def test_registry_build_strategy_creates_and_configures() -> None:
    registry = StrategyRegistry()
    registry.register(FakeStrategy)
    config = StrategyRuntimeConfig(
        strategy_id="fake_strategy",
        symbol="BTCUSDT",
        timeframe="15m",
        mode=RuntimeMode.BACKTEST,
    )

    strategy = registry.build_strategy("fake_strategy", config=config)

    assert isinstance(strategy, FakeStrategy)
    assert strategy.warmup_bars == 5


def test_registry_build_strategy_unknown_raises() -> None:
    registry = StrategyRegistry()

    with pytest.raises(ValueError, match="Unknown strategy"):
        registry.build_strategy("nonexistent")


def test_registry_build_strategy_without_config() -> None:
    registry = StrategyRegistry()
    registry.register(FakeStrategy)

    strategy = registry.build_strategy("fake_strategy")

    assert isinstance(strategy, FakeStrategy)
