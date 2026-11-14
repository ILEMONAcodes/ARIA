"""Bounded document extraction behind a swappable reader interface."""

from __future__ import annotations

import io
import logging
import zipfile
from dataclasses import dataclass
from typing import Protocol

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
MAX_TEXT = 2_000_000

# Third-party parser warnings may quote document data. Keep them out of diagnostics.
_pdf_log = logging.getLogger("pypdf")
_pdf_log.addHandler(logging.NullHandler())
_pdf_log.propagate = False


class LibraryError(ValueError):
    def __init__(self) -> None:
        super().__init__("Policy library could not be read; check its files and manifest.")


@dataclass(frozen=True)
class Passage:
    text: str
    page: int | None = None
    section: str | None = None


class DocumentReader(Protocol):
    def read(self, content: bytes, suffix: str) -> list[Passage]: ...


def _table_text(table: Table, depth: int = 0) -> list[str]:
    if depth > 16:
        raise LibraryError()
    lines = []
    for row in table.rows:
        for cell in row.cells:
            for item in cell.iter_inner_content():
                if isinstance(item, Paragraph):
                    lines.append(item.text)
                else:
                    lines.extend(_table_text(item, depth + 1))
    return lines


def chunks(text: str, page: int | None, section: str | None) -> list[Passage]:
    # Model-free word windows, not a claim about any model's tokenizer.
    if len(text) > MAX_TEXT:
        raise LibraryError()
    words = text.split()
    result = []
    for start in range(0, len(words), 350):
        result.append(Passage(" ".join(words[start : start + 400]), page, section))
        if start + 400 >= len(words):
            break
    return result


class LocalDocumentReader:
    def read(self, content: bytes, suffix: str) -> list[Passage]:
        try:
            if len(content) > MAX_BYTES:
                raise LibraryError()
            blocks: list[Passage] = []
            if suffix == ".txt":
                section = None
                lines: list[str] = []
                for line in content.decode("utf-8-sig").splitlines():
                    if line.startswith("# "):
                        blocks.extend(chunks("\n".join(lines), None, section))
                        section, lines = line[2:].strip(), []
                    else:
                        lines.append(line)
                blocks.extend(chunks("\n".join(lines), None, section))
            elif suffix == ".pdf":
                reader = PdfReader(io.BytesIO(content), strict=True)
                if reader.is_encrypted or not 0 < len(reader.pages) <= 256:
                    raise LibraryError()
                for number, page in enumerate(reader.pages, 1):
                    stream = page.get_contents()
                    if stream is not None and len(stream.get_data()) > 8 * MAX_BYTES:
                        raise LibraryError()
                    text = page.extract_text() or ""
                    # A scanned/blank page is not silently indexed as complete.
                    if not text.strip():
                        raise LibraryError()
                    blocks.extend(chunks(text, number, None))
            elif suffix == ".docx":
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    if (
                        len(archive.infolist()) > 2000
                        or sum(i.file_size for i in archive.infolist()) > 32 * MAX_BYTES
                    ):
                        raise LibraryError()
                document = Document(io.BytesIO(content))
                section = None
                lines = []
                for item in document.iter_inner_content():
                    if isinstance(item, Paragraph):
                        if item.style is not None and item.style.name.startswith("Heading"):
                            blocks.extend(chunks("\n".join(lines), None, section))
                            section, lines = item.text, []
                        else:
                            lines.append(item.text)
                    elif isinstance(item, Table):
                        lines.extend(_table_text(item))
                blocks.extend(chunks("\n".join(lines), None, section))
            else:
                raise LibraryError()
            if not blocks or sum(len(p.text) for p in blocks) > MAX_TEXT or len(blocks) > 5000:
                raise LibraryError()
            return blocks
        except Exception:  # noqa: BLE001 - parser errors may contain source text
            raise LibraryError() from None
