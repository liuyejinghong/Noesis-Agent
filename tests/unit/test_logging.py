from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

import pytest

from noesis_agent.logging import agent_tracer
from noesis_agent.logging import logger as logger_module


def test_json_formatter_produces_valid_json_with_required_fields() -> None:
    formatter = logger_module.JsonFormatter()
    record = logging.makeLogRecord(
        {
            "name": "noesis.agent.trace",
            "levelname": "INFO",
            "msg": "agent run complete",
            "strategy_id": "r_breaker",
            "agent": "analyst",
        }
    )

    payload = cast(dict[str, object], json.loads(formatter.format(record)))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "noesis.agent.trace"
    assert payload["msg"] == "agent run complete"
    assert payload["strategy_id"] == "r_breaker"
    assert payload["agent"] == "analyst"
    assert "ts" in payload


def test_console_formatter_produces_human_readable_output() -> None:
    formatter = logger_module.ConsoleFormatter()
    record = logging.makeLogRecord({"name": "noesis.cli", "levelname": "WARNING", "msg": "something happened"})

    rendered = formatter.format(record)

    assert "WARNING" in rendered
    assert "noesis.cli" in rendered
    assert "something happened" in rendered


def test_setup_logging_creates_file_handler_when_log_dir_given(tmp_path: Path) -> None:
    root = logging.getLogger("noesis")

    logger_module.setup_logging(log_dir=tmp_path, level="DEBUG", console=False)

    assert any(isinstance(handler, logging.Handler) for handler in root.handlers)
    logger = logger_module.get_logger("tests")
    logger.info("written to file")
    for handler in root.handlers:
        handler.flush()
    assert (tmp_path / "noesis.jsonl").exists()


def test_get_logger_returns_namespaced_logger() -> None:
    logger = logger_module.get_logger("agent.analyst")

    assert logger.name == "noesis.agent.analyst"


def test_trace_agent_call_logs_timing_and_status(caplog: pytest.LogCaptureFixture) -> None:
    logger_module.setup_logging(console=False)

    with caplog.at_level(logging.INFO, logger="noesis.agent.trace"):
        with agent_tracer.trace_agent_call("analyst", "gpt-5", "r_breaker") as ctx:
            ctx["prompt_tokens"] = 11
            ctx["completion_tokens"] = 7

    assert len(caplog.records) == 1
    record = caplog.records[0].__dict__
    assert record["agent"] == "analyst"
    assert record["model"] == "gpt-5"
    assert record["strategy_id"] == "r_breaker"
    assert record["status"] == "ok"
    assert record["prompt_tokens"] == 11
    assert record["completion_tokens"] == 7
    assert cast(float, record["latency_ms"]) >= 0


def test_trace_agent_call_error_logs_error_status(caplog: pytest.LogCaptureFixture) -> None:
    logger_module.setup_logging(console=False)

    with pytest.raises(RuntimeError, match="boom"):
        with caplog.at_level(logging.INFO, logger="noesis.agent.trace"):
            with agent_tracer.trace_agent_call("validator", "gpt-5-mini"):
                raise RuntimeError("boom")

    assert len(caplog.records) == 1
    record = caplog.records[0].__dict__
    assert record["status"] == "error"
    assert record["error"] == "RuntimeError: boom"


def test_log_approval_action_logs_with_correct_extra_fields(caplog: pytest.LogCaptureFixture) -> None:
    logger_module.setup_logging(console=False)

    with caplog.at_level(logging.INFO, logger="noesis.approval"):
        agent_tracer.log_approval_action("approved", 42, reason="manual review", user="ethan")

    assert len(caplog.records) == 1
    record = caplog.records[0].__dict__
    assert record["action"] == "approved"
    assert record["proposal_id"] == 42
    assert record["user"] == "ethan"
    assert record["source"] == "manual review"


def test_log_config_change_logs_field_old_and_new(caplog: pytest.LogCaptureFixture) -> None:
    logger_module.setup_logging(console=False)

    with caplog.at_level(logging.INFO, logger="noesis.config"):
        agent_tracer.log_config_change("mode", "paper", "live", source="cli")

    assert len(caplog.records) == 1
    record = caplog.records[0].__dict__
    assert record["action"] == "config_change"
    assert record["field"] == "mode"
    assert record["old"] == "paper"
    assert record["new"] == "live"
    assert record["source"] == "cli"
