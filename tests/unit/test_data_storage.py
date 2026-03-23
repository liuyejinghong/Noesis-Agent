from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd
import pytest

from noesis_agent.data.storage import DataStore


def test_save_and_load_market_data_roundtrip(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "data")
    frame = _market_frame()

    target = store.save_market_data("binance_usdm", "BTCUSDT", "klines_15m", frame)
    loaded = store.load_market_data("binance_usdm", "BTCUSDT", "klines_15m")

    assert target == tmp_path / "data" / "market" / "binance_usdm" / "BTCUSDT" / "klines_15m.parquet"
    pd.testing.assert_frame_equal(loaded, frame)


def test_save_snapshot_appends_deduplicates_and_sorts(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "data")
    initial = _snapshot_frame(["2026-03-21T00:00:00Z", "2026-03-21T01:00:00Z"], [1.0, 2.0])
    update = _snapshot_frame(["2026-03-21T01:00:00Z", "2026-03-21T02:00:00Z"], [2.0, 3.0])

    _ = store.save_snapshot("long_short_ratio", "BTCUSDT", "1h", initial)
    _ = store.save_snapshot("long_short_ratio", "BTCUSDT", "1h", update)
    loaded = store.load_snapshot("long_short_ratio", "BTCUSDT", "1h")

    assert loaded.index.tolist() == list(
        pd.to_datetime(["2026-03-21T00:00:00Z", "2026-03-21T01:00:00Z", "2026-03-21T02:00:00Z"], utc=True)
    )
    assert loaded["value"].tolist() == [1.0, 2.0, 3.0]


def test_load_market_data_falls_back_to_csv_when_parquet_missing(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "data")
    csv_path = tmp_path / "data" / "raw" / "binance_usdm" / "BTCUSDT" / "15m.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    _ = csv_path.write_text(
        "timestamp,open,high,low,close,volume\n2026-03-21T00:00:00Z,100.0,101.0,99.0,100.5,10.0\n",
        encoding="utf-8",
    )

    loaded = store.load_market_data("binance_usdm", "BTCUSDT", "klines_15m")

    assert list(loaded.columns) == ["open", "high", "low", "close", "volume"]
    assert loaded.index.name == "timestamp"
    index = cast(pd.DatetimeIndex, loaded.index)
    assert str(index.tz) == "UTC"


def test_list_symbols_returns_sorted_symbol_directories(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "data")
    _ = store.save_market_data("binance_usdm", "ETHUSDT", "klines_15m", _market_frame())
    _ = store.save_market_data("binance_usdm", "BTCUSDT", "klines_15m", _market_frame())

    assert store.list_symbols("binance_usdm") == ["BTCUSDT", "ETHUSDT"]


def test_load_market_data_raises_when_no_storage_exists(tmp_path: Path) -> None:
    store = DataStore(tmp_path / "data")

    with pytest.raises(FileNotFoundError, match="No data found"):
        _ = store.load_market_data("binance_usdm", "BTCUSDT", "oi_1h")


def _market_frame() -> pd.DataFrame:
    index = pd.to_datetime(["2026-03-21T00:00:00Z", "2026-03-21T00:15:00Z"], utc=True)
    return pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [10.0, 12.0],
        },
        index=index.rename("timestamp"),
    )


def _snapshot_frame(timestamps: list[str], values: list[float]) -> pd.DataFrame:
    index = pd.to_datetime(timestamps, utc=True).rename("timestamp")
    return pd.DataFrame({"value": values}, index=index)
