"""Internal adapter values. These are not additions to the UI contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from agent.contracts.plan import Plan


@dataclass(frozen=True)
class KeywordResult:
    """Internal local-match outcome, never authorization to execute or call cloud."""

    kind: Literal["plan", "cancel", "clarify", "no_match", "unavailable"]
    plan: Plan | None = field(default=None, repr=False)
    question: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (self.kind == "plan") != (self.plan is not None):
            raise ValueError("Only plan outcomes carry a plan")
        if (self.kind == "clarify") != bool(self.question):
            raise ValueError("Only clarification outcomes carry a question")


@dataclass(frozen=True)
class HistoryEntry:
    id: str
    text: str = field(repr=False)
    created_at: datetime


@dataclass(frozen=True)
class PurgeResult:
    transcripts: int
    activity_entries: int


@dataclass(frozen=True)
class ModelMessage:
    role: Literal["system", "user", "assistant"]
    content: str = field(repr=False)


@dataclass(frozen=True)
class DataBlock:
    id: str
    label: str
    text: str = field(repr=False)


@dataclass(frozen=True)
class ModelRequest:
    task: Literal["answer", "summarise", "draft", "reply", "plan"]
    messages: tuple[ModelMessage, ...] = field(repr=False)
    data_blocks: tuple[DataBlock, ...] = field(default=(), repr=False)
    max_tokens: int = 600
    temperature: float = 0.2
    reasoning: bool = False
    json_schema: dict[str, Any] | None = field(default=None, repr=False)
    client_request_id: str | None = None


@dataclass(frozen=True)
class ModelResponse:
    text: str = field(repr=False)
    input_tokens: int = 0
    output_tokens: int = 0
