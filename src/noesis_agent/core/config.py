# pyright: reportAny=false, reportExplicitAny=false, reportImplicitOverride=false, reportUnnecessaryIsInstance=false

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .enums import RuntimeMode
from .models import StrategyRuntimeConfig

ENV_PREFIX = "NOESIS_"
ENV_NESTED_DELIMITER = "__"


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
            continue
        merged[key] = value
    return merged


def _load_toml_file(path: Path) -> dict[str, Any]:
    with path.open("rb") as file_obj:
        payload: dict[str, Any] = tomllib.load(file_obj)
    return payload


def _set_nested_value(target: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    current = target
    for part in path[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[path[-1]] = value


def _get_nested_value(source: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = source
    for part in path:
        current = current[part]
    return current


def _collect_env_override_paths() -> set[tuple[str, ...]]:
    paths: set[tuple[str, ...]] = set()
    for key in os.environ:
        if not key.startswith(ENV_PREFIX):
            continue
        raw_path = key.removeprefix(ENV_PREFIX)
        if not raw_path:
            continue
        parts = tuple(part.lower() for part in raw_path.split(ENV_NESTED_DELIMITER) if part)
        if parts:
            paths.add(parts)
    return paths


def _apply_override_paths(
    merged: dict[str, Any],
    current: dict[str, Any],
    override_paths: set[tuple[str, ...]],
) -> dict[str, Any]:
    result = dict(merged)
    for path in sorted(override_paths):
        _set_nested_value(result, path, _get_nested_value(current, path))
    return result


class RiskConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_position_size: float = 0.01
    max_leverage: float = 3
    read_only: bool = False
    max_daily_loss_pct: float = 0.05


class TradeManagementConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    stop_loss_pct: float | None = Field(default=None, gt=0)
    take_profit_pct: float | None = Field(default=None, gt=0)
    trailing_stop_pct: float | None = Field(default=None, gt=0)
    max_holding_bars: int | None = Field(default=None, ge=1)
    cooldown_bars: int | None = Field(default=None, ge=0)
    confirm_bars: int | None = Field(default=None, ge=1)


class ExchangeConfig(BaseModel):
    exchange_id: str = "binance_usdm"
    account_type: str = "futures"
    base_url: str | None = None
    api_key_env: str | None = None
    api_secret_env: str | None = None

    def resolve_api_key(self) -> str | None:
        if self.api_key_env is None:
            return None
        return os.environ.get(self.api_key_env)

    def resolve_api_secret(self) -> str | None:
        if self.api_secret_env is None:
            return None
        return os.environ.get(self.api_secret_env)


class OptimizeConfig(BaseModel):
    default_method: str = "grid"
    timeframes: list[str] = Field(default_factory=lambda: ["15m"])
    lookback_days: int = 90
    random_max_trials: int = 50
    parameter_space: dict[str, Any] = Field(default_factory=dict)
    trade_management_parameter_space: dict[str, Any] = Field(default_factory=dict)


class AgentRoleConfig(BaseModel):
    model: str = "openai:gpt-4o"
    fallback: str | None = None
    system_prompt: str = ""
    tools: list[str] = Field(default_factory=list)
    output_format: str = "text"


class StrategyConfig(BaseModel):
    strategy_id: str
    strategy_name: str = ""
    display_name: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    status: str = "active"
    source_type: str = "built_in"
    parameters: dict[str, Any] = Field(default_factory=dict)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    trade_management: TradeManagementConfig = Field(default_factory=TradeManagementConfig)
    optimize: OptimizeConfig = Field(default_factory=OptimizeConfig)


class _NoesisSettingsPayload(BaseModel):
    mode: RuntimeMode = RuntimeMode.BACKTEST
    symbol: str = "BTCUSDT"
    timeframe: str = "15m"
    root_dir: Path = Field(default_factory=Path.cwd)
    config_path: Path | None = None
    risk: RiskConfig = Field(default_factory=RiskConfig)
    trade_management: TradeManagementConfig = Field(default_factory=TradeManagementConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    agent_roles: dict[str, AgentRoleConfig] = Field(default_factory=dict)


class NoesisSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_nested_delimiter=ENV_NESTED_DELIMITER,
        extra="ignore",
    )

    mode: RuntimeMode = RuntimeMode.BACKTEST
    symbol: str = "BTCUSDT"
    timeframe: str = "15m"
    root_dir: Path = Field(default_factory=Path.cwd)
    config_path: Path | None = None
    risk: RiskConfig = Field(default_factory=RiskConfig)
    trade_management: TradeManagementConfig = Field(default_factory=TradeManagementConfig)
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    agent_roles: dict[str, AgentRoleConfig] = Field(default_factory=dict)

    @field_validator("config_path")
    @classmethod
    def _expand_config_path(cls, value: Path | None) -> Path | None:
        if value is None:
            return None
        return value.expanduser()

    def model_post_init(self, __context: Any) -> None:
        if isinstance(__context, dict) and __context.get("skip_toml_merge"):
            return

        if self.config_path is None or not self.config_path.exists():
            return

        defaults = self.__class__.model_construct().model_dump(mode="python")
        payload = _load_toml_file(self.config_path)
        merged = _merge_dicts(defaults, payload)
        current = self.model_dump(mode="python")

        env_paths = _collect_env_override_paths()
        nested_env_roots = {path[0] for path in env_paths if len(path) > 1}
        init_paths = {(field_name,) for field_name in self.model_fields_set if field_name not in nested_env_roots}
        override_paths = env_paths | init_paths
        resolved = _apply_override_paths(merged, current, override_paths)
        validated = _NoesisSettingsPayload.model_validate(resolved, context={"skip_toml_merge": True})

        for field_name in self.__class__.model_fields:
            object.__setattr__(self, field_name, getattr(validated, field_name))


def load_strategy_config(path: Path) -> StrategyConfig:
    payload = _load_toml_file(path)
    return StrategyConfig.model_validate(payload)


def _model_overrides(model: BaseModel) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field_name in model.model_fields_set:
        value = getattr(model, field_name)
        if isinstance(value, BaseModel):
            data[field_name] = _model_overrides(value)
            continue
        data[field_name] = value
    return data


def resolve_strategy_runtime_config(
    settings: NoesisSettings,
    strategy_id: str,
    strategies_dir: Path,
) -> StrategyRuntimeConfig:
    strategy = load_strategy_config(strategies_dir / f"{strategy_id}.toml")

    merged_risk = _merge_dicts(settings.risk.model_dump(mode="python"), _model_overrides(strategy.risk))
    merged_trade_management = _merge_dicts(
        settings.trade_management.model_dump(mode="python"),
        _model_overrides(strategy.trade_management),
    )

    return StrategyRuntimeConfig(
        strategy_id=strategy.strategy_id,
        symbol=settings.symbol,
        timeframe=settings.timeframe,
        mode=settings.mode,
        parameters=strategy.parameters,
        risk=merged_risk,
        trade_management=merged_trade_management,
    )
