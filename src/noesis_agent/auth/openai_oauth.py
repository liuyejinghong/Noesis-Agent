# pyright: reportAny=false, reportImplicitOverride=false, reportIncompatibleMethodOverride=false, reportUnusedCallResult=false

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from openai import AsyncOpenAI
from pydantic_ai.providers.openai import OpenAIProvider

from noesis_agent.auth.constants import (
    AUTH_URL,
    BASE_URL,
    CALLBACK_HOST,
    CALLBACK_PORT,
    CLIENT_ID,
    REDIRECT_URI,
    SCOPE,
    TOKEN_REFRESH_BUFFER_MS,
    TOKEN_URL,
    USER_AGENT,
)


def _default_auth_file() -> Path:
    return Path("~/.noesis/auth/openai.json").expanduser()


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2 or not parts[1]:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        data = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def extract_account_id(token: str | None) -> str | None:
    if not token:
        return None
    payload = _decode_jwt_payload(token)
    direct = payload.get("chatgpt_account_id")
    if isinstance(direct, str) and direct:
        return direct
    namespaced = payload.get("https://api.openai.com/auth.chatgpt_account_id")
    if isinstance(namespaced, str) and namespaced:
        return namespaced
    organizations = payload.get("organizations")
    if isinstance(organizations, list):
        for org in organizations:
            if isinstance(org, dict):
                org_id = org.get("id")
                if isinstance(org_id, str) and org_id:
                    return org_id
    return None


def _now_ms() -> int:
    return int(time.time() * 1000)


def _token_payload(token_response: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    access = token_response["access_token"]
    refresh = token_response.get("refresh_token") or (existing or {}).get("refresh")
    expires_in = int(token_response.get("expires_in", 0))
    account_id = extract_account_id(token_response.get("id_token"))
    if account_id is None:
        account_id = extract_account_id(access)
    if account_id is None and existing is not None:
        existing_account_id = existing.get("accountId")
        if isinstance(existing_account_id, str) and existing_account_id:
            account_id = existing_account_id
    return {
        "type": "oauth",
        "access": access,
        "refresh": refresh,
        "expires": _now_ms() + expires_in * 1000,
        "accountId": account_id,
    }


@dataclass
class OAuthCallbackState:
    code: str | None = None
    error: str | None = None
    expected_state: str | None = None
    done: threading.Event = field(default_factory=threading.Event)


def build_callback_handler(state: OAuthCallbackState) -> type[BaseHTTPRequestHandler]:
    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/auth/callback":
                self.send_error(404)
                return

            query = parse_qs(parsed.query)
            code = query.get("code", [None])[0]
            error = query.get("error", [None])[0]
            callback_state = query.get("state", [None])[0]
            if state.expected_state is not None and callback_state != state.expected_state:
                state.error = "invalid_state"
                state.done.set()
            elif isinstance(code, str) and code:
                state.code = code
            elif isinstance(error, str) and error:
                state.error = error
            else:
                state.error = "missing_code"
            if not state.done.is_set():
                state.done.set()

            body = b"OpenAI login complete. You can return to Noesis Agent."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, _format: str, *_args: object) -> None:
            return None

    return OAuthCallbackHandler


