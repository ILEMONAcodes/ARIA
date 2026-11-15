"""Preserve policy passages while enabling stemming and heading search."""

STATEMENTS = (
    "ALTER TABLE kb_passages RENAME TO kb_passages_v2",
    """CREATE VIRTUAL TABLE kb_passages USING fts5(
        document_id UNINDEXED, page UNINDEXED, section,
        title, circular_no, issue_date, text, tokenize='porter unicode61')""",
    """INSERT INTO kb_passages(rowid,document_id,page,section,title,circular_no,issue_date,text)
        SELECT rowid,document_id,page,section,title,circular_no,issue_date,text
        FROM kb_passages_v2""",
    "DROP TABLE kb_passages_v2",
)
