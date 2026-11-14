"""Independent paraphrase/negative regressions and v2-to-v3 index preservation."""

from pathlib import Path

import pytest

from agent.fakes import FakeDatabaseKeys
from agent.kb.evaluation import normalized, prepare_corpus
from agent.kb.library import PolicyLibrary, SearchInput
from agent.store.database import open_database

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    root = tmp_path_factory.mktemp("independent-retrieval")
    corpus = prepare_corpus(ROOT, root / "sources")
    with open_database(root / "search.db", FakeDatabaseKeys()) as database:
        service = PolicyLibrary(corpus.folder, database)
        service.refresh()
        yield service


@pytest.mark.parametrize(
    "query,file,page,phrase",
    [
        (
            "Who may be the technical contact for a .gov.ng domain?",
            "ng-domain-management.pdf",
            6,
            "The Technical Contact may be a staff",
        ),
        (
            "What happens to the old .gov.ng domain when an organisation moves to another .gov.ng domain?",
            "ng-domain-management.pdf",
            7,
            "kept in perpetuity",
        ),
        (
            "Must principal officers of ICT service providers be registered with CPN?",
            "ng-ict-service-providers.pdf",
            3,
            "Principal Officers",
        ),
        (
            "Do ICT service providers have to submit standardised service level agreements?",
            "ng-ict-service-providers.pdf",
            5,
            "All applicants must submit the standardized SLAs",
        ),
        (
            "Which information security management standard is named for cloud providers?",
            "ng-cloud-technical.pdf",
            18,
            "ISO/IEC 27001",
        ),
        (
            "What does the cloud guideline require for an exit strategy?",
            "ng-cloud-technical.pdf",
            36,
            "secure data repatriation",
        ),
        (
            "Do social media KPIs need to measure an institution's goals?",
            "ng-public-social-media.pdf",
            13,
            "KPIs directly measure the goals and objectives",
        ),
        (
            "What compliance report must large platforms file with NITDA?",
            "ng-platform-code.pdf",
            10,
            "File an annual compliance report with NITDA",
        ),
        (
            "What is required to apply for annual leave?",
            "leave.txt",
            None,
            "completed request form",
        ),
        (
            "What proof is needed for fictional travel expenses?",
            "travel.txt",
            None,
            "itemised receipts",
        ),
    ],
)
def test_independent_natural_questions_find_support(library, query, file, page, phrase):
    result = library.search(SearchInput(query=query))
    assert result.found, result.message
    assert any(
        Path(c.file_path).name == file
        and c.page == page
        and normalized(phrase) in normalized(c.passage)
        for c in result.citations
    )


@pytest.mark.parametrize(
    "query",
    [
        "How much housing advance can staff request?",
        "How long is probation for staff in our office?",
        "Which hospital handles our staff HMO?",
        "Who is our current payroll officer?",
        "How much is the duty tour allowance for Lagos?",
        "What is the meal subsidy for overtime work?",
    ],
)
def test_independent_unsupported_office_questions_do_not_claim_a_match(library, query):
    assert library.search(SearchInput(query=query)).found is False


def test_v2_index_upgrade_keeps_passages_and_enables_stemming_and_headings(tmp_path):
    from sqlcipher3 import dbapi2

    from agent.store.migrations import MIGRATIONS, apply_migrations

    path = tmp_path / "v2.db"
    connection = dbapi2.connect(str(path), isolation_level=None)
    connection.execute(f"PRAGMA key = \"x'{bytes(range(32)).hex()}'\"")
    connection.execute("BEGIN")
    apply_migrations(connection, MIGRATIONS[:2])
    connection.execute(
        "INSERT INTO kb_documents VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            "fictional",
            str(tmp_path),
            "policy.txt",
            "a" * 64,
            "Fictional policy",
            None,
            None,
            None,
            None,
            "2026-11-14T00:00:00Z",
        ),
    )
    connection.execute(
        "INSERT INTO kb_passages(rowid,document_id,page,section,title,text) VALUES (42,'fictional',NULL,'Eligibility','Fictional policy','An application is required.')"
    )
    connection.execute("COMMIT")
    connection.close()

    class Keys:
        def get_key(self, database_id, *, create):
            assert not create
            return bytes(range(32))

    with open_database(path, Keys()) as database:
        assert database.fetch_all("SELECT rowid,document_id,section,text FROM kb_passages") == [
            (42, "fictional", "Eligibility", "An application is required.")
        ]
        assert database.fetch_all(
            "SELECT rowid FROM kb_passages WHERE kb_passages MATCH ?", ('"applications"',)
        ) == [(42,)]
        assert database.fetch_all(
            "SELECT rowid FROM kb_passages WHERE kb_passages MATCH ?", ('"eligibility"',)
        ) == [(42,)]
        assert database.fetch_all("SELECT fingerprint FROM kb_documents") == [("a" * 64,)]
        assert not database.fetch_all("SELECT name FROM sqlite_master WHERE name='kb_passages_v2'")


def test_relevance_precedes_newer_unrelated_boilerplate_and_newest_is_explicit(tmp_path):
    root = tmp_path / "sources"
    root.mkdir()
    (root / "old.txt").write_text("Annual leave requires a completed request form.")
    (root / "new.txt").write_text("Annual budget planning requires financial reports.")
    import json

    (root / "manifest.json").write_text(
        json.dumps(
            {
                "documents": [
                    {"file": "old.txt", "title": "Leave", "issue_date": "2020-01-01"},
                    {"file": "new.txt", "title": "Budget", "issue_date": "2026-01-01"},
                ]
            }
        )
    )
    with open_database(tmp_path / "search.db", FakeDatabaseKeys()) as database:
        library = PolicyLibrary(root, database)
        library.refresh()
        assert library.search(SearchInput(query="annual leave")).citations[0].doc == "Leave"
        listing = library.search(SearchInput(query="annual", sort="newest"))
        assert [c.doc for c in listing.citations] == ["Budget", "Leave"]
