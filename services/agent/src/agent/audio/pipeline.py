"""Offline spoken echo only: no planner, tools, cloud, identity or persistence."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from datetime import UTC
from typing import Literal
from uuid import uuid4

from agent.audio.buffers import Endpoint, RingBuffer
from agent.contracts.events import (
    ActivityEntry,
    AgentEvent,
    ErrorEvent,
    ReplyText,
    Status,
    TranscriptFinal,
    TranscriptPartial,
    UIEvent,
)
from agent.interfaces import (
    AudioInput,
    Speaker,
    SpeechToText,
    VoiceActivityDetector,
    WakeWordDetector,
)

Emit = Callable[[AgentEvent], Awaitable[None]]


class VoiceLoop:
    def __init__(
        self,
        audio: AudioInput,
        vad: VoiceActivityDetector,
        stt: SpeechToText,
        speaker: Speaker,
        emit: Emit,
        *,
        silence_ms: int = 700,
        wake: WakeWordDetector | None = None,
        profile: Literal["hosted", "local"] = "hosted",
    ) -> None:
        self.audio, self.vad, self.stt, self.speaker = audio, vad, stt, speaker
        self.wake, self.emit, self.profile = wake, emit, profile
        self.endpoint = Endpoint(silence_ms)
        self.ring = RingBuffer()
        self._capture: asyncio.Task[None] | None = None
        self._job: asyncio.Task[None] | None = None
        self._epoch = 0
        self._closed = False
        self.task_id: str | None = None

    async def status(self, state: Literal["idle", "listening", "thinking", "working"]) -> None:
        await self.emit(Status(state=state, online=False, profile=self.profile))

    async def start(self) -> None:
        await self._idle()

    async def _idle(self) -> None:
        if self._closed:
            return
        await self.audio.pause()
        self.endpoint.clear()
        self.ring.clear()
        self.vad.reset()
        if self.wake is None:
            await self.status("idle")
        else:
            self.wake.reset()
            await self.audio.resume()
            await self.status("listening")
            self._capture = asyncio.create_task(self._capture_frames("wake"))

    async def _stop_tasks(self) -> None:
        self._epoch += 1
        tasks = [
            task
            for task in (self._capture, self._job)
            if task is not None and task is not asyncio.current_task()
        ]
        self._capture = self._job = None
        try:
            await self.speaker.stop()
        finally:
            for task in tasks:
                task.cancel()
            try:
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            finally:
                await self.audio.pause()
                self.endpoint.clear()
                self.ring.clear()
                self.task_id = None

    async def cancel(self) -> None:
        await self._stop_tasks()
        await self._idle()

    async def handle(self, message: UIEvent) -> None:
        if message.type == "ptt.start":
            await self._stop_tasks()
            self.vad.reset()
            self.endpoint.start()
            await self.audio.resume()
            await self.status("listening")
            self._capture = asyncio.create_task(self._capture_frames("utterance"))
        elif message.type == "ptt.stop":
            if self.endpoint.active and self._job is None:
                if self._capture is not None:
                    self._capture.cancel()
                    await asyncio.gather(self._capture, return_exceptions=True)
                    self._capture = None
                await self._finish(self.endpoint.finish())
        elif message.type == "tts.stop":
            await self.cancel()
        elif message.type == "task.cancel":
            if self.task_id == message.task_id:
                await self.cancel()
        else:
            await self.emit(
                ErrorEvent(code="voice_only", message="This phase supports voice echo only.")
            )

    async def _capture_frames(self, mode: Literal["wake", "utterance", "stop"]) -> None:
        try:
            while True:
                frame = await self.audio.read()
                if frame is None:
                    await asyncio.sleep(0.01)
                    continue
                if mode == "wake":
                    self.ring.append(frame)
                    if self.wake is not None and self.wake.detected(frame):
                        self.endpoint.start(self.ring.snapshot())
                        self.ring.clear()
                        mode = "utterance"
                    continue
                utterance = self.endpoint.feed(frame, self.vad.is_speech(frame))
                if utterance is None:
                    continue
                if mode == "utterance":
                    self._capture = None
                    await self._finish(utterance)
                    return
                # During playback speech is used exclusively for stop/cancel.
                text = await self.stt.transcribe(utterance) if utterance else ""
                if re.sub(r"[^a-z ]", "", text.lower()).strip() in {"stop", "cancel"}:
                    await self.cancel()
                    return
                self.endpoint.start()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - native failures must not disclose captured content
            await self._stop_tasks()
            await self.emit(
                ErrorEvent(
                    code="audio_failed", message="Voice input failed. Try push-to-talk again."
                )
            )
            # Keep the mic off on device failure; a fresh PTT explicitly retries.
            await self.status("idle")

    async def _finish(self, audio: bytes) -> None:
        await self.audio.pause()
        if not audio:
            await self._idle()
            return
        self.task_id = str(uuid4())
        await self.status("thinking")
        self._job = asyncio.create_task(self._echo(audio, self._epoch))

    async def _echo(self, audio: bytes, epoch: int) -> None:
        try:
            text = ""
            async for partial in self.stt.stream(audio):
                if epoch != self._epoch or self._closed:
                    return
                text = partial.strip()
                await self.emit(TranscriptPartial(text=text))
            audio = b""
            if epoch != self._epoch or self._closed:
                return
            if text:
                await self.emit(TranscriptFinal(text=text))
                if re.sub(r"[^a-z ]", "", text.lower()).strip() in {"stop", "cancel"}:
                    self._job = None
                    self.task_id = None
                    await self._idle()
                    return
                await self.status("working")
                await self.emit(ReplyText(task_id=self.task_id or "", text=text, spoken=True))
                # Monitor barge-in only while the speaker is active; show microphone use.
                self.endpoint.start()
                await self.audio.resume()
                await self.status("listening")
                self._capture = asyncio.create_task(self._capture_frames("stop"))
                await self.speaker.speak(text)
                if self._capture is not None:
                    capture = self._capture
                    self._capture = None
                    capture.cancel()
                    await asyncio.gather(capture, return_exceptions=True)
                from datetime import datetime

                await self.emit(
                    ActivityEntry(
                        id=str(uuid4()),
                        ts=datetime.now(UTC).isoformat(),
                        text="Voice echo completed.",
                        undoable=False,
                    )
                )
            self._job = None
            self.task_id = None
            await self._idle()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - native failures must not disclose speech text
            await self._stop_tasks()
            await self.emit(
                ErrorEvent(code="speech_failed", message="Local speech failed. Try again.")
            )
            await self.status("idle")

    async def close(self) -> None:
        self._closed = True
        await self._stop_tasks()
