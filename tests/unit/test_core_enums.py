# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide, StrategyStatus


def test_runtime_mode_values_are_identical_to_v1() -> None:
    assert RuntimeMode.BACKTEST == "backtest"
    assert RuntimeMode.TESTNET == "testnet"
    assert RuntimeMode.LIVE == "live"


def test_signal_side_values_are_identical_to_v1() -> None:
    assert SignalSide.LONG == "long"
    assert SignalSide.SHORT == "short"
    assert SignalSide.FLAT == "flat"


def test_order_type_values_are_identical_to_v1() -> None:
    assert OrderType.MARKET == "market"
    assert OrderType.LIMIT == "limit"
    assert OrderType.STOP == "stop"


def test_strategy_status_values_are_identical_to_v1() -> None:
    assert StrategyStatus.ACTIVE == "active"
    assert StrategyStatus.DRAFT == "draft"
    assert StrategyStatus.ARCHIVED == "archived"


def test_enums_are_str_subtypes() -> None:
    assert isinstance(RuntimeMode.BACKTEST, str)
    assert isinstance(SignalSide.LONG, str)
    assert isinstance(OrderType.MARKET, str)
    assert isinstance(StrategyStatus.ACTIVE, str)
