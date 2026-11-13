import asyncio
import io
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from agent.__main__ import main
from agent.bootstrap import StartupError, start_agent
from agent.fakes import (
    FakeClock,
    FakeDatabaseKeys,
    FakeSpeakerIdentifier,
    FakeSpeechToText,
    FakeStore,
    fake_adapters,
)


class ControlledSleep:
    def __init__(self):
        self.waiting = asyncio.Queue()
        self.ticks = asyncio.Queue()

    async def __call__(self, seconds):
        await self.waiting.put(seconds)
        await self.ticks.get()


def test_startup_opens_real_encrypted_store_and_closes_it(tmp_path):
    path = tmp_path / "fixture.db"

    async def run():
        async with start_agent(
            environ={"ARIA_DB_PATH": str(path)}, keys=FakeDatabaseKeys(), clock=FakeClock()
        ) as runtime:
            assert runtime.adapters is None
            assert runtime.tools.names() == []
            assert runtime.store.history.transcripts("fixture") == []
        with pytest.raises(RuntimeError, match="not open"):
            _ = runtime.store.history
        assert not any(task.get_name() == "aria-retention" for task in asyncio.all_tasks())

    asyncio.run(run())
    assert not path.read_bytes().startswith(b"SQLite format 3")


def test_startup_and_shutdown_prepare_each_adapter_once_without_running_requests():
    async def run():
        modules = fake_adapters()
        store = FakeStore()
        async with start_agent(environ={}, store=store, adapters=modules, clock=FakeClock()):
            assert store.active
            assert all(component.active for component in modules.components())
            assert modules.llm.requests == []
            assert modules.speaker.spoken == []
        assert store.closed == 1
        for component in modules.components():
            assert (component.started, component.closed, component.active) == (1, 1, False)

    asyncio.run(run())


def test_invalid_settings_fail_before_opening_storage_and_do_not_leak_values():
    async def run():
        store = FakeStore()
        stream = io.StringIO()
        with pytest.raises(StartupError) as error:
            async with start_agent(
                environ={"ARIA_PROFILE": "fictional-private-value"}, store=store, log_stream=stream
            ):
                pytest.fail("Invalid settings must not yield a runtime")
        assert store.opened == 0
        assert "fictional-private-value" not in str(error.value) + stream.getvalue()
        assert json.loads(stream.getvalue().splitlines()[-1])["event"] == "operation.failed"

    asyncio.run(run())


def test_partial_adapter_start_is_cleaned_up_in_reverse_order_without_leaking_errors():
    async def run():
        order = []
        store = FakeStore()
        stream = io.StringIO()

        class TrackedSTT(FakeSpeechToText):
            async def start(self):
                order.append("stt.start")
                await super().start()

            async def close(self):
                order.append("stt.close")
                await super().close()

        class BrokenSpeaker(FakeSpeakerIdentifier):
            async def start(self):
                order.append("speaker.start")
                await super().start()
                raise RuntimeError("fictional-private-error")

            async def close(self):
                order.append("speaker.close")
                await super().close()

        modules = replace(fake_adapters(), stt=TrackedSTT(), speaker_id=BrokenSpeaker())
        with pytest.raises(StartupError) as error:
            async with start_agent(environ={}, store=store, adapters=modules, log_stream=stream):
                pytest.fail("A partial start must not yield a runtime")
        assert order == ["stt.start", "speaker.start", "speaker.close", "stt.close"]
        assert store.closed == 1
        assert modules.audio.started == 0
        assert "fictional-private-error" not in str(error.value) + stream.getvalue()

    asyncio.run(run())


