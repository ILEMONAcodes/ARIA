"""Offline keyword plans use registered stub tools, never real apps or calendars."""

from datetime import UTC, datetime, timedelta, timezone
from time import perf_counter
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from agent.contracts.plan import Plan
from agent.fakes import FakeClock
from agent.interfaces import KeywordMatcher
from agent.interfaces.models import KeywordResult
from agent.planner.keywords import KeywordPlanner
from agent.tools import Tool, ToolRegistry


class AppInput(BaseModel):
    name: str


class CalendarInput(BaseModel):
    date: str


class Output(BaseModel):
    ok: bool


class ForbiddenTool(Tool[BaseModel, Output]):
    name = "apps.launch"
    risk = "none"
    needs_network = False
    timeout_s = 1.0
    input_model = AppInput
    output_model = Output

    def run(self, args):
        raise AssertionError("Keyword matching must not run tools")

    def dry_run(self, args):
        raise AssertionError("Keyword matching must not invoke tool code")


@pytest.fixture
def components():
    class Calendar(ForbiddenTool):
        name = "cal.list"
        input_model = CalendarInput

    registry = ToolRegistry()
    registry.register(ForbiddenTool())
    registry.register(Calendar())
    clock = FakeClock(datetime(2026, 11, 13, 23, 30, tzinfo=UTC))
    apps = {"excel": ("microsoft excel", "exel", "office"), "word": ("microsoft word", "office")}
    return registry, clock, apps


def planner_for(components, **kwargs):
    registry, clock, apps = components
    return KeywordPlanner(
        registry, apps=apps, clock=clock, time_zone=timezone(timedelta(hours=1)), **kwargs
    )


@pytest.mark.parametrize(
    "text",
    [
        "Open Excel",
        "open microsoft excel",
        "Please open Excel.",
        "Can you launch Excel please?",
        "START EXCEL!",
        " open   Excel ",
    ],
)
def test_open_excel_maps_to_apps_launch(components, text):
    planner: KeywordMatcher = planner_for(components)
    result = planner.match(text)
    assert result.kind == "plan"
    assert result.plan.intent == "open_app"
    assert result.plan.steps[0].tool == "apps.launch"
    assert result.plan.steps[0].args == {"name": "excel"}
    assert not result.plan.needs_network


def test_fuzzy_match_handles_misspelling_opn_exel(components):
    # "exel" is an explicitly configured recognition alias, not a guessed app name.
    result = planner_for(components).match("opn exel")
    assert result.kind == "plan"
    assert result.plan.steps[0].args == {"name": "excel"}
    assert 0.6 <= result.plan.confidence < 1


def test_fuzzy_verb_with_low_configured_confidence_asks_instead(components):
    result = planner_for(components, confidence_threshold=0.9).match("opn excel")
    assert result.kind == "clarify"
    assert result.plan is None
    assert result.question.count("?") == 1


@pytest.mark.parametrize(
    "text",
    [
        "Open",
        "open excell",
        "open office",
        "open unconfigured app",
    ],
)
def test_missing_unknown_or_ambiguous_app_asks_one_question(components, text):
    result = planner_for(components).match(text)
    assert result.kind == "clarify"
    assert result.question == "Which configured app should I open?"
    assert result.plan is None


@pytest.mark.parametrize(
    "text",
    [
        "What's on my calendar today?",
        "What is on my calendar today?",
        "Show my calendar today",
        "calendar today",
        "what’s on my calendar today?",
    ],
)
def test_calendar_today_maps_to_cal_list(components, text):
    result = planner_for(components).match(text)
    assert result.kind == "plan"
    assert result.plan.intent == "calendar_today"
    assert result.plan.steps[0].tool == "cal.list"
    # UTC is Nov 13, but the configured local date is already Nov 14.
    assert result.plan.steps[0].args == {"date": "2026-11-14"}


def test_calendar_uses_current_clock_on_each_request(components):
    planner = planner_for(components)
    components[1].advance(timedelta(days=1))
    assert planner.match("calendar today").plan.steps[0].args["date"] == "2026-11-15"


def test_calendar_without_day_asks_and_never_invents_a_date(components):
    result = planner_for(components).match("show my calendar")
    assert result.kind == "clarify"
    assert result.question == "Which day should I check?"
    assert result.plan is None


