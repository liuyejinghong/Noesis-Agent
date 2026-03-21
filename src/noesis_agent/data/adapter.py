# pyright: reportMissingTypeStubs=false

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class MarketDataAdapter(Protocol):
    source_id: str

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> pd.DataFrame: ...

    def fetch_klines_range(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> pd.DataFrame: ...
