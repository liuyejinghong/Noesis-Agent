# pyright: reportAny=false

from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from noesis_agent.cli import app
from noesis_agent.core.model_registry import ModelInfo, ModelTestResult, ProviderInfo

runner = CliRunner()


def write_prompt_files(base_dir: Path, *, role: str, content: str) -> Path:
    role_dir = base_dir / "config" / "prompts" / role
    role_dir.mkdir(parents=True)
    (role_dir / "meta.toml").write_text(
        'active_version = "v1"\n\n[[versions]]\nversion = "v1"\ndate = "2026-03-23"\nchangelog = "initial"\n',
        encoding="utf-8",
    )
    (role_dir / "v1.md").write_text(content + "\n", encoding="utf-8")
    return role_dir


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

    def test_models_list_shows_available_models(self, monkeypatch: Any) -> None:
        class FakeRegistry:
            providers = {
                "gpt_oauth": ProviderInfo(name="GPT OAuth", provider_type="oauth_openai"),
            }

            def list_models(self, tier: str | None = None) -> list[ModelInfo]:
                assert tier is None
                return [
                    ModelInfo(
                        model_id="gpt-5",
                        provider_id="gpt_oauth",
                        tier="mid",
                        capabilities=["reasoning", "code"],
                        cost="free",
                    )
                ]

        def fake_get_model_registry(_root_dir: Path | None = None) -> FakeRegistry:
            return FakeRegistry()

        monkeypatch.setattr("noesis_agent.cli._get_model_registry", fake_get_model_registry)

        result = runner.invoke(app, ["models", "list"])

        assert result.exit_code == 0
        assert "可用模型" in result.output
        assert "gpt-5" in result.output
        assert "GPT OAuth" in result.output

    def test_models_test_shows_failures_without_crashing(self, monkeypatch: Any) -> None:
        class FakeRegistry:
            def test_all(self) -> list[ModelTestResult]:
                return [
                    ModelTestResult(
                        model_id="claude-sonnet-4-6",
                        provider="Claude Relay",
                        success=False,
                        error="Missing env: CLAUDE_KEY",
                    )
                ]

        def fake_get_model_registry(_root_dir: Path | None = None) -> FakeRegistry:
            return FakeRegistry()

        monkeypatch.setattr("noesis_agent.cli._get_model_registry", fake_get_model_registry)

        result = runner.invoke(app, ["models", "test"])

        assert result.exit_code == 0
        assert "模型连通性测试" in result.output
        assert "claude-sonnet-4-6" in result.output
        assert "Missing env: CLAUDE_KEY" in result.output

    def test_prompts_list_shows_roles_and_active_versions(self, tmp_path: Path) -> None:
        _ = write_prompt_files(tmp_path, role="analyst", content="analyst prompt")
        _ = write_prompt_files(tmp_path, role="proposer", content="proposer prompt")
        _ = write_prompt_files(tmp_path, role="validator", content="validator prompt")

        result = runner.invoke(app, ["prompts", "list", "--root-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "Prompt Roles" in result.output
        assert "analyst" in result.output
        assert "proposer" in result.output
        assert "validator" in result.output
        assert "v1" in result.output

    def test_prompts_show_renders_header_and_markdown_body(self, tmp_path: Path) -> None:
        _ = write_prompt_files(tmp_path, role="analyst", content="# Analyst Prompt\n\nBody")

        result = runner.invoke(app, ["prompts", "show", "analyst", "--root-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "analyst v1" in result.output
        assert "Analyst Prompt" in result.output
        assert "Body" in result.output

    def test_prompts_show_supports_explicit_version(self, tmp_path: Path) -> None:
        role_dir = write_prompt_files(tmp_path, role="analyst", content="active prompt")
        (role_dir / "meta.toml").write_text(
            'active_version = "v2"\n\n[[versions]]\nversion = "v1"\ndate = "2026-03-23"\nchangelog = "initial"\n\n[[versions]]\nversion = "v2"\ndate = "2026-03-24"\nchangelog = "updated"\n',
            encoding="utf-8",
        )
        (role_dir / "v2.md").write_text("active prompt\n", encoding="utf-8")
        (role_dir / "v1.md").write_text("legacy prompt\n", encoding="utf-8")

        result = runner.invoke(app, ["prompts", "show", "analyst", "--version", "v1", "--root-dir", str(tmp_path)])

        assert result.exit_code == 0
        assert "analyst v1" in result.output
        assert "legacy prompt" in result.output
