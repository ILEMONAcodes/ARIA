"""Explicit test/development adapters; never selected as a production fallback."""

from agent.fakes.components import (
    FakeAudioInput,
    FakeLLMAdapter,
    FakeNetwork,
    FakePlanner,
    FakeSpeaker,
    FakeSpeakerIdentifier,
    FakeSpeechToText,
    FakeVAD,
    FakeWakeWord,
)
from agent.fakes.storage import FakeClock, FakeDatabaseKeys, FakeStore
from agent.fakes.tools import FakeTool
from agent.interfaces import ModuleAdapters

__all__ = [
    "FakeAudioInput",
    "FakeClock",
    "FakeDatabaseKeys",
    "FakeLLMAdapter",
    "FakeNetwork",
    "FakePlanner",
    "FakeSpeaker",
    "FakeSpeakerIdentifier",
    "FakeSpeechToText",
    "FakeStore",
    "FakeTool",
    "FakeVAD",
    "FakeWakeWord",
    "fake_adapters",
]


def fake_adapters() -> ModuleAdapters:
    return ModuleAdapters(
        audio=FakeAudioInput(),
        vad=FakeVAD(),
        wake_word=FakeWakeWord(),
        stt=FakeSpeechToText(),
        speaker_id=FakeSpeakerIdentifier(),
        speaker=FakeSpeaker(),
        planner=FakePlanner(),
        llm=FakeLLMAdapter(),
        network=FakeNetwork(),
    )
