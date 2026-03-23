from __future__ import annotations

from pathlib import Path

import pytest

from noesis_agent.core.prompt_registry import PromptRegistry


def write_prompt_fixture(base_dir: Path, *, role: str = "analyst") -> Path:
    role_dir = base_dir / role
    role_dir.mkdir(parents=True)
    meta_content = (
        'active_version = "v2"\n\n'
        "[[versions]]\n"
        'version = "v1"\n'
        'date = "2026-03-23"\n'
        'changelog = "initial"\n\n'
        "[[versions]]\n"
        'version = "v2"\n'
        'date = "2026-03-24"\n'
        'changelog = "updated"\n'
    )
    _ = (role_dir / "meta.toml").write_text(
        meta_content,
        encoding="utf-8",
    )
    _ = (role_dir / "v1.md").write_text("first prompt\n", encoding="utf-8")
    _ = (role_dir / "v2.md").write_text("second prompt\n", encoding="utf-8")
    return role_dir


def test_load_prompt_uses_active_version_from_meta(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    _ = write_prompt_fixture(prompts_dir)
    registry = PromptRegistry(prompts_dir)

    prompt = registry.load_prompt("analyst")

    assert prompt.role == "analyst"
    assert prompt.version == "v2"
    assert prompt.content == "second prompt"
    assert prompt.changelog == "updated"


def test_load_prompt_allows_explicit_version(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    _ = write_prompt_fixture(prompts_dir)
    registry = PromptRegistry(prompts_dir)

    prompt = registry.load_prompt("analyst", version="v1")

    assert prompt.version == "v1"
    assert prompt.content == "first prompt"
    assert prompt.changelog == "initial"


def test_list_roles_returns_all_prompt_roles(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    _ = write_prompt_fixture(prompts_dir, role="validator")
    _ = write_prompt_fixture(prompts_dir, role="analyst")
    registry = PromptRegistry(prompts_dir)

    assert registry.list_roles() == ["analyst", "validator"]


def test_list_versions_returns_version_history(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    _ = write_prompt_fixture(prompts_dir)
    registry = PromptRegistry(prompts_dir)

    versions = registry.list_versions("analyst")

    assert versions == [
        {"version": "v1", "date": "2026-03-23", "changelog": "initial"},
        {"version": "v2", "date": "2026-03-24", "changelog": "updated"},
    ]


def test_load_prompt_raises_for_missing_role(tmp_path: Path) -> None:
    registry = PromptRegistry(tmp_path / "prompts")

    with pytest.raises(FileNotFoundError, match="No prompts found for role: analyst"):
        _ = registry.load_prompt("analyst")


def test_load_prompt_raises_for_missing_version(tmp_path: Path) -> None:
    prompts_dir = tmp_path / "prompts"
    _ = write_prompt_fixture(prompts_dir)
    registry = PromptRegistry(prompts_dir)

    with pytest.raises(FileNotFoundError, match="Prompt version v3 not found for role analyst"):
        _ = registry.load_prompt("analyst", version="v3")
