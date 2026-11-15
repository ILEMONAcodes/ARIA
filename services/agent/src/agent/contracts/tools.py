"""Tool input/output contracts for docs.draft, docs.report, docs.summarise.

This module is the source of truth for tool schemas in docs/API_CONTRACT.md.
Adding a field is fine. Renaming or removing one needs a version bump
and a note in docs/DECISIONS.md.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = 1


class _Base(BaseModel):
    v: int = CONTRACT_VERSION


# ---------------------------------------------------------------- docs.draft
class DocDraftInput(_Base):
    type: Literal["docs.draft.input"] = "docs.draft.input"
    brief: str
    tone: Literal["formal", "direct", "concise"] = "formal"
    max_words: int = Field(default=300, ge=50, le=1000)
    template_name: str | None = None


class DocDraftMissing(BaseModel):
    field: str
    question: str


class DocDraftOutput(_Base):
    type: Literal["docs.draft.output"] = "docs.draft.output"
    subject: str
    body_paragraphs: list[str]
    missing: list[DocDraftMissing] = []
    saved_path: str | None = None


# ---------------------------------------------------------------- docs.report
class DocReportOutlineInput(_Base):
    type: Literal["docs.report.outline.input"] = "docs.report.outline.input"
    brief: str
    sections_hint: int | None = Field(default=None, ge=3, le=12)


class DocReportSection(BaseModel):
    heading: str
    purpose: str


class DocReportOutlineOutput(_Base):
    type: Literal["docs.report.outline.output"] = "docs.report.outline.output"
    title: str
    sections: list[DocReportSection]


class DocReportSectionInput(_Base):
    type: Literal["docs.report.section.input"] = "docs.report.section.input"
    title: str
    heading: str
    purpose: str
    brief: str
    citations: list[DocReportCitation] = []


class DocReportCitation(BaseModel):
    doc: str
    page: int | None = None
    date: str | None = None
    passage: str
    file_path: str


class DocReportSectionOutput(_Base):
    type: Literal["docs.report.section.output"] = "docs.report.section.output"
    heading: str
    content: str
    citations: list[DocReportCitation] = []


class DocReportAssembleInput(_Base):
    type: Literal["docs.report.assemble.input"] = "docs.report.assemble.input"
    title: str
    sections: list[DocReportSectionOutput]
    template_name: str | None = None


class DocReportAssembleOutput(_Base):
    type: Literal["docs.report.assemble.output"] = "docs.report.assemble.output"
    saved_path: str


# ---------------------------------------------------------------- docs.summarise
class DocSummariseInput(_Base):
    type: Literal["docs.summarise.input"] = "docs.summarise.input"
    text: str
    source_label: str
    mode: Literal["one_line", "five_bullets", "one_page"]
    purpose: str | None = None
    page_references: list[PageRef] = []


class PageRef(BaseModel):
    page: int | None
    heading: str | None
    text: str


class DocSummariseOutput(_Base):
    type: Literal["docs.summarise.output"] = "docs.summarise.output"
    summary: str
    citations: list[DocReportCitation] = []
    faithfulness_flags: list[str] = []


DocDraftInput.model_rebuild()
DocDraftOutput.model_rebuild()
DocReportOutlineInput.model_rebuild()
DocReportOutlineOutput.model_rebuild()
DocReportSectionInput.model_rebuild()
DocReportSectionOutput.model_rebuild()
DocReportAssembleInput.model_rebuild()
DocReportAssembleOutput.model_rebuild()
DocSummariseInput.model_rebuild()
DocSummariseOutput.model_rebuild()
