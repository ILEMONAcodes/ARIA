"""UTC retention boundaries shared by startup and the future lifecycle worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.store.database import Database


def timestamp_us(value: datetime) -> int:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timezone-aware timestamp is required")
    delta = value.astimezone(UTC) - datetime(1970, 1, 1, tzinfo=UTC)
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


@dataclass(frozen=True)
class PurgeResult:
    transcripts: int
    activity_entries: int


def purge_expired(database: Database, *, now: datetime) -> PurgeResult:
    # Calculate both cutoffs before writing anything. Equality is retained.
    transcripts_before = timestamp_us(now - timedelta(days=30))
    activity_before = timestamp_us(now - timedelta(days=90))
    with database.transaction() as connection:
        transcripts = connection.execute(
            "DELETE FROM transcripts WHERE created_at < ?", (transcripts_before,)
        ).rowcount
        activity = connection.execute(
            "DELETE FROM activity_log WHERE created_at < ?", (activity_before,)
        ).rowcount
    return PurgeResult(transcripts, activity)
