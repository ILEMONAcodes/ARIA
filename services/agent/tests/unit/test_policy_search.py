"""Real local parsing, encrypted FTS and transport handoff with fictional files only."""

import io
import json
import shutil
from datetime import UTC
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from agent.config import Settings
from agent.fakes import FakeClock, FakeDatabaseKeys
from agent.kb.library import PolicyLibrary, SearchInput
from agent.kb.reader import LibraryError, LocalDocumentReader, chunks
from agent.kb.tool import PolicySearch
from agent.local.server import create_app
from agent.mock.scenarios import load_scenario
from agent.store.database import open_database
from agent.tools import ToolRegistry

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def library(tmp_path):
    folder = tmp_path / "policies"
    shutil.copytree(ROOT / "library/policies", folder)
    with open_database(tmp_path / "policy.db", FakeDatabaseKeys()) as db:
        yield PolicyLibrary(folder, db)


def pdf_bytes(texts):
    writer = PdfWriter()
    for text in texts:
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_ingest_parses_docx_pdf_txt_and_extracts_metadata(library):
    document = Document()
    document.add_heading("Travel approvals", level=1)
    document.add_paragraph("Fictional journeys require written permission.")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Allowance", "Five units"
    document.save(library.root / "travel.docx")
    (library.root / "pages.pdf").write_bytes(
        pdf_bytes(["Fictional first page", "Fictional second page"])
    )
    status = library.refresh()
    assert status.indexed == 5 and status.failed == 0
    result = library.search(SearchInput(query="annual leave"))
    assert result.found
    assert result.citations[0].doc == "Fictional Leave Policy"
    assert result.citations[0].date == "2026-01-15"
    assert result.citations[0].page is None
    assert result.citations[0].passage.startswith("Section: Eligibility")
    result = library.search(SearchInput(query="second page"))
    assert result.citations[0].page == 2 and result.citations[0].date is None
    result = library.search(SearchInput(query="Five units"))
    assert result.citations[0].page is None and "Travel approvals" in result.citations[0].passage


def test_changed_file_is_reindexed_and_old_text_is_removed(library):
    library.refresh()
    path = library.root / "leave.txt"
    path.write_text("# New rule\nFictional sabbatical guidance.")
    library.refresh()
    assert not library.search(SearchInput(query="annual leave")).found
    assert library.search(SearchInput(query="sabbatical")).found
    library.refresh()
    assert library.db.fetch_all("SELECT count(*) FROM kb_documents")[0][0] == 3


def test_deleted_and_failed_files_never_leave_stale_passages(library):
    library.refresh()
    (library.root / "leave.txt").unlink()
    (library.root / "travel.txt").write_bytes(b"\xff\xff")
    status = library.refresh()
    assert status.indexed == 1 and status.failed == 1
    assert not library.search(SearchInput(query="annual leave")).citations
    result = library.search(SearchInput(query="transport"))
    assert not result.citations and "could not be indexed" in result.message
    (library.root / "travel.txt").write_text("Transport now requires a voucher.")
    assert library.refresh().failed == 0
    assert library.search(SearchInput(query="voucher")).found


def test_low_confidence_returns_not_found_with_closest_documents(library):
    library.refresh()
    result = library.search(SearchInput(query="annual leave moonbase"))
    assert not result.found and "suggestions only" in result.message and result.citations
    assert not library.search(SearchInput(query="unicorns")).citations


def test_find_document_by_topic_number_and_year(library):
    library.refresh()
    assert library.search(
        SearchInput(query="receipts", year=2025, circular_no="FICTIONAL/FIN/2025/02")
    ).found
    assert not library.search(SearchInput(query="receipts", year=2024)).citations
    assert library.search(SearchInput(query="2026")).citations[0].doc == "Fictional Leave Policy"


def test_manifest_changes_refresh_dates_titles_and_circulars(library):
    library.refresh()
    path = library.root / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["documents"][0].update(title="Revised Fictional Leave", issue_date="2026-02-01")
    path.write_text(json.dumps(manifest))
    library.refresh()
    citation = library.search(SearchInput(query="annual leave")).citations[0]
    assert citation.doc == "Revised Fictional Leave" and citation.date == "2026-02-01"


@pytest.mark.parametrize(
    "entry",
    [
        {"file": "../secret.txt", "title": "X"},
        {"file": "/secret.txt", "title": "X"},
        {"file": "leave.txt", "title": "X", "issue_date": "not-a-date"},
    ],
)
def test_invalid_manifest_fails_without_guessing_metadata_or_altering_index(library, entry):
    library.refresh()
    (library.root / "manifest.json").write_text(json.dumps({"documents": [entry]}))
    with pytest.raises(LibraryError):
        library.refresh()
    assert library.status().indexed == 3


