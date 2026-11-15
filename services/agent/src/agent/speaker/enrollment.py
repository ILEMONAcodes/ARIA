"""Speaker enrollment flow management."""

from __future__ import annotations

from dataclasses import dataclass

from agent.interfaces import AudioInput
from agent.speaker.identifier import SpeakerEmbedding, SpeakerIdentifier


@dataclass
class EnrollmentConfig:
    """Configuration for enrollment."""

    duration_s: int = 30
    sample_rate: int = 16000
    frame_size: int = 512  # 32ms at 16kHz


class EnrollmentManager:
    """Manages speaker enrollment flow with 30 seconds of audio."""

    def __init__(
        self,
        identifier: SpeakerIdentifier,
        audio_input: AudioInput,
        config: EnrollmentConfig | None = None,
    ) -> None:
        self.identifier = identifier
        self.audio_input = audio_input
        self.config = config or EnrollmentConfig()
        self._enrolling = False
        self._cancelled = False

    @property
    def is_enrolling(self) -> bool:
        return self._enrolling

    async def enroll(self, profile_id: str, name: str) -> SpeakerEmbedding:
        """Enroll a new speaker with configured duration of audio."""
        if self._enrolling:
            raise RuntimeError("Enrollment already in progress")

        self._enrolling = True
        self._cancelled = False
        await self.audio_input.resume()

        frames = []
        target_frames = (self.config.duration_s * self.config.sample_rate) // self.config.frame_size
        collected = 0

        try:
            consecutive_none = 0
            while collected < target_frames and not self._cancelled:
                frame = await self.audio_input.read()
                if frame is None:
                    consecutive_none += 1
                    # If we get many consecutive None reads, the input is exhausted
                    if consecutive_none > 100:
                        break
                    # Brief pause to avoid busy waiting
                    await asyncio.sleep(0.01)
                    continue
                consecutive_none = 0
                frames.append(frame)
                collected += 1
        finally:
            await self.audio_input.pause()
            self._enrolling = False

        if self._cancelled:
            raise RuntimeError("Enrollment cancelled")

        if not frames:
            raise RuntimeError("No audio captured during enrollment")

        # Combine all frames
        audio = b"".join(frames)

        # Compute embedding
        embedding = self.identifier._compute_embedding(audio)

        # Save to store
        self.identifier.embedding_store.save(profile_id, embedding, name)

        return SpeakerEmbedding(
            profile_id=profile_id,
            embedding=embedding,
            name=name,
            enrolled_at=int(__import__("time").time()),
        )

    async def cancel_enrollment(self) -> None:
        """Cancel ongoing enrollment."""
        if self._enrolling:
            self._cancelled = True
            await self.audio_input.pause()
            self._enrolling = False


import asyncio
