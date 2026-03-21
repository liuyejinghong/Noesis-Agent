from __future__ import annotations

import pytest

from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.proposal_manager import ProposalManager
from noesis_agent.agent.roles.types import Proposal, ProposalStatus


def make_proposal(*, strategy_id: str = "breakout_v1", change_type: str = "parameter") -> Proposal:
    return Proposal(
        strategy_id=strategy_id,
        analysis_report_id=101,
        change_type=change_type,
        parameter_changes={"lookback": 30},
        rationale="Reduce false breakouts during chop.",
    )


def make_manager() -> ProposalManager:
    return ProposalManager(MemoryStore(":memory:"))


def test_valid_transition_advances_draft_to_gate_1_memory() -> None:
    manager = make_manager()
    proposal_id = manager.create_proposal(make_proposal())

    manager.advance_proposal(proposal_id, ProposalStatus.GATE_1_MEMORY, reason="No conflicting failures.")

    record = manager.get_proposal(proposal_id)
    assert record is not None
    assert record.status == ProposalStatus.GATE_1_MEMORY.value


def test_invalid_transition_from_draft_to_approved_raises_value_error() -> None:
    manager = make_manager()
    proposal_id = manager.create_proposal(make_proposal())

    with pytest.raises(ValueError, match="Invalid proposal transition"):
        manager.advance_proposal(proposal_id, ProposalStatus.APPROVED)


def test_full_pipeline_advances_until_pending_approval() -> None:
    manager = make_manager()
    proposal_id = manager.create_proposal(make_proposal())

    manager.advance_proposal(proposal_id, ProposalStatus.GATE_1_MEMORY)
    manager.advance_proposal(proposal_id, ProposalStatus.GATE_2_BACKTEST)
    manager.advance_proposal(proposal_id, ProposalStatus.GATE_3_WALKFORWARD)
    manager.advance_proposal(proposal_id, ProposalStatus.PENDING_APPROVAL)

    record = manager.get_proposal(proposal_id)
    assert record is not None
    assert record.status == ProposalStatus.PENDING_APPROVAL.value


def test_reject_proposal_stores_failure_record() -> None:
    manager = make_manager()
    proposal = make_proposal(change_type="trade_management")
    proposal_id = manager.create_proposal(proposal)

    manager.reject_proposal(proposal_id, reason="Validation sample size too small.")

    record = manager.get_proposal(proposal_id)
    failures = manager._memory.query_failures(
        strategy_id=proposal.strategy_id,
        category=proposal.change_type,
    )

    assert record is not None
    assert record.status == ProposalStatus.REJECTED.value
    assert len(failures) == 1
    assert failures[0].title == proposal.proposal_id
    assert "Validation sample size too small." in failures[0].content


def test_get_pending_approvals_returns_only_pending_records() -> None:
    manager = make_manager()
    pending_id = manager.create_proposal(make_proposal(strategy_id="pending_strategy"))
    rejected_id = manager.create_proposal(make_proposal(strategy_id="rejected_strategy"))

    manager.advance_proposal(pending_id, ProposalStatus.GATE_1_MEMORY)
    manager.advance_proposal(pending_id, ProposalStatus.GATE_2_BACKTEST)
    manager.advance_proposal(pending_id, ProposalStatus.GATE_3_WALKFORWARD)
    manager.advance_proposal(pending_id, ProposalStatus.PENDING_APPROVAL)
    manager.reject_proposal(rejected_id, reason="Duplicate idea")

    pending = manager.get_pending_approvals()

    assert [record.id for record in pending] == [pending_id]
    assert pending[0].status == ProposalStatus.PENDING_APPROVAL.value


def test_advancing_rejected_proposal_raises_value_error() -> None:
    manager = make_manager()
    proposal_id = manager.create_proposal(make_proposal())
    manager.reject_proposal(proposal_id, reason="Failed review")

    with pytest.raises(ValueError, match="Invalid proposal transition"):
        manager.advance_proposal(proposal_id, ProposalStatus.GATE_1_MEMORY)