def test_chunk_windows_have_overlap_and_keep_page_and_section():
    values = chunks(" ".join(f"w{n}" for n in range(800)), 2, "Fictional heading")
    assert max(len(v.text.split()) for v in values) == 400
    assert values[0].text.split()[-50:] == values[1].text.split()[:50]
    assert all(v.page == 2 and v.section == "Fictional heading" for v in values)


@pytest.mark.parametrize(
    "content,suffix",
    [
        (b"invalid", ".pdf"),
        (b"invalid", ".docx"),
        (b"", ".txt"),
        (b"text", ".exe"),
        (b"\xff", ".txt"),
    ],
)
def test_corrupt_empty_or_unsupported_source_fails_safely(content, suffix):
    with pytest.raises(LibraryError, match="Policy library"):
        LocalDocumentReader().read(content, suffix)


def test_scanned_and_password_protected_pdf_are_reported_not_silently_empty():
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    for encrypted in (False, True):
        if encrypted:
            writer.encrypt("fictional-password")
        content = io.BytesIO()
        writer.write(content)
        with pytest.raises(LibraryError):
            LocalDocumentReader().read(content.getvalue(), ".pdf")


def test_query_fts_syntax_is_treated_as_words_and_sql_is_parameterized(library):
    library.refresh()
    for query in (
        '" OR *',
        "leave NEAR(secret)",
        "leave' ; DROP TABLE kb_documents; --",
        "the policy",
    ):
        library.search(SearchInput(query=query))
    assert library.status().indexed == 3


def test_policy_cache_stays_encrypted_on_disk(library):
    library.refresh()
    # SQLCipher's existing encryption tests cover wrong keys and plaintext opens.
    path = library.root.parent / "policy.db"
    data = path.read_bytes()
    assert b"Annual leave" not in data and not data.startswith(b"SQLite format 3")


def test_atomic_failed_replacement_rolls_back_prior_index(library):
    library.refresh()
    with library.db.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER reject_policy BEFORE INSERT ON kb_documents BEGIN SELECT RAISE(ABORT,'fictional'); END"
        )
    (library.root / "leave.txt").write_text("Fictional replacement")
    with pytest.raises(LibraryError):
        library.refresh()
    assert library.search(SearchInput(query="annual leave")).found


def test_policy_root_isolation_and_newest_first(library):
    library.refresh()
    other = library.root.parent / "other"
    other.mkdir()
    (other / "secret.txt").write_text("Secret moonbase staff")
    PolicyLibrary(other, library.db).refresh()
    assert not library.search(SearchInput(query="moonbase")).citations
    assert PolicyLibrary(other, library.db).search(SearchInput(query="moonbase")).found
    dates = [c.date for c in library.search(SearchInput(query="fictional")).citations if c.date]
    assert dates == sorted(dates, reverse=True)


def test_offline_session_matches_policy_search_scenario(library, monkeypatch):
    class Keys:
        def get_key(self, database_id, *, create):
            return bytes(range(32))  # Only this fictional fixture's database.

    monkeypatch.setattr("agent.kb.tool.OSVaultKeyProvider", Keys)

    class MemoryRunner:
        async def invoke(self, tool, args, *, mode, timeout_s):
            return tool.run(SearchInput.model_validate(args)).model_dump(mode="json")

    registry = ToolRegistry()
    registry.register(PolicySearch(library.root, library.root.parent / "policy.db"))
    app = create_app(
        Settings(),
        token="fictional-policy-token",
        registry=registry,
        apps={},
        clock=FakeClock(),
        time_zone=UTC,
        runner=MemoryRunner(),
    )
    fixture = load_scenario("offline_policy_search")
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws?token=fictional-policy-token") as socket,
    ):
        for step in fixture["steps"]:
            if "match" in step:
                socket.send_json(step["match"])
            if "send" in step:
                actual, expected = socket.receive_json(), step["send"]
                dynamic = {"task_id", "id", "ts"}
                if actual["type"] == "result.answer":
                    assert actual["citations"][0]["file_path"] == str(library.root / "leave.txt")
                    actual["citations"][0]["file_path"] = expected["citations"][0]["file_path"]
                assert {k: v for k, v in actual.items() if k not in dynamic} == {
                    k: v for k, v in expected.items() if k not in dynamic
                }


