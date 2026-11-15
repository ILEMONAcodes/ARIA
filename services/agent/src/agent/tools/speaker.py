"""Speaker enrollment, identification, confirmation, and profile management tools."""

from __future__ import annotations

import base64
import json
import time
from typing import Any, ClassVar, Protocol

from agent.contracts.events import SpeakerInfo
from agent.contracts.plan import Risk
from agent.contracts.tools import (
    SpeakerConfirmInput,
    SpeakerConfirmOutput,
    SpeakerEnrollInput,
    SpeakerEnrollOutput,
    SpeakerIdentifyInput,
    SpeakerIdentifyOutput,
    SpeakerProfileCreateInput,
    SpeakerProfileCreateOutput,
    SpeakerProfileDeleteInput,
    SpeakerProfileDeleteOutput,
    SpeakerProfileInfo,
    SpeakerProfileListInput,
    SpeakerProfileListOutput,
    SpeakerProfileUpdateInput,
    SpeakerProfileUpdateOutput,
)
from agent.tools.base import Tool


class _Connection(Protocol):
    def execute(self, query: str, params: tuple[Any, ...]) -> Any: ...


class _Database(Protocol):
    @property
    def _connection(self) -> _Connection: ...


class SpeakerEnroll(Tool[SpeakerEnrollInput, SpeakerEnrollOutput]):
    name = "speaker.enroll"
    risk: ClassVar[Risk] = "local_write"
    needs_network = False
    timeout_s = 60.0
    input_model = SpeakerEnrollInput
    output_model = SpeakerEnrollOutput

    def __init__(
        self,
        identifier: Any,  # SpeakerIdentifier
        enrollment_manager: Any,  # EnrollmentManager
    ) -> None:
        self.identifier = identifier
        self.enrollment_manager = enrollment_manager

    def dry_run(self, args: SpeakerEnrollInput) -> str:
        return f"Enroll speaker '{args.name}' with profile ID '{args.profile_id}' using ~30 seconds of audio"

    def run(self, args: SpeakerEnrollInput) -> SpeakerEnrollOutput:
        embedding = self.enrollment_manager.enroll(args.profile_id, args.name)
        return SpeakerEnrollOutput(
            profile_id=embedding.profile_id,
            name=embedding.name,
            enrolled=True,
        )


class SpeakerIdentify(Tool[SpeakerIdentifyInput, SpeakerIdentifyOutput]):
    name = "speaker.identify"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 5.0
    input_model = SpeakerIdentifyInput
    output_model = SpeakerIdentifyOutput

    def __init__(self, identifier: Any) -> None:
        self.identifier = identifier

    def dry_run(self, args: SpeakerIdentifyInput) -> str:
        return "Identify speaker from audio"

    def run(self, args: SpeakerIdentifyInput) -> SpeakerIdentifyOutput:
        audio = base64.b64decode(args.audio)
        result = self.identifier.identify(audio)

        if result is None:
            return SpeakerIdentifyOutput(speaker=None, needs_confirmation=False)

        needs_confirmation = self.identifier.needs_confirmation(result.confidence)
        is_rejected = self.identifier.is_rejected(result.confidence)

        if is_rejected:
            return SpeakerIdentifyOutput(speaker=None, needs_confirmation=False)

        return SpeakerIdentifyOutput(
            speaker=result,
            needs_confirmation=needs_confirmation,
        )


class SpeakerConfirm(Tool[SpeakerConfirmInput, SpeakerConfirmOutput]):
    name = "speaker.confirm"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 5.0
    input_model = SpeakerConfirmInput
    output_model = SpeakerConfirmOutput

    def __init__(self, identifier: Any) -> None:
        self.identifier = identifier
        self._pending_speaker: SpeakerInfo | None = None

    def set_pending(self, speaker: SpeakerInfo) -> None:
        self._pending_speaker = speaker

    def dry_run(self, args: SpeakerConfirmInput) -> str:
        if self._pending_speaker:
            action = "accept" if args.accept else "reject"
            return f"{action.capitalize()} speaker confirmation for '{self._pending_speaker.name}'"
        return "Confirm or reject speaker identification"

    def run(self, args: SpeakerConfirmInput) -> SpeakerConfirmOutput:
        if not self._pending_speaker:
            return SpeakerConfirmOutput(speaker=None)

        if args.accept:
            speaker = self._pending_speaker
            self._pending_speaker = None
            return SpeakerConfirmOutput(speaker=speaker)
        else:
            self._pending_speaker = None
            return SpeakerConfirmOutput(speaker=None)


