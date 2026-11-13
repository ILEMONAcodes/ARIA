"""Exercise the real controller with in-memory PCM and deterministic speech."""

import asyncio
from contextlib import asynccontextmanager

from agent.audio.pipeline import VoiceLoop
from agent.contracts.events import PttStart, PttStop, TaskCancel, TtsStop
from agent.fakes.components import (
    FakeAudioInput,
    FakeSpeaker,
    FakeSpeechToText,
    FakeVAD,
    FakeWakeWord,
)
from agent.mock.scenarios import load_scenario

FRAME = bytes(640)


class LiveAudio(FakeAudioInput):
    def __init__(self):
        super().__init__()
        self.frames = asyncio.Queue()

    async def read(self):
        return await self.frames.get()

    async def pause(self):
        await super().pause()
        while not self.frames.empty():
            self.frames.get_nowait()


class HeldSpeaker(FakeSpeaker):
    def __init__(self):
        super().__init__()
        self.playing = asyncio.Event()
        self.release = asyncio.Event()

    async def speak(self, text):
        await super().speak(text)
        self.playing.set()
        await self.release.wait()

    async def stop(self):
        await super().stop()
        if self.playing.is_set():
            self.release.set()


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0)


@asynccontextmanager
async def running(*, wake=None, stt=None, speaker=None):
    audio, vad = LiveAudio(), FakeVAD(speech=True)
    stt = stt or FakeSpeechToText("Open the policy folder.")
    speaker = speaker or FakeSpeaker()
    events = []

    async def emit(event):
        events.append(event.model_dump(exclude_none=True))

    components = [audio, vad, stt, speaker] + ([wake] if wake else [])
    for component in components:
        await component.start()
    loop = VoiceLoop(audio, vad, stt, speaker, emit, wake=wake)
    await loop.start()
    try:
        yield loop, audio, vad, stt, speaker, events
    finally:
        await loop.close()
        for component in reversed(components):
            await component.close()


async def feed(audio, loop, count=10):
    for _ in range(count):
        audio.frames.put_nowait(FRAME)
    await until(lambda: loop.endpoint.speech_ms >= count * 20)


def test_push_to_talk_feeds_pipeline_from_vad_stage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    async def scenario():
        async with running() as (loop, audio, _, _, speaker, events):
            assert not audio.capturing
            await loop.handle(PttStart())
            await feed(audio, loop)
            await loop.handle(PttStop())
            await until(lambda: events[-1].get("state") == "idle")
            assert speaker.spoken == ["Open the policy folder."]
            assert [e["type"] for e in events] == [
                "status",
                "status",
                "status",
                "transcript.partial",
                "transcript.final",
                "status",
                "reply.text",
                "status",
                "activity.entry",
                "status",
            ]
            assert all(e["online"] is False for e in events if e["type"] == "status")
            assert not audio.capturing
            assert not loop.endpoint.active
            expected = [
                step["send"] for step in load_scenario("voice_echo")["steps"] if "send" in step
            ]
            for actual, fixture in zip(events, expected, strict=True):
                # Runtime UUIDs/timestamps vary; compare every remaining wire field.
                dynamic = {"id", "task_id", "ts"}
                assert {k: v for k, v in actual.items() if k not in dynamic} == {
                    k: v for k, v in fixture.items() if k not in dynamic
                }
        assert list(tmp_path.iterdir()) == []

    asyncio.run(scenario())


def test_barge_in_stop_pauses_playback_and_cancels_task():
    async def scenario():
        speaker = HeldSpeaker()
        async with running(speaker=speaker) as (loop, audio, vad, stt, _, events):
            await loop.handle(PttStart())
            await feed(audio, loop)
            await loop.handle(PttStop())
            await speaker.playing.wait()
            stt.text = "Stop!"
            await feed(audio, loop)
            vad.speech = False
            for _ in range(35):
                audio.frames.put_nowait(FRAME)
            await until(lambda: events[-1].get("state") == "idle")
            assert speaker.stopped >= 2
            assert len(speaker.spoken) == 1
            assert not any(e["type"] == "transcript.final" and e["text"] == "Stop!" for e in events)
            assert loop.task_id is None

    asyncio.run(scenario())


def test_cancel_during_stt_suppresses_late_transcript_and_reply():
    class SlowSTT(FakeSpeechToText):
        async def stream(self, audio):
            started.set()
            await asyncio.Event().wait()
            yield "must not appear"

    async def scenario():
        nonlocal started
        started = asyncio.Event()
        async with running(stt=SlowSTT()) as (loop, audio, _, _, speaker, events):
            await loop.handle(PttStart())
            await feed(audio, loop)
            await loop.handle(PttStop())
            await started.wait()
            await loop.handle(TaskCancel(task_id="unrelated"))
            assert loop.task_id is not None
            await loop.handle(TaskCancel(task_id=loop.task_id))
            assert events[-1]["state"] == "idle"
            assert speaker.spoken == []
            assert not any(e["type"].startswith("transcript") for e in events)
            assert not audio.capturing

    started = None
    asyncio.run(scenario())


def test_ui_stop_cancels_capture_and_disposes_utterance():
    async def scenario():
        async with running() as (loop, audio, _, _, speaker, events):
            await loop.handle(PttStart())
            await feed(audio, loop)
            await loop.handle(TtsStop())
            await loop.handle(PttStop())
            assert speaker.spoken == []
            assert events[-1]["state"] == "idle"
            assert not audio.capturing
            assert loop.endpoint.finish() == b""

    asyncio.run(scenario())


def test_silence_endpoint_and_silent_ptt_do_not_hallucinate():
    async def scenario():
        async with running() as (loop, audio, vad, _, speaker, events):
            await loop.handle(PttStart())
            await loop.handle(PttStop())
            assert speaker.spoken == []
            await loop.handle(PttStart())
            await feed(audio, loop)
            vad.speech = False
            for _ in range(35):
                audio.frames.put_nowait(FRAME)
            await until(lambda: events[-1].get("state") == "idle")
            assert speaker.spoken == ["Open the policy folder."]

    asyncio.run(scenario())


def test_wake_does_not_transcribe_until_activation_and_keeps_preroll():
    class RecordingSTT(FakeSpeechToText):
        async def stream(self, audio):
            self.received = audio
            yield self.text

    async def scenario():
        wake = FakeWakeWord()
        stt = RecordingSTT()
        async with running(wake=wake, stt=stt) as (loop, audio, _, _, speaker, events):
            audio.frames.put_nowait(FRAME)
            await until(lambda: len(loop.ring.snapshot()) == 640)
            assert not any(e["type"].startswith("transcript") for e in events)
            wake.match = True
            audio.frames.put_nowait(FRAME)
            await until(lambda: loop.endpoint.active)
            wake.match = False
            await feed(audio, loop)
            await loop.handle(PttStop())
            await until(lambda: len(speaker.spoken) == 1)
            assert stt.received == FRAME * 12

    asyncio.run(scenario())


def test_native_failure_reports_safe_error_and_releases_mic():
    class BrokenSTT(FakeSpeechToText):
        async def stream(self, audio):
            raise RuntimeError("secret transcript")
            yield ""  # async generator boundary

    async def scenario():
        async with running(stt=BrokenSTT()) as (loop, audio, _, _, _, events):
            await loop.handle(PttStart())
            await feed(audio, loop)
            await loop.handle(PttStop())
            await until(lambda: events[-1].get("state") == "idle")
            assert any(e["type"] == "error" for e in events)
            assert "secret transcript" not in str(events)
            assert not audio.capturing

    asyncio.run(scenario())
