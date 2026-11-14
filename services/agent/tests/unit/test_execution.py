import asyncio
from contextlib import asynccontextmanager

import pytest

from agent.config import Settings
from agent.contracts.events import ConfirmResponse
from agent.contracts.plan import Plan
from agent.fakes import FakeNetwork, FakeTool
from agent.router.executor import PlanExecutor
from agent.tools import ToolRegistry


class MemoryRunner:
    def __init__(self):
        self.calls = []
        self.started = asyncio.Event()
        self.hold = False
        self.bad_output = False

    async def invoke(self, tool, args, *, mode, timeout_s):
        self.calls.append((mode, dict(args)))
        if mode == "dry_run":
            return tool.dry_run(tool.input_model.model_validate(args))
        self.started.set()
        if self.hold:
            await asyncio.Event().wait()
        if self.bad_output:
            return {"text": 123}
        return tool.run(tool.input_model.model_validate(args)).model_dump(mode="json")


def plan(*, risk="none", network=False, count=1, confidence=1):
    return Plan(
        intent="echo",
        confidence=confidence,
        risk=risk,
        needs_confirmation=risk != "none",
        needs_network=network,
        steps=[{"tool": "test.echo", "args": {"text": "fictional"}}] * count,
    )


@asynccontextmanager
async def running(*, risk="none", network=False, online=False, timeout=1):
    class Tool(FakeTool):
        pass

    Tool.risk, Tool.needs_network, Tool.timeout_s = risk, network, timeout
    registry = ToolRegistry()
    registry.register(Tool())
    net = FakeNetwork(online=online)
    await net.start()
    runner = MemoryRunner()
    events = []

    async def emit(event):
        events.append(event.model_dump(mode="json", exclude_none=True))

    executor = PlanExecutor(registry, Settings(), net, emit, runner=runner)
    try:
        yield executor, runner, net, events, Tool
    finally:
        await executor.close()
        await net.close()


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0)


def test_local_task_runs_without_approval_or_network_check():
    async def scenario():
        async with running() as (executor, runner, network, events, _):

            async def forbidden():
                raise AssertionError("Local work must not probe connectivity")

            network.is_online = forbidden
            await executor.submit(plan())
            result = await executor.wait()
            assert result.kind == "completed"
            assert result.completed_steps == 1
            assert runner.calls == [("run", {"text": "fictional"})]
            assert not any(e["type"] == "confirm.request" for e in events)
            assert any(e["type"] == "activity.entry" for e in events)

    asyncio.run(scenario())


@pytest.mark.parametrize("risk", ["local_write", "external_send", "destructive"])
def test_each_risky_step_waits_for_matching_click_or_key_confirmation(risk):
    async def scenario():
        async with running(risk=risk) as (executor, runner, _, events, _tool):
            original = plan(risk=risk, count=2)
            await executor.submit(original)
            original.steps[0].args["text"] = "caller changed it"
            for index in range(2):
                await until(
                    lambda index=index: (
                        len([e for e in events if e["type"] == "confirm.request"]) == index + 1
                    )
                )
                confirmation = [e for e in events if e["type"] == "confirm.request"][-1]
                assert confirmation["needs_click"] is True
                assert not await executor.confirm(
                    ConfirmResponse(confirm_id="wrong", decision="yes", via="click")
                )
                voice = ConfirmResponse.model_construct(
                    confirm_id=confirmation["confirm_id"], decision="yes", via="voice"
                )
                assert not await executor.confirm(voice)
                assert len([c for c in runner.calls if c[0] == "run"]) == index
                answer = ConfirmResponse(
                    confirm_id=confirmation["confirm_id"], decision="yes", via="key"
                )
                assert await executor.confirm(answer)
                assert not await executor.confirm(answer)
            result = await executor.wait()
            assert result.kind == "completed"
            assert result.completed_steps == 2
            assert all(args["text"] == "fictional" for _, args in runner.calls)

    asyncio.run(scenario())


def test_decline_and_cancel_while_waiting_never_run_the_tool():
    async def scenario():
        for cancel in (False, True):
            async with running(risk="local_write") as (executor, runner, _, events, _):
                await executor.submit(plan(risk="local_write"))
                await until(lambda: any(e["type"] == "confirm.request" for e in events))
                confirmation = next(e for e in events if e["type"] == "confirm.request")
                if cancel:
                    await executor.cancel()
                else:
                    await executor.confirm(
                        ConfirmResponse(
                            confirm_id=confirmation["confirm_id"], decision="no", via="click"
                        )
                    )
                    assert (await executor.wait()).kind == "declined"
                assert not any(mode == "run" for mode, _ in runner.calls)

    asyncio.run(scenario())


def test_tool_timeout_is_enforced_and_no_late_success_is_emitted():
    async def scenario():
        async with running(timeout=0.03) as (executor, runner, _, events, _):
            runner.hold = True
            await executor.submit(plan(count=2))
            result = await executor.wait()
            assert result.kind == "failed"
            assert result.completed_steps == 0
            assert len(runner.calls) == 1
            assert not any(e["type"] == "reply.text" for e in events)
            assert any("may have taken effect" in e.get("text", "") for e in events)

    asyncio.run(scenario())


def test_cancel_running_step_stops_later_steps():
    async def scenario():
        async with running() as (executor, runner, _, events, _):
            runner.hold = True
            await executor.submit(plan(count=2))
            await runner.started.wait()
            await executor.cancel()
            assert len(runner.calls) == 1
            assert executor.task_id is None
            assert not any(e["type"] == "reply.text" for e in events)
            assert any("Task cancelled" in e.get("text", "") for e in events)

    asyncio.run(scenario())


def test_offline_network_step_is_not_run_or_falsely_queued():
    async def scenario():
        async with running(network=True) as (executor, runner, _, events, _):
            await executor.submit(plan(network=True))
            assert (await executor.wait()).kind == "failed"
            assert runner.calls == []
            assert any(e.get("code") == "tool_offline" for e in events)
            assert "Nothing was queued" in str(events)

    asyncio.run(scenario())


def test_invalid_plan_and_low_confidence_never_execute():
    async def scenario():
        async with running() as (executor, runner, _, events, _):
            await executor.submit(plan(confidence=0.3))
            assert runner.calls == []
            invalid = plan()
            invalid.steps[0].tool = "shell.exec"
            await executor.submit(invalid)
            assert runner.calls == []
            assert any(e.get("code") == "invalid_plan" for e in events)

    asyncio.run(scenario())


def test_bad_output_and_changed_policy_fail_closed():
    async def scenario():
        async with running() as (executor, runner, _, _events, tool):
            runner.bad_output = True
            await executor.submit(plan(count=2))
            assert (await executor.wait()).kind == "failed"
            assert len(runner.calls) == 1
            tool.risk = "external_send"
            await executor.submit(plan())
            assert (await executor.wait()).kind == "failed"
            assert len(runner.calls) == 1

    asyncio.run(scenario())
