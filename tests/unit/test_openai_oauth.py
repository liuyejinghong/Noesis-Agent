from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
from typing import Any

import httpx

from noesis_agent.auth.constants import BASE_URL, CLIENT_ID, REDIRECT_URI, TOKEN_URL
from noesis_agent.auth.openai_oauth import (
    OpenAIAuthManager,
    OAuthCallbackState,
    build_callback_handler,
    extract_account_id,
)


def _make_jwt(payload: dict[str, Any]) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}."


class DummyServer:
    def __init__(self) -> None:
        self.shutdown_called = False

    def shutdown(self) -> None:
        self.shutdown_called = True


class DummySocket:
    def makefile(self, *_args: object, **_kwargs: object) -> Any:
        return self

    def sendall(self, _data: bytes) -> None:
        return None

    def close(self) -> None:
        return None

    def flush(self) -> None:
        return None

    def write(self, _data: bytes) -> int:
        return 0

    def readline(self, *_args: object, **_kwargs: object) -> bytes:
        return b"GET /auth/callback?code=oauth-code HTTP/1.1\r\n"


class DummyWFile:
    def write(self, _data: bytes) -> int:
        return 0


def test_save_and_load_tokens_round_trip(tmp_path: Path) -> None:
    auth_file = tmp_path / "auth" / "openai.json"
    manager = OpenAIAuthManager(auth_file=auth_file)
    payload = {
        "type": "oauth",
        "access": "access-token",
        "refresh": "refresh-token",
        "expires": 1234567890000,
        "accountId": "acct_123",
    }

    manager.save_tokens(payload)

    assert auth_file.exists()
    assert manager.load_tokens() == payload


