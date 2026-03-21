# pyright: reportUnusedFunction=false

from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent, RunContext

from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.models import ModelRouter
from noesis_agent.agent.roles.types import Proposal
from noesis_agent.agent.skills.registry import SkillRegistry


@dataclass
class ProposerDeps:
    memory_store: MemoryStore
    skill_registry: SkillRegistry


PROPOSER_INSTRUCTIONS = """你是一个加密货币策略改进师。
基于分析报告的发现，提出具体的策略改进提案。

提案类型：
1. parameter — 调整现有参数
2. code — 修改策略逻辑
3. trade_management — 调整交易管理参数

每个提案必须：
- 明确指出改什么、为什么改
- 给出预期效果
- 基于分析报告中的具体发现
- 一个提案只改一件事

输出必须是中文。"""


def create_proposer_agent(router: ModelRouter) -> Agent[ProposerDeps, Proposal]:
    agent = router.create_agent("proposer", output_type=Proposal, deps_type=ProposerDeps)

    @agent.instructions
    def proposer_instructions() -> str:
        return PROPOSER_INSTRUCTIONS

    @agent.tool
    async def query_failure_memory(ctx: RunContext[ProposerDeps], strategy_id: str, change_type: str) -> str:
        records = ctx.deps.memory_store.query_failures(
            strategy_id=strategy_id,
            category=change_type,
            limit=5,
        )
        if not records:
            return "无相关失败记忆"
        return "\n".join(f"- {record.title}: {record.content[:120]}" for record in records)

    @agent.tool
    async def read_strategy_config(ctx: RunContext[ProposerDeps], strategy_id: str) -> str:
        related_records = ctx.deps.memory_store.search_similar(strategy_id, top_k=5)
        if not related_records:
            return f"未找到策略 {strategy_id} 的相关配置记录"
        return "\n".join(f"- {record.title}: {record.content[:120]}" for record in related_records)

    return agent