def test_shutdown_continues_if_an_adapter_close_fails():
    async def run():
        store = FakeStore()

        class BrokenSpeaker(FakeSpeakerIdentifier):
            async def close(self):
                await super().close()
                raise RuntimeError("fictional-close-error")

        modules = replace(fake_adapters(), speaker_id=BrokenSpeaker())
        with pytest.raises(StartupError):
            async with start_agent(environ={}, store=store, adapters=modules):
                pass
        assert store.closed == 1
        assert modules.stt.closed == 1
        assert not any(task.get_name() == "aria-retention" for task in asyncio.all_tasks())

    asyncio.run(run())


def test_failed_storage_open_still_closes_partial_store_and_never_starts_audio():
    async def run():
        class BrokenStore(FakeStore):
            def open(self, *, now):
                raise RuntimeError("fictional-storage-error")

        store = BrokenStore()
        modules = fake_adapters()
        with pytest.raises(StartupError):
            async with start_agent(environ={}, store=store, adapters=modules):
                pass
        assert store.closed == 1
        assert modules.audio.started == 0

    asyncio.run(run())


def test_recurring_retention_uses_injected_clock_and_stops_before_store_close():
    async def run():
        clock = FakeClock()
        store = FakeStore()
        sleep = ControlledSleep()
        async with start_agent(
            environ={}, store=store, clock=clock, sleep=sleep, retention_interval_s=10
        ):
            store.history.add_transcript("fixture", "old", at=clock.now())
            assert await sleep.waiting.get() == 10
            clock.advance(timedelta(days=31))
            await sleep.ticks.put(None)
            assert await sleep.waiting.get() == 10
            assert store.history.transcripts("fixture") == []
            assert store.purged == 2  # open, then the periodic tick
        assert store.closed == 1
        assert not any(task.get_name() == "aria-retention" for task in asyncio.all_tasks())

    asyncio.run(run())


def test_retention_failure_is_logged_safely_and_retried_next_interval():
    async def run():
        class FlakyStore(FakeStore):
            attempts = 0

            def purge(self, *, now):
                self.attempts += 1
                if self.attempts == 2:
                    raise RuntimeError("fictional-retention-secret")
                return super().purge(now=now)

        store, clock, sleep, stream = FlakyStore(), FakeClock(), ControlledSleep(), io.StringIO()
        async with start_agent(
            environ={}, store=store, clock=clock, sleep=sleep, log_stream=stream
        ):
            await sleep.waiting.get()
            await sleep.ticks.put(None)
            await sleep.waiting.get()
            assert store.attempts == 2
            await sleep.ticks.put(None)
            await sleep.waiting.get()
            assert store.attempts == 3
        assert "fictional-retention-secret" not in stream.getvalue()
        assert "operation.failed" in stream.getvalue()

    asyncio.run(run())


def test_cancellation_closes_adapters_storage_and_retention_worker():
    async def run():
        store = FakeStore()
        modules = fake_adapters()
        entered = asyncio.Event()

        async def client():
            async with start_agent(environ={}, store=store, adapters=modules):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(client())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert store.closed == 1
        assert all(component.closed == 1 for component in modules.components())
        assert not any(task.get_name() == "aria-retention" for task in asyncio.all_tasks())

    asyncio.run(run())


@pytest.mark.parametrize("interval", [0, -1, float("nan"), float("inf"), 86401])
def test_invalid_retention_schedule_is_rejected_before_store_open(interval):
    async def run():
        store = FakeStore()
        with pytest.raises(StartupError):
            async with start_agent(environ={}, store=store, retention_interval_s=interval):
                pass
        assert store.opened == 0

    asyncio.run(run())


def test_fake_startup_cli_leaves_no_files_and_reports_foundation_scope(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    assert main(["--fake", "--check"]) == 0
    assert "voice and request serving are not enabled" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_cli_returns_failure_without_echoing_bad_configuration(tmp_path, capsys):
    path = tmp_path / "settings.toml"
    path.write_text('[agent]\nprofile="fictional-private-value"')
    assert main(["--settings", str(path), "--fake", "--check"]) == 1
    captured = capsys.readouterr()
    assert "fictional-private-value" not in captured.out + captured.err
