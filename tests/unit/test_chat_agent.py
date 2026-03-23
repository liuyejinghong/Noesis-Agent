from __future__ import annotations

from noesis_agent.agent.roles.chat import CHAT_SYSTEM_PROMPT, ChatDeps


class TestChatSystemPrompt:
    def test_identifies_as_noesis(self):
        assert "Noesis" in CHAT_SYSTEM_PROMPT

    def test_mentions_capabilities(self):
        assert "策略" in CHAT_SYSTEM_PROMPT
        assert "分析" in CHAT_SYSTEM_PROMPT
        assert "提案" in CHAT_SYSTEM_PROMPT

    def test_chinese_output(self):
        assert "中文" in CHAT_SYSTEM_PROMPT


class TestChatDeps:
    def test_accepts_bootstrap(self):
        deps = ChatDeps(bootstrap=object())
        assert deps.bootstrap is not None
