# pyright: reportAny=false, reportUnusedCallResult=false

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from noesis_agent.core.enums import OrderType, SignalSide
from noesis_agent.core.models import AccountSnapshot, OrderIntent, PositionSnapshot


class BrokerFill(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    side: SignalSide
    order_type: OrderType
    quantity: float
    requested_price: float | None
    executed_price: float
    fee: float
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


@dataclass(slots=True)
class BrokerState:
    cash: float
    equity: float
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    position: PositionSnapshot | None = None


class BrokerSimulator:
    def __init__(
        self,
        initial_cash: float = 10_000.0,
        fee_rate: float = 0.0004,
        slippage_bps: float = 2.0,
    ) -> None:
        self.initial_cash = initial_cash
        self.fee_rate = fee_rate
        self.slippage_bps = slippage_bps
        self.state = BrokerState(cash=initial_cash, equity=initial_cash)

    def account_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(balance=self.state.cash, equity=self.state.equity)

    def mark_to_market(self, last_price: float) -> BrokerState:
        unrealized = 0.0
        position = self.state.position
        if position is not None and position.entry_price is not None:
            if position.side == SignalSide.LONG:
                unrealized = (last_price - position.entry_price) * position.quantity
            elif position.side == SignalSide.SHORT:
                unrealized = (position.entry_price - last_price) * position.quantity
        self.state.equity = self.state.cash + unrealized
        return self.state

    def execute_order(self, intent: OrderIntent, bar: dict[str, float]) -> BrokerFill | None:
        execution_price = self._resolve_execution_price(intent, bar)
        if execution_price is None:
            _ = self.mark_to_market(bar["close"])
            return None

        fee = execution_price * intent.quantity * self.fee_rate
        realized_pnl = self._apply_fill(intent, execution_price)
        self.state.realized_pnl += realized_pnl
        self.state.cash += realized_pnl - fee
        self.state.fees_paid += fee
        _ = self.mark_to_market(bar["close"])

        requested_price = None
        if intent.order_type == OrderType.LIMIT:
            requested_price = intent.limit_price
        elif intent.order_type == OrderType.STOP:
            requested_price = intent.stop_price

        return BrokerFill(
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            quantity=intent.quantity,
            requested_price=requested_price,
            executed_price=execution_price,
            fee=fee,
            timestamp=datetime.now(tz=UTC),
            metadata={"realized_pnl": realized_pnl, **intent.metadata},
        )

    def close_position(
        self,
        *,
        execution_price: float,
        reason: str,
        bar_close: float,
    ) -> BrokerFill | None:
        position = self.state.position
        if position is None:
            _ = self.mark_to_market(bar_close)
            return None

        quantity = position.quantity
        fee = execution_price * quantity * self.fee_rate
        if position.entry_price is None:
            realized_pnl = 0.0
        elif position.side == SignalSide.LONG:
            realized_pnl = (execution_price - position.entry_price) * quantity
        else:
            realized_pnl = (position.entry_price - execution_price) * quantity

        exit_side = SignalSide.SHORT if position.side == SignalSide.LONG else SignalSide.LONG
        self.state.realized_pnl += realized_pnl
        self.state.cash += realized_pnl - fee
        self.state.fees_paid += fee
        self.state.position = None
        _ = self.mark_to_market(bar_close)
        return BrokerFill(
            symbol=position.symbol,
            side=exit_side,
            order_type=OrderType.MARKET,
            quantity=quantity,
            requested_price=None,
            executed_price=execution_price,
            fee=fee,
            timestamp=datetime.now(tz=UTC),
            metadata={"realized_pnl": realized_pnl, "exit_reason": reason},
        )

    def _resolve_execution_price(self, intent: OrderIntent, bar: dict[str, float]) -> float | None:
        close = bar["close"]
        slip_multiplier = self.slippage_bps / 10_000

        if intent.order_type == OrderType.MARKET:
            if intent.side == SignalSide.LONG:
                return close * (1 + slip_multiplier)
            if intent.side == SignalSide.SHORT:
                return close * (1 - slip_multiplier)
            return close

        if intent.order_type == OrderType.LIMIT:
            if intent.limit_price is None:
                raise ValueError("Limit order requires limit_price")
            if bar["low"] <= intent.limit_price <= bar["high"]:
                return intent.limit_price
            return None

        if intent.order_type == OrderType.STOP:
            if intent.stop_price is None:
                raise ValueError("Stop order requires stop_price")
            if intent.side == SignalSide.LONG and bar["high"] >= intent.stop_price:
                return intent.stop_price * (1 + slip_multiplier)
            if intent.side == SignalSide.SHORT and bar["low"] <= intent.stop_price:
                return intent.stop_price * (1 - slip_multiplier)
            return None

        raise ValueError(f"Unsupported order type: {intent.order_type}")

    def _apply_fill(self, intent: OrderIntent, execution_price: float) -> float:
        position = self.state.position
        if position is None:
            if intent.side == SignalSide.FLAT:
                return 0.0
            self.state.position = PositionSnapshot(
                symbol=intent.symbol,
                side=intent.side,
                quantity=intent.quantity,
                entry_price=execution_price,
                entry_bar_index=self._coerce_entry_bar_index(intent.metadata.get("entry_bar_index")),
            )
            return 0.0

        if position.side == intent.side:
            combined_quantity = position.quantity + intent.quantity
            weighted_entry = (
                (position.entry_price or execution_price) * position.quantity + execution_price * intent.quantity
            ) / combined_quantity
            self.state.position = PositionSnapshot(
                symbol=position.symbol,
                side=position.side,
                quantity=combined_quantity,
                entry_price=weighted_entry,
                entry_bar_index=position.entry_bar_index,
            )
            return 0.0

        closing_quantity = min(position.quantity, intent.quantity)
        assert position.entry_price is not None
        if position.side == SignalSide.LONG:
            realized = (execution_price - position.entry_price) * closing_quantity
        else:
            realized = (position.entry_price - execution_price) * closing_quantity

        remaining_quantity = position.quantity - closing_quantity
        incoming_remaining = 0.0 if intent.side == SignalSide.FLAT else intent.quantity - closing_quantity
        if remaining_quantity > 0:
            self.state.position = PositionSnapshot(
                symbol=position.symbol,
                side=position.side,
                quantity=remaining_quantity,
                entry_price=position.entry_price,
                entry_bar_index=position.entry_bar_index,
            )
        elif incoming_remaining > 0:
            self.state.position = PositionSnapshot(
                symbol=intent.symbol,
                side=intent.side,
                quantity=incoming_remaining,
                entry_price=execution_price,
                entry_bar_index=self._coerce_entry_bar_index(intent.metadata.get("entry_bar_index")),
            )
        else:
            self.state.position = None
        return realized

    @staticmethod
    def _coerce_entry_bar_index(value: object | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int | float | str):
            return int(value)
        raise TypeError("entry_bar_index must be int-compatible")
