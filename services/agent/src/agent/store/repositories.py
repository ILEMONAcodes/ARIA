"""History persistence; user-facing actions and undo arrive in their own phases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from agent.store.database import Database
from agent.store.retention import timestamp_us


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    text: str
    created_at: datetime


class HistoryRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def add_transcript(self, profile_id: str, text: str, *, at: datetime) -> str:
        timestamp = timestamp_us(at)
        identifier = str(uuid4())
        with self._database.transaction() as connection:
            connection.execute(
                "INSERT INTO transcripts (id, profile_id, text, created_at) VALUES (?, ?, ?, ?)",
                (identifier, profile_id, text, timestamp),
            )
        return identifier

    def add_activity(self, profile_id: str, text: str, tool: str, *, at: datetime) -> str:
        timestamp = timestamp_us(at)
        identifier = str(uuid4())
        with self._database.transaction() as connection:
            connection.execute(
                """INSERT INTO activity_log (id, profile_id, text, tool, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (identifier, profile_id, text, tool, timestamp),
            )
        return identifier

    def transcripts(self, profile_id: str) -> list[HistoryEntry]:
        rows = self._database.fetch_all(
            "SELECT id, text, created_at FROM transcripts WHERE profile_id = ? ORDER BY created_at, id",
            (profile_id,),
        )
        return [
            HistoryEntry(
                identifier, text, datetime(1970, 1, 1, tzinfo=UTC) + timedelta(microseconds=ts)
            )
            for identifier, text, ts in rows
        ]
