from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager

from noesis_agent.logging.logger import get_logger

_logger = get_logger("agent.trace")


@contextmanager
def trace_agent_call(agent_name: str, model: str, strategy_id: str = "") -> Generator[dict[str, object], None, None]:
    context: dict[str, object] = {"status": "ok"}
    start = time.monotonic()
    try:
        yield context
    except Exception as exc:
        context["status"] = "error"
        context["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        latency_ms = (time.monotonic() - start) * 1000
        _logger.info(
            "%s call completed",
            agent_name,
            extra={
                "agent": agent_name,
                "model": model,
                "strategy_id": strategy_id,
                "action": "run",
                "latency_ms": round(latency_ms, 1),
                "prompt_tokens": context.get("prompt_tokens"),
                "completion_tokens": context.get("completion_tokens"),
                **{key: value for key, value in context.items() if key in {"status", "error"}},
            },
        )


def log_approval_action(action: str, proposal_id: int, reason: str = "", user: str = "system") -> None:
    logger = get_logger("approval")
    logger.info(
        "Proposal #%s %s",
        proposal_id,
        action,
        extra={"action": action, "proposal_id": proposal_id, "user": user, "source": reason},
    )


def log_config_change(field: str, old: object, new: object, source: str = "") -> None:
    logger = get_logger("config")
    logger.info(
        "Config changed: %s",
        field,
        extra={
            "action": "config_change",
            "field": field,
            "old": str(old),
            "new": str(new),
            "source": source,
        },
    )
