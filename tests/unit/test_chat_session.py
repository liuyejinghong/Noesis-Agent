from __future__ import annotations

import json

from noesis_agent.agent.chat_session import ChatSessionStore


class TestChatSessionStore:
    def test_save_and_load(self, tmp_path):
        store = ChatSessionStore(tmp_path / "sessions")
        data = [{"role": "user", "parts": [{"content": "hello"}]}]
        store.save("test_session", json.dumps(data).encode())
        loaded = store.load("test_session")
        assert loaded is not None
        assert json.loads(loaded) == data

    def test_load_nonexistent_returns_none(self, tmp_path):
        store = ChatSessionStore(tmp_path / "sessions")
        assert store.load("nonexistent") is None

    def test_list_sessions(self, tmp_path):
        store = ChatSessionStore(tmp_path / "sessions")
        store.save("s1", json.dumps([{"role": "user"}]).encode())
        store.save("s2", json.dumps([{"role": "user"}, {"role": "assistant"}]).encode())
        sessions = store.list_sessions()
        assert len(sessions) == 2
        ids = {s["session_id"] for s in sessions}
        assert ids == {"s1", "s2"}

    def test_list_sessions_message_count(self, tmp_path):
        store = ChatSessionStore(tmp_path / "sessions")
        store.save("s1", json.dumps([1, 2, 3]).encode())
        sessions = store.list_sessions()
        assert sessions[0]["message_count"] == "3"

    def test_delete(self, tmp_path):
        store = ChatSessionStore(tmp_path / "sessions")
        store.save("to_delete", b"[]")
        assert store.delete("to_delete") is True
        assert store.load("to_delete") is None

    def test_delete_nonexistent(self, tmp_path):
        store = ChatSessionStore(tmp_path / "sessions")
        assert store.delete("nope") is False

    def test_creates_dir(self, tmp_path):
        sessions_dir = tmp_path / "deep" / "nested" / "sessions"
        store = ChatSessionStore(sessions_dir)
        store.save("x", b"[]")
        assert sessions_dir.exists()
