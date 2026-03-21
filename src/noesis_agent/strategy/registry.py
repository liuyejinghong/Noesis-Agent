from __future__ import annotations

import importlib
from inspect import isclass

from noesis_agent.core.models import StrategyRuntimeConfig
from noesis_agent.strategy.base import StrategyBase


class StrategyRegistry:
    def __init__(self) -> None:
        self._strategies: dict[str, type[StrategyBase]] = {}

    def register(self, strategy_cls: type[StrategyBase]) -> None:
        self._strategies[strategy_cls.strategy_id] = strategy_cls

    def get(self, strategy_id: str) -> type[StrategyBase] | None:
        return self._strategies.get(strategy_id) or _load_strategy_class(strategy_id)

    def list_strategies(self) -> list[str]:
        return list(self._strategies)

    def build_strategy(
        self,
        strategy_id: str,
        config: StrategyRuntimeConfig | None = None,
    ) -> StrategyBase:
        strategy_cls = self.get(strategy_id)
        if strategy_cls is None:
            raise ValueError(f"Unknown strategy: {strategy_id}")
        strategy = strategy_cls()
        if config is not None:
            strategy.configure(config)
        return strategy


def _load_strategy_class(strategy_id: str) -> type[StrategyBase] | None:
    try:
        module = importlib.import_module(f"noesis_agent.strategy.{strategy_id}")
    except ModuleNotFoundError:
        return None

    for value in vars(module).values():
        if (
            isclass(value)
            and issubclass(value, StrategyBase)
            and value is not StrategyBase
            and getattr(value, "strategy_id", None) == strategy_id
            and value.__module__ == module.__name__
        ):
            return value  # type: ignore[return-value]
    return None
