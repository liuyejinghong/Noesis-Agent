from __future__ import annotations

from typer.testing import CliRunner

from noesis_agent.cli import app

runner = CliRunner()


class TestChatCommand:
    def test_chat_help(self):
        result = runner.invoke(app, ["chat", "--help"])
        assert result.exit_code == 0
        assert "对话" in result.stdout or "REPL" in result.stdout

    def test_chat_appears_in_main_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "chat" in result.stdout
