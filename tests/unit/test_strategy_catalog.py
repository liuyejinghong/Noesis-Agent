from __future__ import annotations

from pathlib import Path

from noesis_agent.orchestration.strategy_catalog import StrategyCatalog, StrategySpec


def write_strategy_file(path: Path, content: str) -> Path:
    _ = path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def test_list_active_returns_active_strategies_from_toml_files(tmp_path: Path) -> None:
    strategies_dir = tmp_path / "config" / "strategies"
    strategies_dir.mkdir(parents=True)
    _ = write_strategy_file(
        strategies_dir / "btc.toml",
        """
        strategy_id = "btc_breakout"
        symbol = "BTCUSDT"
        timeframe = "1h"
        """,
    )
    _ = write_strategy_file(
        strategies_dir / "eth.toml",
        """
        strategy_id = "eth_reversion"
        symbol = "ETHUSDT"
        timeframe = "4h"
        """,
    )

    catalog = StrategyCatalog(strategies_dir)

    assert catalog.list_active() == [
        StrategySpec(strategy_id="btc_breakout", symbol="BTCUSDT", timeframe="1h"),
        StrategySpec(strategy_id="eth_reversion", symbol="ETHUSDT", timeframe="4h"),
    ]


def test_list_active_skips_template_file(tmp_path: Path) -> None:
    strategies_dir = tmp_path / "config" / "strategies"
    strategies_dir.mkdir(parents=True)
    _ = write_strategy_file(strategies_dir / "template.toml", 'strategy_id = "template"')

    catalog = StrategyCatalog(strategies_dir)

    assert catalog.list_active() == []


def test_list_active_skips_non_active_strategies(tmp_path: Path) -> None:
    strategies_dir = tmp_path / "config" / "strategies"
    strategies_dir.mkdir(parents=True)
    _ = write_strategy_file(
        strategies_dir / "paused.toml",
        """
        strategy_id = "paused_strategy"
        status = "paused"
        """,
    )

    catalog = StrategyCatalog(strategies_dir)

    assert catalog.list_active() == []


def test_list_active_returns_empty_list_for_missing_directory(tmp_path: Path) -> None:
    catalog = StrategyCatalog(tmp_path / "config" / "strategies")

    assert catalog.list_active() == []


def test_get_returns_strategy_by_id(tmp_path: Path) -> None:
    strategies_dir = tmp_path / "config" / "strategies"
    strategies_dir.mkdir(parents=True)
    _ = write_strategy_file(
        strategies_dir / "btc.toml",
        """
        strategy_id = "btc_breakout"
        symbol = "BTCUSDT"
        timeframe = "1h"
        """,
    )

    catalog = StrategyCatalog(strategies_dir)

    assert catalog.get("btc_breakout") == StrategySpec(
        strategy_id="btc_breakout",
        symbol="BTCUSDT",
        timeframe="1h",
    )
    assert catalog.get("missing") is None
