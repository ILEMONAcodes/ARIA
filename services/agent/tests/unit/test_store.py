import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlcipher3.dbapi2 import IntegrityError, OperationalError

from agent.security.keys import KeyUnavailableError
from agent.store import HistoryRepository, StoreError, open_database, purge_expired
from agent.store.migrations import MIGRATIONS, Migration, apply_migrations
from agent.store.retention import timestamp_us

NOW = datetime(2026, 11, 13, 12, tzinfo=UTC)


class FakeKeys:
    def __init__(self, key=b"a" * 32):
        self.key = key
        self.calls = []

    def get_key(self, database_id, *, create):
        self.calls.append((database_id, create))
        return self.key


@pytest.fixture
def keys():
    return FakeKeys()


@pytest.fixture
def database(tmp_path, keys):
    with open_database(tmp_path / "history.db", keys, now=NOW) as database:
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO profiles (id, name, created_at) VALUES (?, ?, ?)",
                ("fictional-profile", "Fictional User", timestamp_us(NOW)),
            )
        yield database


def test_database_file_is_not_readable_as_plain_text(tmp_path, keys):
    path = tmp_path / "encrypted.db"
    with open_database(path, keys, now=NOW) as database, database.transaction() as connection:
        connection.execute("INSERT INTO settings VALUES (?, ?)", ("note", "fictional-private-text"))
    content = path.read_bytes()
    assert not content.startswith(b"SQLite format 3")
    assert b"fictional-private-text" not in content
    with sqlite3.connect(path) as plaintext, pytest.raises(sqlite3.DatabaseError):
        plaintext.execute("SELECT * FROM sqlite_master").fetchall()


def test_database_reopens_with_same_key_and_does_not_reapply_migrations(tmp_path, keys):
    path = tmp_path / "history.db"
    with open_database(path, keys, now=NOW) as database, database.transaction() as connection:
        connection.execute("INSERT INTO settings VALUES ('fictional', 'saved')")
    with open_database(path, keys, now=NOW) as database:
        assert database.fetch_all("SELECT value FROM settings") == [("saved",)]
        assert database.fetch_all("SELECT version FROM schema_migrations") == [
            (m.version,) for m in MIGRATIONS
        ]
    assert [create for _, create in keys.calls] == [True, False]
    assert len({identity for identity, _ in keys.calls}) == 1


def test_wrong_key_does_not_modify_existing_database(tmp_path, keys):
    path = tmp_path / "history.db"
    with open_database(path, keys, now=NOW):
        pass
    before = hashlib.sha256(path.read_bytes()).digest()
    with pytest.raises(StoreError) as error:
        open_database(path, FakeKeys(b"b" * 32), now=NOW)
    assert "bbbb" not in str(error.value)
    assert hashlib.sha256(path.read_bytes()).digest() == before
    with open_database(path, keys, now=NOW):
        pass


def test_existing_plaintext_database_is_rejected_without_overwrite(tmp_path, keys):
    path = tmp_path / "plaintext.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE fictional (id INTEGER)")
    before = path.read_bytes()
    with pytest.raises(StoreError):
        open_database(path, keys, now=NOW)
    assert path.read_bytes() == before
    assert keys.calls[0][1] is False


def test_existing_database_with_missing_key_is_never_rekeyed(tmp_path, keys):
    path = tmp_path / "history.db"
    with open_database(path, keys, now=NOW):
        pass
    before = path.read_bytes()

    class LostKey:
        def get_key(self, database_id, *, create):
            assert create is False
            raise KeyUnavailableError("missing")

    with pytest.raises(StoreError):
        open_database(path, LostKey(), now=NOW)
    assert path.read_bytes() == before


def test_missing_key_does_not_create_a_database(tmp_path):
    class Unavailable:
        def get_key(self, database_id, *, create):
            raise KeyUnavailableError("fictional-vault-secret")

    path = tmp_path / "history.db"
    with pytest.raises(StoreError) as error:
        open_database(path, Unavailable(), now=NOW)
    assert "fictional-vault-secret" not in str(error.value)
    assert not path.exists()


@pytest.mark.parametrize("key", [b"", b"short", "a" * 32])
def test_invalid_key_is_rejected_before_database_creation(tmp_path, key):
    path = tmp_path / "history.db"
    with pytest.raises(StoreError):
        open_database(path, FakeKeys(key), now=NOW)
    assert not path.exists()


def test_plain_sqlite_driver_is_rejected_without_touching_keys_or_file(tmp_path, keys, monkeypatch):
    monkeypatch.setattr("agent.store.database._load_driver", lambda: sqlite3)
    path = tmp_path / "history.db"
    with pytest.raises(StoreError):
        open_database(path, keys, now=NOW)
    assert not path.exists()
    assert keys.calls == []


def test_missing_sqlcipher_driver_is_a_safe_failure(tmp_path, keys, monkeypatch):
    def missing():
        raise ImportError("fictional-system-path")

    monkeypatch.setattr("agent.store.database._load_driver", missing)
    with pytest.raises(StoreError) as error:
        open_database(tmp_path / "history.db", keys, now=NOW)
    assert "fictional-system-path" not in str(error.value)
    assert keys.calls == []


