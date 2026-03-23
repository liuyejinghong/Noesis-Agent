# pyright: reportMissingTypeStubs=false, reportPrivateUsage=false, reportUnusedCallResult=false, reportAny=false, reportCallIssue=false, reportArgumentType=false

from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide
from noesis_agent.core.models import PositionSnapshot, SignalEvent, StrategyRuntimeConfig
from noesis_agent.strategy.r_breaker import RBreaker
from noesis_agent.strategy.registry import StrategyRegistry


def make_ohlcv(
    n: int,
    base_price: float = 100.0,
    volatility: float = 2.0,
) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2025-01-01", periods=n, freq="15min", tz="UTC")
    close = base_price + np.cumsum(np.random.randn(n) * volatility)
    high = close + np.abs(np.random.randn(n)) * volatility
    low = close - np.abs(np.random.randn(n)) * volatility
    open_ = close + np.random.randn(n) * volatility * 0.5
    volume = np.random.randint(100, 1000, n).astype(float)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


def make_config(**parameters: object) -> StrategyRuntimeConfig:
    return StrategyRuntimeConfig(
        strategy_id="r_breaker",
        symbol="BTCUSDT",
        timeframe="15m",
        mode=RuntimeMode.BACKTEST,
        parameters=parameters,
        risk={"max_position_size": 0.25},
    )


def make_breakout_frame(current_close: float) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=4, freq="15min", tz="UTC")
    return pd.DataFrame(
        {
            "open": [100.0, 100.0, 100.0, current_close],
            "high": [110.0, 110.0, 110.0, current_close + 1.0],
            "low": [90.0, 90.0, 90.0, current_close - 1.0],
            "close": [100.0, 100.0, 100.0, current_close],
            "volume": [1000.0, 1000.0, 1000.0, 1000.0],
        },
        index=index,
    )


def make_choppy_breakout_frame(current_close: float = 131.0) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=24, freq="15min", tz="UTC")
    close = [100.0 if idx % 2 == 0 else 101.0 for idx in range(23)] + [current_close]
    high = [110.0] * 23 + [current_close + 1.0]
    low = [90.0] * 23 + [current_close - 1.0]
    return pd.DataFrame(
        {
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1000.0] * 24,
        },
        index=index,
    )


def test_levels_from_hlc() -> None:
    levels = RBreaker._levels_from_hlc(110.0, 90.0, 100.0)

    assert levels == {
        "pivot": 100.0,
        "break_buy": 130.0,
        "sell_setup": 120.0,
        "sell_enter": 110.0,
        "buy_enter": 90.0,
        "buy_setup": 80.0,
        "break_sell": 70.0,
    }
    assert levels["break_buy"] >= levels["sell_setup"] >= levels["sell_enter"]
    assert levels["sell_enter"] >= levels["buy_enter"] >= levels["buy_setup"] >= levels["break_sell"]


def test_rolling_levels() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=10))
    data = make_ohlcv(100)

    levels = strategy._compute_rolling_levels(data)
    window = data.iloc[-11:-1]
    expected = RBreaker._levels_from_hlc(
        float(window["high"].max()),
        float(window["low"].min()),
        float(window.iloc[-1]["close"]),
    )

    assert levels == expected


def test_daily_levels() -> None:
    index = pd.date_range("2025-01-01", periods=6, freq="12h", tz="UTC")
    data = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "high": [105.0, 110.0, 120.0, 121.0, 130.0, 131.0],
            "low": [95.0, 90.0, 100.0, 101.0, 110.0, 111.0],
            "close": [101.0, 100.0, 103.0, 104.0, 112.0, 113.0],
            "volume": [1000.0] * 6,
        },
        index=index,
    )
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="daily"))

    levels = strategy._compute_daily_levels(data)
    prev_day = data.loc["2025-01-02"]
    expected = RBreaker._levels_from_hlc(
        float(prev_day["high"].max()),
        float(prev_day["low"].min()),
        float(prev_day.iloc[-1]["close"]),
    )

    assert levels == expected


def test_breakout_long() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=3))

    signals = strategy.on_bar(make_breakout_frame(131.0), position=None, account=None)

    assert [signal.side for signal in signals] == [SignalSide.LONG]


def test_breakout_short() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=3))

    signals = strategy.on_bar(make_breakout_frame(69.0), position=None, account=None)

    assert [signal.side for signal in signals] == [SignalSide.SHORT]


def test_factor_filters_block_signals_when_direction_efficiency_is_below_min() -> None:
    strategy = RBreaker()
    strategy.configure(
        make_config(
            pivot_mode="rolling",
            rolling_bars=3,
            factor_filters={"direction_eff_20": {"min": 0.8}},
        )
    )

    signals = strategy.on_bar(make_choppy_breakout_frame(), position=None, account=None)

    assert signals == []


def test_no_factor_filters_preserves_existing_breakout_behavior() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=3))

    signals = strategy.on_bar(make_choppy_breakout_frame(), position=None, account=None)

    assert [signal.side for signal in signals] == [SignalSide.LONG]


@pytest.mark.parametrize(
    ("factor_filters", "expected_warmup"),
    [
        ({"direction_eff_20": {"min": 0.15}}, 21),
        ({"ma_slope_50_10": {"min": 0.0}}, 60),
    ],
)
def test_factor_filters_extend_warmup_bars(
    factor_filters: dict[str, dict[str, float]],
    expected_warmup: int,
) -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=3, factor_filters=factor_filters))

    assert strategy.warmup_bars == expected_warmup


