"""Events exchanged between the UI and the agent.

This module is the source of truth for docs/API_CONTRACT.md.
Adding a field is fine. Renaming or removing one needs a version bump
and a note in docs/DECISIONS.md.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field

CONTRACT_VERSION = 1


class _Base(BaseModel):
    v: int = CONTRACT_VERSION


# ---------------------------------------------------------------- agent -> UI
class SpeakerInfo(BaseModel):
    id: str
    name: str
    confidence: float = Field(ge=0, le=1)


class Citation(BaseModel):
    doc: str
    page: int | None = None
    date: str | None = None
    passage: str
    file_path: str


class ConfirmDetails(BaseModel):
    recipients: list[str] = []
    subject: str | None = None
    attachments: list[str] = []


class OutboxItem(BaseModel):
    id: str
    status: Literal["queued", "sending", "sent", "retrying", "failed"]
    to: list[str]
    subject: str
    attempts: int = 0


class Status(_Base):
    type: Literal["status"] = "status"
    state: Literal["idle", "listening", "thinking", "working"]
    online: bool
    profile: Literal["hosted", "local"]


class TranscriptPartial(_Base):
    type: Literal["transcript.partial"] = "transcript.partial"
    text: str


class TranscriptFinal(_Base):
    type: Literal["transcript.final"] = "transcript.final"
    text: str
    speaker: SpeakerInfo | None = None


class SpeakerConfirmRequest(_Base):
    type: Literal["speaker.confirm_request"] = "speaker.confirm_request"
    name: str


class PlanPreview(_Base):
    type: Literal["plan.preview"] = "plan.preview"
    task_id: str
    summary: str


class CloudApprovalRequest(_Base):
    type: Literal["cloud.approval_request"] = "cloud.approval_request"
    approval_id: str
    payload_preview: str


class ConfirmRequest(_Base):
    type: Literal["confirm.request"] = "confirm.request"
    confirm_id: str
    task_id: str
    risk: Literal["local_write", "external_send", "destructive"]
    dry_run_text: str
    details: ConfirmDetails = ConfirmDetails()
    needs_click: bool = True


class ReplyText(_Base):
    type: Literal["reply.text"] = "reply.text"
    task_id: str
    text: str
    spoken: bool = True


class ResultAnswer(_Base):
    type: Literal["result.answer"] = "result.answer"
    text: str
    citations: list[Citation] = []


class ResultDocument(_Base):
    type: Literal["result.document"] = "result.document"
    path: str
    title: str


class OutboxUpdate(_Base):
    type: Literal["outbox.update"] = "outbox.update"
    items: list[OutboxItem]


class ActivityEntry(_Base):
    type: Literal["activity.entry"] = "activity.entry"
    id: str
    ts: str
    text: str
    undoable: bool = False


class ErrorEvent(_Base):
    type: Literal["error"] = "error"
    code: str
    message: str


AgentEvent = Annotated[
    Status
    | TranscriptPartial
    | TranscriptFinal
    | SpeakerConfirmRequest
    | PlanPreview
    | CloudApprovalRequest
    | ConfirmRequest
    | ReplyText
    | ResultAnswer
    | ResultDocument
    | OutboxUpdate
    | ActivityEntry
    | ErrorEvent,
    Field(discriminator="type"),
]


# ---------------------------------------------------------------- UI -> agent
class PttStart(_Base):
    type: Literal["ptt.start"] = "ptt.start"


class PttStop(_Base):
    type: Literal["ptt.stop"] = "ptt.stop"


class TextInput(_Base):
    type: Literal["text.input"] = "text.input"
    text: str


class ConfirmResponse(_Base):
    type: Literal["confirm.response"] = "confirm.response"
    confirm_id: str
    decision: Literal["yes", "no"]
    via: Literal["click", "key"]


class ApprovalResponse(_Base):
    type: Literal["approval.response"] = "approval.response"
    approval_id: str
    decision: Literal["yes", "no"]


class SpeakerConfirmResponse(_Base):
    type: Literal["speaker.confirm_response"] = "speaker.confirm_response"
    accept: bool


class TaskCancel(_Base):
    type: Literal["task.cancel"] = "task.cancel"
    task_id: str


class TtsStop(_Base):
    type: Literal["tts.stop"] = "tts.stop"


class ActivityUndo(_Base):
    type: Literal["activity.undo"] = "activity.undo"
    id: str


class SourceOpen(_Base):
    type: Literal["source.open"] = "source.open"
    file_path: str
    page: int | None = None


UIEvent = Annotated[
    PttStart
    | PttStop
    | TextInput
    | ConfirmResponse
    | ApprovalResponse
    | SpeakerConfirmResponse
    | TaskCancel
    | TtsStop
    | ActivityUndo
    | SourceOpen,
    Field(discriminator="type"),
]
