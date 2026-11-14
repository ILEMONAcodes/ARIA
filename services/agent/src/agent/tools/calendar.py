"""Read a configured local ICS calendar. No writes, sync, model or network calls."""

from __future__ import annotations

import importlib
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, field_validator

from agent.contracts.plan import Risk
from agent.tools.base import Tool


class CalendarInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    date: str

    @field_validator("date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError("Use an explicit ISO date")
        return value


class CalendarEvent(BaseModel):
    summary: str
    start: str
    end: str
    all_day: bool


class CalendarOutput(BaseModel):
    message: str
    events: list[CalendarEvent]


class CalendarList(Tool[CalendarInput, CalendarOutput]):
    name = "cal.list"
    # Reading a calendar is not a local write; create/move/cancel remain later tools.
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 5.0
    input_model = CalendarInput
    output_model = CalendarOutput

    def __init__(self, path: Path, timezone_name: str) -> None:
        self.path = path.resolve()
        self.timezone_name = timezone_name
        ZoneInfo(timezone_name)

    def dry_run(self, args: CalendarInput) -> str:
        return f"Read the local calendar for {args.date}."

    def run(self, args: CalendarInput) -> CalendarOutput:
        with self.path.open("rb") as source:
            raw = source.read(2097153)
        if len(raw) > 2097152:
            raise ValueError("Calendar file is too large")
        calendar = importlib.import_module("icalendar").Calendar.from_ical(raw)
        entries = calendar.walk("VEVENT")
        if len(entries) > 1000:
            raise ValueError("Calendar contains too many series")
        for item in entries:
            if "DTSTART" not in item:
                raise ValueError("Calendar event has no start")
            rule = item.get("RRULE")
            if rule is not None and any(
                str(freq) in {"SECONDLY", "MINUTELY"} for freq in rule.get("FREQ", [])
            ):
                raise ValueError("High-frequency recurrences are unsupported")
        zone = ZoneInfo(self.timezone_name)
        if "X-WR-TIMEZONE" not in calendar:
            calendar.add("X-WR-TIMEZONE", self.timezone_name)
        day = date.fromisoformat(args.date)
        start = datetime.combine(day, time.min, zone)
        stop = datetime.combine(day + timedelta(days=1), time.min, zone)

        def instant(value: Any) -> datetime:
            if isinstance(value, datetime):
                return (
                    value.replace(tzinfo=zone) if value.tzinfo is None else value.astimezone(zone)
                )
            if isinstance(value, date):
                return datetime.combine(value, time.min, zone)
            raise ValueError("Invalid calendar time")

        events = []
        expanded = (
            importlib.import_module("recurring_ical_events")
            .of(calendar)
            .between(day - timedelta(days=1), day + timedelta(days=2))
        )
        if len(expanded) > 1000:
            raise ValueError("Too many calendar occurrences")
        for event in expanded:
            if str(event.get("STATUS", "")).upper() == "CANCELLED":
                continue
            begins = event.decoded("DTSTART")
            ends = event.decoded(
                "DTEND",
                begins + (timedelta(0) if isinstance(begins, datetime) else timedelta(days=1)),
            )
            first, last = instant(begins), instant(ends)
            if last < first:
                raise ValueError("Invalid calendar duration")
            if not (first < stop and (last > start or first == last and first >= start)):
                continue
            all_day = not isinstance(begins, datetime)
            events.append(
                CalendarEvent(
                    summary=str(event.get("SUMMARY", "[No title provided]")),
                    start=begins.isoformat() if all_day else first.isoformat(),
                    end=ends.isoformat() if all_day else last.isoformat(),
                    all_day=all_day,
                )
            )
        events.sort(key=lambda e: (e.start, e.summary))
        details = "; ".join(f"{e.summary} ({'all day' if e.all_day else e.start})" for e in events)
        message = (
            f"Calendar for {args.date}: {details}"
            if events
            else f"No events on the local calendar for {args.date}."
        )
        return CalendarOutput(message=message, events=events)
