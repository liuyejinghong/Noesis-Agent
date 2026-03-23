# `noesis chat` Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `noesis chat` command — REPL + single-shot — that lets users talk to a GPT-5.4 agent which knows it's Noesis Agent and can call existing system tools (status, analyze, config, data collect, etc.).

**Architecture:** PydanticAI Agent with `chat` role, system prompt describing Noesis capabilities, PydanticAI tools wrapping existing CLI functions, message history persisted to SQLite via `MemoryStore`. REPL loop uses `prompt_toolkit` for readline-style input. Single-shot via `noesis chat "message"`.

**Tech Stack:** PydanticAI (agent + tools + message_history), typer (CLI), prompt_toolkit (REPL input), rich (output rendering), SQLite (history persistence via existing MemoryStore pattern).

---

### Task 1: Add `chat` role to config

**Files:**
- Modify: `config/config.toml`

**Step 1: Add chat role config**

Add to `config/config.toml`:
```toml
[agent_roles.chat]
model = "gpt-5.4"
auth_type = "oauth_openai"
output_format = "text"
```

**Step 2: Verify config loads**

Run: `uv run python -c "from noesis_agent.bootstrap import AppBootstrap; b = AppBootstrap(); print(b.router.list_roles())"`
Expected: `['analyst', 'proposer', 'validator', 'chat']`

**Step 3: Commit**

```bash
git add config/config.toml
git commit -m "feat(config): add chat agent role using GPT-5.4"
```

---

### Task 2: Create chat agent with system prompt and tools

**Files:**
- Create: `src/noesis_agent/agent/roles/chat.py`
- Test: `tests/unit/test_chat_agent.py`

**Step 1: Write failing test**

```python
# tests/unit/test_chat_agent.py
from noesis_agent.agent.roles.chat import CHAT_SYSTEM_PROMPT, ChatDeps, create_chat_tools

def test_system_prompt_describes_noesis():
    assert "Noesis" in CHAT_SYSTEM_PROMPT
    assert "策略" in CHAT_SYSTEM_PROMPT

def test_chat_tools_are_callable():
    tools = create_chat_tools()
    tool_names = [t.__name__ for t in tools]
    assert "show_system_status" in tool_names
    assert "show_config" in tool_names
    assert "list_proposals" in tool_names
    assert "list_strategies" in tool_names
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_chat_agent.py -v`
Expected: FAIL — module not found

**Step 3: Implement chat agent**

Create `src/noesis_agent/agent/roles/chat.py`:

- `CHAT_SYSTEM_PROMPT` — Chinese, describes Noesis Agent identity, available tools, capabilities
- `ChatDeps` dataclass — holds `AppBootstrap` reference
- `create_chat_tools()` — returns list of plain functions that wrap existing CLI logic:
  - `show_system_status(deps)` → calls bootstrap.settings + proposal_manager
  - `show_config(deps)` → returns current config as formatted string
  - `list_proposals(deps, status)` → calls memory.get_proposals
  - `list_strategies(deps)` → calls strategy_catalog.list_active
  - `run_analysis(deps, strategy_id, period)` → calls orchestrator.run_analysis
  - `run_full_cycle(deps, strategy_id, period)` → calls orchestrator.run_full_cycle
  - `collect_data(deps, symbols)` → calls BinanceDataCollector
  - `search_memory(deps, query)` → calls memory.search_similar

Each tool is a `@agent.tool` decorated async function that takes `RunContext[ChatDeps]`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_chat_agent.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/noesis_agent/agent/roles/chat.py tests/unit/test_chat_agent.py
git commit -m "feat(agent): add chat role with system prompt and tool definitions"
```

---

### Task 3: Implement chat session persistence

**Files:**
- Create: `src/noesis_agent/agent/chat_session.py`
- Test: `tests/unit/test_chat_session.py`

**Step 1: Write failing test**

```python
# tests/unit/test_chat_session.py
import json
from pathlib import Path
from noesis_agent.agent.chat_session import ChatSessionStore

def test_save_and_load_session(tmp_path):
    store = ChatSessionStore(tmp_path / "sessions")
    messages = [{"role": "user", "content": "hello"}]
    session_id = store.save("test_session", messages)
    loaded = store.load("test_session")
    assert loaded == messages

