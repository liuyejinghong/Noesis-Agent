from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from noesis_agent.core.enums import OrderType, RuntimeMode, SignalSide


class ExecutionOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    side: SignalSide
    order_type: OrderType
    quantity: float
    price: float | None = None
    stop_price: float | None = None
    client_order_id: str | None = None
    exchange_order_id: str | None = None
    status: str = "pending"
    extra: dict[str, Any] = Field(default_factory=dict)


class ExecutionPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    side: SignalSide
    quantity: float
    entry_price: float | None
    leverage: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ExecutionAccount(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance: float
    equity: float
    available_balance: float | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class ExecutionContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: RuntimeMode
    read_only: bool
    exchange_id: str
    symbol: str


@runtime_checkable
class ExecutionAdapter(Protocol):
    exchange_id: str

    def normalize_order(self, payload: dict[str, Any]) -> ExecutionOrder: ...

    def normalize_position(self, payload: dict[str, Any]) -> ExecutionPosition: ...

    def normalize_account(self, payload: dict[str, Any]) -> ExecutionAccount: ...
