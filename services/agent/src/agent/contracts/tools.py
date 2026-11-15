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


# ---------------------------------------------------------------- mail.read_thread
class MailReadThreadInput(_Base):
    type: Literal["mail.read_thread.input"] = "mail.read_thread.input"
    query: str
    max_results: int = Field(default=10, ge=1, le=50)


class MailThread(BaseModel):
    thread_id: str
    subject: str
    sender: str
    recipients: list[str]
    date: str
    preview: str
    message_count: int


class MailReadThreadOutput(_Base):
    type: Literal["mail.read_thread.output"] = "mail.read_thread.output"
    threads: list[MailThread]
    total: int


# ---------------------------------------------------------------- mail.draft_reply
class MailDraftReplyInput(_Base):
    type: Literal["mail.draft_reply.input"] = "mail.draft_reply.input"
    thread_id: str
    instruction: str
    tone: Literal["formal", "friendly", "direct"] = "formal"


class MailDraftReplyOutput(_Base):
    type: Literal["mail.draft_reply.output"] = "mail.draft_reply.output"
    draft_id: str
    to: list[str]
    subject: str
    body: str
    signature: str


# ---------------------------------------------------------------- mail.queue_send
class MailQueueSendInput(_Base):
    type: Literal["mail.queue_send.input"] = "mail.queue_send.input"
    draft_id: str
    confirm: bool = False


class MailQueueSendOutput(_Base):
    type: Literal["mail.queue_send.output"] = "mail.queue_send.output"
    outbox_id: str
    status: Literal["queued", "sending", "sent", "retrying", "failed"]
    message: str


# ---------------------------------------------------------------- mail.attach
class MailAttachInput(_Base):
    type: Literal["mail.attach.input"] = "mail.attach.input"
    draft_id: str
    description: str


class MailAttachOutput(_Base):
    type: Literal["mail.attach.output"] = "mail.attach.output"
    attached: list[str]
    ambiguous: list[str] = []
    question: str | None = None


MailReadThreadInput.model_rebuild()
MailReadThreadOutput.model_rebuild()
MailDraftReplyInput.model_rebuild()
MailDraftReplyOutput.model_rebuild()
MailQueueSendInput.model_rebuild()
MailQueueSendOutput.model_rebuild()
MailAttachInput.model_rebuild()
MailAttachOutput.model_rebuild()


# ---------------------------------------------------------------- cal.list
class CalListInput(_Base):
    type: Literal["cal.list.input"] = "cal.list.input"
    start: str
    end: str


class CalEvent(BaseModel):
    event_id: str
    title: str
    start: str
    end: str
    ics_uid: str | None = None


class CalListOutput(_Base):
    type: Literal["cal.list.output"] = "cal.list.output"
    events: list[CalEvent]


# ---------------------------------------------------------------- cal.create
class CalCreateInput(_Base):
    type: Literal["cal.create.input"] = "cal.create.input"
    title: str
    start: str
    end: str
    description: str | None = None


class CalCreateOutput(_Base):
    type: Literal["cal.create.output"] = "cal.create.output"
    event_id: str
    conflict: bool = False
    conflict_with: list[str] = []


# ---------------------------------------------------------------- cal.move
class CalMoveInput(_Base):
    type: Literal["cal.move.input"] = "cal.move.input"
    event_id: str
    new_start: str
    new_end: str


class CalMoveOutput(_Base):
    type: Literal["cal.move.output"] = "cal.move.output"
    event_id: str
    conflict: bool = False
    conflict_with: list[str] = []


# ---------------------------------------------------------------- cal.cancel
class CalCancelInput(_Base):
    type: Literal["cal.cancel.input"] = "cal.cancel.input"
    event_id: str
    confirm: bool = False


class CalCancelOutput(_Base):
    type: Literal["cal.cancel.output"] = "cal.cancel.output"
    event_id: str
    cancelled: bool


# ---------------------------------------------------------------- files.find
class FilesFindInput(_Base):
    type: Literal["files.find.input"] = "files.find.input"
    query: str
    max_results: int = Field(default=20, ge=1, le=100)
    include_content: bool = False


class FileMatch(BaseModel):
    path: str
    name: str
    modified: str
    size: int
    snippet: str | None = None


class FilesFindOutput(_Base):
    type: Literal["files.find.output"] = "files.find.output"
    matches: list[FileMatch]


# ---------------------------------------------------------------- apps.launch
class AppsLaunchInput(_Base):
    type: Literal["apps.launch.input"] = "apps.launch.input"
    app_name: str


class AppsLaunchOutput(_Base):
    type: Literal["apps.launch.output"] = "apps.launch.output"
    launched: bool
    message: str


CalListInput.model_rebuild()
CalListOutput.model_rebuild()
CalCreateInput.model_rebuild()
CalCreateOutput.model_rebuild()
CalMoveInput.model_rebuild()
CalMoveOutput.model_rebuild()
CalCancelInput.model_rebuild()
CalCancelOutput.model_rebuild()
FilesFindInput.model_rebuild()
FilesFindOutput.model_rebuild()
AppsLaunchInput.model_rebuild()
AppsLaunchOutput.model_rebuild()