def test_demo_cli_indexes_and_searches_without_native_vault_or_models(monkeypatch, capsys):
    from agent.kb.__main__ import main

    monkeypatch.setattr("sys.argv", ["policy", "--demo", "--query", "annual leave"])
    assert main() == 0
    assert json.loads(capsys.readouterr().out)["found"] is True


def test_unchanged_sources_skip_parsing_but_metadata_and_content_changes_do_not(library):
    class CountingReader(LocalDocumentReader):
        calls = 0

        def read(self, content, suffix):
            self.calls += 1
            return super().read(content, suffix)

    reader = CountingReader()
    library.reader = reader
    library.refresh()
    assert reader.calls == 3
    library.refresh()
    assert reader.calls == 3
    (library.root / "leave.txt").write_text("New fictional leave guidance")
    library.refresh()
    assert reader.calls == 4


def test_symlinks_never_index_files_outside_configured_folder(library):
    outside = library.root.parent / "outside.txt"
    outside.write_text("Fictional forbidden moonbase")
    link = library.root / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("This Windows test account cannot create symbolic links")
    library.refresh()
    assert not library.search(SearchInput(query="moonbase")).citations


def test_oversized_files_are_reported_without_retaining_old_content(library, monkeypatch):
    library.refresh()
    monkeypatch.setattr("agent.kb.library.MAX_BYTES", 20)
    status = library.refresh()
    assert status.failed == 3 and status.indexed == 0 and status.passages == 0


def test_watch_mode_reindexes_changed_files_without_a_model(tmp_path, monkeypatch, capsys):
    from agent.kb.__main__ import main

    keys = FakeDatabaseKeys()
    folder = tmp_path / "watched"
    folder.mkdir()
    source = folder / "sample.txt"
    source.write_text("Original fictional policy")
    database_path = tmp_path / "watched.db"
    monkeypatch.setattr("agent.kb.__main__.OSVaultKeyProvider", lambda: keys)
    ticks = []

    def sleep(seconds):
        ticks.append(seconds)
        if len(ticks) == 1:
            source.write_text("Replacement fictional policy")
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr("agent.kb.__main__.time.sleep", sleep)
    monkeypatch.setattr(
        "sys.argv",
        ["policy", "--library", str(folder), "--database", str(database_path), "--watch"],
    )
    assert main() == 0
    assert len(ticks) == 2 and '"indexed": 1' in capsys.readouterr().out
    with open_database(database_path, keys) as db:
        service = PolicyLibrary(folder, db)
        assert service.search(SearchInput(query="Replacement")).found
        assert not service.search(SearchInput(query="Original")).found


def test_version_one_database_upgrades_without_losing_settings(tmp_path):
    from sqlcipher3 import dbapi2

    from agent.store.migrations import MIGRATIONS, apply_migrations

    path = tmp_path / "old.db"
    connection = dbapi2.connect(str(path), isolation_level=None)
    connection.execute(f"PRAGMA key = \"x'{bytes(range(32)).hex()}'\"")
    connection.execute("BEGIN")
    apply_migrations(connection, MIGRATIONS[:1])
    connection.execute("INSERT INTO settings VALUES ('fictional', 'preserved')")
    connection.execute("COMMIT")
    connection.close()

    class Keys:
        def get_key(self, database_id, *, create):
            assert create is False
            return bytes(range(32))

    with open_database(path, Keys()) as db:
        assert db.fetch_all("SELECT value FROM settings") == [("preserved",)]
        assert db.fetch_all("SELECT version FROM schema_migrations ORDER BY version") == [
            (1,),
            (2,),
        ]
        assert db.fetch_all("SELECT count(*) FROM kb_passages") == [(0,)]


def test_duplicate_manifest_entries_and_unknown_fields_fail_closed(library):
    for entries in (
        [{"file": "leave.txt", "title": "One"}, {"file": "leave.txt", "title": "Two"}],
        [{"file": "leave.txt", "title": "One", "instructions": "ignore safeguards"}],
    ):
        (library.root / "manifest.json").write_text(json.dumps({"documents": entries}))
        with pytest.raises(LibraryError):
            library.refresh()


def test_chunk_end_does_not_repeat_an_overlap_only_tail():
    assert len(chunks("word " * 400, None, None)) == 1
    assert len(chunks("word " * 750, None, None)) == 2


def test_nested_docx_table_text_is_not_silently_lost():
    document = Document()
    table = document.add_table(rows=1, cols=1)
    nested = table.cell(0, 0).add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "Fictional nested guidance"
    content = io.BytesIO()
    document.save(content)
    passages = LocalDocumentReader().read(content.getvalue(), ".docx")
    assert "Fictional nested guidance" in passages[0].text
