import io
import json
import logging
from datetime import datetime
from uuid import uuid4

import pytest

from agent.logging_config import configure_logging


@pytest.fixture(autouse=True)
def restore_logger():
    logger = logging.getLogger("aria.agent")
    handlers, level, propagate = logger.handlers[:], logger.level, logger.propagate
    yield
    logger.handlers = handlers
    logger.setLevel(level)
    logger.propagate = propagate


def test_log_is_json_with_utc_time_and_expected_metadata():
    stream = io.StringIO()
    logger = configure_logging("INFO", stream=stream)
    task_id = str(uuid4())
    logger.info(
        "request text is not logged",
        extra={"event": "operation.completed", "task_id": task_id, "duration_ms": 12.5},
    )
    record = json.loads(stream.getvalue())
    assert set(record) == {"ts", "level", "component", "task_id", "event", "duration_ms"}
    assert datetime.fromisoformat(record["ts"]).utcoffset().total_seconds() == 0
    assert record["level"] == "INFO"
    assert record["component"] == "agent"
    assert record["task_id"] == task_id
    assert record["event"] == "operation.completed"
    assert record["duration_ms"] == 12.5


def test_logs_omit_messages_args_exceptions_and_unapproved_fields():
    stream = io.StringIO()
    logger = configure_logging("DEBUG", stream=stream)
    try:
        raise ValueError("fictional-secret-in-exception")
    except ValueError:
        logger.exception(
            "transcript: %s",
            "fictional-private-text",
            extra={"event": "operation.failed", "token": "fictional-install-token"},
        )
    output = stream.getvalue()
    assert "fictional" not in output
    assert "transcript" not in output
    assert "Traceback" not in output
    assert json.loads(output)["event"] == "operation.failed"


@pytest.mark.parametrize("duration", [float("nan"), float("inf"), -1, True, "private", 10**1000])
def test_invalid_metadata_falls_back_to_safe_values(duration):
    stream = io.StringIO()
    logger = configure_logging("INFO", stream=stream)
    logger.info(
        "ignored",
        extra={
            "event": "fictional-private-text",
            "task_id": "fictional-install-token",
            "duration_ms": duration,
        },
    )
    record = json.loads(stream.getvalue())
    assert record["event"] == "log.record"
    assert record["task_id"] is None
    assert record["duration_ms"] is None
    assert "fictional" not in stream.getvalue()


def test_reconfiguration_does_not_duplicate_logs_and_respects_level():
    stream = io.StringIO()
    configure_logging("INFO", stream=stream)
    logger = configure_logging("WARNING", stream=stream)
    logger.info("ignored")
    logger.warning("ignored", extra={"event": "settings.loaded"})
    assert len(stream.getvalue().splitlines()) == 1
    assert logger.propagate is False


def test_invalid_log_level_is_rejected():
    with pytest.raises(ValueError):
        configure_logging("LOUD", stream=io.StringIO())
