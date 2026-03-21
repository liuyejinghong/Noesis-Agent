# pyright: reportMissingImports=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from typing import runtime_checkable

import pytest
from pydantic import ValidationError

from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide
from noesis_agent.execution.base import (
    ExecutionAccount,
    ExecutionAdapter,
    ExecutionContext,
    ExecutionOrder,
    ExecutionPosition,
)


class FakeAdapter:
    exchange_id = "fake"

    def normalize_order(self, payload: dict[str, str | float]) -> ExecutionOrder:
        return ExecutionOrder(
            symbol=str(payload["symbol"]),
            side=SignalSide(str(payload["side"])),
            order_type=OrderType(str(payload["order_type"])),
            quantity=float(payload["quantity"]),
            price=float(payload["price"]),
        )

    def normalize_position(self, payload: dict[str, str | float]) -> ExecutionPosition:
        return ExecutionPosition(
            symbol=str(payload["symbol"]),
            side=SignalSide(str(payload["side"])),
            quantity=float(payload["quantity"]),
            entry_price=float(payload["entry_price"]),
        )

    def normalize_account(self, payload: dict[str, float]) -> ExecutionAccount:
        return ExecutionAccount(
            balance=float(payload["balance"]),
            equity=float(payload["equity"]),
        )


def test_execution_adapter_is_runtime_checkable_protocol() -> None:
    assert runtime_checkable(ExecutionAdapter) is ExecutionAdapter


def test_fake_adapter_is_protocol_compliant() -> None:
    adapter = FakeAdapter()

    assert isinstance(adapter, ExecutionAdapter)


def test_normalize_order_returns_execution_order_with_expected_fields() -> None:
    adapter = FakeAdapter()

    order = adapter.normalize_order(
        {
            "symbol": "BTCUSDT",
            "side": "long",
            "order_type": "limit",
            "quantity": 0.25,
            "price": 63000.0,
        }
    )

    assert order == ExecutionOrder(
        symbol="BTCUSDT",
        side=SignalSide.LONG,
        order_type=OrderType.LIMIT,
        quantity=0.25,
        price=63000.0,
    )


def test_normalize_position_returns_execution_position_with_expected_fields() -> None:
    adapter = FakeAdapter()

    position = adapter.normalize_position(
        {
            "symbol": "ETHUSDT",
            "side": "short",
            "quantity": 1.5,
            "entry_price": 3200.0,
        }
    )

    assert position == ExecutionPosition(
        symbol="ETHUSDT",
        side=SignalSide.SHORT,
        quantity=1.5,
        entry_price=3200.0,
    )


def test_normalize_account_returns_execution_account_with_expected_fields() -> None:
    adapter = FakeAdapter()

    account = adapter.normalize_account({"balance": 1000.0, "equity": 1015.0})

    assert account == ExecutionAccount(balance=1000.0, equity=1015.0)


def test_execution_context_accepts_required_fields() -> None:
    context = ExecutionContext(
        mode=RuntimeMode.TESTNET,
        read_only=True,
        exchange_id="binance",
        symbol="BTCUSDT",
    )

    assert context.mode is RuntimeMode.TESTNET
    assert context.read_only is True
    assert context.exchange_id == "binance"
    assert context.symbol == "BTCUSDT"


def test_execution_models_are_frozen() -> None:
    order = ExecutionOrder(
        symbol="BTCUSDT",
        side=SignalSide.LONG,
        order_type=OrderType.MARKET,
        quantity=1.0,
    )
    position = ExecutionPosition(
        symbol="ETHUSDT",
        side=SignalSide.SHORT,
        quantity=2.0,
        entry_price=3200.0,
    )
    account = ExecutionAccount(balance=1000.0, equity=1005.0)
    context = ExecutionContext(
        mode=RuntimeMode.LIVE,
        read_only=False,
        exchange_id="hyperliquid",
        symbol="SOLUSDT",
    )

    with pytest.raises(ValidationError):
        order.status = "filled"
    with pytest.raises(ValidationError):
        position.quantity = 3.0
    with pytest.raises(ValidationError):
        account.equity = 999.0
    with pytest.raises(ValidationError):
        context.symbol = "ETHUSDT"


def test_execution_model_defaults_match_v1() -> None:
    order = ExecutionOrder(
        symbol="BTCUSDT",
        side=SignalSide.LONG,
        order_type=OrderType.MARKET,
        quantity=0.5,
    )
    position = ExecutionPosition(
        symbol="BTCUSDT",
        side=SignalSide.LONG,
        quantity=0.5,
        entry_price=None,
    )
    account = ExecutionAccount(balance=1000.0, equity=1000.0)

    assert order.price is None
    assert order.stop_price is None
    assert order.client_order_id is None
    assert order.exchange_order_id is None
    assert order.status == "pending"
    assert order.extra == {}
    assert position.leverage is None
    assert position.extra == {}
    assert account.available_balance is None
    assert account.extra == {}
