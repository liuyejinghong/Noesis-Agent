# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from typing import cast

import pandas as pd
import pytest

from noesis_agent.data.binance import BinanceFuturesAdapter, BinanceSpotAdapter


class _MockResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


class _MockHttpClient:
    def __init__(self, payloads: list[object]) -> None:
        self._payloads = payloads
        self.calls: list[dict[str, object]] = []

    def get(self, url: str, *, params: dict[str, object], timeout: float) -> _MockResponse:
        self.calls.append({"url": url, "params": params, "timeout": timeout})
        if not self._payloads:
            raise AssertionError("No payload queued for mock client")
        return _MockResponse(self._payloads.pop(0))


def test_binance_futures_adapter_exposes_market_data_adapter_surface() -> None:
    adapter = BinanceFuturesAdapter(http_client=_MockHttpClient([[]]))

    assert adapter.source_id == "binance_usdm"
    assert hasattr(adapter, "fetch_klines")
    assert callable(adapter.fetch_klines)
    assert hasattr(adapter, "fetch_klines_range")
    assert callable(adapter.fetch_klines_range)


def test_fetch_klines_parses_binance_payload_into_utc_ohlcv_frame() -> None:
    client = _MockHttpClient(
        [
            [
                [1710979200000, "100.0", "110.0", "95.0", "105.0", "12.5", 1710982799999],
                [1710982800000, "105.0", "112.0", "101.0", "108.0", "9.2", 1710986399999],
            ]
        ]
    )
    adapter = BinanceFuturesAdapter(http_client=client)

    frame = adapter.fetch_klines(symbol="BTCUSDT", interval="1h", limit=2)
    params = cast(dict[str, object], client.calls[0]["params"])

    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert str(frame.index.tz) == "UTC"
    assert frame.index.name == "timestamp"
    assert frame.iloc[0].to_dict() == {
        "open": 100.0,
        "high": 110.0,
        "low": 95.0,
        "close": 105.0,
        "volume": 12.5,
    }
    assert params == {"symbol": "BTCUSDT", "interval": "1h", "limit": 2}


def test_fetch_klines_raises_value_error_for_binance_error_payload() -> None:
    adapter = BinanceFuturesAdapter(http_client=_MockHttpClient([{"code": -1121, "msg": "Invalid symbol."}]))

    with pytest.raises(ValueError, match="BTCUSDT"):
        _ = adapter.fetch_klines(symbol="BTCUSDT", interval="1h")


def test_fetch_klines_returns_empty_utc_ohlcv_frame_for_empty_payload() -> None:
    adapter = BinanceFuturesAdapter(http_client=_MockHttpClient([[]]))

    frame = adapter.fetch_klines(symbol="BTCUSDT", interval="1h")

    assert frame.empty
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(frame.index, pd.DatetimeIndex)
    assert str(frame.index.tz) == "UTC"


def test_fetch_klines_range_paginates_and_deduplicates_rows() -> None:
    first_page = _build_payload(start_open_ms=1710979200000, count=1500, interval_ms=60_000)
    duplicate_open_ms = 1710979200000 + (1499 * 60_000)
    second_page = _build_payload(start_open_ms=duplicate_open_ms, count=500, interval_ms=60_000)
    client = _MockHttpClient([first_page, second_page])
    adapter = BinanceFuturesAdapter(http_client=client)
    progress_updates: list[tuple[int, int]] = []

    def on_progress(current: int, total: int) -> None:
        progress_updates.append((current, total))

    frame = adapter.fetch_klines_range(
        symbol="BTCUSDT",
        interval="1m",
        start_time_ms=1710979200000,
        end_time_ms=1711099200000,
        progress_callback=on_progress,
    )

    assert len(frame) == 1999
    assert frame.index.is_monotonic_increasing
    assert not frame.index.duplicated().any()
    assert len(client.calls) == 2
    first_params = cast(dict[str, object], client.calls[0]["params"])
    second_params = cast(dict[str, object], client.calls[1]["params"])
    assert first_params["limit"] == 1500
    assert first_params["startTime"] == 1710979200000
    assert second_params["startTime"] == 1711069200000
    assert progress_updates[-1] == (120000000, 120000000)


def test_binance_spot_adapter_uses_spot_source_id() -> None:
    adapter = BinanceSpotAdapter(http_client=_MockHttpClient([[]]))

    assert adapter.source_id == "binance_spot"


def _build_payload(*, start_open_ms: int, count: int, interval_ms: int) -> list[list[object]]:
    payload: list[list[object]] = []
    for offset in range(count):
        open_ms = start_open_ms + (offset * interval_ms)
        payload.append(
            [
                open_ms,
                "100.0",
                "110.0",
                "95.0",
                "105.0",
                "12.5",
                open_ms + interval_ms - 1,
            ]
        )
    return payload
