from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent.config import Settings
from agent.fakes import FakeClock
from agent.local.server import create_app
from agent.mock.scenarios import load_scenario
from agent.tools.apps import AppLauncher
from agent.tools.base import ToolRegistry
from agent.tools.calendar import CalendarList

TOKEN = "fictional-local-session-token"


class SafeRunner:
    async def invoke(self, tool, args, *, mode, timeout_s):
        values = tool.input_model.model_validate(args)
        if mode == "dry_run":
            return tool.dry_run(values)
        if tool.name == "apps.launch":
            return {"message": "Started excel.", "pid": 42}
        return tool.run(values).model_dump(mode="json")


def app_for_test(tmp_path, **kwargs):
    executable = tmp_path / "EXCEL.EXE"
    executable.touch()
    registry = ToolRegistry()
    registry.register(AppLauncher({"excel": executable}))
    return create_app(
        Settings(),
        token=TOKEN,
        registry=registry,
        apps={"excel": ()},
        clock=FakeClock(),
        time_zone=UTC,
        runner=SafeRunner(),
        **kwargs,
    )


def test_real_local_session_matches_mock_scenario_without_launching_an_app(tmp_path):
    scenario = load_scenario("local_command_execution")
    with (
        TestClient(app_for_test(tmp_path)) as client,
        client.websocket_connect(f"/ws?token={TOKEN}") as socket,
    ):
        for step in scenario["steps"]:
            if "match" in step:
                socket.send_json(step["match"])
            if "send" in step:
                actual = socket.receive_json()
                dynamic = {"task_id", "id", "ts"}
                assert {k: v for k, v in actual.items() if k not in dynamic} == {
                    k: v for k, v in step["send"].items() if k not in dynamic
                }


def test_local_session_calendar_is_real_offline_file_read_with_caption_and_activity(tmp_path):
    from pathlib import Path

    calendar = Path(__file__).resolve().parents[4] / "library/sample_calendar.ics"
    registry = ToolRegistry()
    registry.register(CalendarList(calendar, "Africa/Lagos"))
    app = create_app(
        Settings(),
        token=TOKEN,
        registry=registry,
        apps={},
        time_zone=UTC,
        clock=FakeClock(datetime(2026, 11, 14, tzinfo=UTC)),
        runner=SafeRunner(),
    )
    with TestClient(app) as client, client.websocket_connect(f"/ws?token={TOKEN}") as socket:
        assert socket.receive_json()["state"] == "idle"
        socket.send_json({"v": 1, "type": "text.input", "text": "calendar today"})
        events = []
        while True:
            event = socket.receive_json()
            events.append(event)
            if event.get("state") == "idle":
                break
        assert any(e["type"] == "activity.entry" for e in events)
        caption = next(e["text"] for e in events if e["type"] == "reply.text")
        assert "Fictional planning check-in" in caption


def test_local_session_unknown_text_never_triggers_cloud(tmp_path):
    with (
        TestClient(app_for_test(tmp_path)) as client,
        client.websocket_connect(f"/ws?token={TOKEN}") as socket,
    ):
        socket.receive_json()
        socket.send_json({"v": 1, "type": "text.input", "text": "Draft a report"})
        assert socket.receive_json()["type"] == "transcript.final"
        assert socket.receive_json()["text"] == "That command is not available locally yet."
        assert socket.receive_json()["state"] == "idle"


def test_terminal_command_reports_completion_and_does_not_start_a_server(capsys, tmp_path):
    import asyncio
    from zoneinfo import ZoneInfo

    from agent.local.__main__ import run_command

    registry = ToolRegistry()
    executable = tmp_path / "EXCEL.EXE"
    executable.touch()
    registry.register(AppLauncher({"excel": executable}))
    assert asyncio.run(
        run_command(
            Settings(),
            registry,
            {"excel": ()},
            ZoneInfo("Africa/Lagos"),
            "open excel",
            runner=SafeRunner(),
        )
    )
    assert "Started excel." in capsys.readouterr().out


def test_local_session_requires_auth_origin_version_and_single_owner(tmp_path):
    with TestClient(app_for_test(tmp_path)) as client:
        assert client.get("/api/health").status_code == 401
        assert (
            client.get("/api/health", headers={"Authorization": f"Bearer {TOKEN}"}).json()["mode"]
            == "local-commands"
        )
        assert client.get("/docs").status_code == 404
        with pytest.raises(WebSocketDisconnect), client.websocket_connect("/ws"):
            pass
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(
                f"/ws?token={TOKEN}", headers={"Origin": "https://untrusted.invalid"}
            ),
        ):
            pass
        with client.websocket_connect(f"/ws?token={TOKEN}") as socket:
            socket.receive_json()
            with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/ws?token={TOKEN}"):
                pass
            socket.send_json({"v": 2, "type": "text.input", "text": "Open Excel"})
            with pytest.raises(WebSocketDisconnect):
                socket.receive_json()
