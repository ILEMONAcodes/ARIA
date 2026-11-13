"""Deterministic in-memory doubles. Never capture audio or contact a provider."""

from __future__ import annotations

from collections.abc import AsyncIterator

from agent.contracts.events import SpeakerInfo
from agent.contracts.plan import Plan
from agent.interfaces.models import ModelRequest, ModelResponse


class FakeComponent:
    def __init__(self) -> None:
        self.started = 0
        self.closed = 0
        self.active = False

    async def start(self) -> None:
        self.started += 1
        self.active = True

    async def close(self) -> None:
        self.closed += 1
        self.active = False

    def require_active(self) -> None:
        if not self.active:
            raise RuntimeError("Fake component has not started")


class FakeAudioInput(FakeComponent):
    def __init__(self, frames: tuple[bytes, ...] = ()) -> None:
        super().__init__()
        self._frames = frames
        self._index = 0
        self.capturing = False

    async def resume(self) -> None:
        self.require_active()
        self.capturing = True

    async def pause(self) -> None:
        self.capturing = False

    async def start(self) -> None:
        await super().start()
        self._index = 0

    async def read(self) -> bytes | None:
        self.require_active()
        if self._index == len(self._frames):
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame


class FakeVAD(FakeComponent):
    def reset(self) -> None:
        pass

    def __init__(self, speech: bool = False) -> None:
        super().__init__()
        self.speech = speech

    def is_speech(self, audio: bytes) -> bool:
        self.require_active()
        return self.speech


class FakeWakeWord(FakeComponent):
    def reset(self) -> None:
        pass

    def __init__(self, match: bool = False) -> None:
        super().__init__()
        self.match = match

    def detected(self, audio: bytes) -> bool:
        self.require_active()
        return self.match


class FakeSpeechToText(FakeComponent):
    def __init__(self, text: str = "fictional test request") -> None:
        super().__init__()
        self.text = text

    async def transcribe(self, audio: bytes) -> str:
        self.require_active()
        return self.text

    async def stream(self, audio: bytes) -> AsyncIterator[str]:
        yield await self.transcribe(audio)


class FakeSpeakerIdentifier(FakeComponent):
    def __init__(self, result: SpeakerInfo | None = None) -> None:
        super().__init__()
        self.result = result.model_copy(deep=True) if result is not None else None

    async def identify(self, audio: bytes) -> SpeakerInfo | None:
        self.require_active()
        return self.result.model_copy(deep=True) if self.result is not None else None


class FakeSpeaker(FakeComponent):
    def __init__(self) -> None:
        super().__init__()
        self.spoken: list[str] = []
        self.stopped = 0

    async def speak(self, text: str) -> None:
        self.require_active()
        self.spoken.append(text)

    async def stop(self) -> None:
        self.require_active()
        self.stopped += 1


class FakePlanner(FakeComponent):
    def __init__(self, result: Plan | None = None) -> None:
        super().__init__()
        self.result = (
            result.model_copy(deep=True)
            if result is not None
            else Plan(intent="clarify", confidence=0, missing=["request"])
        )

    async def plan(self, text: str) -> Plan:
        self.require_active()
        return self.result.model_copy(deep=True)


class FakeLLMAdapter(FakeComponent):
    def __init__(self, text: str = "fictional test response") -> None:
        super().__init__()
        self.text = text
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.require_active()
        self.requests.append(request)
        return ModelResponse(text=self.text)


class FakeNetwork(FakeComponent):
    def __init__(self, online: bool = False) -> None:
        super().__init__()
        self.online = online

    async def is_online(self) -> bool:
        self.require_active()
        return self.online
