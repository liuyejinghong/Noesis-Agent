from __future__ import annotations

from pathlib import Path

from noesis_agent.agent.memory.models import FailureRecord, MemoryRecord
from noesis_agent.agent.memory.store import MemoryStore


def test_store_and_retrieve_knowledge_record(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")

    record_id = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="report",
            title="Weekly market report",
            content="Momentum stayed positive across majors.",
            tags=["weekly", "market"],
        )
    )
    reports = store.get_reports()

    assert record_id > 0
    assert [record.id for record in reports] == [record_id]
    assert reports[0].title == "Weekly market report"


def test_store_failure_and_query_by_strategy_id(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    failure_id = store.store_failure(
        FailureRecord(
            strategy_id="mean_reversion",
            category="execution",
            title="Stop loss too tight",
            content="The strategy exited before the reversal completed.",
            tags=["risk", "exit"],
        )
    )

    failures = store.query_failures(strategy_id="mean_reversion")

    assert [record.id for record in failures] == [failure_id]
    assert failures[0].memory_type == "failure"


def test_search_similar_uses_fts5_to_match_relevant_record(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    _ = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="report",
            title="Trend day summary",
            content="Bitcoin broke out after a volatility squeeze.",
            tags=["trend", "btc"],
        )
    )
    _ = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="report",
            title="Range day summary",
            content="Ethereum rotated in a narrow intraday range.",
            tags=["range", "eth"],
        )
    )

    matches = store.search_similar("squeeze")

    assert len(matches) == 1
    assert matches[0].title == "Trend day summary"


def test_search_similar_normalizes_hyphenated_terms(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    _ = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="report",
            title="BTC-USDT breakout note",
            content="BTC USDT breakout held above resistance.",
            tags=["btc-usdt", "breakout"],
        )
    )

    matches = store.search_similar("btc-usdt breakout")

    assert len(matches) == 1
    assert matches[0].title == "BTC-USDT breakout note"


def test_search_similar_matches_cjk_terms(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    _ = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="report",
            title="震荡市策略分析",
            content="这份报告讨论了震荡行情中的仓位管理。",
            tags=["震荡", "策略"],
        )
    )

    matches = store.search_similar("震荡")

    assert len(matches) == 1
    assert matches[0].title == "震荡市策略分析"


def test_failure_records_are_not_returned_by_get_reports(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    _ = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="report",
            title="Daily report",
            content="The desk stayed flat into the close.",
        )
    )
    _ = store.store_failure(
        FailureRecord(
            strategy_id="breakout",
            category="proposal",
            title="Rejected idea",
            content="The sample size was too small.",
        )
    )

    reports = store.get_reports()

    assert len(reports) == 1
    assert reports[0].memory_type == "knowledge"
    assert reports[0].title == "Daily report"


def test_get_reports_accepts_analysis_report_category(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    _ = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="analysis_report",
            title="Structured report",
            content="The setup matched the regime template.",
        )
    )

    reports = store.get_reports()

    assert len(reports) == 1
    assert reports[0].category == "analysis_report"


def test_get_proposals_filters_by_proposal_category(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    _ = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="proposal",
            strategy_id="breakout",
            title="Add confirmation filter",
            content="Require a follow-through close before entry.",
            status="pending",
        )
    )
    _ = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="report",
            strategy_id="breakout",
            title="Observation",
            content="Volume faded after the open.",
            status="pending",
        )
    )

    proposals = store.get_proposals()

    assert len(proposals) == 1
    assert proposals[0].category == "proposal"
    assert proposals[0].title == "Add confirmation filter"


def test_get_proposals_excludes_failure_records(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    _ = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="proposal",
            strategy_id="breakout",
            title="Live proposal",
            content="Increase confirmation bars during chop.",
        )
    )
    _ = store.store_failure(
        FailureRecord(
            strategy_id="breakout",
            category="proposal",
            title="Rejected proposal",
            content="This failed in validation.",
        )
    )

    proposals = store.get_proposals()

    assert len(proposals) == 1
    assert proposals[0].title == "Live proposal"


def test_query_failures_matches_complete_tags_only(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.db")
    _ = store.store_failure(
        FailureRecord(
            strategy_id="mean_reversion",
            category="execution",
            title="Exact tag",
            content="Matched the intended tag.",
            tags=["risk"],
        )
    )
    _ = store.store_failure(
        FailureRecord(
            strategy_id="mean_reversion",
            category="execution",
            title="Near match",
            content="Should not match substring tags.",
            tags=["brisk"],
        )
    )

    failures = store.query_failures(tags=["risk"])

    assert len(failures) == 1
    assert failures[0].title == "Exact tag"


def test_memory_store_supports_in_memory_database() -> None:
    store = MemoryStore(":memory:")

    record_id = store.store(
        MemoryRecord(
            memory_type="knowledge",
            category="report",
            title="In-memory report",
            content="The store should not require a file on disk.",
        )
    )

    reports = store.get_reports()

    assert record_id > 0
    assert len(reports) == 1
    assert reports[0].title == "In-memory report"