def test_failed_transaction_rolls_back_all_writes(database):
    with pytest.raises(ValueError), database.transaction() as connection:
        connection.execute("INSERT INTO settings VALUES ('fictional', 'temporary')")
        raise ValueError("simulated interruption")
    assert database.fetch_all("SELECT * FROM settings") == []


def test_foreign_keys_reject_orphaned_history(database):
    with pytest.raises(IntegrityError):
        HistoryRepository(database).add_transcript("missing-profile", "fictional text", at=NOW)
    assert database.fetch_all("SELECT * FROM transcripts") == []


def test_failed_migration_rolls_back_schema_and_version(database):
    broken = Migration(
        len(MIGRATIONS) + 1, "broken", ("CREATE TABLE temporary_table (id TEXT)", "INVALID SQL")
    )
    with pytest.raises(OperationalError), database.transaction() as connection:
        apply_migrations(connection, (*MIGRATIONS, broken))
    assert database.fetch_all("SELECT version FROM schema_migrations") == [
        (m.version,) for m in MIGRATIONS
    ]
    assert database.fetch_all("SELECT name FROM sqlite_master WHERE name='temporary_table'") == []


def test_migration_checksum_mismatch_is_rejected(database):
    with pytest.raises(ValueError, match="history"), database.transaction() as connection:
        apply_migrations(connection, (Migration(1, "foundations", ("SELECT 1",)),))
    assert database.fetch_all("SELECT version FROM schema_migrations") == [
        (m.version,) for m in MIGRATIONS
    ]


def test_newer_database_schema_is_rejected(database):
    with database.transaction() as connection:
        connection.execute("INSERT INTO schema_migrations VALUES (999, 'future', 'unknown')")
    with pytest.raises(ValueError, match="history"), database.transaction() as connection:
        apply_migrations(connection)


def test_migrations_must_have_contiguous_versions(database):
    with pytest.raises(ValueError, match="contiguous"), database.transaction() as connection:
        apply_migrations(connection, (Migration(2, "gap", ("SELECT 1",)),))


def test_retention_purges_transcripts_after_30_days_and_logs_after_90(database):
    history = HistoryRepository(database)
    for label, age in (("old", 1), ("boundary", 0), ("new", -1)):
        history.add_transcript(
            "fictional-profile", label, at=NOW - timedelta(days=30, microseconds=age)
        )
        history.add_activity(
            "fictional-profile", label, "test.tool", at=NOW - timedelta(days=90, microseconds=age)
        )
    purged = purge_expired(database, now=NOW)
    assert (purged.transcripts, purged.activity_entries) == (1, 1)
    assert [entry.text for entry in history.transcripts("fictional-profile")] == ["boundary", "new"]
    assert database.fetch_all("SELECT text FROM activity_log ORDER BY created_at") == [
        ("boundary",),
        ("new",),
    ]
    assert database.fetch_all("SELECT name FROM profiles") == [("Fictional User",)]
    assert purge_expired(database, now=NOW).transcripts == 0


def test_opening_database_automatically_purges_expired_history(tmp_path, keys):
    path = tmp_path / "history.db"
    with open_database(path, keys, now=NOW) as database:
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO profiles (id, name, created_at) VALUES ('p', 'Test', 0)"
            )
        HistoryRepository(database).add_transcript("p", "expired", at=NOW - timedelta(days=31))
    with open_database(path, keys, now=NOW) as database:
        assert HistoryRepository(database).transcripts("p") == []


def test_retention_is_atomic_if_second_delete_fails(database):
    history = HistoryRepository(database)
    history.add_transcript("fictional-profile", "old", at=NOW - timedelta(days=31))
    history.add_activity("fictional-profile", "old", "test", at=NOW - timedelta(days=91))
    with database.transaction() as connection:
        connection.execute(
            """CREATE TRIGGER prevent_activity_delete BEFORE DELETE ON activity_log
               BEGIN SELECT RAISE(ABORT, 'simulated failure'); END"""
        )
    with pytest.raises(IntegrityError):
        purge_expired(database, now=NOW)
    assert len(history.transcripts("fictional-profile")) == 1
    assert len(database.fetch_all("SELECT id FROM activity_log")) == 1


def test_naive_retention_time_is_rejected_before_deleting(database):
    with pytest.raises(ValueError, match="timezone"):
        purge_expired(database, now=NOW.replace(tzinfo=None))


def test_utc_timestamp_preserves_offsets_and_microseconds():
    offset = timezone(timedelta(hours=1))
    assert timestamp_us(NOW.astimezone(offset)) == timestamp_us(NOW)
    assert timestamp_us(NOW + timedelta(microseconds=1)) == timestamp_us(NOW) + 1


def test_history_queries_are_parameterized_and_isolated_by_profile(database):
    history = HistoryRepository(database)
    text = "fictional text'); DROP TABLE profiles; --"
    history.add_transcript("fictional-profile", text, at=NOW)
    assert history.transcripts("fictional-profile")[0].text == text
    assert history.transcripts("other-profile") == []
    assert database.fetch_all("SELECT count(*) FROM profiles") == [(1,)]
