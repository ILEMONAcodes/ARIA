"""Encrypted FTS5 cache with atomic per-document replacement and explicit provenance."""

from __future__ import annotations

import hashlib
import os
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from agent.contracts.events import Citation
from agent.kb.reader import MAX_BYTES, DocumentReader, LibraryError, LocalDocumentReader, Passage
from agent.store.database import Connection, Database


class Metadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file: str
    title: str = Field(min_length=1, max_length=300)
    circular_no: str | None = Field(default=None, max_length=120)
    issue_date: date | None = None
    issuer: str | None = Field(default=None, max_length=300)
    supersedes: str | None = Field(default=None, max_length=300)

    @field_validator("issue_date", mode="before")
    @classmethod
    def explicit_date(cls, value: Any) -> Any:
        if value is not None and (
            not isinstance(value, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None
        ):
            raise ValueError("Use an explicit ISO issue date")
        return value

    @field_validator("title")
    @classmethod
    def named_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("An explicit title is required")
        return value.strip()

    @field_validator("file")
    @classmethod
    def relative_file(cls, value: str) -> str:
        # A leading slash is drive-relative on Windows, not is_absolute().
        if (
            not value
            or value.startswith("/")
            or "\\" in value
            or ":" in value
            or ".." in Path(value).parts
        ):
            raise ValueError("Manifest paths must stay within the policy folder")
        return value


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    documents: list[Metadata] = Field(max_length=1000)


class IndexStatus(BaseModel):
    indexed: int
    failed: int
    passages: int
    errors: list[str]


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=512)
    year: int | None = Field(default=None, ge=1900, le=9999)
    circular_no: str | None = Field(default=None, min_length=1, max_length=120)


class SearchOutput(BaseModel):
    message: str
    found: bool
    citations: list[Citation]


_STOP = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "what",
        "which",
        "when",
        "where",
        "how",
        "do",
        "does",
        "can",
        "i",
        "me",
        "my",
        "we",
        "our",
        "about",
        "of",
        "to",
        "for",
        "in",
        "on",
        "and",
        "or",
        "please",
        "policy",
        "policies",
        "find",
        "show",
        "search",
        "tell",
    ]
)


