from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StrategySpec:
    strategy_id: str
    status: str = "active"
    scope: str = "single_asset"
    symbol: str = "BTCUSDT"
    timeframe: str = "15m"


class StrategyCatalog:
    def __init__(self, strategies_dir: Path) -> None:
        self._dir = strategies_dir

    def list_active(self) -> list[StrategySpec]:
        if not self._dir.exists():
            return []

        specs: list[StrategySpec] = []
        for file_path in sorted(self._dir.glob("*.toml")):
            if file_path.name == "template.toml":
                continue
            with file_path.open("rb") as file_handle:
                data = tomllib.load(file_handle)
            status = self._string_value(data, "status", "active")
            if status != "active":
                continue
            specs.append(
                StrategySpec(
                    strategy_id=self._string_value(data, "strategy_id", file_path.stem),
                    status=status,
                    scope=self._string_value(data, "scope", "single_asset"),
                    symbol=self._string_value(data, "symbol", "BTCUSDT"),
                    timeframe=self._string_value(data, "timeframe", "15m"),
                )
            )
        return specs

    def get(self, strategy_id: str) -> StrategySpec | None:
        for spec in self.list_active():
            if spec.strategy_id == strategy_id:
                return spec
        return None

    @staticmethod
    def _string_value(data: dict[str, object], key: str, default: str) -> str:
        value = data.get(key, default)
        return value if isinstance(value, str) else default
