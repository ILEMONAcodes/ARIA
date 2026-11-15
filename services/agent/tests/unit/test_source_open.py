"""POL-3: source provenance and launch policy with fictional files and stub viewers."""

import asyncio
import io
import json
import shutil
from contextlib import asynccontextmanager
from datetime import UTC
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from starlette.websockets import WebSocketDisconnect

from agent.config import Settings
from agent.contracts.events import SourceOpen, TextInput, TtsStop
from agent.fakes import FakeClock, FakeNetwork
from agent.kb.library import PolicyLibrary, SearchInput
from agent.kb.source import (
    PolicySourceOpen,
    SourceIssue,
    SourceOpenInput,
    Viewer,
    ViewerLaunch,
    WindowsSourceViewer,
)
from agent.kb.tool import PolicySearch
from agent.local.config import load_tools
from agent.local.server import create_app
from agent.mock.scenarios import load_scenario
from agent.planner.keywords import KeywordPlanner
from agent.router.executor import PlanExecutor
from agent.router.session import LocalSession
from agent.store.database import open_database
from agent.tools import ToolRegistry

ROOT = Path(__file__).resolve().parents[4]


class Keys:
    def get_key(self, database_id, *, create):
        return bytes(range(32))  # Fixture-only key, never a production fallback.


class StubViewer:
    def __init__(self):
        self.calls = []
        self.mutate = None

    def open(self, path, page, *, check):
        if self.mutate:
            self.mutate()
        check()
        self.calls.append((path, page))
        return ViewerLaunch(42, page is not None)


@pytest.fixture
def library(tmp_path, monkeypatch):
    folder = tmp_path / "policies"
    shutil.copytree(ROOT / "library/policies", folder)
    monkeypatch.setattr("agent.kb.source.OSVaultKeyProvider", Keys)
    monkeypatch.setattr("agent.kb.tool.OSVaultKeyProvider", Keys)
    with open_database(tmp_path / "policy.db", Keys()) as database:
        library = PolicyLibrary(folder, database)
        library.refresh()
        yield library


def receipt(library):
    return library.search(SearchInput(query="annual leave")).sources[0]


def opener(library, viewer):
    return PolicySourceOpen(library.root, library.root.parent / "policy.db", viewer)


def test_only_unchanged_indexed_source_is_opened(library):
    source = receipt(library)
    viewer = StubViewer()
    result = opener(library, viewer).run(SourceOpenInput(source=source))
    assert result.opened and result.pid == 42
    assert viewer.calls == [(library.root / "leave.txt", None)]
    assert "section" in result.message


@pytest.mark.parametrize(
    "change", ["content", "metadata", "delete", "reindex", "unreadable", "index_removed"]
)
def test_changed_missing_and_reindexed_sources_never_launch(library, change):
    source = receipt(library)
    path = library.root / "leave.txt"
    if change == "metadata":
        manifest = json.loads((library.root / "manifest.json").read_text())
        manifest["documents"][0]["issue_date"] = "2026-02-01"
        (library.root / "manifest.json").write_text(json.dumps(manifest))
    elif change == "delete":
        path.unlink()
    elif change == "unreadable":
        path.write_bytes(b"\xff\xff")
    elif change == "index_removed":
        with library.db.transaction() as connection:
            connection.execute("DELETE FROM kb_passages")
    else:
        path.write_text("Changed fictional content")
        if change == "reindex":
            library.refresh()
    viewer = StubViewer()
    result = opener(library, viewer).run(SourceOpenInput(source=source))
    assert not result.opened and result.code in {"changed", "missing"}
    assert viewer.calls == []


@pytest.mark.parametrize(
    "path",
    [
        "../outside.txt",
        "/outside.txt",
        "https://example.invalid/policy.pdf",
        "//server/share/policy.txt",
        "file:///policy.txt",
    ],
)
def test_arbitrary_paths_cannot_be_opened_even_with_a_real_fingerprint(library, path):
    source = receipt(library).model_copy(update={"file_path": path})
    viewer = StubViewer()
    assert not opener(library, viewer).run(SourceOpenInput(source=source)).opened
    assert viewer.calls == []


