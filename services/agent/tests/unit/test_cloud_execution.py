"""C6 session -> fake gateway -> real validator/executor, with sockets blocked."""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest

from agent.config import Settings
from agent.contracts.events import ApprovalResponse, ConfirmResponse, TaskCancel, TextInput, TtsStop
from agent.contracts.plan import Plan
from agent.fakes import FakeLLMAdapter, FakeNetwork, FakeTool
from agent.interfaces.models import KeywordResult, ModelMessage, ModelRequest, ModelResponse
from agent.llm.flow import CloudFlow
from agent.llm.gateway import GatewayClient, GatewayFailure
from agent.llm.wire import encode_request
from agent.mock.scenarios import load_scenario
from agent.router.executor import PlanExecutor
from agent.router.session import LocalSession
from agent.tools import ToolRegistry


def request():
    return ModelRequest(
        task="plan",
        messages=(ModelMessage("user", "Run the fictional two-step example."),),
        client_request_id="00000000-0000-4000-8000-000000000006",
    )


def plan(*, count=2, confidence=1, missing=()):
    return Plan(
        intent="echo",
        confidence=confidence,
        missing=list(missing),
        risk="local_write",
        needs_confirmation=True,
        steps=[{"tool": "test.echo", "args": {"text": "fictional"}}]
        + [{"tool": "test.echo", "args": {"text": "$step1.text"}}] * (count - 1),
    )


class Echo(FakeTool):
    risk = "local_write"

    def dry_run(self, args):
        return f"Echo {args.text}."


class Matcher:
    def match(self, text):
        if text == "cancel":
            return KeywordResult("cancel")
        if text == "local":
            return KeywordResult("plan", plan=plan(count=1))
        return KeywordResult("no_match")


class Runner:
    def __init__(self):
        self.calls = []
        self.fail = False

    async def invoke(self, tool, args, *, mode, timeout_s):
        self.calls.append((mode, dict(args)))
        if mode == "dry_run":
            return tool.dry_run(tool.input_model.model_validate(args))
        if self.fail:
            raise RuntimeError("private tool failure")
        return tool.run(tool.input_model.model_validate(args)).model_dump(mode="json")


@asynccontextmanager
async def running(adapter=None, *, online=True, executor_registry=None, **settings):
    config = Settings(cloud_timeout_s=1, **settings)
    registry = ToolRegistry()
    registry.register(Echo())
    adapter = adapter or FakeLLMAdapter(plan().model_dump_json())
    network = FakeNetwork(online=online)
    await adapter.start()
    await network.start()
    events = []

    async def emit(event):
        events.append(event.model_dump(mode="json", exclude_none=True))

    runner = Runner()
    executor = PlanExecutor(
        executor_registry if executor_registry is not None else registry,
        config,
        network,
        emit,
        runner=runner,
    )
    cloud = CloudFlow(config, adapter, network, emit, registry=registry)
    session = LocalSession(Matcher(), executor, emit, cloud=cloud)
    try:
        await session.start()
        yield session, cloud, executor, runner, adapter, network, events
    finally:
        await session.close()
        await network.close()
        await adapter.close()


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0)


async def approve(session, identifier, decision="yes"):
    await session.handle(ApprovalResponse(approval_id=identifier, decision=decision))
    await session.wait()


async def confirm_next(session, events, count, decision="yes"):
    await until(lambda: len([e for e in events if e["type"] == "confirm.request"]) == count)
    confirmation = [e for e in events if e["type"] == "confirm.request"][-1]
    response = ConfirmResponse(
        confirm_id=confirmation["confirm_id"], decision=decision, via="click"
    )
    await session.handle(response)
    return response


def actions(runner):
    return [args for mode, args in runner.calls if mode == "run"]


