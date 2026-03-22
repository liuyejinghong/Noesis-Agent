from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from noesis_agent.cli import app

runner = CliRunner()


class TestCLIBasics:
    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "Noesis Agent" in result.output

    def test_status(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["status", "--root-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "系统状态" in result.output

    def test_config_show(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["config", "show", "--root-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "当前配置" in result.output

    def test_proposals_empty(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["proposals", "--root-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "暂无提案" in result.output

    def test_analyze_no_api_key(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["analyze", "sma_cross", "--period", "2025-01", "--root-dir", str(tmp_path)])

        assert result.exit_code in (0, 1)

    def test_approve_nonexistent(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["approve", "999", "--root-dir", str(tmp_path)])

        assert result.exit_code == 1

    def test_reject_nonexistent(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["reject", "999", "--reason", "测试", "--root-dir", str(tmp_path)])

        assert result.exit_code == 1

    def test_login_status_shows_not_logged_in_when_token_missing(self, monkeypatch: Any) -> None:
        class FakeAuthManager:
            def load_tokens(self) -> None:
                return None

        monkeypatch.setattr("noesis_agent.cli.OpenAIAuthManager", FakeAuthManager)

        result = runner.invoke(app, ["login", "status"])

        assert result.exit_code == 0
        assert "未登录" in result.output

    def test_login_logout_succeeds_when_not_logged_in(self, monkeypatch: Any) -> None:
        class FakeAuthManager:
            def clear_tokens(self) -> bool:
                return False

        monkeypatch.setattr("noesis_agent.cli.OpenAIAuthManager", FakeAuthManager)

        result = runner.invoke(app, ["login", "logout"])

        assert result.exit_code == 0
