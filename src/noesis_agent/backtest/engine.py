# pyright: reportMissingTypeStubs=false, reportAny=false, reportUnusedCallResult=false

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from noesis_agent.backtest.broker import BrokerFill, BrokerSimulator
from noesis_agent.core.enums import SignalSide
from noesis_agent.core.models import PositionSnapshot, SignalEvent, StrategyRuntimeConfig, generate_run_id
from noesis_agent.strategy.base import StrategyBase


class BacktestBarResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    timestamp: Any
    close: float
    equity: float
    cash: float
    position_quantity: float
    position_side: str | None
    signal_count: int
    fill_count: int


class BacktestRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    strategy_id: str
    bars_processed: int
    fills: list[BrokerFill] = Field(default_factory=list)
    bar_results: list[BacktestBarResult] = Field(default_factory=list)
    final_equity: float = 0.0
    final_cash: float = 0.0
    realized_pnl: float = 0.0
    fees_paid: float = 0.0


@dataclass(slots=True)
class TradeManagementState:
    trailing_reference_price: float | None = None
    last_exit_bar_index: int | None = None
    pending_entry_side: SignalSide | None = None
    pending_entry_count: int = 0


class BacktestEngine:
    def __init__(self, broker: BrokerSimulator | None = None) -> None:
        self.broker = broker or BrokerSimulator()

    def run(
        self,
        strategy: StrategyBase,
        data: pd.DataFrame,
        config: StrategyRuntimeConfig,
        warmup_bars: int | None = None,
        trading_start_index: int = 0,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> BacktestRunResult:
        run_id = generate_run_id("backtest")
        fills: list[BrokerFill] = []
        bar_results: list[BacktestBarResult] = []
        required_warmup = warmup_bars if warmup_bars is not None else 1
        trade_management = dict(config.trade_management)
        state = TradeManagementState()

        for bar_index in range(len(data)):
            window = data.iloc[: bar_index + 1]
            current_bar = window.iloc[-1]
            _ = self.broker.mark_to_market(self._bar_value(current_bar, "close"))

            if len(window) <= required_warmup or bar_index < trading_start_index:
                bar_results.append(self._build_bar_result(bar_index, current_bar, 0, 0))
                if progress_callback is not None:
                    progress_callback(bar_index + 1, len(data))
                continue

            fill_count = 0
            exit_fill = self._maybe_apply_trade_management_exit(
                bar_index=bar_index,
                current_bar=current_bar,
                trade_management=trade_management,
                state=state,
            )
            if exit_fill is not None:
                fills.append(exit_fill)
                fill_count += 1
                bar_results.append(self._build_bar_result(bar_index, current_bar, 0, fill_count))
                if progress_callback is not None:
                    progress_callback(bar_index + 1, len(data))
                continue

            signals = strategy.on_bar(
                data=window,
                position=self.broker.state.position,
                account=self.broker.account_snapshot(),
            )
            gated_signals = self._apply_entry_trade_management(
                bar_index=bar_index,
                signals=signals,
                trade_management=trade_management,
                state=state,
            )
            intents = strategy.build_order_intents(gated_signals, config)
            for intent in intents:
                previous_position = self.broker.state.position
                intent = intent.model_copy(update={"metadata": {**intent.metadata, "entry_bar_index": bar_index}})
                fill = self.broker.execute_order(
                    intent,
                    {
                        "open": self._bar_value(current_bar, "open"),
                        "high": self._bar_value(current_bar, "high"),
                        "low": self._bar_value(current_bar, "low"),
                        "close": self._bar_value(current_bar, "close"),
                    },
                )
                if fill is not None:
                    self._update_trade_management_after_fill(
                        bar_index=bar_index,
                        current_bar=current_bar,
                        previous_position=previous_position,
                        state=state,
                    )
                    fills.append(fill)
                    fill_count += 1

            bar_results.append(self._build_bar_result(bar_index, current_bar, len(gated_signals), fill_count))
            if progress_callback is not None:
                progress_callback(bar_index + 1, len(data))

        if progress_callback is not None and len(data) == 0:
            progress_callback(0, 0)

        return BacktestRunResult(
            run_id=run_id,
            strategy_id=config.strategy_id,
            bars_processed=len(data),
            fills=fills,
            bar_results=bar_results,
            final_equity=self.broker.state.equity,
            final_cash=self.broker.state.cash,
            realized_pnl=self.broker.state.realized_pnl,
            fees_paid=self.broker.state.fees_paid,
        )

    def _build_bar_result(
        self,
        bar_index: int,
        current_bar: pd.Series,
        signal_count: int,
        fill_count: int,
    ) -> BacktestBarResult:
        position = self.broker.state.position
        return BacktestBarResult(
            index=bar_index,
            timestamp=current_bar.name,
            close=self._bar_value(current_bar, "close"),
            equity=self.broker.state.equity,
            cash=self.broker.state.cash,
            position_quantity=0.0 if position is None else position.quantity,
            position_side=None if position is None else position.side.value,
            signal_count=signal_count,
            fill_count=fill_count,
        )

    def _maybe_apply_trade_management_exit(
        self,
        *,
        bar_index: int,
        current_bar: pd.Series,
        trade_management: dict[str, Any],
        state: TradeManagementState,
    ) -> BrokerFill | None:
        position = self.broker.state.position
        if position is None or position.entry_price is None:
            state.trailing_reference_price = None
            return None

        stop_loss_pct = self._coerce_positive_float(trade_management.get("stop_loss_pct"))
        take_profit_pct = self._coerce_positive_float(trade_management.get("take_profit_pct"))
        trailing_stop_pct = self._coerce_positive_float(trade_management.get("trailing_stop_pct"))
        max_holding_bars = self._coerce_positive_int(trade_management.get("max_holding_bars"))
        close_price = self._bar_value(current_bar, "close")
        high_price = self._bar_value(current_bar, "high")
        low_price = self._bar_value(current_bar, "low")

        if stop_loss_pct is not None:
            stop_fill = self._build_stop_loss_exit(
                position=position,
                stop_loss_pct=stop_loss_pct,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
            )
            if stop_fill is not None:
                self._mark_exit(bar_index=bar_index, state=state)
                return stop_fill

        if take_profit_pct is not None:
            take_profit_fill = self._build_take_profit_exit(
                position=position,
                take_profit_pct=take_profit_pct,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
            )
            if take_profit_fill is not None:
                self._mark_exit(bar_index=bar_index, state=state)
                return take_profit_fill

        if trailing_stop_pct is not None:
            trailing_stop_fill = self._build_trailing_stop_exit(
                position=position,
                trailing_stop_pct=trailing_stop_pct,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                state=state,
            )
            if trailing_stop_fill is not None:
                self._mark_exit(bar_index=bar_index, state=state)
                return trailing_stop_fill

        if max_holding_bars is not None and position.entry_bar_index is not None:
            if (bar_index - position.entry_bar_index) >= max_holding_bars:
                fill = self.broker.close_position(
                    execution_price=close_price,
                    reason="max_holding_bars_reached",
                    bar_close=close_price,
                )
                if fill is not None:
                    self._mark_exit(bar_index=bar_index, state=state)
                return fill

        self._update_trailing_reference(
            position_side=position.side,
            high_price=high_price,
            low_price=low_price,
            reference_price=position.entry_price,
            state=state,
        )
        return None

    def _build_stop_loss_exit(
        self,
        *,
        position: PositionSnapshot,
        stop_loss_pct: float,
        high_price: float,
        low_price: float,
        close_price: float,
    ) -> BrokerFill | None:
        assert position.entry_price is not None
        slip_multiplier = self.broker.slippage_bps / 10_000
        if position.side == SignalSide.LONG:
            stop_price = position.entry_price * (1 - stop_loss_pct)
            if low_price <= stop_price:
                execution_price = stop_price * (1 - slip_multiplier)
                return self.broker.close_position(
                    execution_price=execution_price,
                    reason="stop_loss_pct_hit",
                    bar_close=close_price,
                )
            return None

        stop_price = position.entry_price * (1 + stop_loss_pct)
        if high_price >= stop_price:
            execution_price = stop_price * (1 + slip_multiplier)
            return self.broker.close_position(
                execution_price=execution_price,
                reason="stop_loss_pct_hit",
                bar_close=close_price,
            )
        return None

    def _build_take_profit_exit(
        self,
        *,
        position: PositionSnapshot,
        take_profit_pct: float,
        high_price: float,
        low_price: float,
        close_price: float,
    ) -> BrokerFill | None:
        assert position.entry_price is not None
        if position.side == SignalSide.LONG:
            target_price = position.entry_price * (1 + take_profit_pct)
            if high_price >= target_price:
                return self.broker.close_position(
                    execution_price=target_price,
                    reason="take_profit_pct_hit",
                    bar_close=close_price,
                )
            return None

        target_price = position.entry_price * (1 - take_profit_pct)
        if low_price <= target_price:
            return self.broker.close_position(
                execution_price=target_price,
                reason="take_profit_pct_hit",
                bar_close=close_price,
            )
        return None

    def _build_trailing_stop_exit(
        self,
        *,
        position: PositionSnapshot,
        trailing_stop_pct: float,
        high_price: float,
        low_price: float,
        close_price: float,
        state: TradeManagementState,
    ) -> BrokerFill | None:
        assert position.entry_price is not None
        reference_price = state.trailing_reference_price or position.entry_price
        slip_multiplier = self.broker.slippage_bps / 10_000
        if position.side == SignalSide.LONG:
            stop_price = reference_price * (1 - trailing_stop_pct)
            if low_price <= stop_price:
                execution_price = stop_price * (1 - slip_multiplier)
                return self.broker.close_position(
                    execution_price=execution_price,
                    reason="trailing_stop_pct_hit",
                    bar_close=close_price,
                )
            return None

        stop_price = reference_price * (1 + trailing_stop_pct)
        if high_price >= stop_price:
            execution_price = stop_price * (1 + slip_multiplier)
            return self.broker.close_position(
                execution_price=execution_price,
                reason="trailing_stop_pct_hit",
                bar_close=close_price,
            )
        return None

    def _apply_entry_trade_management(
        self,
        *,
        bar_index: int,
        signals: list[SignalEvent],
        trade_management: dict[str, Any],
        state: TradeManagementState,
    ) -> list[SignalEvent]:
        if self.broker.state.position is not None:
            self._reset_pending_entry(state)
            return signals

        cooldown_bars = self._coerce_positive_int(trade_management.get("cooldown_bars"))
        if cooldown_bars is not None and self._is_cooldown_active(
            bar_index=bar_index,
            cooldown_bars=cooldown_bars,
            state=state,
        ):
            self._reset_pending_entry(state)
            return []

        confirm_bars = self._coerce_positive_int(trade_management.get("confirm_bars"))
        if confirm_bars is None or confirm_bars <= 1:
            if not signals:
                self._reset_pending_entry(state)
            return signals
        if not signals:
            self._reset_pending_entry(state)
            return []

        signal_side = self._extract_signal_side(signals)
        if signal_side is None:
            self._reset_pending_entry(state)
            return signals
        if state.pending_entry_side == signal_side:
            state.pending_entry_count += 1
        else:
            state.pending_entry_side = signal_side
            state.pending_entry_count = 1

        if state.pending_entry_count < confirm_bars:
            return []

        self._reset_pending_entry(state)
        return signals

    def _update_trade_management_after_fill(
        self,
        *,
        bar_index: int,
        current_bar: pd.Series,
        previous_position: PositionSnapshot | None,
        state: TradeManagementState,
    ) -> None:
        position = self.broker.state.position
        if position is None:
            if previous_position is not None:
                self._mark_exit(bar_index=bar_index, state=state)
            return
        if previous_position is None or previous_position.side != position.side:
            state.trailing_reference_price = position.entry_price
            self._reset_pending_entry(state)
            return
        if state.trailing_reference_price is None:
            self._update_trailing_reference(
                position_side=position.side,
                high_price=self._bar_value(current_bar, "high"),
                low_price=self._bar_value(current_bar, "low"),
                reference_price=position.entry_price or self._bar_value(current_bar, "close"),
                state=state,
            )

    def _update_trailing_reference(
        self,
        *,
        position_side: SignalSide,
        high_price: float,
        low_price: float,
        reference_price: float,
        state: TradeManagementState,
    ) -> None:
        current_reference = state.trailing_reference_price or reference_price
        if position_side == SignalSide.LONG:
            state.trailing_reference_price = max(current_reference, high_price)
            return
        state.trailing_reference_price = min(current_reference, low_price)

    def _mark_exit(self, *, bar_index: int, state: TradeManagementState) -> None:
        state.trailing_reference_price = None
        state.last_exit_bar_index = bar_index
        self._reset_pending_entry(state)

    @staticmethod
    def _reset_pending_entry(state: TradeManagementState) -> None:
        state.pending_entry_side = None
        state.pending_entry_count = 0

    @staticmethod
    def _extract_signal_side(signals: list[SignalEvent]) -> SignalSide | None:
        if not signals:
            return None
        signal_side = signals[0].side
        for signal in signals[1:]:
            if signal.side != signal_side:
                return None
        return signal_side

    @staticmethod
    def _is_cooldown_active(
        *,
        bar_index: int,
        cooldown_bars: int,
        state: TradeManagementState,
    ) -> bool:
        if state.last_exit_bar_index is None:
            return False
        return (bar_index - state.last_exit_bar_index) <= cooldown_bars

    @staticmethod
    def _coerce_positive_float(value: Any) -> float | None:
        if value in (None, "", 0):
            return None
        numeric = float(value)
        return numeric if numeric > 0 else None

    @staticmethod
    def _coerce_positive_int(value: Any) -> int | None:
        if value in (None, "", 0):
            return None
        numeric = int(value)
        return numeric if numeric > 0 else None

    @staticmethod
    def _bar_value(current_bar: pd.Series, key: str) -> float:
        return float(current_bar.loc[key])