class OpenAIAuthManager:
    def __init__(self, auth_file: Path | None = None):
        self.auth_file = (auth_file or _default_auth_file()).expanduser()

    def load_tokens(self) -> dict[str, Any] | None:
        if not self.auth_file.exists():
            return None
        return json.loads(self.auth_file.read_text(encoding="utf-8"))

    def save_tokens(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.auth_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.auth_file.write_text(json.dumps(payload, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
        os.chmod(self.auth_file, 0o600)
        return payload

    def clear_tokens(self) -> bool:
        if not self.auth_file.exists():
            return False
        self.auth_file.unlink()
        return True

    def refresh_tokens(self) -> dict[str, Any]:
        current = self.load_tokens()
        if current is None:
            raise RuntimeError("Not logged in to OpenAI")
        refresh_token = current.get("refresh")
        if not isinstance(refresh_token, str) or not refresh_token:
            raise RuntimeError("Missing refresh token")

        response = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
            timeout=30.0,
        )
        if response.is_error:
            response.raise_for_status()
        payload = _token_payload(response.json(), existing=current)
        return self.save_tokens(payload)

    def ensure_valid(self, *, now_ms: int | None = None) -> dict[str, Any]:
        tokens = self.load_tokens()
        if tokens is None:
            raise RuntimeError("Not logged in to OpenAI")
        current_time = _now_ms() if now_ms is None else now_ms
        expires = tokens.get("expires")
        if not isinstance(expires, int) or expires - current_time <= TOKEN_REFRESH_BUFFER_MS:
            return self.refresh_tokens()
        return tokens

    def make_provider(self) -> OpenAIProvider:
        tokens = self.ensure_valid()
        headers = {"User-Agent": USER_AGENT}
        account_id = tokens.get("accountId")
        if isinstance(account_id, str) and account_id:
            headers["ChatGPT-Account-Id"] = account_id
        http_client = httpx.AsyncClient(proxy=os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"))
        openai_client = AsyncOpenAI(
            api_key=tokens["access"],
            base_url=BASE_URL,
            default_headers=headers,
            http_client=http_client,
        )
        return OpenAIProvider(openai_client=openai_client)


def _make_codex_model(model_name: str, provider: OpenAIProvider) -> Any:
    from pydantic_ai.models.openai import OpenAIResponsesModel

    class _CodexModel(OpenAIResponsesModel):
        """Codex API requires stream=True and store=False. Overrides request() to force streaming."""

        async def request(self, messages: Any, model_settings: Any = None, model_request_parameters: Any = None) -> Any:
            settings = dict(model_settings or {})
            settings.setdefault("openai_store", False)
            async with super().request_stream(messages, settings, model_request_parameters) as stream:
                async for _ in stream:
                    pass
                return stream.get()

        @asynccontextmanager
        async def request_stream(
            self,
            messages: Any,
            model_settings: Any = None,
            model_request_parameters: Any = None,
            run_context: Any = None,
        ) -> Any:
            settings = dict(model_settings or {})
            settings.setdefault("openai_store", False)
            async with super().request_stream(messages, settings, model_request_parameters, run_context) as stream:
                yield stream

    return _CodexModel(model_name, provider=provider)


def _generate_pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(96))
    challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _authorization_url(code_challenge: str, state: str) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": SCOPE,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "state": state,
            "id_token_add_organizations": "true",
            "codex_cli_simplified_flow": "true",
            "originator": "noesis-agent",
        }
    )
    return f"{AUTH_URL}?{query}"


def openai_login(auth_file: Path | None = None, *, timeout_seconds: float = 300.0) -> dict[str, Any]:
    manager = OpenAIAuthManager(auth_file=auth_file)
    code_verifier, code_challenge = _generate_pkce_pair()
    oauth_state = secrets.token_urlsafe(32)
    state = OAuthCallbackState()
    state.expected_state = oauth_state
    server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), build_callback_handler(state))
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        auth_url = _authorization_url(code_challenge, oauth_state)
        if webbrowser.open(auth_url) is False:
            raise RuntimeError("OpenAI login browser launch failed")
        if not state.done.wait(timeout_seconds):
            raise TimeoutError("Timed out waiting for OpenAI login callback")
        if state.error:
            raise RuntimeError(f"OpenAI login failed: {state.error}")
        if not state.code:
            raise RuntimeError("OpenAI login did not return an authorization code")

        response = httpx.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": state.code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "code_verifier": code_verifier,
            },
            timeout=30.0,
        )
        if response.is_error:
            response.raise_for_status()
        return manager.save_tokens(_token_payload(response.json()))
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=1.0)
