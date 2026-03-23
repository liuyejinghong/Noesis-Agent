# pyright: reportUnusedFunction=false

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.models import ModelRouter
from noesis_agent.agent.roles.types import AnalysisReport
from noesis_agent.agent.skills.registry import SkillRegistry
from noesis_agent.core.prompt_registry import PromptRegistry


@dataclass
class AnalystDeps:
    memory_store: MemoryStore
    skill_registry: SkillRegistry


ANALYST_INSTRUCTIONS = """你是一个加密货币策略分析师。
你的任务是分析策略在指定周期内的交易表现，生成结构化分析报告。

分析维度：
1. 绩效概览（收益率、回撤、胜率、交易频率）
2. 市场环境判断（趋势/震荡/混合）
3. 策略优势
4. 策略弱点
5. 发现的规律
6. 改进建议

关于手续费和交易对的重要知识：
- 如果手续费占毛利润比例超过 30%，必须指出并建议优化
- Binance 的 USDC 交易对（如 BTCUSDC）Maker 费率通常为 0%，远低于 USDT 交易对
- 策略使用限价单（Limit/Maker）比市价单（Market/Taker）手续费低很多
- 如果策略当前用的是 USDT 交易对，应建议评估同品种的 USDC 交易对
- 手续费优化往往比调整策略参数更有效（实测可带来 24 倍收益提升）

输出必须是中文。用数据支撑每个观点。"""


def create_analyst_agent(router: ModelRouter, prompts_dir: Path | None = None) -> Agent[AnalystDeps, AnalysisReport]:
    agent = router.create_agent("analyst", output_type=AnalysisReport, deps_type=AnalystDeps)

    if prompts_dir is not None:
        registry = PromptRegistry(prompts_dir)
        prompt = registry.load_prompt("analyst")
        instructions_text = prompt.content
    else:
        instructions_text = ANALYST_INSTRUCTIONS

    @agent.instructions
    def analyst_instructions() -> str:
        return instructions_text

    @agent.tool
    async def get_trade_records(ctx: RunContext[AnalystDeps], period: str, strategy_id: str) -> str:
        del strategy_id

        records = ctx.deps.memory_store.get_reports(period=period)
        if not records:
            return "该周期无交易记录"
        return "\n".join(record.content[:200] for record in records[:10])

    @agent.tool
    async def search_related_analysis(ctx: RunContext[AnalystDeps], query: str) -> str:
        records = ctx.deps.memory_store.search_similar(query, top_k=5)
        if not records:
            return "无相关历史分析"
        return "\n".join(f"- {record.title}: {record.content[:100]}" for record in records)

    return agent