class SpeakerProfileCreate(Tool[SpeakerProfileCreateInput, SpeakerProfileCreateOutput]):
    name = "speaker.profile.create"
    risk: ClassVar[Risk] = "local_write"
    needs_network = False
    timeout_s = 10.0
    input_model = SpeakerProfileCreateInput
    output_model = SpeakerProfileCreateOutput

    def __init__(self, db: _Database) -> None:
        self._db = db

    def dry_run(self, args: SpeakerProfileCreateInput) -> str:
        return f"Create profile '{args.name}' with ID '{args.profile_id}'"

    def run(self, args: SpeakerProfileCreateInput) -> SpeakerProfileCreateOutput:
        self._db._connection.execute(
            """INSERT OR REPLACE INTO profiles (id, name, role, voice_embedding, settings_json, created_at)
               VALUES (?, ?, '', NULL, ?, ?)""",
            (args.profile_id, args.name, json.dumps(args.settings or {}), int(time.time())),
        )
        return SpeakerProfileCreateOutput(
            profile_id=args.profile_id,
            name=args.name,
            created=True,
        )


class SpeakerProfileUpdate(Tool[SpeakerProfileUpdateInput, SpeakerProfileUpdateOutput]):
    name = "speaker.profile.update"
    risk: ClassVar[Risk] = "local_write"
    needs_network = False
    timeout_s = 10.0
    input_model = SpeakerProfileUpdateInput
    output_model = SpeakerProfileUpdateOutput

    def __init__(self, db: _Database) -> None:
        self._db = db

    def dry_run(self, args: SpeakerProfileUpdateInput) -> str:
        updates = []
        if args.name:
            updates.append(f"name='{args.name}'")
        if args.settings:
            updates.append(f"settings={json.dumps(args.settings)}")
        return f"Update profile '{args.profile_id}': {', '.join(updates) or 'no changes'}"

    def run(self, args: SpeakerProfileUpdateInput) -> SpeakerProfileUpdateOutput:
        fields = []
        values: list[Any] = []
        if args.name is not None:
            fields.append("name = ?")
            values.append(args.name)
        if args.settings is not None:
            fields.append("settings_json = ?")
            values.append(json.dumps(args.settings))
        if not fields:
            return SpeakerProfileUpdateOutput(profile_id=args.profile_id, updated=False)
        values.append(args.profile_id)
        self._db._connection.execute(
            f"UPDATE profiles SET {', '.join(fields)} WHERE id = ?",
            tuple(values),
        )
        return SpeakerProfileUpdateOutput(profile_id=args.profile_id, updated=True)


class SpeakerProfileDelete(Tool[SpeakerProfileDeleteInput, SpeakerProfileDeleteOutput]):
    name = "speaker.profile.delete"
    risk: ClassVar[Risk] = "destructive"
    needs_network = False
    timeout_s = 10.0
    input_model = SpeakerProfileDeleteInput
    output_model = SpeakerProfileDeleteOutput

    def __init__(
        self,
        db: _Database,
        embedding_store: Any,  # EmbeddingStore
    ) -> None:
        self._db = db
        self._embedding_store = embedding_store

    def dry_run(self, args: SpeakerProfileDeleteInput) -> str:
        if args.confirm:
            return f"Delete profile '{args.profile_id}' and all associated data (embeddings, history, queued items)"
        return f"Request confirmation to delete profile '{args.profile_id}'"

    def run(self, args: SpeakerProfileDeleteInput) -> SpeakerProfileDeleteOutput:
        if not args.confirm:
            return SpeakerProfileDeleteOutput(profile_id=args.profile_id, deleted=False)

        # Delete embedding
        self._embedding_store.delete(args.profile_id)

        # Delete profile (cascades to transcripts, activity_log via foreign keys)
        self._db._connection.execute("DELETE FROM profiles WHERE id = ?", (args.profile_id,))

        return SpeakerProfileDeleteOutput(profile_id=args.profile_id, deleted=True)


class SpeakerProfileList(Tool[SpeakerProfileListInput, SpeakerProfileListOutput]):
    name = "speaker.profile.list"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 5.0
    input_model = SpeakerProfileListInput
    output_model = SpeakerProfileListOutput

    def __init__(self, db: _Database, embedding_store: Any) -> None:
        self._db = db
        self._embedding_store = embedding_store

    def dry_run(self, args: SpeakerProfileListInput) -> str:
        return "List all speaker profiles"

    def run(self, args: SpeakerProfileListInput) -> SpeakerProfileListOutput:
        rows = self._db._connection.execute(
            "SELECT id, name, settings_json, created_at FROM profiles ORDER BY created_at", ()
        ).fetchall()

        profiles = []
        for row in rows:
            profile_id, name, settings_json, created_at = row
            has_embedding = self._embedding_store.load(profile_id) is not None
            profiles.append(
                SpeakerProfileInfo(
                    profile_id=profile_id,
                    name=name,
                    has_embedding=has_embedding,
                    settings=json.loads(settings_json) if settings_json else {},
                    created_at=created_at,
                )
            )

        return SpeakerProfileListOutput(profiles=profiles)
