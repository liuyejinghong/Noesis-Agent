# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

import pytest

from noesis_agent.core.model_registry import ModelInfo, ModelRegistry, ProviderInfo


def write_toml(path: Path, content: str) -> Path:
    _ = path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


class TestProviderInfo:
    def test_resolve_api_key_reads_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("RELAY_API_KEY", "secret")
        provider = ProviderInfo(
            name="Claude Relay",
            provider_type="relay",
            base_url="https://api.example.com/v1",
            api_key_env="RELAY_API_KEY",
        )

        assert provider.resolve_api_key() == "secret"

    def test_resolve_api_key_returns_none_without_env(self) -> None:
        provider = ProviderInfo(name="OAuth", provider_type="oauth_openai")

        assert provider.resolve_api_key() is None


class TestModelInfo:
    def test_defaults(self) -> None:
        model = ModelInfo(model_id="gpt-5", provider_id="gpt_oauth")

        assert model.model_id == "gpt-5"
        assert model.provider_id == "gpt_oauth"
        assert model.tier == "mid"
        assert model.capabilities == []
        assert model.cost == "$"


class TestModelRegistry:
    def test_loads_providers_and_models_from_toml(self, tmp_path: Path) -> None:
        config_path = write_toml(
            tmp_path / "models.toml",
            """
            [providers.claude_relay]
            name = "Claude"
            type = "relay"
            base_url = "https://api.example.com/v1"
            api_key_env = "CLAUDE_KEY"

            [models.claude-sonnet-4-6]
            provider = "claude_relay"
            tier = "mid"
            capabilities = ["analysis", "code"]
            cost = "$"
            """,
        )

        registry = ModelRegistry(config_path)

        assert registry.providers["claude_relay"].name == "Claude"
        assert registry.models["claude-sonnet-4-6"].provider_id == "claude_relay"
        assert registry.models["claude-sonnet-4-6"].capabilities == ["analysis", "code"]

    def test_list_models_returns_sorted_models(self, tmp_path: Path) -> None:
        config_path = write_toml(
            tmp_path / "models.toml",
            """
            [providers.shared]
            name = "Shared"
            type = "relay"
            base_url = "https://api.example.com/v1"
            api_key_env = "SHARED_KEY"

            [models.low-model]
            provider = "shared"
            tier = "low"

            [models.high-model]
            provider = "shared"
            tier = "high"

            [models.mid-model]
            provider = "shared"
            tier = "mid"
            """,
        )

        registry = ModelRegistry(config_path)

        assert [model.model_id for model in registry.list_models()] == ["high-model", "mid-model", "low-model"]

    def test_list_models_filters_by_tier(self, tmp_path: Path) -> None:
        config_path = write_toml(
            tmp_path / "models.toml",
            """
            [providers.shared]
            name = "Shared"
            type = "relay"

            [models.high-model]
            provider = "shared"
            tier = "high"

            [models.mid-model]
            provider = "shared"
            tier = "mid"
            """,
        )

        registry = ModelRegistry(config_path)

        assert [model.model_id for model in registry.list_models(tier="high")] == ["high-model"]

    def test_get_provider_returns_provider_for_model(self, tmp_path: Path) -> None:
        config_path = write_toml(
            tmp_path / "models.toml",
            """
            [providers.gpt_oauth]
            name = "GPT OAuth"
            type = "oauth_openai"

            [models.gpt-5]
            provider = "gpt_oauth"
            """,
        )

        registry = ModelRegistry(config_path)

        provider = registry.get_provider("gpt-5")

        assert provider is not None
        assert provider.name == "GPT OAuth"

    def test_get_provider_returns_none_for_unknown_model(self, tmp_path: Path) -> None:
        config_path = write_toml(
            tmp_path / "models.toml",
            """
            [providers.gpt_oauth]
            name = "GPT OAuth"
            type = "oauth_openai"
            """,
        )

        registry = ModelRegistry(config_path)

        assert registry.get_provider("missing-model") is None

    def test_test_model_returns_failure_for_unknown_model(self, tmp_path: Path) -> None:
        config_path = write_toml(
            tmp_path / "models.toml",
            """
            [providers.gpt_oauth]
            name = "GPT OAuth"
            type = "oauth_openai"
            """,
        )

        registry = ModelRegistry(config_path)

        result = registry.test_model("missing-model")

        assert result.model_id == "missing-model"
        assert result.success is False
        assert result.error == "Model not found"