def test_symlink_replacement_cannot_redirect_opening(library):
    source = receipt(library)
    path = library.root / "leave.txt"
    original = path.read_bytes()
    path.unlink()
    target = library.root.parent / "outside.txt"
    target.write_bytes(original)
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("The Windows test account cannot create symbolic links")
    viewer = StubViewer()
    assert not opener(library, viewer).run(SourceOpenInput(source=source)).opened
    assert viewer.calls == []


def test_source_is_rechecked_immediately_before_launch(library):
    viewer = StubViewer()
    viewer.mutate = lambda: (library.root / "leave.txt").write_text("Changed during viewer setup")
    result = opener(library, viewer).run(SourceOpenInput(source=receipt(library)))
    assert result.code == "changed" and viewer.calls == []


def test_snapshot_is_not_leaked_to_public_citations(library):
    output = library.search(SearchInput(query="annual leave"))
    assert "fingerprint" not in str([c.model_dump() for c in output.citations])
    assert len(output.sources) == len(output.citations)


def pdf_content():
    writer = PdfWriter()
    for text in ("Fictional overview", "Fictional eligibility"):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 40 700 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(content)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdf_opens_only_a_page_recorded_in_the_snapshot(library):
    (library.root / "sample.pdf").write_bytes(pdf_content())
    library.refresh()
    source = library.search(SearchInput(query="sample eligibility")).sources[0]
    assert source.page == 2
    viewer = StubViewer()
    result = opener(library, viewer).run(SourceOpenInput(source=source))
    assert result.opened and "page 2" in result.message
    source = source.model_copy(update={"page": 256})
    assert not opener(library, viewer).run(SourceOpenInput(source=source)).opened
    assert len(viewer.calls) == 1


@pytest.mark.parametrize(
    "kind,page,navigation", [("sumatra", 2, True), ("file", 2, False), ("file", None, False)]
)
def test_windows_adapter_uses_fixed_arguments_without_shell_or_secrets(
    tmp_path, monkeypatch, kind, page, navigation
):
    executable = tmp_path / "Configured Viewer.exe"
    executable.touch()
    source = tmp_path / "fictional policy & report.pdf"
    source.touch()
    calls = []

    class Process:
        pid = 42

    def popen(command, **kwargs):
        calls.append((command, kwargs))
        return Process()

    monkeypatch.setattr("agent.kb.source.sys.platform", "win32")
    monkeypatch.setattr("agent.kb.source.subprocess.Popen", popen)
    monkeypatch.setenv("ARIA_INSTALL_TOKEN", "fictional-agent-secret")
    monkeypatch.setenv("GATEWAY_PROVIDER_API_KEY", "fictional-provider-secret")
    checks = []
    launch = WindowsSourceViewer({".pdf": Viewer(executable, kind)}).open(
        source, page, check=lambda: checks.append(True)
    )
    assert launch.page_navigation is navigation and checks == [True]
    expected = (
        [str(executable)] + (["-restrict", "-page", "2"] if navigation else []) + [str(source)]
    )
    assert calls[0][0] == expected and calls[0][1]["shell"] is False
    assert "fictional-agent-secret" not in str(calls) and "fictional-provider-secret" not in str(
        calls
    )


def test_missing_viewer_and_native_launch_failure_are_safe(tmp_path, monkeypatch):
    source = tmp_path / "fictional.pdf"
    source.touch()
    monkeypatch.setattr("agent.kb.source.sys.platform", "win32")
    viewer = WindowsSourceViewer({".pdf": Viewer(tmp_path / "missing.exe")})
    with pytest.raises(SourceIssue, match="unavailable"):
        viewer.open(source, 1, check=lambda: None)
    executable = tmp_path / "viewer.exe"
    executable.touch()

    def fail(*args, **kwargs):
        raise OSError("private native diagnostics")

    monkeypatch.setattr("agent.kb.source.subprocess.Popen", fail)
    viewer = WindowsSourceViewer({".pdf": Viewer(executable)})
    with pytest.raises(SourceIssue) as error:
        viewer.open(source, 1, check=lambda: None)
    assert "private" not in str(error.value)


