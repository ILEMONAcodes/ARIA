"""Dependency boundaries for the local agent; adapters perform all external I/O.

Component.start prepares local resources only. It must not send data to a
provider or execute user actions. Those operations require routing/approval.
Audio values are in-memory 16 kHz mono signed 16-bit PCM. No interface writes
raw audio to storage. External source text belongs in ModelRequest.data_blocks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from agent.contracts.events import SpeakerInfo
from agent.contracts.plan import Plan
from agent.interfaces.models import (
    HistoryEntry,
    KeywordResult,
    ModelRequest,
    ModelResponse,
    PurgeResult,
)
from agent.security.keys import DatabaseKeyProvider as DatabaseKeyProvider
from agent.tools.base import Tool as Tool


class Component(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...


class AudioInput(Component, Protocol):
    async def resume(self) -> None: ...

    async def pause(self) -> None: ...

    async def read(self) -> bytes | None: ...


class VoiceActivityDetector(Component, Protocol):
    def reset(self) -> None: ...

    def is_speech(self, audio: bytes) -> bool: ...


class WakeWordDetector(Component, Protocol):
    def reset(self) -> None: ...

    def detected(self, audio: bytes) -> bool: ...


class SpeechToText(Component, Protocol):
    async def transcribe(self, audio: bytes) -> str: ...

    def stream(self, audio: bytes) -> AsyncIterator[str]: ...


class SpeakerIdentifier(Component, Protocol):
    async def identify(self, audio: bytes) -> SpeakerInfo | None: ...


class Speaker(Component, Protocol):
    async def speak(self, text: str) -> None: ...

    async def stop(self) -> None: ...


class Planner(Component, Protocol):
    async def plan(self, text: str) -> Plan: ...


class KeywordMatcher(Protocol):
    def match(self, text: str) -> KeywordResult: ...


class LLMAdapter(Component, Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...


class Network(Component, Protocol):
    async def is_online(self) -> bool: ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class HistoryStore(Protocol):
    def add_transcript(self, profile_id: str, text: str, *, at: datetime) -> str: ...

    def add_activity(self, profile_id: str, text: str, tool: str, *, at: datetime) -> str: ...

    def transcripts(self, profile_id: str) -> list[HistoryEntry]: ...


class LocalStore(Protocol):
    """open must run initial retention; close must tolerate partial/failed open."""

    def open(self, *, now: datetime) -> None: ...

    @property
    def history(self) -> HistoryStore: ...

    def purge(self, *, now: datetime) -> PurgeResult: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ModuleAdapters:
    audio: AudioInput
    vad: VoiceActivityDetector
    wake_word: WakeWordDetector
    stt: SpeechToText
    speaker_id: SpeakerIdentifier
    speaker: Speaker
    planner: Planner
    llm: LLMAdapter
    network: Network

    def components(self) -> tuple[Component, ...]:
        # Prepare processing before starting capture; shutdown reverses this order.
        return (
            self.stt,
            self.speaker_id,
            self.speaker,
            self.vad,
            self.wake_word,
            self.planner,
            self.llm,
            self.network,
            self.audio,
        )