@pytest.mark.parametrize(
    "text", ["cancel", "cancel that", "STOP!", "please cancel", "stop speaking"]
)
def test_cancel_maps_to_cancel_current_task(components, text):
    # A control outcome needs no registered cancellation tool or task-ID guessing.
    planner = KeywordPlanner(ToolRegistry(), apps={}, clock=components[1], time_zone=UTC)
    result = planner.match(text)
    assert result.kind == "cancel"
    assert result.plan is None


@pytest.mark.parametrize(
    "text",
    [
        "write a memo",
        "calendar tomorrow",
        "please do not open excel",
        "don't cancel",
        "do not open excel",
        "I said open excel yesterday",
        "how do I open excel",
        "summarise this: open excel",
        "cancel and send the email",
        "",
        "x" * 513,
    ],
)
def test_unknown_command_falls_through_to_planner(components, text):
    # no_match is a handoff signal only; this matcher never invokes an AI provider.
    assert planner_for(components).match(text).kind == "no_match"


@pytest.mark.parametrize(
    "text",
    [
        "open excel and send the email",
        "open excel; delete files",
        "open C:/secret.exe",
        "open excel --argument",
        "open excel\nlaunch word",
    ],
)
def test_compound_commands_and_paths_never_produce_a_local_plan(components, text):
    assert planner_for(components).match(text).plan is None


def test_missing_network_or_incompatible_tools_are_unavailable(components):
    registry, clock, apps = components
    planner = KeywordPlanner(ToolRegistry(), apps=apps, clock=clock, time_zone=UTC)
    assert planner.match("open excel").kind == "unavailable"

    class NetworkApp(ForbiddenTool):
        needs_network = True

    class WrongSchema(ForbiddenTool):
        input_model = CalendarInput

    for tool in (NetworkApp(), WrongSchema()):
        registry = ToolRegistry()
        registry.register(tool)
        planner = KeywordPlanner(registry, apps=apps, clock=clock, time_zone=UTC)
        assert planner.match("open excel").kind == "unavailable"


def test_registered_risk_is_preserved_for_approval(components):
    class LocalWrite(ForbiddenTool):
        risk = "local_write"

    registry = ToolRegistry()
    registry.register(LocalWrite())
    planner = KeywordPlanner(registry, apps=components[2], clock=components[1], time_zone=UTC)
    plan = planner.match("open excel").plan
    assert plan.risk == "local_write"
    assert plan.needs_confirmation


def test_no_network_or_files_or_tool_calls_and_catalog_is_copied(components, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    planner = planner_for(components)
    components[2].clear()
    for command in ("open excel", "calendar today", "cancel", "write a report"):
        planner.match(command)
    assert planner.match("open excel").kind == "plan"
    assert list(tmp_path.iterdir()) == []


def test_keyword_path_under_one_second(components):
    planner = planner_for(components)
    for command in ("open excel", "opn exel", "calendar today", "cancel", "write a memo"):
        started = perf_counter()
        planner.match(command)
        assert perf_counter() - started < 1  # CPU regression only, not a Windows end-to-end claim.


@pytest.mark.parametrize(
    "apps",
    [
        {"C:/app.exe": ()},
        {"excel": "not a tuple"},
        {"excel": ("",)},
        {"excel": ("excel; delete",)},
        {"excel": ("x" * 81,)},
        {f"app{i}": () for i in range(257)},
    ],
)
def test_invalid_app_catalog_fails_before_matching(components, apps):
    with pytest.raises(ValueError):
        KeywordPlanner(components[0], apps=apps, clock=components[1], time_zone=UTC)


def test_naive_calendar_clock_is_rejected(components):
    planner = KeywordPlanner(
        components[0],
        apps={},
        time_zone=UTC,
        clock=SimpleNamespace(now=lambda: datetime(2026, 11, 13)),
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        planner.match("calendar today")


def test_outcomes_cannot_mix_plan_control_and_clarification():
    with pytest.raises(ValueError):
        KeywordResult("cancel", plan=Plan(intent="cancel", confidence=1))
    with pytest.raises(ValueError):
        KeywordResult("clarify")
    assert "private words" not in repr(KeywordResult("clarify", question="private words?"))
