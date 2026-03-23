from __future__ import annotations

import json
from pathlib import Path


class ChatSessionStore:
    def __init__(self, sessions_dir: Path) -> None:
        self._dir = sessions_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe_name = session_id.replace("/", "_").replace("\\", "_")
        return self._dir / f"{safe_name}.json"

    def save(self, session_id: str, messages_json: bytes) -> None:
        self._path(session_id).write_bytes(messages_json)

    def load(self, session_id: str) -> bytes | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        return path.read_bytes()

    def list_sessions(self) -> list[dict[str, str]]:
        sessions = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                msg_count = len(data) if isinstance(data, list) else 0
            except (json.JSONDecodeError, OSError):
                msg_count = 0
            sessions.append(
                {
                    "session_id": path.stem,
                    "message_count": str(msg_count),
                    "modified": str(path.stat().st_mtime),
                }
            )
        return sessions

    def delete(self, session_id: str) -> bool:
        path = self._path(session_id)
        if path.exists():
            path.unlink()
            return True
        return False