def test_real_gateway_fake_provider_and_session_match_cloud_execution_scenario():
    from gateway.config import Settings as GatewaySettings
    from gateway.llm import LLMResult
    from gateway.main import create_app

    class Provider:
        calls = 0

        def complete(self, messages, params):
            self.calls += 1
            return LLMResult(plan().model_dump_json(), 10, 20)

    async def scenario():
        provider = Provider()
        app = create_app(GatewaySettings(install_tokens={"fictional-token"}), provider)
        adapter = GatewayClient(
            Settings(gateway_url="https://gateway.invalid", install_token="fictional-token"),
            transport=httpx.ASGITransport(app=app),
        )
        async with running(adapter) as (session, _, executor, runner, _, _, events):
            identifier = await session.request_cloud(request())
            assert provider.calls == 0 and runner.calls == []
            await session.handle(ApprovalResponse(approval_id="wrong", decision="yes"))
            assert provider.calls == 0
            await approve(session, identifier)
            assert provider.calls == 1
            assert not actions(runner)  # Payload approval cannot approve even the first action.
            for n in (1, 2):
                await confirm_next(session, events, n)
            assert (await executor.wait()).completed_steps == 2
            assert actions(runner) == [{"text": "fictional"}] * 2
            expected = [
                s["send"] for s in load_scenario("cloud_plan_execution")["steps"] if "send" in s
            ]
            dynamic = {"id", "task_id", "ts", "approval_id", "confirm_id"}
            assert [{k: v for k, v in e.items() if k not in dynamic} for e in events] == [
                {k: v for k, v in e.items() if k not in dynamic} for e in expected
            ]
            await session.handle(ApprovalResponse(approval_id=identifier, decision="yes"))
            await session.wait()
            assert provider.calls == 1 and len(actions(runner)) == 2

    asyncio.run(scenario())


def test_exact_approved_payload_and_action_decline_do_not_retry_tools():
    async def scenario():
        async with running() as (session, _, executor, runner, adapter, _, events):
            identifier = await session.request_cloud(request())
            preview = events[-1]["payload_preview"]
            await approve(session, identifier)
            assert encode_request(adapter.requests[0]).decode() == preview
            response = await confirm_next(session, events, 1, decision="no")
            assert (await executor.wait()).kind == "declined"
            await session.handle(response.model_copy(update={"decision": "yes"}))
            assert actions(runner) == []
            assert len([e for e in events if e["type"] == "confirm.request"]) == 1

    asyncio.run(scenario())


def test_cloud_decline_never_calls_provider_or_executor():
    async def scenario():
        async with running() as (session, _, _, runner, adapter, _, _):
            await approve(session, await session.request_cloud(request()), "no")
            assert adapter.requests == [] and runner.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "configuration,online",
    [({"profile": "local"}, True), ({"cloud_enabled": False}, True), ({}, False)],
)
def test_local_disabled_and_offline_sessions_never_dispatch(configuration, online):
    async def scenario():
        async with running(online=online, **configuration) as (
            session,
            _,
            _,
            runner,
            adapter,
            _,
            _,
        ):
            assert await session.request_cloud(request()) is None
            assert adapter.requests == [] and runner.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "response",
    [
        "invalid",
        '{"confidence":1,"intent":"bad","steps":[{"tool":"unknown","args":{}}]}',
        plan(confidence=0.5).model_dump_json(),
        plan(missing=["recipient"]).model_dump_json(),
    ],
)
def test_invalid_or_incomplete_gateway_plans_do_not_reach_executor(response):
    async def scenario():
        async with running(FakeLLMAdapter(response)) as (session, _, _, runner, adapter, _, events):
            await approve(session, await session.request_cloud(request()))
            assert runner.calls == []
            assert any(e["type"] == "reply.text" and "rephrase" in e["text"] for e in events)
            assert len(adapter.requests) in (1, 2)

    asyncio.run(scenario())


def test_transient_gateway_retry_dispatches_only_one_plan_and_tool_failure_does_not_retry():
    class Flaky(FakeLLMAdapter):
        async def complete(self, req):
            self.requests.append(req)
            if len(self.requests) == 1:
                raise GatewayFailure(retryable=True)
            return ModelResponse(plan().model_dump_json())

    async def scenario():
        async with running(Flaky()) as (session, _, executor, runner, adapter, _, events):
            runner.fail = True
            await approve(session, await session.request_cloud(request()))
            await confirm_next(session, events, 1)
            outcome = await executor.wait()
            assert outcome.kind == "failed" and outcome.completed_steps == 0
            assert len(adapter.requests) == 2 and len(actions(runner)) == 1
            assert not any("private tool failure" in str(e) for e in events)
            assert len([e for e in events if e["type"] == "confirm.request"]) == 1

    asyncio.run(scenario())


