"""Calendar, file finder, and app launcher tools."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, ClassVar, Protocol

from agent.contracts.plan import Risk
from agent.contracts.tools import (
    AppsLaunchInput,
    AppsLaunchOutput,
    CalCancelInput,
    CalCancelOutput,
    CalCreateInput,
    CalCreateOutput,
    CalEvent,
    CalListInput,
    CalListOutput,
    CalMoveInput,
    CalMoveOutput,
    FileMatch,
    FilesFindInput,
    FilesFindOutput,
)
from agent.tools.base import Tool


class _LLMAdapter(Protocol):
    """Protocol for LLM adapters used by tools."""

    def complete(self, prompt: str) -> str: ...


class _CalendarStore(Protocol):
    """Protocol for calendar storage (local ICS)."""

    def list_events(self, start: str, end: str) -> list[CalEvent]: ...
    def create_event(
        self, title: str, start: str, end: str, description: str | None
    ) -> tuple[str, list[str]]: ...  # returns (event_id, conflict_ids)
    def move_event(
        self, event_id: str, new_start: str, new_end: str
    ) -> tuple[str, list[str]]: ...  # returns (event_id, conflict_ids)
    def cancel_event(self, event_id: str) -> bool: ...


class _FileIndex(Protocol):
    """Protocol for file search index."""

    def search(self, query: str, max_results: int, include_content: bool) -> list[FileMatch]: ...


class _AppLauncher(Protocol):
    """Protocol for app launcher."""

    def launch(self, app_name: str) -> tuple[bool, str]: ...  # returns (launched, message)


class CalList(Tool[CalListInput, CalListOutput]):
    name = "cal.list"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 5.0
    input_model = CalListInput
    output_model = CalListOutput

    def __init__(
        self,
        calendar: _CalendarStore | None = None,
    ) -> None:
        self.calendar = calendar or _FakeCalendarStore()

    def dry_run(self, args: CalListInput) -> str:
        return f"List calendar events from {args.start} to {args.end}"

    def run(self, args: CalListInput) -> CalListOutput:
        events = self.calendar.list_events(args.start, args.end)
        return CalListOutput(events=events)


class CalCreate(Tool[CalCreateInput, CalCreateOutput]):
    name = "cal.create"
    risk: ClassVar[Risk] = "local_write"
    needs_network = False
    timeout_s = 5.0
    input_model = CalCreateInput
    output_model = CalCreateOutput

    def __init__(
        self,
        calendar: _CalendarStore | None = None,
    ) -> None:
        self.calendar = calendar or _FakeCalendarStore()

    def dry_run(self, args: CalCreateInput) -> str:
        return f"Create calendar event '{args.title}' from {args.start} to {args.end}"

    def run(self, args: CalCreateInput) -> CalCreateOutput:
        event_id, conflict_ids = self.calendar.create_event(
            args.title, args.start, args.end, args.description
        )
        return CalCreateOutput(
            event_id=event_id,
            conflict=len(conflict_ids) > 0,
            conflict_with=conflict_ids,
        )


class CalMove(Tool[CalMoveInput, CalMoveOutput]):
    name = "cal.move"
    risk: ClassVar[Risk] = "local_write"
    needs_network = False
    timeout_s = 5.0
    input_model = CalMoveInput
    output_model = CalMoveOutput

    def __init__(
        self,
        calendar: _CalendarStore | None = None,
    ) -> None:
        self.calendar = calendar or _FakeCalendarStore()

    def dry_run(self, args: CalMoveInput) -> str:
        return f"Move event {args.event_id} to {args.new_start}-{args.new_end}"

    def run(self, args: CalMoveInput) -> CalMoveOutput:
        event_id, conflict_ids = self.calendar.move_event(
            args.event_id, args.new_start, args.new_end
        )
        return CalMoveOutput(
            event_id=event_id,
            conflict=len(conflict_ids) > 0,
            conflict_with=conflict_ids,
        )


class CalCancel(Tool[CalCancelInput, CalCancelOutput]):
    name = "cal.cancel"
    risk: ClassVar[Risk] = "destructive"
    needs_network = False
    timeout_s = 5.0
    input_model = CalCancelInput
    output_model = CalCancelOutput

    def __init__(
        self,
        calendar: _CalendarStore | None = None,
    ) -> None:
        self.calendar = calendar or _FakeCalendarStore()

    def dry_run(self, args: CalCancelInput) -> str:
        return f"Cancel event {args.event_id} (confirm={args.confirm})"

    def run(self, args: CalCancelInput) -> CalCancelOutput:
        if not args.confirm:
            return CalCancelOutput(event_id=args.event_id, cancelled=False)
        cancelled = self.calendar.cancel_event(args.event_id)
        return CalCancelOutput(event_id=args.event_id, cancelled=cancelled)


class FilesFind(Tool[FilesFindInput, FilesFindOutput]):
    name = "files.find"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 10.0
    input_model = FilesFindInput
    output_model = FilesFindOutput

    def __init__(
        self,
        file_index: _FileIndex | None = None,
        llm: _LLMAdapter | None = None,
    ) -> None:
        self.file_index = file_index or _FakeFileIndex()
        self.llm = llm or _SimpleFakeLLM()

    def dry_run(self, args: FilesFindInput) -> str:
        return f"Find files matching '{args.query}' (max {args.max_results})"

    def run(self, args: FilesFindInput) -> FilesFindOutput:
        # First try the local file index
        matches = self.file_index.search(args.query, args.max_results, args.include_content)
        if matches:
            return FilesFindOutput(matches=matches)

        # Fall back to LLM for content-based search if index doesn't have content
        if args.include_content:
            prompt = self._build_prompt(args)
            response = self.llm.complete(prompt)
            data = _parse_json(response)
            matches = [FileMatch(**m) for m in data.get("matches", [])]
            return FilesFindOutput(matches=matches)

        return FilesFindOutput(matches=[])

    def _build_prompt(self, args: FilesFindInput) -> str:
        template = (
            Path(__file__).parent.parent / "planner" / "prompts" / "files_find.txt"
        ).read_text()
        return template


class AppsLaunch(Tool[AppsLaunchInput, AppsLaunchOutput]):
    name = "apps.launch"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 5.0
    input_model = AppsLaunchInput
    output_model = AppsLaunchOutput

    # Allow-listed apps for security
    ALLOWED_APPS: ClassVar[set[str]] = {
        "notepad",
        "word",
        "excel",
        "powerpoint",
        "outlook",
        "teams",
        "chrome",
        "edge",
        "firefox",
        "explorer",
        "cmd",
        "powershell",
        "calculator",
        "snippingtool",
        "onenote",
        "pdf",
    }

    def __init__(
        self,
        app_launcher: _AppLauncher | None = None,
        llm: _LLMAdapter | None = None,
    ) -> None:
        self.app_launcher = app_launcher or _FakeAppLauncher()
        self.llm = llm or _SimpleFakeLLM()

    def dry_run(self, args: AppsLaunchInput) -> str:
        return f"Launch app '{args.app_name}'"

    def run(self, args: AppsLaunchInput) -> AppsLaunchOutput:
        # Check allow-list
        if args.app_name.lower() not in self.ALLOWED_APPS:
            return AppsLaunchOutput(
                launched=False,
                message=f"App '{args.app_name}' is not on the allow-list",
            )

        # In production, use the app launcher
        launched, message = self.app_launcher.launch(args.app_name)
        return AppsLaunchOutput(launched=launched, message=message)


class _SimpleFakeLLM:
    """Simple fake LLM adapter for tests."""

    def __init__(self) -> None:
        self.responses: list[str] = []

    def complete(self, prompt: str) -> str:
        if self.responses:
            return self.responses.pop(0)
        return '{"matches": []}'


class _FakeCalendarStore:
    """Fake calendar store for tests."""

    def __init__(self) -> None:
        self.events: dict[str, CalEvent] = {}

    def list_events(self, start: str, end: str) -> list[CalEvent]:
        # In production, filter by date range
        return list(self.events.values())

    def create_event(
        self, title: str, start: str, end: str, description: str | None
    ) -> tuple[str, list[str]]:
        event_id = str(uuid.uuid4())
        event = CalEvent(
            event_id=event_id,
            title=title,
            start=start,
            end=end,
            ics_uid=f"{event_id}@aria.local",
        )
        self.events[event_id] = event
        return event_id, []

    def move_event(self, event_id: str, new_start: str, new_end: str) -> tuple[str, list[str]]:
        if event_id in self.events:
            self.events[event_id].start = new_start
            self.events[event_id].end = new_end
        return event_id, []

    def cancel_event(self, event_id: str) -> bool:
        if event_id in self.events:
            del self.events[event_id]
            return True
        return False


class _FakeFileIndex:
    """Fake file index for tests."""

    def search(self, query: str, max_results: int, include_content: bool) -> list[FileMatch]:
        return []


class _FakeAppLauncher:
    """Fake app launcher for tests."""

    def launch(self, app_name: str) -> tuple[bool, str]:
        return True, f"Launched {app_name}"


def _parse_json(text: str) -> dict[str, Any]:
    import json

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
        return {}
    except json.JSONDecodeError:
        return {}
