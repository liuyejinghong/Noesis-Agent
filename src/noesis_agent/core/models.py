# pyright: reportExplicitAny=false, reportMissingImports=false, reportUnannotatedClassAttribute=false, reportUnknownVariableType=false, reportUntypedBaseClass=false

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .enums import OrderType, RuntimeMode, SignalSide


def generate_run_id(prefix: str = "run") -> str:
    stamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


class PositionSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    side: SignalSide
    quantity: float
    entry_price: float | None = None
    entry_bar_index: int | None = None


class AccountSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    balance: float
    equity: float
    leverage: float | None = None


class SignalEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    side: SignalSide
    timestamp: datetime
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    side: SignalSide
    order_type: OrderType
    quantity: float
    limit_price: float | None = None
    stop_price: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StrategyRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_id: str
    symbol: str
    timeframe: str
    mode: RuntimeMode
    parameters: dict[str, Any] = Field(default_factory=dict)
    risk: dict[str, Any] = Field(default_factory=dict)
    trade_management: dict[str, Any] = Field(default_factory=dict)


class AppContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    root_dir: Path
    config_dir: Path
    data_dir: Path
    state_dir: Path
    artifacts_dir: Path
    logs_dir: Path
