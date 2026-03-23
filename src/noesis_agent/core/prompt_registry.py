from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class PromptVersion:
    role: str
    version: str
    content: str
    changelog: str = ""


@dataclass(frozen=True)
class PromptMeta:
    role: str
    active_version: str
    versions: list[dict[str, str]] = field(default_factory=list)


class PromptRegistry:
    def __init__(self, prompts_dir: Path):
        self._dir = prompts_dir

    def load_prompt(self, role: str, version: str | None = None) -> PromptVersion:
        role_dir = self._dir / role
        if not role_dir.exists():
            raise FileNotFoundError(f"No prompts found for role: {role}")

        meta = self._load_meta(role)
        target_version = version or meta.active_version
        prompt_file = role_dir / f"{target_version}.md"
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt version {target_version} not found for role {role}")

        content = prompt_file.read_text(encoding="utf-8").strip()
        changelog = ""
        for item in meta.versions:
            if item.get("version") == target_version:
                changelog = item.get("changelog", "")
                break

        return PromptVersion(role=role, version=target_version, content=content, changelog=changelog)

    def list_versions(self, role: str) -> list[dict[str, str]]:
        meta = self._load_meta(role)
        return meta.versions

    def list_roles(self) -> list[str]:
        if not self._dir.exists():
            return []
        return sorted(d.name for d in self._dir.iterdir() if d.is_dir() and (d / "meta.toml").exists())

    def _load_meta(self, role: str) -> PromptMeta:
        meta_file = self._dir / role / "meta.toml"
        if not meta_file.exists():
            raise FileNotFoundError(f"No meta.toml found for role: {role}")
        with meta_file.open("rb") as file_obj:
            data = tomllib.load(file_obj)
        return PromptMeta(
            role=role,
            active_version=data.get("active_version", "v1"),
            versions=data.get("versions", []),
        )
