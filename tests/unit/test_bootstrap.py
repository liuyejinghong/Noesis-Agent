from __future__ import annotations

from pathlib import Path

from noesis_agent.bootstrap import AppBootstrap
from noesis_agent.core.enums import RuntimeMode


def write_toml(path: Path, content: str) -> Path:
    _ = path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def test_app_bootstrap_initializes_all_components(tmp_path: Path) -> None:
    bootstrap = AppBootstrap(root_dir=tmp_path)

    assert bootstrap.settings.root_dir == tmp_path
    assert bootstrap.memory is not None
    assert bootstrap.router is not None
    assert bootstrap.skill_registry is not None
    assert bootstrap.proposal_manager is not None
    assert bootstrap.orchestrator is not None


def test_app_bootstrap_creates_memory_db_under_state_directory(tmp_path: Path) -> None:
    _ = AppBootstrap(root_dir=tmp_path)

    assert (tmp_path / "state" / "memory.db").exists()


def test_app_bootstrap_uses_default_settings_when_config_is_missing(tmp_path: Path) -> None:
    bootstrap = AppBootstrap(root_dir=tmp_path)

    assert bootstrap.settings.config_path is None
    assert bootstrap.settings.mode is RuntimeMode.BACKTEST
    assert bootstrap.settings.symbol == "BTCUSDT"
    assert bootstrap.settings.timeframe == "15m"


def test_app_bootstrap_loads_root_config_when_present(tmp_path: Path) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    _ = write_toml(
        config_dir / "config.toml",
        """
        symbol = "ETHUSDT"
        timeframe = "1h"

        [risk]
        max_position_size = 0.02

        [agent_roles.analyst]
        model = "openai:gpt-4.1"
        """,
    )

    bootstrap = AppBootstrap(root_dir=tmp_path)

    assert bootstrap.settings.config_path == config_dir / "config.toml"
    assert bootstrap.settings.symbol == "ETHUSDT"
    assert bootstrap.settings.timeframe == "1h"
    assert bootstrap.settings.risk.max_position_size == 0.02
    assert bootstrap.router.list_roles() == ["analyst"]


def test_app_bootstrap_leaves_prompts_dir_unset_when_prompt_files_are_missing(tmp_path: Path) -> None:
    bootstrap = AppBootstrap(root_dir=tmp_path)

    assert bootstrap.orchestrator.prompts_dir is None


def test_app_bootstrap_sets_prompts_dir_when_prompt_files_exist(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "config" / "prompts" / "analyst"
    prompts_dir.mkdir(parents=True)

    bootstrap = AppBootstrap(root_dir=tmp_path)

    assert bootstrap.orchestrator.prompts_dir == tmp_path / "config" / "prompts"


def test_app_bootstrap_initializes_alert_manager_and_logs_dir(tmp_path: Path) -> None:
    bootstrap = AppBootstrap(root_dir=tmp_path)

    assert bootstrap.alert_manager.channel_count == 2
    assert (tmp_path / "logs").exists()


def test_app_bootstrap_initializes_strategy_catalog_and_batch_coordinator(tmp_path: Path) -> None:
    strategies_dir = tmp_path / "config" / "strategies"
    strategies_dir.mkdir(parents=True)

    bootstrap = AppBootstrap(root_dir=tmp_path)

    assert bootstrap.strategy_catalog.list_active() == []
    assert bootstrap.batch_coordinator is not None
