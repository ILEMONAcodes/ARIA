"""Tests for speaker identification and enrollment."""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from agent.speaker.enrollment import EnrollmentManager
from agent.speaker.identifier import (
    InMemoryEmbeddingStore,
    SpeakerIdentifier,
    _FakeECAPAModel,
)


class FakeAudioInput:
    """Fake audio input for testing enrollment."""

    def __init__(self, frames: list[bytes], frame_delay: float = 0.001) -> None:
        self._frames = frames
        self._index = 0
        self._paused = True
        self._frame_delay = frame_delay

    async def resume(self) -> None:
        self._paused = False

    async def pause(self) -> None:
        self._paused = True

    async def read(self) -> bytes | None:
        if self._paused or self._index >= len(self._frames):
            return None
        await asyncio.sleep(self._frame_delay)
        frame = self._frames[self._index]
        self._index += 1
        return frame


class TestInMemoryEmbeddingStore:
    def test_save_and_load(self) -> None:
        store = InMemoryEmbeddingStore()
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)

        store.save("profile_1", embedding, "Alice")
        loaded = store.load("profile_1")

        assert loaded is not None
        assert loaded.profile_id == "profile_1"
        assert loaded.name == "Alice"
        np.testing.assert_array_almost_equal(loaded.embedding, embedding)

    def test_delete(self) -> None:
        store = InMemoryEmbeddingStore()
        embedding = np.random.randn(192).astype(np.float32)
        embedding = embedding / np.linalg.norm(embedding)

        store.save("profile_1", embedding, "Alice")
        assert store.delete("profile_1") is True
        assert store.load("profile_1") is None
        assert store.delete("profile_1") is False

    def test_list_all(self) -> None:
        store = InMemoryEmbeddingStore()
        emb1 = np.random.randn(192).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)
        emb2 = np.random.randn(192).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)

        store.save("profile_1", emb1, "Alice")
        store.save("profile_2", emb2, "Bob")

        all_speakers = store.list_all()
        assert len(all_speakers) == 2
        names = {s.name for s in all_speakers}
        assert names == {"Alice", "Bob"}


class TestSpeakerIdentifier:
    @pytest.fixture
    def store(self) -> InMemoryEmbeddingStore:
        return InMemoryEmbeddingStore()

    @pytest.fixture
    def fake_model(self) -> _FakeECAPAModel:
        return _FakeECAPAModel()

    @pytest.fixture
    def identifier(
        self, store: InMemoryEmbeddingStore, fake_model: _FakeECAPAModel
    ) -> SpeakerIdentifier:
        return SpeakerIdentifier(embedding_store=store, model=fake_model)

    @pytest.mark.asyncio
    async def test_identify_no_enrolled_speakers(self, identifier: SpeakerIdentifier) -> None:
        await identifier.start()
        audio = b"test audio"
        result = await identifier.identify(audio)
        assert result is None
        await identifier.close()

    @pytest.mark.asyncio
    async def test_identify_single_speaker(
        self, identifier: SpeakerIdentifier, fake_model: _FakeECAPAModel
    ) -> None:
        # Create a specific embedding for the test
        test_embedding = np.random.randn(192).astype(np.float32)
        test_embedding = test_embedding / np.linalg.norm(test_embedding)

        # Configure fake model to return this embedding
        fake_model.responses[b"test audio"] = test_embedding

        # Enroll a speaker with the same embedding
        identifier.embedding_store.save("profile_1", test_embedding, "Alice")

        await identifier.start()
        result = await identifier.identify(b"test audio")

        assert result is not None
        assert result.id == "profile_1"
        assert result.name == "Alice"
        assert result.confidence > 0.9  # Should be very high for exact match
        await identifier.close()

    @pytest.mark.asyncio
    async def test_identify_best_match(
        self, identifier: SpeakerIdentifier, fake_model: _FakeECAPAModel
    ) -> None:
        # Create two different embeddings
        emb1 = np.random.randn(192).astype(np.float32)
        emb1 = emb1 / np.linalg.norm(emb1)

        emb2 = np.random.randn(192).astype(np.float32)
        emb2 = emb2 / np.linalg.norm(emb2)

        # Make them somewhat similar but distinct
        emb2 = (emb1 + emb2) / 2
        emb2 = emb2 / np.linalg.norm(emb2)

        fake_model.responses[b"test audio"] = emb1

        identifier.embedding_store.save("profile_1", emb1, "Alice")
        identifier.embedding_store.save("profile_2", emb2, "Bob")

        await identifier.start()
        result = await identifier.identify(b"test audio")

        assert result is not None
        assert result.id == "profile_1"
        assert result.name == "Alice"
        await identifier.close()

    def test_needs_confirmation(self, identifier: SpeakerIdentifier) -> None:
        # Above threshold - no confirmation needed
        assert identifier.needs_confirmation(0.8) is False
        assert identifier.needs_confirmation(1.0) is False

        # In low-confidence zone - needs confirmation
        assert identifier.needs_confirmation(0.7) is True
        assert identifier.needs_confirmation(0.65) is True
        assert identifier.needs_confirmation(0.6) is True

        # Below low-confidence threshold - rejected
        assert identifier.needs_confirmation(0.5) is False

    def test_is_rejected(self, identifier: SpeakerIdentifier) -> None:
        assert identifier.is_rejected(0.8) is False
        assert identifier.is_rejected(0.7) is False
        assert identifier.is_rejected(0.6) is False
        assert identifier.is_rejected(0.59) is True
        assert identifier.is_rejected(0.0) is True

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, identifier: SpeakerIdentifier) -> None:
        await identifier.start()
        # Should work after start
        result = await identifier.identify(b"test")
        assert result is None
        await identifier.close()
        # Should fail after close
        with pytest.raises(RuntimeError):
            await identifier.identify(b"test")


