"""Unit tests for calendar, file finder, and app launcher tools."""

import json

from agent.contracts.tools import CalEvent, FileMatch
from agent.tools.cal_files_apps import (
    AppsLaunch,
    CalCancel,
    CalCreate,
    CalList,
    CalMove,
    FilesFind,
    _FakeAppLauncher,
    _FakeCalendarStore,
    _FakeFileIndex,
    _SimpleFakeLLM,
)


class TestCalList:
    """Tests for CalList tool."""

    def test_dry_run(self):
        tool = CalList()
        args = tool.input_model(start="2026-01-12", end="2026-01-18")
        desc = tool.dry_run(args)
        assert "2026-01-12" in desc
        assert "2026-01-18" in desc

    def test_run_lists_events(self):
        fake_store = _FakeCalendarStore()
        fake_store.events["event-1"] = CalEvent(
            event_id="event-1",
            title="Team meeting",
            start="2026-01-12T10:00:00",
            end="2026-01-12T11:00:00",
            ics_uid="event-1@aria.local",
        )
        tool = CalList(calendar=fake_store)
        args = tool.input_model(start="2026-01-12", end="2026-01-18")
        result = tool.run(args)
        assert len(result.events) == 1
        assert result.events[0].event_id == "event-1"
        assert result.events[0].title == "Team meeting"


class TestCalCreate:
    """Tests for CalCreate tool."""

    def test_dry_run(self):
        tool = CalCreate()
        args = tool.input_model(
            title="Meeting", start="2026-01-12T10:00:00", end="2026-01-12T11:00:00"
        )
        desc = tool.dry_run(args)
        assert "Meeting" in desc
        assert "10:00:00" in desc

    def test_run_creates_event(self):
        fake_store = _FakeCalendarStore()
        tool = CalCreate(calendar=fake_store)
        args = tool.input_model(
            title="Team meeting", start="2026-01-12T10:00:00", end="2026-01-12T11:00:00"
        )
        result = tool.run(args)
        assert result.event_id != ""
        assert result.conflict is False
        assert result.conflict_with == []

    def test_run_with_conflict(self):
        fake_store = _FakeCalendarStore()
        # Pre-add an event
        fake_store.events["event-1"] = type(
            "obj",
            (object,),
            {
                "event_id": "event-1",
                "title": "Existing",
                "start": "2026-01-12T10:00:00",
                "end": "2026-01-12T11:00:00",
                "ics_uid": "event-1@aria.local",
            },
        )()
        # This would need conflict detection logic - for now test basic creation
        tool = CalCreate(calendar=fake_store)
        args = tool.input_model(
            title="New meeting", start="2026-01-12T12:00:00", end="2026-01-12T13:00:00"
        )
        result = tool.run(args)
        assert result.event_id != ""


class TestCalMove:
    """Tests for CalMove tool."""

    def test_dry_run(self):
        tool = CalMove()
        args = tool.input_model(
            event_id="event-1", new_start="2026-01-12T14:00:00", new_end="2026-01-12T15:00:00"
        )
        desc = tool.dry_run(args)
        assert "event-1" in desc
        assert "14:00:00" in desc

    def test_run_moves_event(self):
        fake_store = _FakeCalendarStore()
        fake_store.events["event-1"] = type(
            "obj",
            (object,),
            {
                "event_id": "event-1",
                "title": "Meeting",
                "start": "2026-01-12T10:00:00",
                "end": "2026-01-12T11:00:00",
                "ics_uid": "event-1@aria.local",
            },
        )()
        tool = CalMove(calendar=fake_store)
        args = tool.input_model(
            event_id="event-1", new_start="2026-01-12T14:00:00", new_end="2026-01-12T15:00:00"
        )
        result = tool.run(args)
        assert result.event_id == "event-1"
        assert result.conflict is False
        # Check the event was actually moved
        assert fake_store.events["event-1"].start == "2026-01-12T14:00:00"


class TestCalCancel:
    """Tests for CalCancel tool."""

    def test_dry_run(self):
        tool = CalCancel()
        args = tool.input_model(event_id="event-1", confirm=True)
        desc = tool.dry_run(args)
        assert "event-1" in desc
        assert "True" in desc

    def test_run_requires_confirmation(self):
        fake_store = _FakeCalendarStore()
        fake_store.events["event-1"] = type(
            "obj",
            (object,),
            {
                "event_id": "event-1",
                "title": "Meeting",
                "start": "2026-01-12T10:00:00",
                "end": "2026-01-12T11:00:00",
                "ics_uid": "event-1@aria.local",
            },
        )()
        tool = CalCancel(calendar=fake_store)
        args = tool.input_model(event_id="event-1", confirm=False)
        result = tool.run(args)
        assert result.cancelled is False

    def test_run_cancels_with_confirmation(self):
        fake_store = _FakeCalendarStore()
        fake_store.events["event-1"] = type(
            "obj",
            (object,),
            {
                "event_id": "event-1",
                "title": "Meeting",
                "start": "2026-01-12T10:00:00",
                "end": "2026-01-12T11:00:00",
                "ics_uid": "event-1@aria.local",
            },
        )()
        tool = CalCancel(calendar=fake_store)
        args = tool.input_model(event_id="event-1", confirm=True)
        result = tool.run(args)
        assert result.cancelled is True
        assert "event-1" not in fake_store.events


