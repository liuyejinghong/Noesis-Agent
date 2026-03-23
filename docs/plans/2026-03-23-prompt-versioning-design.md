# Prompt Versioning Design

**Date:** 2026-03-23

## Goal

Externalize agent system prompts from Python source into versioned markdown files under `config/prompts/`, while preserving the current hardcoded strings as a safe fallback for tests and minimal environments.

## Chosen Approach

Use a small `PromptRegistry` in `src/noesis_agent/core/prompt_registry.py` and inject `prompts_dir` from bootstrap into the orchestrator and role factory functions.

Why this approach:
- Keeps prompt storage concerns separate from `ModelRouter`
- Avoids re-reading prompt files during every instruction callback
- Preserves compatibility by keeping hardcoded prompt constants as fallback
- Makes prompt discovery available to CLI and tests through one shared API

## Scope

1. Add registry support for:
- listing roles
- listing versions per role
- loading active or explicit versions
- surfacing changelog metadata

2. Add prompt assets for:
- `analyst`
- `proposer`
- `validator`

3. Update agent creation so each role can load prompts from files when `prompts_dir` is provided, otherwise use existing in-code constants.

4. Thread `prompts_dir` through:
- `AgentOrchestrator`
- `AppBootstrap`
- CLI prompt inspection commands

5. Add CLI support:
- `noesis prompts list`
- `noesis prompts show <role>`
- `noesis prompts show <role> --version <vx>`

## Output Contract

For `noesis prompts show`, print a small header with role and version, then render the markdown body. This keeps the active-version view and explicit-version view unambiguous.

## Error Handling

- Missing role directory -> `FileNotFoundError`
- Missing `meta.toml` -> `FileNotFoundError`
- Missing version file -> `FileNotFoundError`
- CLI catches prompt-loading errors and exits with code 1

## Testing Strategy

- Add unit tests for `PromptRegistry`
- Add agent tests proving fallback still works when `prompts_dir` is `None`
- Add bootstrap/orchestrator tests for `prompts_dir` wiring
- Add CLI tests for `prompts list` and `prompts show`

## Non-Goals

- No hot-reload behavior
- No prompt editing CLI
- No automatic prompt migrations between versions
