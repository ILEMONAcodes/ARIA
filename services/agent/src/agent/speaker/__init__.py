"""Speaker identification and profiles."""

from agent.speaker.enrollment import EnrollmentManager
from agent.speaker.identifier import EmbeddingStore, SpeakerIdentifier

__all__ = [
    "EmbeddingStore",
    "EnrollmentManager",
    "SpeakerIdentifier",
]
