from __future__ import annotations

import json
import os
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import httpx


@dataclass
class ProviderInfo:
    name: str
    provider_type: str
    base_url: str | None = None
    api_key_env: str | None = None

    def resolve_api_key(self) -> str | None:
        if self.api_key_env is None:
            return None
        return os.environ.get(self.api_key_env)


@dataclass
class ModelInfo:
    model_id: str
    provider_id: str
    tier: str = "mid"
    capabilities: list[str] = field(default_factory=list)
    cost: str = "$"


@dataclass
class ModelTestResult:
    model_id: str
    provider: str
    success: bool
    latency_ms: float = 0.0
    error: str = ""


class ModelRegistry:
    def __init__(self, config_path: Path | None = None):
        self.providers: dict[str, ProviderInfo] = {}
        self.models: dict[str, ModelInfo] = {}
        if config_path is not None and config_path.exists():
            self._load(config_path)

    def _load(self, path: Path) -> None:
        with path.open("rb") as file_obj:
            payload: dict[str, object] = tomllib.load(file_obj)

        providers = payload.get("providers", {})
        if isinstance(providers, dict):
            for provider_id, provider_data in providers.items():
                if not isinstance(provider_data, dict):
                    continue
                self.providers[provider_id] = ProviderInfo(
                    name=str(provider_data.get("name", provider_id)),
                    provider_type=str(provider_data.get("type", "relay")),
                    base_url=self._optional_str(provider_data.get("base_url")),
                    api_key_env=self._optional_str(provider_data.get("api_key_env")),
                )

        models = payload.get("models", {})
        if isinstance(models, dict):
            for model_id, model_data in models.items():
                if not isinstance(model_data, dict):
                    continue
                self.models[model_id] = ModelInfo(
                    model_id=model_id,
                    provider_id=str(model_data.get("provider", "")),
                    tier=str(model_data.get("tier", "mid")),
                    capabilities=self._coerce_str_list(model_data.get("capabilities")),
                    cost=str(model_data.get("cost", "$")),
                )

    @staticmethod
    def _optional_str(value: object) -> str | None:
        return value if isinstance(value, str) else None

    @staticmethod
    def _coerce_str_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, str)]

    def list_models(self, tier: str | None = None) -> list[ModelInfo]:
        models = list(self.models.values())
        if tier is not None:
            models = [model for model in models if model.tier == tier]
        order = {"high": 0, "mid": 1, "low": 2}
        return sorted(models, key=lambda model: (order.get(model.tier, 9), model.model_id))

    def get_provider(self, model_id: str) -> ProviderInfo | None:
        model = self.models.get(model_id)
        if model is None:
            return None
        return self.providers.get(model.provider_id)

    def test_model(self, model_id: str) -> ModelTestResult:
        model = self.models.get(model_id)
        if model is None:
            return ModelTestResult(model_id=model_id, provider="?", success=False, error="Model not found")

        provider = self.providers.get(model.provider_id)
        if provider is None:
            return ModelTestResult(model_id=model_id, provider="?", success=False, error="Provider not found")

        if provider.provider_type == "oauth_openai":
            return self._test_oauth_model(model_id, provider)
        return self._test_relay_model(model_id, provider)

    def test_all(self) -> list[ModelTestResult]:
        return [self.test_model(model_id) for model_id in self.models]

    def _test_relay_model(self, model_id: str, provider: ProviderInfo) -> ModelTestResult:
        api_key = provider.resolve_api_key()
        if not api_key:
            return ModelTestResult(
                model_id=model_id,
                provider=provider.name,
                success=False,
                error=f"Missing env: {provider.api_key_env}",
            )

        if not provider.base_url:
            return ModelTestResult(
                model_id=model_id, provider=provider.name, success=False, error="Provider base_url missing"
            )

        try:
            start = time.monotonic()
            response = httpx.post(
                f"{provider.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model_id,
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                },
                timeout=30.0,
            )
            latency_ms = (time.monotonic() - start) * 1000
        except Exception as exc:
            return ModelTestResult(model_id=model_id, provider=provider.name, success=False, error=str(exc))

        if response.status_code == 200:
            return ModelTestResult(model_id=model_id, provider=provider.name, success=True, latency_ms=latency_ms)

        return ModelTestResult(
            model_id=model_id,
            provider=provider.name,
            success=False,
            latency_ms=latency_ms,
            error=f"HTTP {response.status_code}",
        )

    def _test_oauth_model(self, model_id: str, provider: ProviderInfo) -> ModelTestResult:
        try:
            from openai import OpenAI

            from noesis_agent.auth.constants import BASE_URL, USER_AGENT
            from noesis_agent.auth.openai_oauth import OpenAIAuthManager

            manager = OpenAIAuthManager()
            tokens = manager.load_tokens()
            if not tokens:
                return ModelTestResult(model_id=model_id, provider=provider.name, success=False, error="Not logged in")
            access_token = tokens.get("access")
            if not isinstance(access_token, str) or not access_token:
                return ModelTestResult(
                    model_id=model_id, provider=provider.name, success=False, error="Missing access token"
                )

            headers = {"User-Agent": USER_AGENT}
            account_id = tokens.get("accountId")
            if isinstance(account_id, str) and account_id:
                headers["ChatGPT-Account-Id"] = account_id

            client = OpenAI(api_key=access_token, base_url=BASE_URL, default_headers=headers, timeout=30.0)
            start = time.monotonic()
            response = client.models.with_raw_response.list(extra_query={"client_version": "0.1.0"})
            latency_ms = (time.monotonic() - start) * 1000
            payload_raw = cast(object, json.loads(response.text))
        except Exception as exc:
            return ModelTestResult(model_id=model_id, provider=provider.name, success=False, error=str(exc))

        payload = payload_raw if isinstance(payload_raw, dict) else {}

        models_payload = payload.get("models", [])
        available: list[str] = []
        if isinstance(models_payload, list):
            for entry in models_payload:
                if not isinstance(entry, dict):
                    continue
                slug = entry.get("slug")
                if isinstance(slug, str):
                    available.append(slug)
        if model_id in available:
            return ModelTestResult(model_id=model_id, provider=provider.name, success=True, latency_ms=latency_ms)

        return ModelTestResult(
            model_id=model_id,
            provider=provider.name,
            success=False,
            latency_ms=latency_ms,
            error=f"Model not in available list: {available}",
        )