class MemoryRunner:
    def __init__(self):
        self.started = asyncio.Event()
        self.hold = False
        self.open_calls = 0

    async def invoke(self, tool, args, *, mode, timeout_s):
        if tool.name == "files.open":
            self.open_calls += 1
            self.started.set()
            if self.hold:
                await asyncio.Event().wait()
        return tool.run(tool.input_model.model_validate(args)).model_dump(mode="json")


@asynccontextmanager
async def running(library):
    viewer = StubViewer()
    registry = ToolRegistry()
    registry.register(PolicySearch(library.root, library.root.parent / "policy.db"))
    registry.register(opener(library, viewer))
    events = []

    async def emit(event):
        events.append(event.model_dump(mode="json", exclude_none=True))

    runner = MemoryRunner()
    executor = PlanExecutor(registry, Settings(), FakeNetwork(), emit, runner=runner)
    session = LocalSession(
        KeywordPlanner(registry, apps={}, clock=FakeClock(), time_zone=UTC), executor, emit
    )
    try:
        yield session, executor, runner, viewer, events
    finally:
        await session.close()


async def search(session, executor):
    await session.handle(TextInput(text="search policy annual leave"))
    assert (await executor.wait()).kind == "completed"


def test_session_requires_a_previously_returned_source_and_exact_page(library):
    async def scenario():
        async with running(library) as (session, executor, runner, viewer, events):
            request = SourceOpen(file_path=str(library.root / "leave.txt"))
            await session.handle(request)
            assert runner.open_calls == 0 and events[-2]["code"] == "source_invalid"
            await search(session, executor)
            await session.handle(request.model_copy(update={"page": 1}))
            assert runner.open_calls == 0
            await session.handle(request)
            assert (await executor.wait()).kind == "completed" and len(viewer.calls) == 1
            assert any(e.get("text") == "Completed files.open." for e in events)

    asyncio.run(scenario())


def test_new_search_clears_old_citation_authority_and_close_cannot_restart(library):
    async def scenario():
        async with running(library) as (session, executor, runner, viewer, _):
            await search(session, executor)
            await session.handle(TextInput(text="search policy receipts"))
            await executor.wait()
            await session.handle(SourceOpen(file_path=str(library.root / "leave.txt")))
            assert runner.open_calls == 0
            await session.close()
            await session.handle(SourceOpen(file_path=str(library.root / "travel.txt")))
            assert viewer.calls == []

    asyncio.run(scenario())


def test_changed_source_reports_reason_and_never_logs_success(library):
    async def scenario():
        async with running(library) as (session, executor, _, viewer, events):
            await search(session, executor)
            (library.root / "leave.txt").unlink()
            await session.handle(SourceOpen(file_path=str(library.root / "leave.txt")))
            assert (await executor.wait()).kind == "failed" and viewer.calls == []
            assert any(e.get("code") == "source_missing" for e in events)
            assert not any(e.get("text") == "Completed files.open." for e in events)

    asyncio.run(scenario())


def test_stop_during_source_worker_prevents_a_late_launch(library):
    async def scenario():
        async with running(library) as (session, executor, runner, viewer, _):
            await search(session, executor)
            runner.hold = True
            await session.handle(SourceOpen(file_path=str(library.root / "leave.txt")))
            await runner.started.wait()
            await session.handle(TtsStop())
            assert await executor.wait() is None and viewer.calls == []

    asyncio.run(scenario())


