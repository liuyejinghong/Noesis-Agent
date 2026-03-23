from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class FactorDefinition:
    factor_id: str
    name: str
    category: str
    compute_fn: Callable[[pd.DataFrame, dict], pd.Series]
    default_params: dict = field(default_factory=dict)


class FactorRegistry:
    def __init__(self) -> None:
        self._factors: dict[str, FactorDefinition] = {}

    def register(self, definition: FactorDefinition) -> None:
        self._factors[definition.factor_id] = definition

    def get(self, factor_id: str) -> FactorDefinition:
        if factor_id not in self._factors:
            raise KeyError(f"Unknown factor: {factor_id}")
        return self._factors[factor_id]

    def list_factors(self, category: str | None = None) -> list[FactorDefinition]:
        factors = list(self._factors.values())
        if category is not None:
            factors = [factor for factor in factors if factor.category == category]
        return sorted(factors, key=lambda factor: factor.factor_id)

    def compute(
        self,
        factor_id: str,
        data: pd.DataFrame,
        params: dict | None = None,
    ) -> pd.Series:
        definition = self.get(factor_id)
        merged_params = {**definition.default_params, **(params or {})}
        return definition.compute_fn(data, merged_params)
