from __future__ import annotations

from pathlib import Path

import pandas as pd


class DataStore:
    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir

    def save_market_data(self, source: str, symbol: str, data_type: str, df: pd.DataFrame) -> Path:
        path = self._base / "market" / source / symbol / f"{data_type}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, engine="pyarrow", index=True)
        return path

    def load_market_data(self, source: str, symbol: str, data_type: str) -> pd.DataFrame:
        path = self._base / "market" / source / symbol / f"{data_type}.parquet"
        if path.exists():
            return pd.read_parquet(path, engine="pyarrow")

        csv_name = data_type.removeprefix("klines_") if data_type.startswith("klines_") else data_type
        csv_path = self._base / "raw" / source / symbol / f"{csv_name}.csv"
        if csv_path.exists():
            return pd.read_csv(csv_path, parse_dates=["timestamp"], index_col="timestamp")

        raise FileNotFoundError(f"No data found: {path}")

    def save_snapshot(self, category: str, symbol: str, period: str, df: pd.DataFrame) -> Path:
        path = self._base / "snapshots" / category / f"{symbol}_{period}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = pd.read_parquet(path, engine="pyarrow")
            df = pd.concat([existing, df]).drop_duplicates().sort_index()
        df.to_parquet(path, engine="pyarrow", index=True)
        return path

    def load_snapshot(self, category: str, symbol: str, period: str) -> pd.DataFrame:
        path = self._base / "snapshots" / category / f"{symbol}_{period}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"No snapshot: {path}")
        return pd.read_parquet(path, engine="pyarrow")

    def list_symbols(self, source: str) -> list[str]:
        source_dir = self._base / "market" / source
        if not source_dir.exists():
            return []
        return sorted(item.name for item in source_dir.iterdir() if item.is_dir())
