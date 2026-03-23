from __future__ import annotations

from typing import Any

from noesis_agent.agent.gates import gate_1_failure_memory, gate_2_backtest_comparison, gate_3_walk_forward
from noesis_agent.agent.memory.models import MemoryRecord
from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.models import ModelRouter
from noesis_agent.agent.proposal_manager import ProposalManager
from noesis_agent.agent.roles.analyst import AnalystDeps, create_analyst_agent
from noesis_agent.agent.roles.proposer import ProposerDeps, create_proposer_agent
from noesis_agent.agent.roles.types import AnalysisReport, GateResult, Proposal, ProposalStatus, ValidationReport
from noesis_agent.agent.roles.validator import ValidatorDeps, create_validator_agent
from noesis_agent.agent.skills.registry import SkillRegistry

ALLOWED_CHANGE_TYPES = {"parameter", "code", "trade_management"}


class AgentOrchestrator:
    def __init__(
        self,
        router: ModelRouter,
        memory: MemoryStore,
        proposal_manager: ProposalManager,
        skill_registry: SkillRegistry,
    ) -> None:
        self.router = router
        self.memory = memory
        self.proposal_manager = proposal_manager
        self.skill_registry = skill_registry

    async def run_analysis(self, strategy_id: str, period: str) -> AnalysisReport:
        report, _ = await self._run_analysis_with_record(strategy_id=strategy_id, period=period)
        return report

    async def run_proposal(self, analysis_report: AnalysisReport, report_id: int) -> Proposal:
        proposal, _ = await self._run_proposal_with_record(analysis_report=analysis_report, report_id=report_id)
        return proposal

    async def run_validation(self, proposal: Proposal) -> ValidationReport:
        agent = create_validator_agent(self.router)
        prompt = f"验证策略 {proposal.strategy_id} 的提案 {proposal.proposal_id}"
        result = await agent.run(prompt, deps=self._validator_deps())
        report = result.output
        return report.model_copy(update={"proposal_id": proposal.proposal_id})

    async def run_gate_sequence(
        self, proposal_id: int, proposal: Proposal, validation: ValidationReport
    ) -> list[GateResult]:
        results: list[GateResult] = []

        failure_records = [
            {"strategy_id": record.strategy_id, "category": record.category}
            for record in self.memory.query_failures(limit=50)
        ]
        gate_1 = gate_1_failure_memory(
            strategy_id=proposal.strategy_id,
            change_type=proposal.change_type,
            failure_records=failure_records,
        )
        results.append(gate_1)
        if not gate_1.passed:
            self.proposal_manager.reject_proposal(proposal_id, reason=gate_1.reason)
            return results
        self.proposal_manager.advance_proposal(proposal_id, ProposalStatus.GATE_1_MEMORY, reason="Gate 1 passed")

        gate_2 = gate_2_backtest_comparison(validation.baseline, validation.proposed)
        results.append(gate_2)
        if not gate_2.passed:
            self.proposal_manager.reject_proposal(proposal_id, reason=gate_2.reason)
            return results
        self.proposal_manager.advance_proposal(proposal_id, ProposalStatus.GATE_2_BACKTEST, reason="Gate 2 passed")

        gate_3 = gate_3_walk_forward(decay_pct=validation.walk_forward_decay_pct)
        results.append(gate_3)
        if not gate_3.passed:
            self.proposal_manager.reject_proposal(proposal_id, reason=gate_3.reason)
            return results
        self.proposal_manager.advance_proposal(proposal_id, ProposalStatus.GATE_3_WALKFORWARD, reason="Gate 3 passed")
        self.proposal_manager.advance_proposal(
            proposal_id,
            ProposalStatus.PENDING_APPROVAL,
            reason="All offline validation gates passed",
        )
        return results

    async def run_full_cycle(self, strategy_id: str, period: str) -> dict[str, Any]:
        analysis, report_id = await self._run_analysis_with_record(strategy_id=strategy_id, period=period)
        proposal, proposal_id = await self._run_proposal_with_record(analysis_report=analysis, report_id=report_id)
        validation = await self.run_validation(proposal)
        gates = await self.run_gate_sequence(proposal_id, proposal, validation)
        record = self.proposal_manager.get_proposal(proposal_id)
        if record is None:
            raise RuntimeError(f"Proposal disappeared after orchestration: {proposal_id}")
        return {
            "analysis": analysis,
            "proposal": proposal,
            "validation": validation,
            "gates": gates,
            "final_status": ProposalStatus(record.status),
        }

    async def _run_analysis_with_record(self, *, strategy_id: str, period: str) -> tuple[AnalysisReport, int]:
        agent = create_analyst_agent(self.router)

        context_parts = [f"分析策略 {strategy_id} 在 {period} 的表现，并生成结构化报告。"]

        reports = self.memory.get_reports(period=period)
        if not reports:
            reports = self.memory.search_similar(f"{strategy_id} {period}", top_k=5)
        if reports:
            context_parts.append("\n以下是可用的回测数据和历史记录：\n")
            for r in reports[:5]:
                context_parts.append(f"--- {r.title} ---\n{r.content}\n")

        prompt = "\n".join(context_parts)
        result = await agent.run(prompt, deps=self._analyst_deps())
        report = result.output.model_copy(update={"strategy_id": strategy_id, "period": period})
        record_id = self.memory.store(self._analysis_record(report))
        return report, record_id

    async def _run_proposal_with_record(
        self, *, analysis_report: AnalysisReport, report_id: int
    ) -> tuple[Proposal, int]:
        agent = create_proposer_agent(self.router)
        analysis_json = analysis_report.model_dump_json(indent=2)
        prompt = (
            f"基于以下分析报告为策略 {analysis_report.strategy_id} 生成一个改进提案。\n\n"
            f"分析报告内容：\n{analysis_json}\n\n"
            f"请针对报告中发现的问题提出具体、可回测验证的改进方案。"
        )
        result = await agent.run(prompt, deps=self._proposer_deps())
        proposal = result.output.model_copy(
            update={
                "strategy_id": analysis_report.strategy_id,
                "analysis_report_id": report_id,
                "change_type": self._normalize_change_type(result.output.change_type),
                "status": ProposalStatus.DRAFT,
            }
        )
        proposal_id = self.proposal_manager.create_proposal(proposal)
        return proposal, proposal_id

    def _analysis_record(self, report: AnalysisReport) -> MemoryRecord:
        return MemoryRecord(
            memory_type="knowledge",
            category="analysis_report",
            strategy_id=report.strategy_id,
            title=f"{report.strategy_id}:{report.period}",
            content=report.model_dump_json(),
            metadata=report.model_dump(mode="json"),
            tags=[report.period],
        )

    def _normalize_change_type(self, change_type: str) -> str:
        if change_type in ALLOWED_CHANGE_TYPES:
            return change_type
        return "parameter"

    def _analyst_deps(self) -> AnalystDeps:
        return AnalystDeps(memory_store=self.memory, skill_registry=self.skill_registry)

    def _proposer_deps(self) -> ProposerDeps:
        return ProposerDeps(memory_store=self.memory, skill_registry=self.skill_registry)

    def _validator_deps(self) -> ValidatorDeps:
        return ValidatorDeps(memory_store=self.memory, skill_registry=self.skill_registry)
