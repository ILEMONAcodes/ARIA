"""Content-free structured diagnostics for the local agent.

Messages, formatting arguments, exception details and arbitrary extra fields
are deliberately omitted. User-facing activity history is a separate module.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import UTC, datetime
from typing import TextIO
from uuid import UUID

EVENTS = frozenset(
    {
        "log.record",
        "settings.loaded",
        "settings.failed",
        "component.started",
        "component.stopped",
        "operation.started",
        "operation.completed",
        "operation.failed",
    }
)
LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", None)
        if not isinstance(event, str) or event not in EVENTS:
            event = "log.record"
        task_id = getattr(record, "task_id", None)
        try:
            task_id = str(UUID(task_id)) if isinstance(task_id, str) else None
        except ValueError:
            task_id = None
        duration = getattr(record, "duration_ms", None)
        try:
            duration = (
                float(duration)
                if isinstance(duration, (int, float)) and not isinstance(duration, bool)
                else None
            )
        except OverflowError:
            duration = None
        if duration is not None and (not math.isfinite(duration) or duration < 0):
            duration = None
        return json.dumps(
            {
                "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                "level": logging.getLevelName(record.levelno),
                "component": "agent",
                "task_id": task_id,
                "event": event,
                "duration_ms": duration,
            },
            allow_nan=False,
        )


def configure_logging(level: str = "INFO", *, stream: TextIO | None = None) -> logging.Logger:
    """Configure the agent's logger without changing the process's root logger.

    Repeated calls replace the agent handler rather than duplicating output.
    Output defaults to stderr; no diagnostic files are created automatically.
    """
    if level not in LEVELS:
        raise ValueError("Invalid agent log level")
    logger = logging.getLogger("aria.agent")
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    for previous in logger.handlers[:]:
        logger.removeHandler(previous)
        previous.close()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger
