# pyright: reportUnusedFunction=false

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.models import ModelRouter
from noesis_agent.agent.roles.types import ValidationReport
from noesis_agent.agent.skills.registry import SkillRegistry
from noesis_agent.core.prompt_registry import PromptRegistry


@dataclass
class ValidatorDeps:
    memory_store: MemoryStore
    skill_registry: SkillRegistry


VALIDATOR_INSTRUCTIONS = """你是一个提案验证员。
通过回测对比和 walk-forward 验证评估改进提案的效果。

验证流程：
1. 用当前参数运行基准回测
2. 用提案参数运行改进回测
3. 对比关键指标
4. 运行 walk-forward 验证
5. 给出 pass/fail/marginal 判定

判定标准：
- pass: 指标不劣于基准 AND 衰减率 < 30%
- fail: 关键指标明显劣化 OR 衰减率 > 50%
- marginal: 介于两者之间

输出必须客观、数据驱动。"""


def create_validator_agent(
    router: ModelRouter, prompts_dir: Path | None = None
) -> Agent[ValidatorDeps, ValidationReport]:
    agent = router.create_agent("validator", output_type=ValidationReport, deps_type=ValidatorDeps)

    if prompts_dir is not None:
        registry = PromptRegistry(prompts_dir)
        prompt = registry.load_prompt("validator")
        instructions_text = prompt.content
    else:
        instructions_text = VALIDATOR_INSTRUCTIONS

    @agent.instructions
    def validator_instructions() -> str:
        return instructions_text

    @agent.tool
    async def run_backtest_comparison(ctx: RunContext[ValidatorDeps], proposal_id: str, strategy_id: str) -> str:
        records = ctx.deps.memory_store.search_similar(f"{proposal_id} {strategy_id}", top_k=5)
        if not records:
            return "未找到相关回测记录"
        return "\n".join(f"- {record.title}: {record.content[:120]}" for record in records)

    @agent.tool
    async def calculate_walk_forward_decay(
        ctx: RunContext[ValidatorDeps], proposal_id: str, baseline_return_pct: float, proposed_return_pct: float
    ) -> str:
        del ctx
        if baseline_return_pct == 0:
            return f"proposal_id={proposal_id}; decay_pct=0.0"
        decay_pct = max(0.0, (baseline_return_pct - proposed_return_pct) / abs(baseline_return_pct) * 100)
        return f"proposal_id={proposal_id}; decay_pct={decay_pct:.2f}"

    return agent
