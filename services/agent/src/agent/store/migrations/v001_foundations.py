"""Phase A tables only. Later features add their own migrations."""

STATEMENTS = (
    """CREATE TABLE profiles (
        id TEXT PRIMARY KEY NOT NULL,
        name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT '',
        voice_embedding BLOB,
        settings_json TEXT NOT NULL DEFAULT '{}',
        created_at INTEGER NOT NULL
    )""",
    "CREATE TABLE settings (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)",
    """CREATE TABLE transcripts (
        id TEXT PRIMARY KEY NOT NULL,
        profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX transcripts_created_at ON transcripts(created_at)",
    """CREATE TABLE activity_log (
        id TEXT PRIMARY KEY NOT NULL,
        profile_id TEXT NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
        text TEXT NOT NULL,
        tool TEXT NOT NULL,
        undoable INTEGER NOT NULL DEFAULT 0 CHECK (undoable IN (0, 1)),
        undo_payload TEXT,
        created_at INTEGER NOT NULL
    )""",
    "CREATE INDEX activity_created_at ON activity_log(created_at)",
)
