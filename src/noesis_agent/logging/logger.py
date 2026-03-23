from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

from typing_extensions import override


class JsonFormatter(logging.Formatter):
    EXTRA_FIELDS = (
        "strategy_id",
        "agent",
        "model",
        "action",
        "proposal_id",
        "prompt_tokens",
        "completion_tokens",
        "latency_ms",
        "status",
        "error",
        "period",
        "user",
        "field",
        "old",
        "new",
        "source",
    )

    @override
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in self.EXTRA_FIELDS:
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value
        if record.exc_info and record.exc_info[0]:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    @override
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now(tz=UTC).strftime("%H:%M:%S")
        return f"{color}{ts} [{record.levelname:>8}]{self.RESET} {record.name}: {record.getMessage()}"


def setup_logging(log_dir: Path | None = None, level: str = "INFO", console: bool = True) -> None:
    root = logging.getLogger("noesis")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    if console:
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setFormatter(ConsoleFormatter())
        console_handler.setLevel(logging.INFO)
        root.addHandler(console_handler)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "noesis.jsonl",
            maxBytes=10_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(JsonFormatter())
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"noesis.{name}")