def test_refresh_tokens_posts_expected_payload(monkeypatch: Any, tmp_path: Path) -> None:
    manager = OpenAIAuthManager(auth_file=tmp_path / "openai.json")
    manager.save_tokens(
        {
            "type": "oauth",
            "access": "old-access",
            "refresh": "refresh-token",
            "expires": 1,
            "accountId": "acct_123",
        }
    )
    captured: dict[str, Any] = {}

    def fake_post(url: str, *, data: dict[str, str], timeout: float) -> httpx.Response:
        captured.update({"url": url, "data": data, "timeout": timeout})
        return httpx.Response(
            200,
            json={
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_in": 3600,
                "id_token": _make_jwt({"chatgpt_account_id": "acct_999"}),
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    refreshed = manager.refresh_tokens()

    assert captured == {
        "url": TOKEN_URL,
        "data": {
            "grant_type": "refresh_token",
            "refresh_token": "refresh-token",
            "client_id": CLIENT_ID,
        },
        "timeout": 10.0,
    }
    assert refreshed["access"] == "new-access"
    assert refreshed["refresh"] == "new-refresh"
    assert refreshed["accountId"] == "acct_999"


def test_ensure_valid_refreshes_when_expiring_soon(monkeypatch: Any, tmp_path: Path) -> None:
    manager = OpenAIAuthManager(auth_file=tmp_path / "openai.json")
    manager.save_tokens(
        {
            "type": "oauth",
            "access": "soon-expired",
            "refresh": "refresh-token",
            "expires": 1,
            "accountId": "acct_123",
        }
    )
    calls: list[str] = []

    def fake_refresh() -> dict[str, Any]:
        calls.append("refresh")
        refreshed = {
            "type": "oauth",
            "access": "fresh-access",
            "refresh": "fresh-refresh",
            "expires": 9999999999999,
            "accountId": "acct_456",
        }
        manager.save_tokens(refreshed)
        return refreshed

    monkeypatch.setattr(manager, "refresh_tokens", fake_refresh)

    tokens = manager.ensure_valid(now_ms=0)

    assert calls == ["refresh"]
    assert tokens["access"] == "fresh-access"


def test_extract_account_id_uses_fallback_priority() -> None:
    direct = _make_jwt({"chatgpt_account_id": "acct_direct"})
    namespaced = _make_jwt({"https://api.openai.com/auth.chatgpt_account_id": "acct_namespaced"})
    org = _make_jwt({"organizations": [{"id": "org_123"}]})

    assert extract_account_id(direct) == "acct_direct"
    assert extract_account_id(namespaced) == "acct_namespaced"
    assert extract_account_id(org) == "org_123"


def test_make_provider_uses_codex_base_url_and_headers(monkeypatch: Any, tmp_path: Path) -> None:
    manager = OpenAIAuthManager(auth_file=tmp_path / "openai.json")
    manager.save_tokens(
        {
            "type": "oauth",
            "access": "oauth-access",
            "refresh": "oauth-refresh",
            "expires": 9999999999999,
            "accountId": "acct_123",
        }
    )

    provider = manager.make_provider()

    assert str(provider.base_url).rstrip("/") == BASE_URL
    assert provider.client.api_key == "oauth-access"
    assert provider.client.default_headers["User-Agent"] == "noesis-agent/0.1.0"
    assert provider.client.default_headers["ChatGPT-Account-Id"] == "acct_123"


def test_callback_handler_captures_code_and_triggers_shutdown(monkeypatch: Any) -> None:
    state = OAuthCallbackState(done=threading.Event())
    server = DummyServer()
    shutdown_calls: list[str] = []
    original_thread = threading.Thread

    class ImmediateThread:
        def __init__(self, target: Any, *_args: Any, **_kwargs: Any) -> None:
            self._target = target

        def start(self) -> None:
            shutdown_calls.append("started")
            self._target()

    monkeypatch.setattr(threading, "Thread", ImmediateThread)
    handler_cls = build_callback_handler(state)

    handler = object.__new__(handler_cls)
    handler.path = "/auth/callback?code=oauth-code"
    handler.server = server
    handler.wfile = DummyWFile()
    handler.send_response = lambda _status: None
    handler.send_header = lambda _key, _value: None
    handler.end_headers = lambda: None

    handler.do_GET()
    monkeypatch.setattr(threading, "Thread", original_thread)

    assert state.code == "oauth-code"
    assert state.done.is_set() is True
    assert shutdown_calls == ["started"]
    assert server.shutdown_called is True


def test_callback_handler_ignores_non_callback_path() -> None:
    state = OAuthCallbackState(done=threading.Event())
    handler_cls = build_callback_handler(state)

    handler = object.__new__(handler_cls)
    handler.path = "/other"
    handler.server = DummyServer()
    handler.wfile = DummyWFile()
    handler.send_error = lambda _status: None

    handler.do_GET()

    assert state.code is None
    assert state.done.is_set() is False


def test_login_authorization_url_contains_pkce_and_redirect(monkeypatch: Any, tmp_path: Path) -> None:
    opened_urls: list[str] = []
    state = OAuthCallbackState(code="oauth-code", done=threading.Event())
    state.done.set()

    class DummyHTTPServer:
        def __init__(self, server_address: tuple[str, int], handler_cls: Any) -> None:
            self.server_address = server_address
            self.handler_cls = handler_cls

        def serve_forever(self) -> None:
            return None

        def shutdown(self) -> None:
            return None

        def server_close(self) -> None:
            return None

    def fake_post(url: str, *, data: dict[str, str], timeout: float) -> httpx.Response:
        assert url == TOKEN_URL
        assert data["code"] == "oauth-code"
        assert data["redirect_uri"] == REDIRECT_URI
        assert data["client_id"] == CLIENT_ID
        assert data["grant_type"] == "authorization_code"
        assert data["code_verifier"]
        return httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 3600,
                "id_token": _make_jwt({"chatgpt_account_id": "acct_123"}),
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    from noesis_agent.auth import openai_oauth

    monkeypatch.setattr(openai_oauth.webbrowser, "open", lambda url: opened_urls.append(url))
    monkeypatch.setattr(openai_oauth, "OAuthCallbackState", lambda: state)
    monkeypatch.setattr(openai_oauth, "HTTPServer", DummyHTTPServer)

    tokens = openai_oauth.openai_login(auth_file=tmp_path / "openai.json")

    assert tokens["access"] == "access-token"
    assert opened_urls
    assert "code_challenge=" in opened_urls[0]
    assert "response_type=code" in opened_urls[0]
    assert f"redirect_uri={REDIRECT_URI.replace(':', '%3A').replace('/', '%2F')}" in opened_urls[0]
