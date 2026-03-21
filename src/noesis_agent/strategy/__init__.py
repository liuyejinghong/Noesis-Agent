from noesis_agent.core.models import StrategyRuntimeConfig
from noesis_agent.strategy.registry import StrategyRegistry


def build_strategy(strategy_id: str, config: StrategyRuntimeConfig | None = None):
    return StrategyRegistry().build_strategy(strategy_id, config=config)


__all__ = ["StrategyRegistry", "build_strategy"]
