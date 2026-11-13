"""In-memory fixtures only. These doubles must never back a real user database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agent.interfaces.models import HistoryEntry, PurgeResult
from agent.security.keys import KeyUnavailableError
from agent.store.retention import timestamp_us


class FakeClock:
    def __init__(self, at: datetime = datetime(2026, 1, 1, tzinfo=UTC)) -> None:
        timestamp_us(at)
        self.at = at

    def now(self) -> datetime:
        return self.at

    def advance(self, elapsed: timedelta) -> None:
        self.at += elapsed


class FakeDatabaseKeys:
    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}

    def get_key(self, database_id: str, *, create: bool) -> bytes:
        if database_id not in self._keys:
            if not create:
                raise KeyUnavailableError("Fictional key is missing")
            self._keys[database_id] = bytes(range(32))
        return self._keys[database_id]


class FakeStore:
    def __init__(self) -> None:
        self.opened = 0
        self.closed = 0
        self.active = False
        self.purged = 0
        self._next_id = 0
        self._transcripts: list[tuple[str, HistoryEntry]] = []
        self._activities: list[tuple[str, HistoryEntry]] = []

    def _require_open(self) -> None:
        if not self.active:
            raise RuntimeError("Fake store is not open")

    def open(self, *, now: datetime) -> None:
        if self.active:
            raise RuntimeError("Fake store is already open")
        timestamp_us(now)
        self.active = True
        self.opened += 1
        self.purge(now=now)

    @property
    def history(self) -> FakeStore:
        self._require_open()
        return self

    def add_transcript(self, profile_id: str, text: str, *, at: datetime) -> str:
        self._require_open()
        timestamp_us(at)
        self._next_id += 1
        identifier = f"fake-{self._next_id:08d}"
        self._transcripts.append((profile_id, HistoryEntry(identifier, text, at)))
        return identifier

    def add_activity(self, profile_id: str, text: str, tool: str, *, at: datetime) -> str:
        self._require_open()
        timestamp_us(at)
        self._next_id += 1
        identifier = f"fake-{self._next_id:08d}"
        self._activities.append((profile_id, HistoryEntry(identifier, text, at)))
        return identifier

    def transcripts(self, profile_id: str) -> list[HistoryEntry]:
        self._require_open()
        return sorted(
            (entry for profile, entry in self._transcripts if profile == profile_id),
            key=lambda entry: (entry.created_at, entry.id),
        )

    def purge(self, *, now: datetime) -> PurgeResult:
        self._require_open()
        timestamp_us(now)
        before_transcripts, before_activity = len(self._transcripts), len(self._activities)
        self._transcripts = [
            pair for pair in self._transcripts if pair[1].created_at >= now - timedelta(days=30)
        ]
        self._activities = [
            pair for pair in self._activities if pair[1].created_at >= now - timedelta(days=90)
        ]
        self.purged += 1
        return PurgeResult(
            before_transcripts - len(self._transcripts), before_activity - len(self._activities)
        )

    def close(self) -> None:
        self.closed += 1
        self.active = False
