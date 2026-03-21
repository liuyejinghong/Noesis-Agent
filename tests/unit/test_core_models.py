# pyright: reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide
from noesis_agent.core.models import (
    AccountSnapshot,
    AppContext,
    OrderIntent,
    PositionSnapshot,
    SignalEvent,
    StrategyRuntimeConfig,
    generate_run_id,
)

FIXTURE_ROOT = Path("fixtures/noesis")
FIXTURE_CONFIG = FIXTURE_ROOT / "config"
FIXTURE_DATA = FIXTURE_ROOT / "data"
FIXTURE_STATE = FIXTURE_ROOT / "state"
FIXTURE_ARTIFACTS = FIXTURE_ROOT / "artifacts"
FIXTURE_LOGS = FIXTURE_ROOT / "logs"
FIXTURE_OTHER_LOGS = FIXTURE_ROOT / "other-logs"


def test_generate_run_id_uses_default_prefix_and_expected_format() -> None:
    run_id = generate_run_id()

    assert re.fullmatch(r"run_\d{8}T\d{6}Z_[0-9a-f]{8}", run_id)


def test_generate_run_id_supports_custom_prefix() -> None:
    run_id = generate_run_id(prefix="session")

    assert re.fullmatch(r"session_\d{8}T\d{6}Z_[0-9a-f]{8}", run_id)


def test_generate_run_id_is_unique_across_many_calls() -> None:
    run_ids = {generate_run_id() for _ in range(100)}

    assert len(run_ids) == 100


def test_position_snapshot_defaults_match_v1() -> None:
    snapshot = PositionSnapshot(symbol="BTCUSDT", side=SignalSide.LONG, quantity=1.0)

    assert snapshot.entry_price is None
    assert snapshot.entry_bar_index is None


def test_account_snapshot_defaults_match_v1() -> None:
    snapshot = AccountSnapshot(balance=1000.0, equity=1050.0)

    assert snapshot.leverage is None


def test_signal_event_defaults_match_v1() -> None:
    event = SignalEvent(
        strategy_id="mean-reversion",
        symbol="BTCUSDT",
        side=SignalSide.LONG,
        timestamp=datetime(2026, 3, 21, tzinfo=UTC),
        reason="entry",
    )

    assert event.metadata == {}


def test_order_intent_defaults_match_v1() -> None:
    intent = OrderIntent(
        strategy_id="mean-reversion",
        symbol="BTCUSDT",
        side=SignalSide.SHORT,
        order_type=OrderType.MARKET,
        quantity=0.5,
    )

    assert intent.limit_price is None
    assert intent.stop_price is None
    assert intent.metadata == {}


def test_strategy_runtime_config_defaults_match_v1() -> None:
    config = StrategyRuntimeConfig(
        strategy_id="mean-reversion",
        symbol="BTCUSDT",
        timeframe="1h",
        mode=RuntimeMode.BACKTEST,
    )

    assert config.parameters == {}
    assert config.risk == {}
    assert config.trade_management == {}


def test_all_models_are_frozen() -> None:
    position = PositionSnapshot(symbol="BTCUSDT", side=SignalSide.LONG, quantity=1.0)
    account = AccountSnapshot(balance=1000.0, equity=1050.0)
    event = SignalEvent(
        strategy_id="mean-reversion",
        symbol="BTCUSDT",
        side=SignalSide.LONG,
        timestamp=datetime(2026, 3, 21, tzinfo=UTC),
        reason="entry",
    )
    intent = OrderIntent(
        strategy_id="mean-reversion",
        symbol="BTCUSDT",
        side=SignalSide.SHORT,
        order_type=OrderType.LIMIT,
        quantity=0.5,
    )
    config = StrategyRuntimeConfig(
        strategy_id="mean-reversion",
        symbol="BTCUSDT",
        timeframe="1h",
        mode=RuntimeMode.BACKTEST,
    )
    context = AppContext(
        root_dir=FIXTURE_ROOT,
        config_dir=FIXTURE_CONFIG,
        data_dir=FIXTURE_DATA,
        state_dir=FIXTURE_STATE,
        artifacts_dir=FIXTURE_ARTIFACTS,
        logs_dir=FIXTURE_LOGS,
    )

    with pytest.raises(ValidationError):
        position.quantity = 2.0
    with pytest.raises(ValidationError):
        account.equity = 1100.0
    with pytest.raises(ValidationError):
        event.reason = "exit"
    with pytest.raises(ValidationError):
        intent.quantity = 1.0
    with pytest.raises(ValidationError):
        config.timeframe = "4h"
    with pytest.raises(ValidationError):
        context.logs_dir = FIXTURE_OTHER_LOGS


def test_app_context_accepts_all_required_paths() -> None:
    context = AppContext(
        root_dir=FIXTURE_ROOT,
        config_dir=FIXTURE_CONFIG,
        data_dir=FIXTURE_DATA,
        state_dir=FIXTURE_STATE,
        artifacts_dir=FIXTURE_ARTIFACTS,
        logs_dir=FIXTURE_LOGS,
    )

    assert context.root_dir == FIXTURE_ROOT
    assert context.config_dir == FIXTURE_CONFIG
    assert context.data_dir == FIXTURE_DATA
    assert context.state_dir == FIXTURE_STATE
    assert context.artifacts_dir == FIXTURE_ARTIFACTS
    assert context.logs_dir == FIXTURE_LOGS
