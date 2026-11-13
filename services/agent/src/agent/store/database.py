"""SQLCipher-only connections; no plaintext fallback or automatic key replacement."""

from __future__ import annotations

import hashlib
import importlib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol, Self, cast

from filelock import FileLock

from agent.security.keys import DatabaseKeyProvider
from agent.store.migrations import apply_migrations

Value = str | int | float | bytes | None


class Cursor(Protocol):
    @property
    def rowcount(self) -> int: ...

    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...


class Connection(Protocol):
    def execute(self, sql: str, parameters: Sequence[Value] = ()) -> Cursor: ...

    def close(self) -> None: ...


class Driver(Protocol):
    def connect(self, database: str, *, isolation_level: None = None) -> Connection: ...


class StoreError(RuntimeError):
    """Sanitized storage failure suitable for an application error boundary."""


def _load_driver() -> Driver:
    return cast(Driver, importlib.import_module("sqlcipher3.dbapi2"))


class Database:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield self._connection
            self._connection.execute("COMMIT")
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise

    def fetch_all(self, sql: str, parameters: Sequence[Value] = ()) -> list[tuple[Any, ...]]:
        return self._connection.execute(sql, parameters).fetchall()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def open_database(
    path: Path, keys: DatabaseKeyProvider, *, now: datetime | None = None
) -> Database:
    """Open/migrate an encrypted file and purge expired history before returning it.

    A short file lock serializes key provisioning and schema upgrades across
    processes. Keys must already exist for an existing file, including an empty
    file left by an interrupted setup. No recovery path replaces a missing key.
    """
    connection: Connection | None = None
    try:
        driver = _load_driver()
        # Test support in memory before touching a user's database or key vault.
        probe = driver.connect(":memory:", isolation_level=None)
        try:
            version = probe.execute("PRAGMA cipher_version").fetchone()
            if not version or not str(version[0]).startswith("4."):
                raise StoreError("SQLCipher 4 encryption support is required")
        finally:
            probe.close()
        path = path.resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(path) + ".lock", timeout=5):
            identity = hashlib.sha256(str(path).encode()).hexdigest()
            key = keys.get_key(identity, create=not path.exists())
            if not isinstance(key, bytes) or len(key) != 32:
                raise StoreError("A valid database encryption key is required")
            connection = driver.connect(str(path), isolation_level=None)
            # Only hex-encoded random bytes are interpolated; no SQL from input.
            connection.execute(f"PRAGMA key = \"x'{key.hex()}'\"")
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.execute("PRAGMA journal_mode = DELETE")
            database = Database(connection)
            with database.transaction() as transaction:
                apply_migrations(transaction)
            from agent.store.retention import purge_expired

            purge_expired(database, now=now if now is not None else datetime.now(UTC))
            return database
    except Exception:  # noqa: BLE001 - do not expose paths, keys or native error details
        if connection is not None:
            connection.close()
        raise StoreError(
            "Could not open encrypted storage; check SQLCipher and the OS vault"
        ) from None
