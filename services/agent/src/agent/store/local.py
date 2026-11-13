"""Lifecycle adapter around the SQLCipher store."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from agent.interfaces import HistoryStore
from agent.interfaces.models import PurgeResult
from agent.security.keys import DatabaseKeyProvider
from agent.store.database import Database, open_database
from agent.store.repositories import HistoryRepository
from agent.store.retention import purge_expired


class SqlCipherStore:
    def __init__(self, path: Path, keys: DatabaseKeyProvider) -> None:
        self._path = path
        self._keys = keys
        self._database: Database | None = None

    def open(self, *, now: datetime) -> None:
        if self._database is not None:
            raise RuntimeError("Storage is already open")
        self._database = open_database(self._path, self._keys, now=now)

    def _opened(self) -> Database:
        if self._database is None:
            raise RuntimeError("Storage is not open")
        return self._database

    @property
    def history(self) -> HistoryStore:
        return HistoryRepository(self._opened())

    def purge(self, *, now: datetime) -> PurgeResult:
        return purge_expired(self._opened(), now=now)

    def close(self) -> None:
        if self._database is not None:
            self._database.close()
            self._database = None