def test_authenticated_session_matches_open_source_scenario_without_launching_apps(library):
    registry = ToolRegistry()
    registry.register(PolicySearch(library.root, library.root.parent / "policy.db"))
    viewer = StubViewer()
    registry.register(opener(library, viewer))
    app = create_app(
        Settings(),
        token="fictional-source-session-token",
        registry=registry,
        apps={},
        clock=FakeClock(),
        time_zone=UTC,
        runner=MemoryRunner(),
    )
    fixture = load_scenario("open_policy_source")
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws?token=fictional-source-session-token") as socket,
    ):
        for step in fixture["steps"]:
            if "match" in step:
                response = dict(step["match"])
                if response["type"] == "source.open":
                    response["file_path"] = str(library.root / "leave.txt")
                socket.send_json(response)
            if "send" in step:
                actual, expected = socket.receive_json(), step["send"]
                if actual["type"] == "result.answer":
                    assert actual["citations"][0]["file_path"] == str(library.root / "leave.txt")
                    actual["citations"][0]["file_path"] = expected["citations"][0]["file_path"]
                dynamic = {"task_id", "id", "ts"}
                assert {k: v for k, v in actual.items() if k not in dynamic} == {
                    k: v for k, v in expected.items() if k not in dynamic
                }
        assert len(viewer.calls) == 1
    assert "fingerprint" not in str(fixture)


def test_source_viewers_require_explicit_library_and_valid_paths(tmp_path):
    executable = tmp_path / "viewer.exe"
    executable.touch()
    folder = tmp_path / "policies"
    folder.mkdir()
    config = tmp_path / "tools.toml"
    config.write_text(
        f'timezone="Africa/Lagos"\npolicy_folder="policies"\npolicy_database="cache.db"\n[source_viewers.pdf]\nexecutable={json.dumps(executable.as_posix())}\nkind="sumatra"\n'
    )
    registry, _, _ = load_tools(config)
    assert registry.spec("files.open").needs_network is False
    config.write_text(
        f'timezone="Africa/Lagos"\n[source_viewers.pdf]\nexecutable={json.dumps(executable.as_posix())}\n'
    )
    with pytest.raises(ValueError):
        load_tools(config)


def test_source_open_rejects_non_integer_wire_page(library):
    app = create_app(
        Settings(),
        token="fictional-source-session-token",
        registry=ToolRegistry(),
        apps={},
        clock=FakeClock(),
        time_zone=UTC,
        runner=MemoryRunner(),
    )
    with (
        TestClient(app) as client,
        client.websocket_connect("/ws?token=fictional-source-session-token") as socket,
    ):
        socket.receive_json()
        socket.send_json(
            {"v": 1, "type": "source.open", "file_path": "fictional.pdf", "page": True}
        )
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()


def test_cancelled_result_delivery_does_not_publish_source_selection(library):
    async def scenario():
        async with running(library) as (session, executor, runner, viewer, _):
            started = asyncio.Event()
            original = executor.emit

            async def emit(event):
                if event.type == "result.answer":
                    started.set()
                    await asyncio.Event().wait()
                await original(event)

            executor.emit = emit
            await session.handle(TextInput(text="search policy annual leave"))
            await started.wait()
            await session.cancel()
            await session.handle(SourceOpen(file_path=str(library.root / "leave.txt")))
            assert runner.open_calls == 0 and viewer.calls == []

    asyncio.run(scenario())


def test_wrong_fingerprint_cannot_open_a_current_source(library):
    source = receipt(library).model_copy(update={"fingerprint": "0" * 64})
    viewer = StubViewer()
    result = opener(library, viewer).run(SourceOpenInput(source=source))
    assert not result.opened and result.code == "changed" and viewer.calls == []


def test_non_windows_adapter_never_launches_an_app(tmp_path, monkeypatch):
    executable = tmp_path / "viewer.exe"
    executable.touch()
    monkeypatch.setattr("agent.kb.source.sys.platform", "linux")
    viewer = WindowsSourceViewer({".txt": Viewer(executable)})
    with pytest.raises(SourceIssue, match="unavailable"):
        viewer.open(tmp_path / "fictional.txt", None, check=lambda: None)


def test_invalid_plan_object_remains_a_sanitized_failure(library):
    import warnings

    from agent.contracts.plan import Plan

    async def scenario():
        async with running(library) as (_, executor, _, _, events):
            with warnings.catch_warnings(record=True) as diagnostics:
                await executor.submit(
                    Plan.model_construct(steps=[{"private": "fictional-private-data"}])
                )
            assert not diagnostics
            assert any(e.get("code") == "invalid_plan" for e in events)
            assert "fictional-private-data" not in str(events)

    asyncio.run(scenario())