def test_configure_raises_for_unknown_factor_filter() -> None:
    strategy = RBreaker()

    with pytest.raises(KeyError, match="Unknown factor: missing_factor"):
        strategy.configure(
            make_config(
                pivot_mode="rolling",
                rolling_bars=3,
                factor_filters={"missing_factor": {"min": 0.1}},
            )
        )


def test_no_signal_in_range() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=3))

    signals = strategy.on_bar(make_breakout_frame(100.0), position=None, account=None)

    assert signals == []


def test_reversal_long_to_flat() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=3))
    position = PositionSnapshot(symbol="BTCUSDT", side=SignalSide.LONG, quantity=1.0)

    setup_touch = make_breakout_frame(115.0)
    setup_touch.iloc[-1, setup_touch.columns.get_loc("high")] = 121.0
    _ = strategy.on_bar(setup_touch, position=position, account=None)

    reversal = make_breakout_frame(109.0)
    signals = strategy.on_bar(reversal, position=position, account=None)

    assert [signal.side for signal in signals] == [SignalSide.FLAT]


def test_reversal_short_to_flat() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=3))
    position = PositionSnapshot(symbol="BTCUSDT", side=SignalSide.SHORT, quantity=1.0)

    setup_touch = make_breakout_frame(85.0)
    setup_touch.iloc[-1, setup_touch.columns.get_loc("low")] = 79.0
    _ = strategy.on_bar(setup_touch, position=position, account=None)

    reversal = make_breakout_frame(91.0)
    signals = strategy.on_bar(reversal, position=position, account=None)

    assert [signal.side for signal in signals] == [SignalSide.FLAT]


def test_reversal_disabled() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=3, reverse_enabled=False))
    position = PositionSnapshot(symbol="BTCUSDT", side=SignalSide.LONG, quantity=1.0)
    data = make_breakout_frame(109.0)
    data.iloc[-1, data.columns.get_loc("high")] = 121.0

    signals = strategy.on_bar(data, position=position, account=None)

    assert signals == []


def test_reverse_to_opposite() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=3, reverse_to_opposite=True))
    position = PositionSnapshot(symbol="BTCUSDT", side=SignalSide.LONG, quantity=1.0)
    data = make_breakout_frame(109.0)
    data.iloc[-1, data.columns.get_loc("high")] = 121.0

    signals = strategy.on_bar(data, position=position, account=None)

    assert [signal.side for signal in signals] == [SignalSide.FLAT, SignalSide.SHORT]


def test_warmup() -> None:
    strategy = RBreaker()
    strategy.configure(make_config(pivot_mode="rolling", rolling_bars=10))

    signals = strategy.on_bar(make_ohlcv(10), position=None, account=None)

    assert signals == []


def test_configure_sets_params() -> None:
    strategy = RBreaker()
    strategy.configure(
        make_config(
            pivot_mode="daily",
            rolling_bars=48,
            order_mode="limit",
            reverse_enabled=False,
            reverse_to_opposite=True,
        )
    )

    assert strategy.pivot_mode == "daily"
    assert strategy.rolling_bars == 48
    assert strategy.order_mode == "limit"
    assert strategy.reverse_enabled is False
    assert strategy.reverse_to_opposite is True
    assert strategy.warmup_bars == 2


def test_limit_order_mode() -> None:
    strategy = RBreaker()
    config = make_config(order_mode="limit")
    strategy.configure(config)
    signals = [
        SignalEvent(
            strategy_id="r_breaker",
            symbol="BTCUSDT",
            side=SignalSide.LONG,
            timestamp=datetime.now(tz=UTC),
            reason="突破买入线 95000.00",
        )
    ]

    intents = strategy.build_order_intents(signals, config)

    assert len(intents) == 1
    assert intents[0].order_type is OrderType.LIMIT
    assert intents[0].limit_price == 95000.0
    assert intents[0].quantity == 0.25
    assert intents[0].side is SignalSide.LONG
    assert intents[0].symbol == "BTCUSDT"


def test_market_order_mode() -> None:
    strategy = RBreaker()
    config = make_config()
    strategy.configure(config)
    signals = [
        SignalEvent(
            strategy_id="r_breaker",
            symbol="BTCUSDT",
            side=SignalSide.LONG,
            timestamp=datetime.now(tz=UTC),
            reason="突破买入线 95000.00",
        )
    ]

    intents = strategy.build_order_intents(signals, config)

    assert len(intents) == 1
    assert intents[0].order_type is OrderType.MARKET
    assert intents[0].limit_price is None
    assert intents[0].quantity == 0.25
    assert intents[0].side is SignalSide.LONG
    assert intents[0].symbol == "BTCUSDT"


def test_limit_order_mode_keeps_flat_exit_as_market() -> None:
    strategy = RBreaker()
    config = make_config(order_mode="limit")
    strategy.configure(config)
    signals = [
        SignalEvent(
            strategy_id="r_breaker",
            symbol="BTCUSDT",
            side=SignalSide.FLAT,
            timestamp=datetime.now(tz=UTC),
            reason="close < sell_enter 93000.00",
        )
    ]

    intents = strategy.build_order_intents(signals, config)

    assert len(intents) == 1
    assert intents[0].order_type is OrderType.MARKET
    assert intents[0].limit_price is None


def test_strategy_registry() -> None:
    strategy = StrategyRegistry().build_strategy("r_breaker")

    assert strategy.strategy_id == "r_breaker"
