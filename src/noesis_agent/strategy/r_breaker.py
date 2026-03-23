# pyright: reportMissingTypeStubs=false, reportImplicitOverride=false, reportAny=false

from __future__ import annotations

import re
from datetime import UTC, datetime

import pandas as pd

from noesis_agent.core.enums import OrderType, SignalSide
from noesis_agent.core.models import (
    AccountSnapshot,
    OrderIntent,
    PositionSnapshot,
    SignalEvent,
    StrategyRuntimeConfig,
)
from noesis_agent.strategy.base import StrategyBase


class RBreaker(StrategyBase):
    strategy_id = "r_breaker"
    version = "1.0.0"
    warmup_bars = 2

    def configure(self, config: StrategyRuntimeConfig) -> None:
        super().configure(config)
        params = config.parameters
        self.pivot_mode = str(params.get("pivot_mode", "rolling"))
        self.rolling_bars = int(params.get("rolling_bars", 96))
        self.order_mode = str(params.get("order_mode", "market"))
        self.reverse_enabled = bool(params.get("reverse_enabled", True))
        self.reverse_to_opposite = bool(params.get("reverse_to_opposite", False))
        self.warmup_bars = max(
            self.warmup_bars,
            self.rolling_bars + 1 if self.pivot_mode == "rolling" else 2,
        )
        self._session_high: float | None = None
        self._session_low: float | None = None
        self._touched_sell_setup = False
        self._touched_buy_setup = False

    def on_bar(
        self,
        data: pd.DataFrame,
        position: PositionSnapshot | None,
        account: AccountSnapshot | None,
    ) -> list[SignalEvent]:
        del account
        if len(data) < self.warmup_bars:
            return []

        levels = self._compute_levels(data)
        if levels is None:
            return []

        current = data.iloc[-1]
        close = float(current["close"])
        high = float(current["high"])
        low = float(current["low"])
        timestamp = data.index[-1]

        self._update_session_tracking(high, low, levels)

        current_side = position.side if position is not None else SignalSide.FLAT
        if current_side is SignalSide.FLAT:
            if close > levels["break_buy"]:
                return [self._signal(timestamp, SignalSide.LONG, f"close > break_buy {levels['break_buy']:.2f}")]
            if close < levels["break_sell"]:
                return [self._signal(timestamp, SignalSide.SHORT, f"close < break_sell {levels['break_sell']:.2f}")]
            return []

        if not self.reverse_enabled:
            return []

        signals: list[SignalEvent] = []
        if current_side is SignalSide.LONG and self._touched_sell_setup and close < levels["sell_enter"]:
            signals.append(self._signal(timestamp, SignalSide.FLAT, f"close < sell_enter {levels['sell_enter']:.2f}"))
            if self.reverse_to_opposite:
                signals.append(self._signal(timestamp, SignalSide.SHORT, "reverse to short"))
            self._touched_sell_setup = False
        elif current_side is SignalSide.SHORT and self._touched_buy_setup and close > levels["buy_enter"]:
            signals.append(self._signal(timestamp, SignalSide.FLAT, f"close > buy_enter {levels['buy_enter']:.2f}"))
            if self.reverse_to_opposite:
                signals.append(self._signal(timestamp, SignalSide.LONG, "reverse to long"))
            self._touched_buy_setup = False
        return signals

    def build_order_intents(
        self,
        signals: list[SignalEvent],
        config: StrategyRuntimeConfig,
    ) -> list[OrderIntent]:
        quantity = float(config.risk.get("max_position_size", 0.01))
        return [
            OrderIntent(
                strategy_id=self.strategy_id,
                symbol=config.symbol,
                side=signal.side,
                order_type=(
                    OrderType.LIMIT
                    if self.order_mode == "limit" and signal.side != SignalSide.FLAT
                    else OrderType.MARKET
                ),
                quantity=quantity,
                limit_price=(
                    self._extract_price_from_reason(signal.reason)
                    if self.order_mode == "limit" and signal.side != SignalSide.FLAT
                    else None
                ),
            )
            for signal in signals
        ]

    def _compute_levels(self, data: pd.DataFrame) -> dict[str, float] | None:
        if self.pivot_mode == "rolling":
            return self._compute_rolling_levels(data)
        return self._compute_daily_levels(data)

    def _compute_rolling_levels(self, data: pd.DataFrame) -> dict[str, float] | None:
        if len(data) < self.rolling_bars + 1:
            return None
        window = data.iloc[-(self.rolling_bars + 1) : -1]
        return self._levels_from_hlc(
            high_price=float(window["high"].max()),
            low_price=float(window["low"].min()),
            close_price=float(window.iloc[-1]["close"]),
        )

    def _compute_daily_levels(self, data: pd.DataFrame) -> dict[str, float] | None:
        dates = [ts.tz_convert(UTC).date() if isinstance(ts, pd.Timestamp) else ts.date() for ts in data.index]
        current_date = dates[-1]
        prev_indices = [idx for idx, date in enumerate(dates) if date < current_date]
        if not prev_indices:
            return None
        last_date = dates[prev_indices[-1]]
        day_rows = [idx for idx, date in enumerate(dates) if date == last_date]
        day_data = data.iloc[day_rows]
        return self._levels_from_hlc(
            high_price=float(day_data["high"].max()),
            low_price=float(day_data["low"].min()),
            close_price=float(day_data.iloc[-1]["close"]),
        )

    @staticmethod
    def _levels_from_hlc(high_price: float, low_price: float, close_price: float) -> dict[str, float]:
        pivot = (high_price + low_price + close_price) / 3.0
        return {
            "pivot": pivot,
            "break_buy": high_price + 2.0 * (pivot - low_price),
            "sell_setup": pivot + (high_price - low_price),
            "sell_enter": 2.0 * pivot - low_price,
            "buy_enter": 2.0 * pivot - high_price,
            "buy_setup": pivot - (high_price - low_price),
            "break_sell": low_price - 2.0 * (high_price - pivot),
        }

    def _update_session_tracking(self, high: float, low: float, levels: dict[str, float]) -> None:
        self._session_high = high if self._session_high is None else max(self._session_high, high)
        self._session_low = low if self._session_low is None else min(self._session_low, low)
        if high >= levels["sell_setup"]:
            self._touched_sell_setup = True
        if low <= levels["buy_setup"]:
            self._touched_buy_setup = True

    @staticmethod
    def _extract_price_from_reason(reason: str) -> float | None:
        match = re.search(r"[\d.]+", reason)
        return float(match.group()) if match else None

    def _signal(self, timestamp: object, side: SignalSide, reason: str) -> SignalEvent:
        if isinstance(timestamp, pd.Timestamp):
            ts = timestamp.to_pydatetime()
        elif isinstance(timestamp, datetime):
            ts = timestamp
        else:
            ts = datetime.now(tz=UTC)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return SignalEvent(
            strategy_id=self.strategy_id,
            symbol="",
            side=side,
            timestamp=ts,
            reason=reason,
        )