class PolicyLibrary:
    def __init__(
        self, root: Path, database: Database, *, reader: DocumentReader | None = None
    ) -> None:
        self.root = root.resolve(strict=True)
        if not self.root.is_dir():
            raise LibraryError()
        self.db = database
        self.reader = reader if reader is not None else LocalDocumentReader()

    def _manifest(self) -> dict[str, Metadata]:
        path = self.root / "manifest.json"
        if path.is_symlink():
            raise LibraryError()
        if not path.exists():
            return {}
        if path.stat().st_size > 1024 * 1024:
            raise LibraryError()
        manifest = Manifest.model_validate_json(path.read_bytes())
        result = {item.file: item for item in manifest.documents}
        if len(result) != len(manifest.documents):
            raise LibraryError()
        return result

    def _files(self) -> list[Path]:
        result = []
        visited = 0

        def failed(error: OSError) -> None:
            raise LibraryError()

        for folder, directories, names in os.walk(self.root, followlinks=False, onerror=failed):
            directories[:] = sorted(d for d in directories if not (Path(folder) / d).is_symlink())
            visited += 1 + len(names)
            if visited > 10000:
                raise LibraryError()
            for name in sorted(names):
                path = Path(folder) / name
                if (
                    path.suffix.lower() in {".txt", ".pdf", ".docx"}
                    and not path.is_symlink()
                    and path.is_file()
                ):
                    if not path.resolve(strict=True).is_relative_to(self.root):
                        raise LibraryError()
                    result.append(path)
                    if len(result) > 1000:
                        raise LibraryError()
        return result

    def _remove(self, connection: Connection, identifier: str) -> None:
        connection.execute("DELETE FROM kb_passages WHERE document_id=?", (identifier,))
        connection.execute("DELETE FROM kb_documents WHERE id=?", (identifier,))

    def refresh(self) -> IndexStatus:
        try:
            manifest, files = self._manifest(), self._files()
            seen = set()
            for path in files:
                relative = path.relative_to(self.root).as_posix()
                identifier = hashlib.sha256(f"{self.root}\0{relative}".encode()).hexdigest()
                seen.add(identifier)
                meta = manifest.get(relative, Metadata(file=relative, title=path.name))
                error = None
                passages: list[Passage] = []
                content = b""
                try:
                    # Recheck containment and size before bounded reading.
                    if path.is_symlink() or not path.resolve(strict=True).is_relative_to(self.root):
                        raise LibraryError()
                    with path.open("rb") as stream:
                        content = stream.read(MAX_BYTES + 1)
                    if len(content) > MAX_BYTES:
                        raise LibraryError()
                    fingerprint = hashlib.sha256(
                        b"reader-v1\0" + content + meta.model_dump_json().encode()
                    ).hexdigest()
                    prior = self.db.fetch_all(
                        "SELECT fingerprint FROM kb_documents WHERE id=?", (identifier,)
                    )
                    if prior and prior[0][0] == fingerprint:
                        continue
                    passages = self.reader.read(content, path.suffix.lower())
                except Exception:  # noqa: BLE001 - source/parser diagnostics stay private
                    error = "unreadable_or_unsupported"
                    fingerprint = hashlib.sha256(
                        content + meta.model_dump_json().encode()
                    ).hexdigest()
                with self.db.transaction() as connection:
                    self._remove(connection, identifier)
                    connection.execute(
                        "INSERT INTO kb_documents VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (
                            identifier,
                            str(self.root),
                            relative,
                            fingerprint,
                            meta.title,
                            meta.circular_no,
                            meta.issue_date.isoformat() if meta.issue_date else None,
                            meta.issuer,
                            error,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
                    if error is None:
                        for passage in passages:
                            connection.execute(
                                "INSERT INTO kb_passages VALUES (?,?,?,?,?,?,?)",
                                (
                                    identifier,
                                    passage.page,
                                    passage.section,
                                    meta.title,
                                    meta.circular_no,
                                    meta.issue_date.isoformat() if meta.issue_date else None,
                                    passage.text,
                                ),
                            )
            with self.db.transaction() as connection:
                for (identifier,) in self.db.fetch_all(
                    "SELECT id FROM kb_documents WHERE root=?", (str(self.root),)
                ):
                    if identifier not in seen:
                        self._remove(connection, identifier)
            return self.status()
        except Exception:  # noqa: BLE001 - sanitize manifest/path/storage failures
            raise LibraryError() from None

    def status(self) -> IndexStatus:
        rows = self.db.fetch_all(
            "SELECT path,error FROM kb_documents WHERE root=? ORDER BY path", (str(self.root),)
        )
        count = self.db.fetch_all(
            "SELECT count(*) FROM kb_passages p JOIN kb_documents d ON p.document_id=d.id WHERE d.root=?",
            (str(self.root),),
        )[0][0]
        return IndexStatus(
            indexed=sum(r[1] is None for r in rows),
            failed=sum(r[1] is not None for r in rows),
            passages=count,
            errors=[r[0] for r in rows if r[1] is not None],
        )

    def search(self, args: SearchInput) -> SearchOutput:
        try:
            tokens = list(
                dict.fromkeys(
                    t for t in re.findall(r"[^\W_]+", args.query.casefold()) if t not in _STOP
                )
            )
            if not tokens or len(tokens) > 16 or any(len(t) > 64 for t in tokens):
                return SearchOutput(
                    message="No searchable keywords were supplied.", found=False, citations=[]
                )
            parameters: list[Any] = [str(self.root)]
            condition = "d.root=? AND d.error IS NULL"
            if args.year is not None:
                condition += " AND substr(d.issue_date,1,4)=?"
                parameters.append(str(args.year))
            if args.circular_no is not None:
                condition += " AND d.circular_no=?"
                parameters.append(args.circular_no)

            def lookup(operator: str) -> list[tuple[Any, ...]]:
                expression = operator.join('"' + t + '"' for t in tokens)
                return self.db.fetch_all(
                    "SELECT d.title,d.path,d.issue_date,p.page,p.section,p.text "
                    "FROM kb_passages p JOIN kb_documents d ON p.document_id=d.id "
                    "WHERE " + condition + " AND kb_passages MATCH ? "
                    "ORDER BY d.issue_date DESC,bm25(kb_passages),d.path,p.rowid LIMIT 8",
                    (*parameters, expression),
                )

            rows = lookup(" AND ")
            found = bool(rows)
            if not rows:
                rows = lookup(" OR ")
            citations = [
                Citation(
                    doc=title,
                    file_path=str(self.root / path),
                    date=issued,
                    page=page,
                    passage=(f"Section: {section}\n\n" if section else "") + text,
                )
                for title, path, issued, page, section, text in rows
            ]
            message = (
                "Offline keyword matches; these passages are not a generated answer."
                if found
                else "No matching passages found. Closest documents are suggestions only."
            )
            if not citations:
                message = "No matching passages found in the policy library."
            if self.status().failed:
                message += " Some files could not be indexed; check library status."
            return SearchOutput(message=message, found=found, citations=citations)
        except Exception:  # noqa: BLE001
            raise LibraryError() from None
