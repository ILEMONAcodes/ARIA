"""Ordered, checksummed migrations; the caller supplies one atomic transaction."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from agent.store.migrations.v001_foundations import STATEMENTS
from agent.store.migrations.v002_policy import STATEMENTS as POLICY_STATEMENTS
from agent.store.migrations.v003_retrieval import STATEMENTS as RETRIEVAL_STATEMENTS

if TYPE_CHECKING:
    from agent.store.database import Connection


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]

    @property
    def checksum(self) -> str:
        return hashlib.sha256("\n".join(self.statements).encode()).hexdigest()


MIGRATIONS = (
    Migration(1, "foundations", STATEMENTS),
    Migration(2, "policy", POLICY_STATEMENTS),
    Migration(3, "retrieval", RETRIEVAL_STATEMENTS),
)


def apply_migrations(
    connection: Connection, migrations: tuple[Migration, ...] = MIGRATIONS
) -> None:
    if [migration.version for migration in migrations] != list(range(1, len(migrations) + 1)):
        raise ValueError("Migration versions must be contiguous and start at one")
    connection.execute(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            checksum TEXT NOT NULL
        )"""
    )
    applied = connection.execute(
        "SELECT version, name, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    expected = [(m.version, m.name, m.checksum) for m in migrations]
    if len(applied) > len(expected) or applied != expected[: len(applied)]:
        raise ValueError("Database migration history does not match this application")
    for migration in migrations[len(applied) :]:
        for statement in migration.statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations (version, name, checksum) VALUES (?, ?, ?)",
            (migration.version, migration.name, migration.checksum),
        )
