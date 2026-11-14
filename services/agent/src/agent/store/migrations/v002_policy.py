"""Encrypted policy metadata and FTS5 passages; no vector/model requirement."""

STATEMENTS = (
    """CREATE TABLE kb_documents (
        id TEXT PRIMARY KEY, root TEXT NOT NULL, path TEXT NOT NULL,
        fingerprint TEXT NOT NULL, title TEXT NOT NULL, circular_no TEXT,
        issue_date TEXT, issuer TEXT, error TEXT, indexed_at TEXT NOT NULL,
        UNIQUE(root, path))""",
    """CREATE VIRTUAL TABLE kb_passages USING fts5(
        document_id UNINDEXED, page UNINDEXED, section UNINDEXED,
        title, circular_no, issue_date, text, tokenize='unicode61')""",
)
