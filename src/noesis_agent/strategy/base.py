from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from noesis_agent.core.models import (
    AccountSnapshot,
    OrderIntent,
    PositionSnapshot,
    SignalEvent,
    StrategyRuntimeConfig,
)


class StrategyBase(ABC):
    strategy_id: str
    version: str = "0.1.0"
    warmup_bars: int = 0

    def configure(self, config: StrategyRuntimeConfig) -> None:
        self.warmup_bars = max(self.warmup_bars, 0)

    @abstractmethod
    def on_bar(
        self,
        data: pd.DataFrame,
        position: PositionSnapshot | None,
        account: AccountSnapshot | None,
    ) -> list[SignalEvent]:
        raise NotImplementedError

    @abstractmethod
    def build_order_intents(
        self,
        signals: list[SignalEvent],
        config: StrategyRuntimeConfig,
    ) -> list[OrderIntent]:
        raise NotImplementedError
