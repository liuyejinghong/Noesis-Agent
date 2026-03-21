from __future__ import annotations

from enum import Enum


class RuntimeMode(str, Enum):  # noqa: UP042
    BACKTEST = "backtest"
    TESTNET = "testnet"
    LIVE = "live"


class SignalSide(str, Enum):  # noqa: UP042
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class OrderType(str, Enum):  # noqa: UP042
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class StrategyStatus(str, Enum):  # noqa: UP042
    ACTIVE = "active"
    DRAFT = "draft"
    ARCHIVED = "archived"
