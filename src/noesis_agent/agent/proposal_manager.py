from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from noesis_agent.agent.memory.models import FailureRecord, MemoryRecord
from noesis_agent.agent.memory.store import MemoryStore
from noesis_agent.agent.roles.types import Proposal, ProposalStatus

VALID_TRANSITIONS: dict[ProposalStatus, list[ProposalStatus]] = {
    ProposalStatus.DRAFT: [ProposalStatus.GATE_1_MEMORY, ProposalStatus.REJECTED],
    ProposalStatus.GATE_1_MEMORY: [ProposalStatus.GATE_2_BACKTEST, ProposalStatus.REJECTED],
    ProposalStatus.GATE_2_BACKTEST: [ProposalStatus.GATE_3_WALKFORWARD, ProposalStatus.REJECTED],
    ProposalStatus.GATE_3_WALKFORWARD: [ProposalStatus.PENDING_APPROVAL, ProposalStatus.REJECTED],
    ProposalStatus.PENDING_APPROVAL: [ProposalStatus.APPROVED, ProposalStatus.REJECTED],
    ProposalStatus.APPROVED: [ProposalStatus.TESTNET_DEPLOYED, ProposalStatus.REJECTED],
    ProposalStatus.TESTNET_DEPLOYED: [
        ProposalStatus.GATE_4_MIN_PERIOD,
        ProposalStatus.REJECTED,
        ProposalStatus.AUTO_ROLLBACK,
    ],
    ProposalStatus.GATE_4_MIN_PERIOD: [ProposalStatus.GATE_5_PERFORMANCE, ProposalStatus.REJECTED],
    ProposalStatus.GATE_5_PERFORMANCE: [ProposalStatus.PENDING_LIVE_APPROVAL, ProposalStatus.REJECTED],
    ProposalStatus.PENDING_LIVE_APPROVAL: [ProposalStatus.LIVE_DEPLOYED, ProposalStatus.REJECTED],
    ProposalStatus.LIVE_DEPLOYED: [ProposalStatus.MONITORING, ProposalStatus.AUTO_ROLLBACK],
    ProposalStatus.MONITORING: [ProposalStatus.GRADUATED, ProposalStatus.AUTO_ROLLBACK],
}


class ProposalManager:
    def __init__(self, memory: MemoryStore):
        self._memory = memory

    def create_proposal(self, proposal: Proposal) -> int:
        record = MemoryRecord(
            memory_type="knowledge",
            category="proposal",
            strategy_id=proposal.strategy_id,
            title=proposal.proposal_id,
            content=proposal.model_dump_json(),
            metadata=_serialize_proposal(proposal),
            status=proposal.status.value,
            tags=[proposal.change_type],
        )
        return self._memory.store(record)

    def advance_proposal(self, proposal_id: int, new_status: ProposalStatus, *, reason: str = "") -> None:
        record = self.get_proposal(proposal_id)
        proposal = _load_proposal_record(record, proposal_id)
        current_status = proposal.status

        if new_status not in VALID_TRANSITIONS.get(current_status, []):
            raise ValueError(f"Invalid proposal transition: {current_status.value} -> {new_status.value}")

        updated_proposal = proposal.model_copy(update={"status": new_status})
        transition_history = list(record.metadata.get("transition_history", []))
        transition_history.append(
            {
                "from_status": current_status.value,
                "to_status": new_status.value,
                "reason": reason,
                "timestamp": _utc_now(),
            }
        )
        metadata = _serialize_proposal(updated_proposal)
        metadata["transition_history"] = transition_history
        self._update_proposal_record(proposal_id, updated_proposal, metadata)

    def reject_proposal(self, proposal_id: int, *, reason: str, record_failure: bool = True) -> None:
        record = self.get_proposal(proposal_id)
        proposal = _load_proposal_record(record, proposal_id)
        previous_status = proposal.status

        self.advance_proposal(proposal_id, ProposalStatus.REJECTED, reason=reason)

        if record_failure:
            _ = self._memory.store_failure(
                FailureRecord(
                    strategy_id=proposal.strategy_id,
                    category=proposal.change_type,
                    title=proposal.proposal_id,
                    content=reason,
                    tags=["proposal_rejection", proposal.change_type],
                    metadata={
                        "proposal_id": proposal.proposal_id,
                        "rejected_from_status": previous_status.value,
                    },
                )
            )

    def get_pending_approvals(self) -> list[MemoryRecord]:
        return self._memory.get_proposals(status=ProposalStatus.PENDING_APPROVAL.value)

    def get_proposal(self, proposal_id: int) -> MemoryRecord | None:
        row = self._memory._connection.execute(  # noqa: SLF001
            """
            SELECT *
            FROM memory_records
            WHERE id = ? AND category = 'proposal' AND memory_type != 'failure'
            """,
            (proposal_id,),
        ).fetchone()
        if row is None:
            return None
        return MemoryRecord(
            id=row["id"],
            memory_type=row["memory_type"],
            category=row["category"],
            strategy_id=row["strategy_id"],
            title=row["title"],
            content=row["content"],
            tags=[tag for tag in row["tags"].split(",") if tag],
            metadata=json.loads(row["metadata_json"]),
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _update_proposal_record(self, proposal_id: int, proposal: Proposal, metadata: dict[str, Any]) -> None:
        stamp = _utc_now()
        self._memory._connection.execute(  # noqa: SLF001
            """
            UPDATE memory_records
            SET content = ?, metadata_json = ?, status = ?, updated_at = ?
            WHERE id = ? AND category = 'proposal' AND memory_type != 'failure'
            """,
            (proposal.model_dump_json(), json.dumps(metadata), proposal.status.value, stamp, proposal_id),
        )
        self._memory._connection.commit()  # noqa: SLF001


def _load_proposal_record(record: MemoryRecord | None, proposal_id: int) -> Proposal:
    if record is None:
        raise ValueError(f"Proposal not found: {proposal_id}")
    return Proposal.model_validate(record.metadata)


def _serialize_proposal(proposal: Proposal) -> dict[str, Any]:
    return proposal.model_dump(mode="json")


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()