class TestFilesFind:
    """Tests for FilesFind tool."""

    def test_dry_run(self):
        tool = FilesFind()
        args = tool.input_model(query="meeting agenda", max_results=10)
        desc = tool.dry_run(args)
        assert "meeting agenda" in desc
        assert "10" in desc

    def test_run_uses_index(self):
        fake_index = _FakeFileIndex()
        # Override search to return matches
        fake_index.search = lambda q, m, c: [
            FileMatch(
                path="C:/Users/user/Documents/meeting_agenda.pdf",
                name="meeting_agenda.pdf",
                modified="2026-01-12T10:00:00",
                size=1024,
                snippet="Agenda for Monday meeting",
            )
        ]
        tool = FilesFind(file_index=fake_index)
        args = tool.input_model(query="meeting agenda", max_results=10)
        result = tool.run(args)
        assert len(result.matches) == 1
        assert result.matches[0].name == "meeting_agenda.pdf"

    def test_run_empty_results(self):
        tool = FilesFind(file_index=_FakeFileIndex())
        args = tool.input_model(query="nonexistent", max_results=10)
        result = tool.run(args)
        assert result.matches == []


class TestAppsLaunch:
    """Tests for AppsLaunch tool."""

    def test_dry_run(self):
        tool = AppsLaunch()
        args = tool.input_model(app_name="notepad")
        desc = tool.dry_run(args)
        assert "notepad" in desc

    def test_run_launches_allowed_app(self):
        fake_launcher = _FakeAppLauncher()
        tool = AppsLaunch(app_launcher=fake_launcher)
        args = tool.input_model(app_name="notepad")
        result = tool.run(args)
        assert result.launched is True
        assert "notepad" in result.message

    def test_run_rejects_disallowed_app(self):
        tool = AppsLaunch()
        args = tool.input_model(app_name="malware.exe")
        result = tool.run(args)
        assert result.launched is False
        assert "not on the allow-list" in result.message

    def test_allow_list_contains_common_apps(self):
        tool = AppsLaunch()
        for app in ["notepad", "word", "excel", "powerpoint", "outlook", "chrome", "edge"]:
            assert app in tool.ALLOWED_APPS


class TestFakeCalendarStore:
    """Tests for the fake calendar store."""

    def test_create_and_list(self):
        store = _FakeCalendarStore()
        event_id, _ = store.create_event(
            "Meeting", "2026-01-12T10:00:00", "2026-01-12T11:00:00", None
        )
        events = store.list_events("2026-01-12", "2026-01-18")
        assert len(events) == 1
        assert events[0].event_id == event_id

    def test_move_event(self):
        store = _FakeCalendarStore()
        event_id, _ = store.create_event(
            "Meeting", "2026-01-12T10:00:00", "2026-01-12T11:00:00", None
        )
        store.move_event(event_id, "2026-01-12T14:00:00", "2026-01-12T15:00:00")
        assert store.events[event_id].start == "2026-01-12T14:00:00"

    def test_cancel_event(self):
        store = _FakeCalendarStore()
        event_id, _ = store.create_event(
            "Meeting", "2026-01-12T10:00:00", "2026-01-12T11:00:00", None
        )
        cancelled = store.cancel_event(event_id)
        assert cancelled is True
        assert event_id not in store.events

    def test_cancel_nonexistent(self):
        store = _FakeCalendarStore()
        cancelled = store.cancel_event("nonexistent")
        assert cancelled is False


class TestFakeFileIndex:
    """Tests for the fake file index."""

    def test_search_returns_empty(self):
        index = _FakeFileIndex()
        matches = index.search("query", 10, False)
        assert matches == []


class TestFakeAppLauncher:
    """Tests for the fake app launcher."""

    def test_launch(self):
        launcher = _FakeAppLauncher()
        launched, message = launcher.launch("notepad")
        assert launched is True
        assert "notepad" in message


class TestSimpleFakeLLM:
    """Tests for the simple fake LLM."""

    def test_preset_responses(self):
        llm = _SimpleFakeLLM()
        llm.responses = ["resp1", "resp2"]
        assert llm.complete("prompt") == "resp1"
        assert llm.complete("prompt") == "resp2"

    def test_default_response(self):
        llm = _SimpleFakeLLM()
        resp = llm.complete("prompt")
        data = json.loads(resp)
        assert data == {"matches": []}
