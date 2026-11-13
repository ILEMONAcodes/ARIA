"""16 kHz mono int16 frames, bounded volatile pre-roll and endpointing."""

from __future__ import annotations

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2


def frame_duration_ms(frame: bytes) -> int:
    if len(frame) not in (640, 960):
        raise ValueError("Audio frames must be 20 or 30 ms of 16 kHz mono int16 PCM")
    return len(frame) * 1000 // BYTES_PER_SECOND


class RingBuffer:
    """At most one second of RAM; never a file or transcript."""

    def __init__(self) -> None:
        self._audio = bytearray()

    def append(self, frame: bytes) -> None:
        frame_duration_ms(frame)
        self._audio.extend(frame)
        if len(self._audio) > BYTES_PER_SECOND:
            del self._audio[: len(self._audio) - BYTES_PER_SECOND]

    def snapshot(self) -> bytes:
        return bytes(self._audio)

    def clear(self) -> None:
        self._audio.clear()


class Endpoint:
    """One activated utterance. Nothing is retained before activation here."""

    def __init__(self, silence_ms: int = 700, max_ms: int = 30000) -> None:
        if not 500 <= silence_ms <= 800 or max_ms < 1000:
            raise ValueError("Invalid endpoint limits")
        self.silence_ms = silence_ms
        self.max_ms = max_ms
        self._audio = bytearray()
        self.active = False
        self.elapsed_ms = 0
        self.silent_ms = 0
        self.speech_ms = 0

    def start(self, prefix: bytes = b"") -> None:
        if len(prefix) > BYTES_PER_SECOND or len(prefix) % 2:
            raise ValueError("Pre-roll must be at most one second of PCM")
        self.clear()
        self.active = True
        self._audio.extend(prefix)

    def feed(self, frame: bytes, speech: bool) -> bytes | None:
        duration = frame_duration_ms(frame)
        if not self.active:
            return None
        self._audio.extend(frame)
        self.elapsed_ms += duration
        self.speech_ms += duration if speech else 0
        self.silent_ms = 0 if speech else self.silent_ms + duration
        if self.elapsed_ms >= self.max_ms or (
            self.speech_ms >= 100 and self.silent_ms >= self.silence_ms
        ):
            return self.finish()
        return None

    def finish(self) -> bytes:
        audio = bytes(self._audio) if self.speech_ms >= 100 else b""
        self.clear()
        return audio

    def clear(self) -> None:
        self._audio.clear()
        self.active = False
        self.elapsed_ms = self.silent_ms = self.speech_ms = 0
