# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from noesis_agent.data.catalog import load_catalog
from noesis_agent.data.ingestion import (
    interval_to_milliseconds,
    load_market_data_csv,
    write_market_data_csv,
)
from noesis_agent.data.resample import analyze_ohlcv, resample_ohlcv


def test_interval_to_milliseconds_supports_minute_hour_day_and_week_units() -> None:
    assert interval_to_milliseconds("1m") == 60_000
    assert interval_to_milliseconds("4h") == 14_400_000
    assert interval_to_milliseconds("2d") == 172_800_000
    assert interval_to_milliseconds("3w") == 1_814_400_000


def test_interval_to_milliseconds_rejects_unsupported_units() -> None:
    with pytest.raises(ValueError, match="Unsupported interval: 1M"):
        _ = interval_to_milliseconds("1M")


def test_write_and_load_market_data_csv_roundtrip_updates_catalog(tmp_path: Path) -> None:
    frame = _sample_frame()

    target = write_market_data_csv(
        tmp_path,
        source="binance_usdm",
        symbol="BTCUSDT",
        timeframe="1h",
        frame=frame,
    )
    loaded = load_market_data_csv(
        tmp_path,
        source="binance_usdm",
        symbol="BTCUSDT",
        timeframe="1h",
    )
    entries = load_catalog(tmp_path)

    assert target == tmp_path / "raw" / "binance_usdm" / "BTCUSDT" / "1h.csv"
    pd.testing.assert_frame_equal(loaded, frame)
    assert len(entries) == 1
    assert entries[0].source == "binance_usdm"
    assert entries[0].symbol == "BTCUSDT"
    assert entries[0].timeframe == "1h"
    assert entries[0].path == "raw/binance_usdm/BTCUSDT/1h.csv"
    assert entries[0].rows == len(frame)
    assert entries[0].start_ts == str(frame.index.min())
    assert entries[0].end_ts == str(frame.index.max())


def test_load_market_data_csv_drops_v1_close_time_column(tmp_path: Path) -> None:
    target = tmp_path / "raw" / "binance_usdm" / "BTCUSDT" / "1h.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(
        (
            "timestamp,open,high,low,close,volume,close_time\n"
            "2026-03-21T00:00:00Z,100.0,102.0,99.0,101.0,10.0,2026-03-21T00:59:59Z\n"
            "2026-03-21T01:00:00Z,101.0,103.0,100.0,102.0,12.0,2026-03-21T01:59:59Z\n"
        ),
        encoding="utf-8",
    )

    loaded = load_market_data_csv(
        tmp_path,
        source="binance_usdm",
        symbol="BTCUSDT",
        timeframe="1h",
    )

    assert list(loaded.columns) == ["open", "high", "low", "close", "volume"]
    assert isinstance(loaded.index, pd.DatetimeIndex)
    assert str(loaded.index.tz) == "UTC"


def test_write_market_data_csv_keeps_distinct_catalog_entries_per_source(tmp_path: Path) -> None:
    frame = _sample_frame()

    _ = write_market_data_csv(
        tmp_path,
        source="binance_usdm",
        symbol="BTCUSDT",
        timeframe="1h",
        frame=frame,
    )
    _ = write_market_data_csv(
        tmp_path,
        source="binance_spot",
        symbol="BTCUSDT",
        timeframe="1h",
        frame=frame,
    )

    entries = load_catalog(tmp_path)

    assert len(entries) == 2
    assert {entry.source for entry in entries} == {"binance_usdm", "binance_spot"}


def test_resample_ohlcv_supports_standard_ohlcv_frames_without_close_time() -> None:
    frame = _sample_frame()

    resampled = resample_ohlcv(frame, "2h")

    assert list(resampled.columns) == ["open", "high", "low", "close", "volume"]
    assert resampled.iloc[0].to_dict() == {
        "open": 100.0,
        "high": 103.0,
        "low": 99.0,
        "close": 102.0,
        "volume": 22.0,
    }


def test_analyze_ohlcv_reports_missing_columns_without_raising() -> None:
    frame = _sample_frame().drop(columns=["high"])

    report = analyze_ohlcv(frame)

    assert report.errors == ["missing columns: high"]


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
