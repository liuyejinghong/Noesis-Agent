from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast


@dataclass(slots=True)
class CatalogEntry:
    symbol: str
    timeframe: str
    source: str
    path: str
    rows: int
    start_ts: str
    end_ts: str


@dataclass(slots=True)
class CatalogSummary:
    entry_count: int
    symbols: list[str]
    timeframes: list[str]
    latest_end_ts: str | None


def catalog_path(data_dir: Path) -> Path:
    return data_dir / "catalog.json"


def load_catalog(data_dir: Path) -> list[CatalogEntry]:
    path = catalog_path(data_dir)
    if not path.exists():
        return []
    payload = cast(list[dict[str, str | int]], json.loads(path.read_text(encoding="utf-8")))
    return [
        CatalogEntry(
            symbol=cast(str, item["symbol"]),
            timeframe=cast(str, item["timeframe"]),
            source=cast(str, item["source"]),
            path=cast(str, item["path"]),
            rows=cast(int, item["rows"]),
            start_ts=cast(str, item["start_ts"]),
            end_ts=cast(str, item["end_ts"]),
        )
        for item in payload
    ]


def upsert_catalog_entry(data_dir: Path, entry: CatalogEntry) -> Path:
    entries = [
        item
        for item in load_catalog(data_dir)
        if not (item.source == entry.source and item.symbol == entry.symbol and item.timeframe == entry.timeframe)
    ]
    entries.append(entry)
    path = catalog_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps([asdict(item) for item in entries], indent=2), encoding="utf-8")
    return path


def summarize_catalog(entries: list[CatalogEntry]) -> CatalogSummary:
    symbols = sorted({entry.symbol for entry in entries})
    timeframes = sorted({entry.timeframe for entry in entries})
    latest_end_ts = max((entry.end_ts for entry in entries if entry.end_ts), default=None)
    return CatalogSummary(
        entry_count=len(entries),
        symbols=symbols,
        timeframes=timeframes,
        latest_end_ts=latest_end_ts,
    )
