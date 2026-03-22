# OpenAI OAuth Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add `noesis login openai` OAuth PKCE login so Noesis can authenticate with ChatGPT accounts, store refreshable tokens locally, and route configured agents through the Codex-compatible OpenAI backend without API keys.

**Architecture:** Add a dedicated auth module for constants, token persistence, PKCE login, JWT account extraction, refresh, and provider creation. Keep CLI auth commands thin by delegating token work to `OpenAIAuthManager`, and extend `ModelRouter` to create `OpenAIProvider` instances from stored OAuth credentials when `AgentRoleConfig.auth_type == "oauth_openai"`.

**Tech Stack:** Typer / Pydantic v2 / PydanticAI OpenAI provider / httpx / stdlib HTTP server / pytest / authlib (dependency only)

---

### Task 1: OAuth token manager tests

**Files:**
- Create: `tests/unit/test_openai_oauth.py`

**Step 1: Write the failing tests**

Add tests for:
- saving/loading `~/.noesis/auth/openai.json`-shaped payloads via a temp path
- refresh requests posting `grant_type=refresh_token`, `refresh_token`, and `client_id`
- `ensure_valid()` refreshing when expiry is within 30 seconds
- JWT account-id extraction fallback order
- `make_provider()` returning an `OpenAIProvider` using the Codex base URL
- login callback handler capturing an auth code and stopping the local server

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_openai_oauth.py -q`
Expected: FAIL because auth module does not exist yet.

**Step 3: Write minimal implementation**

Create:
- `src/noesis_agent/auth/__init__.py`
- `src/noesis_agent/auth/constants.py`
- `src/noesis_agent/auth/openai_oauth.py`

Implement:
- OAuth constants
- token dataclass/model or dict-based manager logic
- PKCE helpers
- JWT payload decode helper
- refresh + ensure-valid logic
- provider creation with custom headers
- login flow with localhost callback server and clean shutdown

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_openai_oauth.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/test_openai_oauth.py src/noesis_agent/auth/__init__.py src/noesis_agent/auth/constants.py src/noesis_agent/auth/openai_oauth.py
git commit -m "feat(auth): add OpenAI OAuth PKCE login flow with token management"
```

### Task 2: CLI and router integration tests

**Files:**
- Modify: `tests/unit/test_cli.py`
- Modify: `tests/unit/test_agent_models.py`
- Modify: `tests/unit/test_config.py`

**Step 1: Write the failing tests**

Add tests for:
- `noesis login status` showing `未登录` when token file is missing
- `noesis login logout` succeeding even when no login exists
- `AgentRoleConfig(auth_type="oauth_openai")` accepting and exposing the field
- `ModelRouter.create_agent()` building an OAuth-backed `OpenAIChatModel` through `OpenAIAuthManager`

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_agent_models.py tests/unit/test_config.py -q`
Expected: FAIL because config/CLI/router do not support OAuth yet.

**Step 3: Write minimal implementation**

Modify:
- `src/noesis_agent/core/config.py`
- `src/noesis_agent/agent/models.py`
- `src/noesis_agent/cli.py`

Implement:
- `auth_type: str | None = None` in `AgentRoleConfig`
- router branch for `auth_type == "oauth_openai"`
- `login` Typer group with `openai`, `status`, and `logout` commands

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli.py tests/unit/test_agent_models.py tests/unit/test_config.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/test_cli.py tests/unit/test_agent_models.py tests/unit/test_config.py src/noesis_agent/core/config.py src/noesis_agent/agent/models.py src/noesis_agent/cli.py
git commit -m "feat(auth): integrate OAuth provider into ModelRouter and CLI"
```

### Task 3: Dependency update

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Step 1: Write the failing dependency change**

Add `authlib>=1.4` to project dependencies.

**Step 2: Refresh lockfile**

Run: `uv lock`
Expected: `uv.lock` includes `authlib`.

**Step 3: Verify project still passes**

Run:
- `uv run pytest tests/ -q`
- `uv run ruff check src/ tests/`

Expected: both commands pass cleanly.

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): add authlib for OAuth2Client"
```
