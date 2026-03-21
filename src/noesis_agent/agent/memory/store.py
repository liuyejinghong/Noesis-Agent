from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import FailureRecord, MemoryRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_type TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT '',
    strategy_id TEXT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT DEFAULT '',
    metadata_json TEXT DEFAULT '{}',
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    title,
    content,
    tags,
    content=memory_records,
    content_rowid=id
);
"""


class MemoryStore:
    def __init__(self, db_path: str | Path):
        self._db_path = db_path
        if db_path != ":memory:":
            Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA)

    def store(self, record: MemoryRecord) -> int:
        stamp = _utc_now()
        tags = _serialize_tags(record.tags)
        cursor = self._connection.execute(
            """
            INSERT INTO memory_records (
                memory_type,
                category,
                strategy_id,
                title,
                content,
                tags,
                metadata_json,
                status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.memory_type,
                record.category,
                record.strategy_id,
                record.title,
                record.content,
                tags,
                json.dumps(record.metadata),
                record.status,
                stamp,
                stamp,
            ),
        )
        record_id = int(cursor.lastrowid)
        self._connection.execute(
            "INSERT INTO memory_fts(rowid, title, content, tags) VALUES (?, ?, ?, ?)",
            (record_id, record.title, record.content, tags),
        )
        self._connection.commit()
        return record_id

    def store_failure(self, failure: FailureRecord) -> int:
        return self.store(failure)

    def query_failures(
        self,
        *,
        strategy_id: str | None = None,
        category: str | None = None,
        tags: list[str] | None = None,
        limit: int = 20,
    ) -> list[MemoryRecord]:
        clauses = ["memory_type = 'failure'"]
        params: list[Any] = []

        if strategy_id is not None:
            clauses.append("strategy_id = ?")
            params.append(strategy_id)
        if category is not None:
            clauses.append("category = ?")
            params.append(category)
        if tags:
            clauses.extend("tags LIKE ?" for _ in tags)
            params.extend(f"%{tag}%" for tag in tags)

        params.append(limit)
        query = f"SELECT * FROM memory_records WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?"
        rows = self._connection.execute(query, params).fetchall()
        return [_row_to_record(row) for row in rows]

    def search_similar(self, query: str, *, top_k: int = 10) -> list[MemoryRecord]:
        rows = self._connection.execute(
            """
            SELECT memory_records.*
            FROM memory_fts
            JOIN memory_records ON memory_records.id = memory_fts.rowid
            WHERE memory_fts MATCH ?
            ORDER BY bm25(memory_fts), memory_records.created_at DESC
            LIMIT ?
            """,
            (query, top_k),
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_proposals(self, *, strategy_id: str | None = None, status: str | None = None) -> list[MemoryRecord]:
        clauses = ["category = 'proposal'"]
        params: list[Any] = []

        if strategy_id is not None:
            clauses.append("strategy_id = ?")
            params.append(strategy_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)

        rows = self._connection.execute(
            f"SELECT * FROM memory_records WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
            params,
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    def get_reports(self, *, period: str | None = None) -> list[MemoryRecord]:
        clauses = ["category = 'report'", "memory_type != 'failure'"]
        params: list[Any] = []

        if period is not None:
            clauses.append("created_at LIKE ?")
            params.append(f"{period}%")

        rows = self._connection.execute(
            f"SELECT * FROM memory_records WHERE {' AND '.join(clauses)} ORDER BY created_at DESC",
            params,
        ).fetchall()
        return [_row_to_record(row) for row in rows]


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _serialize_tags(tags: list[str]) -> str:
    return ",".join(tags)


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
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
