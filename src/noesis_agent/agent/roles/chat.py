# pyright: reportUnusedFunction=false

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic_ai import Agent, RunContext

from noesis_agent.agent.models import ModelRouter

CHAT_SYSTEM_PROMPT = """你是 Noesis Agent — 一个 AI 驱动的加密货币策略研究与执行系统。

## 你的身份

你是用户的量化交易研究助手。你了解 Noesis 系统的所有能力，并能通过工具直接操作系统。

## 你的能力

你可以通过工具完成以下操作：

1. **查看系统状态** — 当前运行模式、交易品种、时间周期、待审批提案数量
2. **查看配置** — 风控参数（最大仓位、最大杠杆、日亏损上限）
3. **列出提案** — 查看所有提案及其状态
4. **列出活跃策略** — 查看已注册的策略列表
5. **运行策略分析** — 分析指定策略在指定周期的表现，生成结构化报告
6. **运行完整闭环** — 分析 → 提案 → 门控验证，一键完成
7. **采集市场数据** — 从 Binance 采集 OI、资金费率、多空比等快照数据
8. **搜索记忆** — 搜索历史分析报告、提案、失败记录

## 沟通风格

- 用中文回复
- 简洁、专业、用数据说话
- 如果用户的请求需要调用工具，直接调用，不要问"要不要帮你做"
- 如果工具调用失败，如实告知错误原因
- 不确定的事情说"不确定"，不要编造数据
"""


@dataclass
class ChatDeps:
    bootstrap: Any


def create_chat_agent(router: ModelRouter, bootstrap: Any) -> Agent[ChatDeps, str]:
    agent = router.create_agent("chat", output_type=str, deps_type=ChatDeps)

    @agent.instructions
    def chat_instructions() -> str:
        return CHAT_SYSTEM_PROMPT

    @agent.tool
    async def show_system_status(ctx: RunContext[ChatDeps]) -> str:
        """查看系统状态：运行模式、交易品种、时间周期、待审批提案数、已注册技能数"""
        b = ctx.deps.bootstrap
        pending = b.proposal_manager.get_pending_approvals()
        skills = b.skill_registry.list_skills()
        roles = b.router.list_roles()
        lines = [
            f"运行模式: {b.settings.mode.value}",
            f"交易品种: {b.settings.symbol}",
            f"时间周期: {b.settings.timeframe}",
            f"Agent 角色: {', '.join(roles)}",
            f"已注册技能: {len(skills)}",
            f"待审批提案: {len(pending)}",
        ]
        return "\n".join(lines)

    @agent.tool
    async def show_config(ctx: RunContext[ChatDeps]) -> str:
        """查看风控配置：最大仓位、最大杠杆、日亏损上限、只读模式"""
        risk = ctx.deps.bootstrap.settings.risk
        lines = [
            f"最大仓位: {risk.max_position_size}",
            f"最大杠杆: {risk.max_leverage}",
            f"日亏损上限: {risk.max_daily_loss_pct:.0%}",
            f"只读模式: {risk.read_only}",
        ]
        return "\n".join(lines)

    @agent.tool
    async def list_proposals(ctx: RunContext[ChatDeps], status_filter: str | None = None) -> str:
        """列出提案。可选按状态过滤（draft/pending_approval/approved/rejected 等）"""
        records = ctx.deps.bootstrap.memory.get_proposals(status=status_filter)
        if not records:
            return "暂无提案"
        lines = []
        for r in records[:20]:
            lines.append(f"#{r.id} | {r.title} | 状态: {r.status} | {r.created_at or ''}")
        return "\n".join(lines)

    @agent.tool
    async def list_strategies(ctx: RunContext[ChatDeps]) -> str:
        """列出所有活跃策略"""
        specs = ctx.deps.bootstrap.strategy_catalog.list_active()
        if not specs:
            return "暂无活跃策略"
        lines = []
        for s in specs:
            lines.append(f"{s.strategy_id} | {s.symbol} {s.timeframe} | 状态: {s.status}")
        return "\n".join(lines)

    @agent.tool
    async def run_analysis(ctx: RunContext[ChatDeps], strategy_id: str, period: str) -> str:
        """运行策略分析。strategy_id: 策略ID, period: 分析周期如 2025-01"""
        try:
            report = await ctx.deps.bootstrap.orchestrator.run_analysis(strategy_id, period)
            lines = [
                f"策略: {report.strategy_id} | 周期: {report.period}",
                f"市场环境: {report.market_regime}",
                f"优势: {', '.join(report.strengths) if report.strengths else '无'}",
                f"弱点: {', '.join(report.weaknesses) if report.weaknesses else '无'}",
                f"建议: {', '.join(report.recommendations) if report.recommendations else '无'}",
            ]
            return "\n".join(lines)
        except Exception as exc:
            return f"分析失败: {exc}"

    @agent.tool
    async def run_full_cycle(ctx: RunContext[ChatDeps], strategy_id: str, period: str) -> str:
        """运行完整闭环：分析 → 提案 → 门控验证。strategy_id: 策略ID, period: 周期"""
        try:
            result = await ctx.deps.bootstrap.orchestrator.run_full_cycle(strategy_id, period)
            from noesis_agent.agent.roles.types import ProposalStatus

            final_status = result.get("final_status", "unknown")
            status_str = final_status.value if isinstance(final_status, ProposalStatus) else str(final_status)
            return f"闭环完成。最终状态: {status_str}"
        except Exception as exc:
            return f"闭环失败: {exc}"

    @agent.tool
    async def collect_data(ctx: RunContext[ChatDeps], symbols: str = "BTCUSDT,ETHUSDT") -> str:
        """采集 Binance 快照数据。symbols: 逗号分隔的交易对，如 BTCUSDT,ETHUSDT"""
        try:
            from noesis_agent.data.collector import BinanceDataCollector
            from noesis_agent.data.storage import DataStore

            root = ctx.deps.bootstrap.root_dir
            store = DataStore(root / "data")
            symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
            collector = BinanceDataCollector(store, symbols=symbol_list)
            results = collector.collect_all()
            lines = [f"{name}: {count} 条" for name, count in sorted(results.items())]
            return "\n".join(lines) if lines else "无数据采集"
        except Exception as exc:
            return f"数据采集失败: {exc}"

    @agent.tool
    async def search_memory(ctx: RunContext[ChatDeps], query: str) -> str:
        """搜索历史记忆（分析报告、提案、失败记录等）"""
        records = ctx.deps.bootstrap.memory.search_similar(query, top_k=10)
        if not records:
            return "未找到相关记录"
        lines = []
        for r in records[:10]:
            lines.append(f"#{r.id} [{r.category}] {r.title}: {r.content[:100]}...")
        return "\n".join(lines)

    return agent