def test_gateway_failure_falls_back_without_dispatch():
    class Down(FakeLLMAdapter):
        async def complete(self, req):
            self.requests.append(req)
            raise GatewayFailure(retryable=True)

    async def scenario():
        async with running(Down()) as (session, _, _, runner, adapter, _, events):
            await approve(session, await session.request_cloud(request()))
            assert len(adapter.requests) == 2 and runner.calls == []
            assert any(e.get("code") == "cloud_unreachable" for e in events)

    asyncio.run(scenario())


def test_non_plan_response_containing_json_is_displayed_without_execution():
    async def scenario():
        async with running() as (session, _, _, runner, _, _, events):
            await approve(session, await session.request_cloud(replace(request(), task="answer")))
            assert runner.calls == []
            assert any(
                e["type"] == "reply.text" and json.loads(e["text"])["intent"] == "echo"
                for e in events
            )

    asyncio.run(scenario())


@pytest.mark.parametrize("target", ["cloud", "executor"])
def test_policy_change_after_response_blocks_handoff(target):
    async def scenario():
        async with running() as (session, cloud, executor, runner, _, _, events):
            original = cloud.emit

            async def emit(event):
                await original(event)
                if event.type == "status" and event.state == "idle":
                    owner = cloud if target == "cloud" else executor
                    owner.settings = owner.settings.model_copy(update={"cloud_enabled": False})

            cloud.emit = emit
            await approve(session, await session.request_cloud(request()))
            assert runner.calls == []
            assert any(e.get("code") == "cloud_disabled" for e in events)

    asyncio.run(scenario())


def test_executor_revalidates_with_its_own_registry():
    async def scenario():
        async with running(executor_registry=ToolRegistry()) as (
            session,
            _,
            _,
            runner,
            _,
            _,
            events,
        ):
            await approve(session, await session.request_cloud(request()))
            assert runner.calls == []
            assert any(e.get("code") == "invalid_plan" for e in events)

    asyncio.run(scenario())


@pytest.mark.parametrize("control", ["stop", "cancel", "text", "task", "close", "replace"])
def test_cancel_or_supersede_during_gateway_call_blocks_late_plan_even_if_adapter_returns(control):
    class Late(FakeLLMAdapter):
        async def complete(self, req):
            self.requests.append(req)
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return ModelResponse(plan().model_dump_json())

    async def scenario():
        nonlocal started
        started = asyncio.Event()
        async with running(Late()) as (session, cloud, executor, runner, adapter, _, events):
            identifier = await session.request_cloud(request())
            await session.handle(ApprovalResponse(approval_id=identifier, decision="yes"))
            await started.wait()
            if control == "stop":
                await session.handle(TtsStop())
            elif control == "cancel":
                await session.cancel()
            elif control == "text":
                await session.handle(TextInput(text="cancel"))
            elif control == "task":
                await session.handle(TaskCancel(task_id=cloud.task_id))
            elif control == "close":
                await session.close()
            else:
                assert await session.request_cloud(request()) is not None
            assert executor.task_id is None and runner.calls == []
            assert not any(e["type"] == "confirm.request" for e in events)
            assert len(adapter.requests) == 1

    started = None
    asyncio.run(scenario())


def test_cancel_while_connectivity_probe_is_pending_does_not_block_or_show_late_approval():
    async def scenario():
        async with running() as (session, _, _, runner, adapter, network, events):
            started = asyncio.Event()

            async def probe():
                started.set()
                await asyncio.Event().wait()

            network.is_online = probe
            submission = asyncio.create_task(session.request_cloud(request()))
            await started.wait()
            async with asyncio.timeout(1):
                await session.cancel()
                assert await submission is None
            assert runner.calls == [] and adapter.requests == []
            assert not any(e["type"] == "cloud.approval_request" for e in events)

    asyncio.run(scenario())


def test_cancellation_during_handoff_submit_stops_before_any_tool_starts():
    async def scenario():
        async with running() as (session, _, executor, runner, _, _, _):
            started = asyncio.Event()
            original = executor.emit

            async def emit(event):
                if event.type == "plan.preview":
                    started.set()
                    await asyncio.Event().wait()
                await original(event)

            executor.emit = emit
            identifier = await session.request_cloud(request())
            await session.handle(ApprovalResponse(approval_id=identifier, decision="yes"))
            await started.wait()
            await session.cancel()
            assert runner.calls == [] and executor.task_id is None

    asyncio.run(scenario())


