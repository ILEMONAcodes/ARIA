"""Speaker identification using ECAPA-TDNN embeddings."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from agent.contracts.events import SpeakerInfo
from agent.interfaces import SpeakerIdentifier as SpeakerIdentifierInterface


@dataclass
class SpeakerEmbedding:
    """Speaker embedding with metadata."""

    profile_id: str
    embedding: np.ndarray
    name: str
    enrolled_at: int  # unix timestamp


class EmbeddingStore(Protocol):
    """Protocol for embedding storage."""

    def save(self, profile_id: str, embedding: np.ndarray, name: str) -> None: ...
    def load(self, profile_id: str) -> SpeakerEmbedding | None: ...
    def delete(self, profile_id: str) -> bool: ...
    def list_all(self) -> list[SpeakerEmbedding]: ...


class InMemoryEmbeddingStore:
    """In-memory embedding store for tests."""

    def __init__(self) -> None:
        self._embeddings: dict[str, SpeakerEmbedding] = {}

    def save(self, profile_id: str, embedding: np.ndarray, name: str) -> None:
        self._embeddings[profile_id] = SpeakerEmbedding(
            profile_id=profile_id,
            embedding=embedding.copy(),
            name=name,
            enrolled_at=int(__import__("time").time()),
        )

    def load(self, profile_id: str) -> SpeakerEmbedding | None:
        return self._embeddings.get(profile_id)

    def delete(self, profile_id: str) -> bool:
        if profile_id in self._embeddings:
            del self._embeddings[profile_id]
            return True
        return False

    def list_all(self) -> list[SpeakerEmbedding]:
        return list(self._embeddings.values())


class SQLiteEmbeddingStore:
    """SQLite embedding store using the profiles table."""

    def __init__(self, db: Any) -> None:
        self._db = db

    def save(self, profile_id: str, embedding: np.ndarray, name: str) -> None:
        import time

        self._db._connection.execute(
            """INSERT OR REPLACE INTO profiles (id, name, voice_embedding, settings_json, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (profile_id, name, embedding.tobytes(), json.dumps({}), int(time.time())),
        )

    def load(self, profile_id: str) -> SpeakerEmbedding | None:
        row = self._db._connection.execute(
            "SELECT id, name, voice_embedding, created_at FROM profiles WHERE id = ?",
            (profile_id,),
        ).fetchone()
        if row and row[2]:
            embedding = np.frombuffer(row[2], dtype=np.float32)
            return SpeakerEmbedding(
                profile_id=row[0],
                embedding=embedding,
                name=row[1],
                enrolled_at=row[3],
            )
        return None

    def delete(self, profile_id: str) -> bool:
        cursor = self._db._connection.execute("DELETE FROM profiles WHERE id = ?", (profile_id,))
        return bool(cursor.rowcount > 0)

    def list_all(self) -> list[SpeakerEmbedding]:
        rows = self._db._connection.execute(
            "SELECT id, name, voice_embedding, created_at FROM profiles WHERE voice_embedding IS NOT NULL"
        ).fetchall()
        result = []
        for row in rows:
            if row[2]:
                embedding = np.frombuffer(row[2], dtype=np.float32)
                result.append(
                    SpeakerEmbedding(
                        profile_id=row[0],
                        embedding=embedding,
                        name=row[1],
                        enrolled_at=row[3],
                    )
                )
        return result


class SpeakerIdentifier(SpeakerIdentifierInterface):
    """Speaker identification using ECAPA-TDNN embeddings with cosine similarity."""

    EMBEDDING_DIM = 192  # ECAPA-TDNN output dimension
    CONFIDENCE_THRESHOLD = 0.75  # Minimum cosine similarity for positive match
    LOW_CONFIDENCE_THRESHOLD = 0.60  # Below this, ask for confirmation

    def __init__(
        self,
        embedding_store: EmbeddingStore,
        model: Any | None = None,
    ) -> None:
        self.embedding_store = embedding_store
        self.model = model or _FakeECAPAModel()
        self._active = False

    async def start(self) -> None:
        self._active = True

    async def close(self) -> None:
        self._active = False

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("SpeakerIdentifier has not started")

    def _compute_embedding(self, audio: bytes) -> np.ndarray:
        """Compute embedding from audio. Returns normalized vector."""
        return self.model.compute_embedding(audio)

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two normalized vectors."""
        return float(np.dot(a, b))

    async def identify(self, audio: bytes) -> SpeakerInfo | None:
        self._require_active()

        # Compute embedding from input audio
        embedding = self._compute_embedding(audio)

        # Get all enrolled speakers
        enrolled = self.embedding_store.list_all()
        if not enrolled:
            return None

        # Find best match
        best_match = None
        best_score = -1.0

        for speaker in enrolled:
            score = self._cosine_similarity(embedding, speaker.embedding)
            if score > best_score:
                best_score = score
                best_match = speaker

        if best_match is None:
            return None

        # Return SpeakerInfo with confidence
        confidence = max(0.0, min(1.0, (best_score + 1) / 2))  # Map [-1,1] to [0,1]

        return SpeakerInfo(
            id=best_match.profile_id,
            name=best_match.name,
            confidence=confidence,
        )

    def needs_confirmation(self, confidence: float) -> bool:
        """Check if confidence is in the low-confidence zone requiring user confirmation."""
        return (
            confidence < self.CONFIDENCE_THRESHOLD and confidence >= self.LOW_CONFIDENCE_THRESHOLD
        )

    def is_rejected(self, confidence: float) -> bool:
        """Check if confidence is too low (below low-confidence threshold)."""
        return confidence < self.LOW_CONFIDENCE_THRESHOLD


class _FakeECAPAModel:
    """Fake ECAPA-TDNN model for testing."""

    def __init__(self) -> None:
        self.responses: dict[bytes, np.ndarray] = {}
        self.default_embedding = self._random_embedding()

    def _random_embedding(self) -> np.ndarray:
        """Generate a random normalized embedding."""
        emb = np.random.randn(SpeakerIdentifier.EMBEDDING_DIM).astype(np.float32)
        return emb / np.linalg.norm(emb)

    def compute_embedding(self, audio: bytes) -> np.ndarray:
        if audio in self.responses:
            return self.responses[audio]
        return self.default_embedding
