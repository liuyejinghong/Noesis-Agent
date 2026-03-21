# pyright: reportMissingTypeStubs=false

from __future__ import annotations

from pathlib import Path

import pandas as pd

from noesis_agent.data.catalog import CatalogEntry, upsert_catalog_entry

OHLCV_COLUMNS = ["open", "high", "low", "close", "volume"]


def interval_to_milliseconds(interval: str) -> int:
    unit = interval[-1]
    value = int(interval[:-1])
    if unit == "m":
        return value * 60_000
    if unit == "h":
        return value * 3_600_000
    if unit == "d":
        return value * 86_400_000
    if unit == "w":
        return value * 604_800_000
    raise ValueError(f"Unsupported interval: {interval}")


def write_market_data_csv(
    data_dir: Path,
    *,
    source: str,
    symbol: str,
    timeframe: str,
    frame: pd.DataFrame,
) -> Path:
    target = data_dir / "raw" / source / symbol / f"{timeframe}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    output = frame.loc[:, OHLCV_COLUMNS].copy()
    output.index = pd.to_datetime(output.index, utc=True)
    output.index.name = "timestamp"
    output.to_csv(target, index_label="timestamp")
    _ = upsert_catalog_entry(
        data_dir,
        CatalogEntry(
            symbol=symbol,
            timeframe=timeframe,
            source=source,
            path=str(target.relative_to(data_dir)),
            rows=len(output),
            start_ts=str(output.index.min()) if not output.empty else "",
            end_ts=str(output.index.max()) if not output.empty else "",
        ),
    )
    return target


def load_market_data_csv(data_dir: Path, *, source: str, symbol: str, timeframe: str) -> pd.DataFrame:
    target = data_dir / "raw" / source / symbol / f"{timeframe}.csv"
    frame = pd.read_csv(target, parse_dates=["timestamp"], index_col="timestamp")
    frame.index = pd.to_datetime(frame.index, utc=True)
    frame.index.name = None
    if "close_time" in frame.columns:
        frame = frame.drop(columns=["close_time"])
    return frame.loc[:, OHLCV_COLUMNS]