class TestEnrollmentManager:
    @pytest.mark.asyncio
    async def test_enroll_new_speaker(self) -> None:
        store = InMemoryEmbeddingStore()
        model = _FakeECAPAModel()
        identifier = SpeakerIdentifier(embedding_store=store, model=model)

        # Create 30 seconds worth of frames (at 512 bytes/frame, 16kHz)
        # 30 * 16000 / 512 = 937.5 frames
        frames = [b"x" * 512 for _ in range(938)]
        audio_input = FakeAudioInput(frames)

        enrollment = EnrollmentManager(identifier, audio_input)
        embedding = await enrollment.enroll("profile_1", "Alice")

        assert embedding.profile_id == "profile_1"
        assert embedding.name == "Alice"
        assert embedding.embedding.shape == (192,)

        # Verify it's saved in store
        loaded = store.load("profile_1")
        assert loaded is not None
        assert loaded.name == "Alice"
        np.testing.assert_array_almost_equal(loaded.embedding, embedding.embedding)

        await identifier.close()

    @pytest.mark.asyncio
    async def test_enroll_cancel(self) -> None:
        store = InMemoryEmbeddingStore()
        model = _FakeECAPAModel()
        identifier = SpeakerIdentifier(embedding_store=store, model=model)

        # Use many frames with slower delay so we have time to cancel
        frames = [b"x" * 512 for _ in range(2000)]
        audio_input = FakeAudioInput(frames, frame_delay=0.01)  # 10ms per frame

        enrollment = EnrollmentManager(identifier, audio_input)

        # Start enrollment in background
        enroll_task = asyncio.create_task(enrollment.enroll("profile_1", "Alice"))
        # Wait for some frames to be collected (about 5 frames at 10ms each)
        await asyncio.sleep(0.06)
        print(
            f"After sleep, _cancelled={enrollment._cancelled}, _enrolling={enrollment._enrolling}"
        )
        # Cancel it
        await enrollment.cancel_enrollment()
        print(
            f"After cancel, _cancelled={enrollment._cancelled}, _enrolling={enrollment._enrolling}"
        )

        # Should complete without saving
        try:
            result = await enroll_task
            print(f"Task completed with result: {result}")
            pytest.fail("Expected RuntimeError but task completed")
        except RuntimeError as e:
            print(f"Got expected error: {e}")
            assert "Enrollment cancelled" in str(e)

        assert store.load("profile_1") is None

    @pytest.mark.asyncio
    async def test_enroll_empty_audio(self) -> None:
        store = InMemoryEmbeddingStore()
        model = _FakeECAPAModel()
        identifier = SpeakerIdentifier(embedding_store=store, model=model)

        audio_input = FakeAudioInput([])

        enrollment = EnrollmentManager(identifier, audio_input)

        with pytest.raises(RuntimeError, match="No audio captured"):
            await enrollment.enroll("profile_1", "Alice")


class TestFakeECAPAModel:
    def test_default_embedding(self) -> None:
        model = _FakeECAPAModel()
        emb = model.compute_embedding(b"any audio")
        assert emb.shape == (192,)
        # Should be normalized
        assert abs(np.linalg.norm(emb) - 1.0) < 1e-5

    def test_custom_response(self) -> None:
        model = _FakeECAPAModel()
        custom_emb = np.random.randn(192).astype(np.float32)
        custom_emb = custom_emb / np.linalg.norm(custom_emb)
        model.responses[b"specific audio"] = custom_emb

        result = model.compute_embedding(b"specific audio")
        np.testing.assert_array_almost_equal(result, custom_emb)

    def test_different_audio_returns_default(self) -> None:
        model = _FakeECAPAModel()
        emb1 = model.compute_embedding(b"audio 1")
        emb2 = model.compute_embedding(b"audio 2")
        # Both should be the default embedding
        np.testing.assert_array_almost_equal(emb1, emb2)
