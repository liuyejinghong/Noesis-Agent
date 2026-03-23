# Prompt Versioning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move agent prompts into versioned markdown files with a shared registry, CLI inspection commands, and compatibility-preserving fallbacks.

**Architecture:** Introduce a filesystem-backed `PromptRegistry`, wire `prompts_dir` through bootstrap and orchestration, and keep role-local fallback constants so tests and minimal environments still work without prompt assets.

**Tech Stack:** Python 3.11+, `tomllib`, Typer, Rich, pytest, Ruff

---

### Task 1: Add failing tests for prompt registry

**Files:**
- Create: `tests/unit/test_prompt_registry.py`
- Modify: `src/noesis_agent/core/prompt_registry.py`

**Step 1: Write the failing test**

Cover:
- active-version load
- explicit-version load
- `list_roles`
- `list_versions`
- missing role
- missing version

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_prompt_registry.py -q`
Expected: FAIL because `PromptRegistry` does not exist yet.

**Step 3: Write minimal implementation**

Add `PromptVersion`, `PromptMeta`, and `PromptRegistry` in `src/noesis_agent/core/prompt_registry.py`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_prompt_registry.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add tests/unit/test_prompt_registry.py src/noesis_agent/core/prompt_registry.py
git commit -m "feat(prompts): add prompt registry with versioned markdown files"
```

### Task 2: Add failing tests for prompt-backed roles and wiring

**Files:**
- Modify: `tests/unit/test_analyst_agent.py`
- Modify: `tests/unit/test_proposer_agent.py`
- Modify: `tests/unit/test_validator_agent.py`
- Modify: `tests/unit/test_orchestrator.py`
- Modify: `tests/unit/test_bootstrap.py`
- Modify: `src/noesis_agent/agent/roles/analyst.py`
- Modify: `src/noesis_agent/agent/roles/proposer.py`
- Modify: `src/noesis_agent/agent/roles/validator.py`
- Modify: `src/noesis_agent/agent/orchestrator.py`
- Modify: `src/noesis_agent/bootstrap.py`
- Create: `config/prompts/analyst/meta.toml`
- Create: `config/prompts/analyst/v1.md`
- Create: `config/prompts/proposer/meta.toml`
- Create: `config/prompts/proposer/v1.md`
- Create: `config/prompts/validator/meta.toml`
- Create: `config/prompts/validator/v1.md`

**Step 1: Write the failing tests**

Add tests covering:
- fallback path when `prompts_dir` is `None`
- prompt-backed agent creation when `prompts_dir` is provided
- orchestrator stores `prompts_dir`
- bootstrap points orchestrator at `root/config/prompts`

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_analyst_agent.py tests/unit/test_proposer_agent.py tests/unit/test_validator_agent.py tests/unit/test_orchestrator.py tests/unit/test_bootstrap.py -q`
Expected: FAIL on new prompt versioning expectations.

**Step 3: Write minimal implementation**

Thread `prompts_dir` into role factories, orchestrator, and bootstrap. Add the prompt files under `config/prompts/`.

**Step 4: Run tests to verify they pass**

Run the same pytest command.
Expected: PASS.

**Step 5: Commit**

```bash
git add config/prompts src/noesis_agent/agent/roles src/noesis_agent/agent/orchestrator.py src/noesis_agent/bootstrap.py tests/unit/test_analyst_agent.py tests/unit/test_proposer_agent.py tests/unit/test_validator_agent.py tests/unit/test_orchestrator.py tests/unit/test_bootstrap.py
git commit -m "feat(prompts): migrate agent prompts from code to versioned files"
```

### Task 3: Add failing tests for prompt CLI commands

**Files:**
- Modify: `tests/unit/test_cli.py`
- Modify: `src/noesis_agent/cli.py`

**Step 1: Write the failing tests**

Add tests for:
- `noesis prompts list`
- `noesis prompts show analyst`
- `noesis prompts show analyst --version v1`

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: FAIL because prompt commands are missing.

**Step 3: Write minimal implementation**

Add a Typer subgroup for prompt inspection and use `PromptRegistry` with `_get_app()`.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_cli.py -q`
Expected: PASS.

**Step 5: Commit**

```bash
git add src/noesis_agent/cli.py tests/unit/test_cli.py
git commit -m "feat(cli): add noesis prompts list/show commands"
```

### Task 4: Final verification

**Files:**
- Verify all changed files

**Step 1: Run diagnostics and tests**

Run:
- `uv run pytest tests/ -q`
- `uv run ruff check src/ tests/`
- `uv run noesis prompts list`
- `uv run noesis prompts show analyst`

**Step 2: Confirm clean outputs**

Expected:
- all tests pass
- Ruff is clean
- prompt list shows 3 roles
- prompt show prints analyst header and prompt body