def test_list_sessions(tmp_path):
    store = ChatSessionStore(tmp_path / "sessions")
    store.save("s1", [{"role": "user", "content": "a"}])
    store.save("s2", [{"role": "user", "content": "b"}])
    sessions = store.list_sessions()
    assert len(sessions) == 2

def test_load_nonexistent_returns_empty(tmp_path):
    store = ChatSessionStore(tmp_path / "sessions")
    assert store.load("nonexistent") == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_chat_session.py -v`
Expected: FAIL

**Step 3: Implement ChatSessionStore**

Simple JSON file-based storage in `state/chat_sessions/`:
- `save(session_id, messages_json)` → writes `{session_id}.json`
- `load(session_id)` → reads and returns messages list, or `[]`
- `list_sessions()` → lists `.json` files with metadata (name, last modified, message count)
- Uses `pydantic_ai` `ModelMessage` JSON serialization via `result.all_messages_json()`

**Step 4: Run test, verify pass**

**Step 5: Commit**

```bash
git add src/noesis_agent/agent/chat_session.py tests/unit/test_chat_session.py
git commit -m "feat(agent): add chat session persistence"
```

---

### Task 4: Add `noesis chat` CLI command

**Files:**
- Modify: `src/noesis_agent/cli.py`
- Test: `tests/unit/test_cli_chat.py`

**Step 1: Write failing test**

```python
# tests/unit/test_cli_chat.py
from typer.testing import CliRunner
from noesis_agent.cli import app

runner = CliRunner()

def test_chat_command_exists():
    result = runner.invoke(app, ["chat", "--help"])
    assert result.exit_code == 0
    assert "对话" in result.stdout or "chat" in result.stdout.lower()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli_chat.py -v`
Expected: FAIL — no such command "chat"

**Step 3: Implement `chat` command in cli.py**

Add to `cli.py`:

```python
@app.command(help="与 Noesis Agent 对话")
def chat(
    message: Annotated[str | None, typer.Argument(help="单轮消息，不传则进入 REPL")] = None,
    session: Annotated[str, typer.Option("--session", "-s", help="会话名")] = "default",
    new: Annotated[bool, typer.Option("--new", help="开启新会话")] = False,
    root_dir: ...,
    config: ...,
) -> None:
```

Logic:
1. Bootstrap app, create chat agent via `router.create_agent("chat", ...)`
2. Load session history from `ChatSessionStore`
3. If `message` provided → single-shot: run agent once, print, save, exit
4. If no `message` → enter REPL loop:
   - Print welcome banner
   - `prompt_toolkit` input loop
   - Each turn: `agent.run(user_input, message_history=history)`
   - Append `result.new_messages()` to history
   - Render response with `rich` Markdown
   - Save session after each turn
   - Ctrl+C / "exit" / "quit" to quit

**Step 4: Run test to verify it passes**

**Step 5: Commit**

```bash
git add src/noesis_agent/cli.py tests/unit/test_cli_chat.py
git commit -m "feat(cli): add noesis chat command with REPL and single-shot modes"
```

---

### Task 5: Integration test — full chat round-trip

**Files:**
- Test: `tests/unit/test_chat_integration.py`

**Step 1: Write integration test**

Test that:
- Chat agent can be created with tools
- System prompt is set correctly
- Session save/load round-trips work
- Tool list matches expected set

This is a "wiring" test, not an LLM test — it verifies the pieces connect.

**Step 2: Run all tests**

Run: `uv run pytest tests/unit/ -v`
Expected: All pass

**Step 3: Commit**

```bash
git add tests/unit/test_chat_integration.py
git commit -m "test(chat): add integration wiring tests"
```

---

### Task 6: Add `prompt_toolkit` dependency if missing

**Files:**
- Modify: `pyproject.toml`

**Step 1: Check if prompt_toolkit is already available**

`prompt_toolkit` ships with `typer[all]` which is already a dependency. Verify:

Run: `uv run python -c "import prompt_toolkit; print(prompt_toolkit.__version__)"`

If it works, skip this task. If not, add `prompt_toolkit>=3.0` to dependencies.

**Step 2: Commit if changed**

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Config: add `chat` role | `config/config.toml` |
| 2 | Agent: system prompt + tools | `agent/roles/chat.py` |
| 3 | Persistence: session store | `agent/chat_session.py` |
| 4 | CLI: `noesis chat` command | `cli.py` |
| 5 | Tests: integration wiring | `test_chat_integration.py` |
| 6 | Deps: verify prompt_toolkit | `pyproject.toml` |
