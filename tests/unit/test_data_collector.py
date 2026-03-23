# pyright: reportAny=false

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from noesis_agent.data.collector import BinanceDataCollector
from noesis_agent.data.storage import DataStore


class _MockResponse:
    def __init__(self, payload: object, *, status_code: int = 200, url: str = "https://example.test") -> None:
        self._payload = payload
        self._status_code = status_code
        self._url = url

    def raise_for_status(self) -> None:
        if self._status_code >= 400:
            request = httpx.Request("GET", self._url)
            response = httpx.Response(self._status_code, json=self._payload, request=request)
            raise httpx.HTTPStatusError("mock error", request=request, response=response)

    def json(self) -> object:
        return self._payload


def test_collect_funding_rates_parses_and_persists_snapshot(tmp_path: Path, monkeypatch: Any) -> None:
    collector = BinanceDataCollector(DataStore(tmp_path / "data"), symbols=["BTCUSDT"])

    def fake_get(url: str, *, params: dict[str, object], timeout: float) -> _MockResponse:
        del params, timeout
        return _MockResponse(
            [
                {
                    "fundingTime": 1710979200000,
                    "fundingRate": "0.0001",
                    "markPrice": "62000.5",
                }
            ],
            url=url,
        )

    monkeypatch.setattr("noesis_agent.data.collector.httpx.get", fake_get)

    frame = collector.collect_funding_rates("BTCUSDT", limit=1)

    assert frame.index.name == "timestamp"
    assert frame.iloc[0].to_dict() == {"fundingRate": 0.0001, "markPrice": 62000.5}
    saved = pd.read_parquet(
        tmp_path / "data" / "snapshots" / "funding_rate" / "BTCUSDT_history.parquet", engine="pyarrow"
    )
    pd.testing.assert_frame_equal(saved, frame)


def test_collect_open_interest_parses_and_persists_snapshot(tmp_path: Path, monkeypatch: Any) -> None:
    collector = BinanceDataCollector(DataStore(tmp_path / "data"), symbols=["BTCUSDT"])

    def fake_get(url: str, *, params: dict[str, object], timeout: float) -> _MockResponse:
        del params, timeout
        return _MockResponse(
            [
                {
                    "timestamp": 1710979200000,
                    "sumOpenInterest": "1000.5",
                    "sumOpenInterestValue": "62000000.0",
                }
            ],
            url=url,
        )

    monkeypatch.setattr("noesis_agent.data.collector.httpx.get", fake_get)

    frame = collector.collect_open_interest("BTCUSDT", period="1h", limit=1)

    assert frame.iloc[0].to_dict() == {"sumOpenInterest": 1000.5, "sumOpenInterestValue": 62000000.0}
    saved = pd.read_parquet(tmp_path / "data" / "snapshots" / "open_interest" / "BTCUSDT_1h.parquet", engine="pyarrow")
    pd.testing.assert_frame_equal(saved, frame)


def test_collect_long_short_ratio_parses_and_persists_snapshot(tmp_path: Path, monkeypatch: Any) -> None:
    collector = BinanceDataCollector(DataStore(tmp_path / "data"), symbols=["BTCUSDT"])

    def fake_get(url: str, *, params: dict[str, object], timeout: float) -> _MockResponse:
        del params, timeout
        return _MockResponse(
            [
                {
                    "timestamp": 1710979200000,
                    "longAccount": "0.55",
                    "shortAccount": "0.45",
                    "longShortRatio": "1.22",
                }
            ],
            url=url,
        )

    monkeypatch.setattr("noesis_agent.data.collector.httpx.get", fake_get)

    frame = collector.collect_long_short_ratio("BTCUSDT", period="1h", limit=1)

    assert frame.iloc[0].to_dict() == {"longAccount": 0.55, "shortAccount": 0.45, "longShortRatio": 1.22}
    saved = pd.read_parquet(
        tmp_path / "data" / "snapshots" / "long_short_ratio" / "BTCUSDT_1h.parquet", engine="pyarrow"
    )
    pd.testing.assert_frame_equal(saved, frame)


def test_collect_taker_buy_sell_parses_and_persists_snapshot(tmp_path: Path, monkeypatch: Any) -> None:
    collector = BinanceDataCollector(DataStore(tmp_path / "data"), symbols=["BTCUSDT"])

    def fake_get(url: str, *, params: dict[str, object], timeout: float) -> _MockResponse:
        del params, timeout
        return _MockResponse(
            [
                {
                    "timestamp": 1710979200000,
                    "buySellRatio": "1.1",
                    "buyVol": "200.0",
                    "sellVol": "180.0",
                }
            ],
            url=url,
        )

    monkeypatch.setattr("noesis_agent.data.collector.httpx.get", fake_get)

    frame = collector.collect_taker_buy_sell("BTCUSDT", period="1h", limit=1)

    assert frame.iloc[0].to_dict() == {"buySellRatio": 1.1, "buyVol": 200.0, "sellVol": 180.0}
    saved = pd.read_parquet(tmp_path / "data" / "snapshots" / "taker_buy_sell" / "BTCUSDT_1h.parquet", engine="pyarrow")
    pd.testing.assert_frame_equal(saved, frame)


def test_collect_all_handles_errors_and_continues(tmp_path: Path, monkeypatch: Any) -> None:
    collector = BinanceDataCollector(DataStore(tmp_path / "data"), symbols=["BTCUSDT"])
    payloads = {
        "/fapi/v1/fundingRate": _MockResponse([], url="https://example.test/fapi/v1/fundingRate"),
        "/futures/data/openInterestHist": RuntimeError("boom"),
        "/futures/data/globalLongShortAccountRatio": _MockResponse(
            [], url="https://example.test/futures/data/globalLongShortAccountRatio"
        ),
        "/futures/data/takerlongshortRatio": _MockResponse(
            [], url="https://example.test/futures/data/takerlongshortRatio"
        ),
    }

    def fake_get(url: str, *, params: dict[str, object], timeout: float) -> _MockResponse:
        del params, timeout
        response = payloads[url.removeprefix(BinanceDataCollector.BASE_URL)]
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr("noesis_agent.data.collector.httpx.get", fake_get)

    results = collector.collect_all()

    assert results == {
        "BTCUSDT_funding_rate": 0,
        "BTCUSDT_open_interest": 0,
        "BTCUSDT_long_short_ratio": 0,
        "BTCUSDT_taker_buy_sell": 0,
    }
