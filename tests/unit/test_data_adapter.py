# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from typing import runtime_checkable

import pandas as pd

from noesis_agent.data.adapter import MarketDataAdapter


class FakeAdapter:
    source_id = "fake"

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int = 500,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> pd.DataFrame:
        del symbol, interval, limit, start_time_ms, end_time_ms
        return _sample_frame()

    def fetch_klines_range(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        progress_callback: object | None = None,
    ) -> pd.DataFrame:
        del symbol, interval, start_time_ms, end_time_ms, progress_callback
        return _sample_frame()


def _sample_frame() -> pd.DataFrame:
    index = pd.to_datetime(["2026-03-21T00:00:00Z", "2026-03-21T01:00:00Z"], utc=True)
    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [10.0, 12.0],
        },
        index=index,
    )


def test_market_data_adapter_is_runtime_checkable_protocol() -> None:
    assert runtime_checkable(MarketDataAdapter) is MarketDataAdapter


def test_fake_adapter_is_protocol_compliant() -> None:
    adapter = FakeAdapter()

    assert isinstance(adapter, MarketDataAdapter)


def test_market_data_adapter_returns_only_ohlcv_columns_with_utc_index() -> None:
    adapter = FakeAdapter()
    frame = adapter.fetch_klines(symbol="BTCUSDT", interval="1h")

    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert str(frame.index.tz) == "UTC"


def test_market_data_adapter_range_returns_only_ohlcv_columns_with_utc_index() -> None:
    adapter = FakeAdapter()
    frame = adapter.fetch_klines_range(
        symbol="BTCUSDT",
        interval="1h",
        start_time_ms=0,
        end_time_ms=3_600_000,
    )

    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert str(frame.index.tz) == "UTC"
