from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent.local.config import load_tools
from agent.tools.apps import AppLauncher, LaunchInput
from agent.tools.calendar import CalendarInput, CalendarList


def test_apps_launch_only_allowed_apps_without_shell_or_arguments(tmp_path, monkeypatch):
    executable = tmp_path / "EXCEL.EXE"
    executable.touch()
    launcher = AppLauncher({"excel": executable})
    monkeypatch.setenv("ARIA_INSTALL_TOKEN", "private-install-token")
    with (
        patch("agent.tools.apps.sys.platform", "win32"),
        patch("agent.tools.apps.subprocess.Popen") as popen,
    ):
        popen.return_value = SimpleNamespace(pid=123)
        assert launcher.run(LaunchInput(name="excel")).pid == 123
        assert popen.call_args.args == ([str(executable)],)
        assert popen.call_args.kwargs["shell"] is False
        assert "ARIA_INSTALL_TOKEN" not in popen.call_args.kwargs["env"]
        with pytest.raises(KeyError):
            launcher.run(LaunchInput(name="cmd.exe /c delete"))
        assert popen.call_count == 1


def test_app_dry_run_has_no_process_side_effects(tmp_path):
    executable = tmp_path / "EXCEL.EXE"
    executable.touch()
    with patch("agent.tools.apps.subprocess.Popen") as popen:
        assert "excel" in AppLauncher({"excel": executable}).dry_run(LaunchInput(name="excel"))
        popen.assert_not_called()


def write_calendar(path, events):
    path.write_text(
        "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//ARIA//Fictional//EN\n" + events + "END:VCALENDAR\n"
    )


def test_calendar_lists_recurrences_all_day_and_timezone_overlaps_without_writes(tmp_path):
    path = tmp_path / "fictional.ics"
    write_calendar(
        path,
        """BEGIN:VEVENT
UID:daily
DTSTART:20260101T080000Z
DTEND:20260101T090000Z
RRULE:FREQ=DAILY;COUNT=365
EXDATE:20261115T080000Z
SUMMARY:Fictional daily meeting
END:VEVENT
BEGIN:VEVENT
UID:holiday
DTSTART;VALUE=DATE:20261114
DTEND;VALUE=DATE:20261115
SUMMARY:Fictional all-day event
END:VEVENT
BEGIN:VEVENT
UID:overlap
DTSTART:20261113T233000Z
DTEND:20261114T003000Z
SUMMARY:Fictional late event
END:VEVENT
BEGIN:VEVENT
UID:cancelled
DTSTART:20261114T110000Z
STATUS:CANCELLED
SUMMARY:Must not appear
END:VEVENT
""",
    )
    before = path.read_bytes()
    tool = CalendarList(path, "Africa/Lagos")
    output = tool.run(CalendarInput(date="2026-11-14"))
    assert len(output.events) == 3
    assert "Must not appear" not in output.message
    assert "Fictional late event" in output.message
    assert next(e for e in output.events if e.summary == "Fictional late event").start.startswith(
        "2026-11-14T00:30"
    )
    assert any(e.all_day for e in output.events)
    assert path.read_bytes() == before
    assert not tool.run(CalendarInput(date="2026-11-15")).events


def test_bad_missing_or_high_frequency_calendars_never_report_empty_success(tmp_path):
    tool = CalendarList(tmp_path / "missing.ics", "Africa/Lagos")
    with pytest.raises(OSError):
        tool.run(CalendarInput(date="2026-11-14"))
    path = tmp_path / "bad.ics"
    write_calendar(path, "BEGIN:VEVENT\nUID:bad\nSUMMARY:No start\nEND:VEVENT\n")
    with pytest.raises(ValueError):
        CalendarList(path, "Africa/Lagos").run(CalendarInput(date="2026-11-14"))
    write_calendar(
        path, "BEGIN:VEVENT\nUID:bad\nDTSTART:20261114T080000Z\nRRULE:FREQ=SECONDLY\nEND:VEVENT\n"
    )
    with pytest.raises(ValueError):
        CalendarList(path, "Africa/Lagos").run(CalendarInput(date="2026-11-14"))


def test_local_configuration_rejects_unknown_fields_and_uses_relative_calendar(tmp_path):
    (tmp_path / "calendar.ics").write_text("BEGIN:VCALENDAR\nVERSION:2.0\nEND:VCALENDAR\n")
    config = tmp_path / "local.toml"
    config.write_text('timezone="Africa/Lagos"\ncalendar="calendar.ics"\n')
    registry, apps, zone = load_tools(config)
    assert registry.names() == ["cal.list"]
    assert apps == {}
    assert str(zone) == "Africa/Lagos"
    config.write_text('timezone="Africa/Lagos"\nsecret="private"\n')
    with pytest.raises(ValueError) as error:
        load_tools(config)
    assert "private" not in str(error.value)