def test_cancellation_during_confirmation_invalidates_action_and_cloud_approvals():
    async def scenario():
        async with running() as (session, _, executor, runner, _, _, events):
            identifier = await session.request_cloud(request())
            await approve(session, identifier)
            await until(lambda: any(e["type"] == "confirm.request" for e in events))
            confirm = next(e for e in events if e["type"] == "confirm.request")
            await session.handle(TaskCancel(task_id=executor.task_id))
            await session.handle(
                ConfirmResponse(confirm_id=confirm["confirm_id"], decision="yes", via="key")
            )
            await session.handle(ApprovalResponse(approval_id=identifier, decision="yes"))
            assert actions(runner) == [] and await executor.wait() is None

    asyncio.run(scenario())


def test_unknown_text_stays_local_and_closed_session_cannot_restart():
    async def scenario():
        async with running() as (session, _, _, runner, adapter, _, events):
            await session.handle(TextInput(text="unrecognised request"))
            assert not any(e["type"] == "cloud.approval_request" for e in events)
            await session.close()
            assert await session.request_cloud(request()) is None
            await session.handle(TextInput(text="local"))
            assert adapter.requests == [] and runner.calls == []

    asyncio.run(scenario())


@pytest.mark.parametrize("control", ["stop", "cancel", "close", "local"])
def test_replacing_pending_payload_approval_revokes_old_id(control):
    async def scenario():
        async with running() as (session, _, executor, runner, adapter, _, events):
            identifier = await session.request_cloud(request())
            if control == "stop":
                await session.handle(TtsStop())
            elif control == "cancel":
                await session.cancel()
            elif control == "close":
                await session.close()
            else:
                await session.handle(TextInput(text="local"))
            await session.handle(ApprovalResponse(approval_id=identifier, decision="yes"))
            assert adapter.requests == [] and actions(runner) == []
            if control == "local":
                await confirm_next(session, events, 1)
                assert (await executor.wait()).kind == "completed"
                assert actions(runner) == [{"text": "fictional"}]

    asyncio.run(scenario())


def test_new_cloud_request_invalidates_previous_action_confirmation():
    async def scenario():
        async with running() as (session, _, executor, runner, adapter, _, events):
            old = await session.request_cloud(request())
            await approve(session, old)
            await until(lambda: any(e["type"] == "confirm.request" for e in events))
            stale = next(e for e in events if e["type"] == "confirm.request")
            fresh = await session.request_cloud(request())
            assert fresh != old
            await session.handle(
                ConfirmResponse(confirm_id=stale["confirm_id"], decision="yes", via="click")
            )
            await session.handle(ApprovalResponse(approval_id=old, decision="yes"))
            assert len(adapter.requests) == 1 and actions(runner) == []
            await approve(session, fresh)
            await confirm_next(session, events, 2, decision="no")
            assert (await executor.wait()).kind == "declined"
            assert len(adapter.requests) == 2 and actions(runner) == []

    asyncio.run(scenario())


def test_cancelling_request_caller_revokes_pending_connectivity_probe():
    async def scenario():
        async with running() as (session, _, _, runner, adapter, network, events):
            started = asyncio.Event()

            async def probe():
                started.set()
                await asyncio.Event().wait()

            network.is_online = probe
            submission = asyncio.create_task(session.request_cloud(request()))
            await started.wait()
            submission.cancel()
            with pytest.raises(asyncio.CancelledError):
                await submission
            assert adapter.requests == [] and runner.calls == []
            assert not any(e["type"] == "cloud.approval_request" for e in events)

    asyncio.run(scenario())


def test_unrelated_cancel_id_does_not_authorize_or_cancel_waiting_action():
    async def scenario():
        async with running() as (session, _, executor, runner, _, _, events):
            await approve(session, await session.request_cloud(request()))
            await until(lambda: any(e["type"] == "confirm.request" for e in events))
            task = executor.task_id
            await session.handle(TaskCancel(task_id="unrelated-task"))
            assert executor.task_id == task and actions(runner) == []
            await confirm_next(session, events, 1, decision="no")
            assert (await executor.wait()).kind == "declined"

    asyncio.run(scenario())
