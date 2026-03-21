# pyright: reportMissingImports=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from noesis_agent.core.config import (
    ExchangeConfig,
    NoesisSettings,
    RiskConfig,
    TradeManagementConfig,
    load_strategy_config,
    resolve_strategy_runtime_config,
)
from noesis_agent.core.enums import RuntimeMode


def write_toml(path: Path, content: str) -> Path:
    _ = path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


class TestNoesisSettings:
    def test_defaults(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.delenv("NOESIS_SYMBOL", raising=False)

        settings = NoesisSettings(root_dir=tmp_path)

        assert settings.mode is RuntimeMode.BACKTEST
        assert settings.symbol == "BTCUSDT"
        assert settings.timeframe == "15m"
        assert settings.root_dir == tmp_path
        assert settings.config_path is None
        assert settings.risk == RiskConfig()
        assert settings.trade_management == TradeManagementConfig()
        assert settings.exchange.exchange_id == "binance_usdm"
        assert settings.agent_roles == {}

    def test_toml_override(self, tmp_path: Path) -> None:
        config_path = write_toml(
            tmp_path / "config.toml",
            """
            symbol = "ETHUSDT"
            timeframe = "1h"

            [risk]
            max_position_size = 0.02
            read_only = true

            [trade_management]
            stop_loss_pct = 0.03
            confirm_bars = 2

            [exchange]
            exchange_id = "hyperliquid"
            account_type = "swap"

            [agent_roles.researcher]
            model = "openai:gpt-4.1"
            tools = ["search", "report"]
            output_format = "json"
            """,
        )

        settings = NoesisSettings(config_path=config_path)

        assert settings.symbol == "ETHUSDT"
        assert settings.timeframe == "1h"
        assert settings.risk.max_position_size == 0.02
        assert settings.risk.read_only is True
        assert settings.trade_management.stop_loss_pct == 0.03
        assert settings.trade_management.confirm_bars == 2
        assert settings.exchange.exchange_id == "hyperliquid"
        assert settings.agent_roles["researcher"].output_format == "json"

    def test_env_override_toml(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        config_path = write_toml(tmp_path / "config.toml", 'symbol = "ETHUSDT"')
        monkeypatch.setenv("NOESIS_SYMBOL", "SOLUSDT")

        settings = NoesisSettings(config_path=config_path)

        assert settings.symbol == "SOLUSDT"


class TestExchangeConfig:
    def test_api_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BINANCE_API_KEY", "secret-key")
        config = ExchangeConfig(api_key_env="BINANCE_API_KEY")

        assert config.resolve_api_key() == "secret-key"

    def test_missing_env_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BINANCE_API_SECRET", raising=False)
        config = ExchangeConfig(api_secret_env="BINANCE_API_SECRET")  # noqa: S106

        assert config.resolve_api_secret() is None


class TestRiskConfig:
    def test_defaults(self) -> None:
        risk = RiskConfig()

        assert risk.max_position_size == 0.01
        assert risk.max_leverage == 3
        assert risk.read_only is False
        assert risk.max_daily_loss_pct == 0.05


class TestTradeManagementConfig:
    def test_defaults_all_none(self) -> None:
        trade_management = TradeManagementConfig()

        assert trade_management.stop_loss_pct is None
        assert trade_management.take_profit_pct is None
        assert trade_management.trailing_stop_pct is None
        assert trade_management.max_holding_bars is None
        assert trade_management.cooldown_bars is None
        assert trade_management.confirm_bars is None

    def test_validation_positive_float(self) -> None:
        with pytest.raises(ValidationError):
            _ = TradeManagementConfig(stop_loss_pct=-0.01)

    def test_validation_min_bars(self) -> None:
        with pytest.raises(ValidationError):
            _ = TradeManagementConfig(max_holding_bars=0)


class TestStrategyConfig:
    def test_load_from_toml(self, tmp_path: Path) -> None:
        strategy_path = write_toml(
            tmp_path / "sma_cross.toml",
            """
            strategy_id = "sma_cross"
            strategy_name = "sma_cross"
            display_name = "SMA Cross"
            description = "Dual moving average crossover trend strategy."
            tags = ["built_in", "trend"]
            status = "active"
            source_type = "built_in"

            [parameters]
            fast_window = 20
            slow_window = 60

            [trade_management]
            stop_loss_pct = 0.02
            take_profit_pct = 0.04
            trailing_stop_pct = 0.015
            max_holding_bars = 120
            cooldown_bars = 4
            confirm_bars = 2

            [optimize]
            default_method = "grid"
            timeframes = ["15m", "1h"]
            lookback_days = 365
            random_max_trials = 12

            [optimize.parameter_space]
            fast_window = [10, 20, 30]

            [optimize.trade_management_parameter_space]
            stop_loss_pct = [0.01, 0.02, 0.03]
            """,
        )

        strategy = load_strategy_config(strategy_path)

        assert strategy.strategy_id == "sma_cross"
        assert strategy.parameters == {"fast_window": 20, "slow_window": 60}
        assert strategy.trade_management.stop_loss_pct == 0.02
        assert strategy.optimize.timeframes == ["15m", "1h"]
        assert strategy.optimize.parameter_space == {"fast_window": [10, 20, 30]}


class TestResolveStrategyRuntimeConfig:
    def test_merge_strategy_over_system(self, tmp_path: Path) -> None:
        settings = NoesisSettings(
            symbol="BTCUSDT",
            timeframe="15m",
            risk=RiskConfig(max_position_size=0.01, max_leverage=3, read_only=False, max_daily_loss_pct=0.05),
            trade_management=TradeManagementConfig(stop_loss_pct=0.01, confirm_bars=1),
        )
        strategies_dir = tmp_path / "strategies"
        strategies_dir.mkdir()
        _ = write_toml(
            strategies_dir / "sma_cross.toml",
            """
            strategy_id = "sma_cross"

            [parameters]
            fast_window = 20

            [risk]
            max_position_size = 0.02

            [trade_management]
            stop_loss_pct = 0.03
            cooldown_bars = 4
            """,
        )

        runtime_config = resolve_strategy_runtime_config(settings, "sma_cross", strategies_dir)

        assert runtime_config.strategy_id == "sma_cross"
        assert runtime_config.symbol == "BTCUSDT"
        assert runtime_config.timeframe == "15m"
        assert runtime_config.mode is RuntimeMode.BACKTEST
        assert runtime_config.parameters == {"fast_window": 20}
        assert runtime_config.risk == {
            "max_position_size": 0.02,
            "max_leverage": 3.0,
            "read_only": False,
            "max_daily_loss_pct": 0.05,
        }
        assert runtime_config.trade_management == {
            "stop_loss_pct": 0.03,
            "take_profit_pct": None,
            "trailing_stop_pct": None,
            "max_holding_bars": None,
            "cooldown_bars": 4,
            "confirm_bars": 1,
        }
