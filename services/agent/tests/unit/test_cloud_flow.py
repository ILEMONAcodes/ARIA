"""C3 approval/retry/fallback tests without network, real providers or tool actions."""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from time import perf_counter

import httpx
import pytest

from agent.config import Settings
from agent.contracts.events import ApprovalResponse
from agent.fakes import FakeLLMAdapter, FakeNetwork, FakeTool
from agent.interfaces.models import ModelMessage, ModelRequest, ModelResponse
from agent.llm.flow import CloudFlow
from agent.llm.gateway import GatewayClient, GatewayFailure
from agent.mock.scenarios import load_scenario
from agent.tools import ToolRegistry


def request():
    return ModelRequest(task="answer", messages=(ModelMessage("user", "Fictional request"),))


@asynccontextmanager
async def running(adapter=None, *, online=True, registry=None, **overrides):
    config = Settings(cloud_timeout_s=overrides.pop("cloud_timeout_s", 1.0), **overrides)
    adapter = adapter or FakeLLMAdapter("Fictional response")
    network = FakeNetwork(online=online)
    events = []

    async def emit(event):
        events.append(event.model_dump(mode="json", exclude_none=True))

    await adapter.start()
    await network.start()
    flow = CloudFlow(config, adapter, network, emit, registry=registry)
    try:
        yield flow, adapter, network, events
    finally:
        await flow.close()
        await network.close()
        await adapter.close()


async def approve(flow, identifier):
    assert await flow.approve(ApprovalResponse(approval_id=identifier, decision="yes"))
    return await flow.wait()


def test_cloud_task_asks_approval_with_exact_payload_and_rejects_replays():
    async def scenario():
        async with running() as (flow, adapter, _, events):
            identifier = await flow.submit(request())
            assert adapter.requests == []
            assert events[-1]["type"] == "cloud.approval_request"
            preview = events[-1]["payload_preview"]
            assert json.loads(preview)["messages"][0]["content"] == "Fictional request"
            assert not await flow.approve(ApprovalResponse(approval_id="wrong", decision="yes"))
            assert not await flow.approve(
                ApprovalResponse(v=2, approval_id=identifier, decision="yes")
            )
            result = await approve(flow, identifier)
            assert result.kind == "completed"
            from agent.llm.wire import encode_request

            assert encode_request(adapter.requests[0]).decode() == preview
            assert not await flow.approve(ApprovalResponse(approval_id=identifier, decision="yes"))
            assert len(adapter.requests) == 1

    asyncio.run(scenario())


def test_decline_or_cancel_before_approval_sends_nothing():
    async def scenario():
        async with running() as (flow, adapter, _, _events):
            identifier = await flow.submit(request())
            await flow.approve(ApprovalResponse(approval_id=identifier, decision="no"))
            assert (await flow.wait()).kind == "declined"
            identifier = await flow.submit(request())
            await flow.cancel()
            assert not await flow.approve(ApprovalResponse(approval_id=identifier, decision="yes"))
            assert adapter.requests == []

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "configuration,online,code",
    [
        ({"profile": "local"}, True, "cloud_disabled"),
        ({"cloud_enabled": False}, True, "cloud_disabled"),
        ({}, False, "cloud_offline"),
    ],
)
def test_disabled_local_or_offline_requests_never_call_cloud(configuration, online, code):
    async def scenario():
        async with running(online=online, **configuration) as (flow, adapter, _, events):
            assert await flow.submit(request()) is None
            assert adapter.requests == []
            assert [e["code"] for e in events if e["type"] == "error"] == [code]
            assert not any(e["type"] == "cloud.approval_request" for e in events)

    asyncio.run(scenario())


def test_profile_and_connectivity_are_rechecked_after_approval():
    async def scenario():
        for setting in ("cloud_enabled", "online"):
            async with running() as (flow, adapter, network, _events):
                identifier = await flow.submit(request())
                if setting == "online":
                    network.online = False
                else:
                    flow.settings = flow.settings.model_copy(update={"cloud_enabled": False})
                assert (await approve(flow, identifier)).kind == "fallback"
                assert adapter.requests == []

    asyncio.run(scenario())


def test_gateway_client_retries_once_before_fallback_matches_scenario():
    class Down(FakeLLMAdapter):
        async def complete(self, req):
            self.requests.append(req)
            raise GatewayFailure(retryable=True)

    async def scenario():
        fixture = load_scenario("gateway_retry_fallback")
        from agent.interfaces.models import DataBlock

        source = ModelRequest(
            task="summarise",
            messages=(ModelMessage("user", "Summarise the fictional circular."),),
            data_blocks=(
                DataBlock("sample", "circular", "This fictional policy allows five days of leave."),
            ),
            client_request_id="00000000-0000-4000-8000-000000000003",
        )
        async with running(Down()) as (flow, adapter, _, events):
            identifier = await flow.submit(source)
            assert (await approve(flow, identifier)).kind == "fallback"
            assert len(adapter.requests) == 2
            assert adapter.requests[0] is adapter.requests[1]
            expected = [s["send"] for s in fixture["steps"] if "send" in s]
            dynamic = {"id", "task_id", "ts", "approval_id"}
            for actual, documented in zip(events, expected, strict=True):
                assert {k: v for k, v in actual.items() if k not in dynamic} == {
                    k: v for k, v in documented.items() if k not in dynamic
                }

    asyncio.run(scenario())


def test_transient_failure_can_succeed_on_second_attempt_without_new_approval():
    class Flaky(FakeLLMAdapter):
        async def complete(self, req):
            self.requests.append(req)
            if len(self.requests) == 1:
                raise GatewayFailure(retryable=True)
            return ModelResponse("Recovered")

    async def scenario():
        async with running(Flaky()) as (flow, adapter, _, events):
            identifier = await flow.submit(request())
            outcome = await approve(flow, identifier)
            assert outcome.response.text == "Recovered"
            assert len(adapter.requests) == 2
            assert sum(e["type"] == "cloud.approval_request" for e in events) == 1
            assert not any(e["type"] == "error" for e in events)

    asyncio.run(scenario())


def test_permanent_rejection_does_not_retry_or_leak_adapter_errors():
    class Rejected(FakeLLMAdapter):
        async def complete(self, req):
            self.requests.append(req)
            raise GatewayFailure(retryable=False)

    async def scenario():
        async with running(Rejected()) as (flow, adapter, _, events):
            await approve(flow, await flow.submit(request()))
            assert len(adapter.requests) == 1
            assert [e["code"] for e in events if e["type"] == "error"] == ["cloud_rejected"]

    asyncio.run(scenario())


def test_gateway_client_times_out_after_shared_budget_and_falls_back():
    class Hanging(FakeLLMAdapter):
        async def complete(self, req):
            self.requests.append(req)
            await asyncio.Event().wait()

    async def scenario():
        # Scale the production <=8-second wall budget down for a fast deterministic test.
        async with running(Hanging(), cloud_timeout_s=0.06) as (flow, adapter, _, events):
            identifier = await flow.submit(request())
            started = perf_counter()
            assert (await approve(flow, identifier)).kind == "fallback"
            assert perf_counter() - started < 0.3
            assert len(adapter.requests) == 2
            assert sum(e["type"] == "error" for e in events) == 1
        assert Settings().cloud_timeout_s == 8

    asyncio.run(scenario())


def test_cancellation_during_request_has_no_late_reply_or_fallback():
    class Hanging(FakeLLMAdapter):
        async def complete(self, req):
            self.requests.append(req)
            started.set()
            await asyncio.Event().wait()

    async def scenario():
        nonlocal started
        started = asyncio.Event()
        async with running(Hanging()) as (flow, _adapter, _, events):
            identifier = await flow.submit(request())
            await flow.approve(ApprovalResponse(approval_id=identifier, decision="yes"))
            await started.wait()
            await flow.cancel()
            assert await flow.wait() is None
            assert not any(e["type"] in {"reply.text", "error", "activity.entry"} for e in events)

    started = None
    asyncio.run(scenario())


@pytest.mark.parametrize(
    "responses,kind,calls",
    [
        (["invalid", "invalid"], "clarify", 2),
        (["invalid", '{"intent":"ask","confidence":0.5,"missing":["recipient"]}'], "clarify", 2),
        (
            [
                '{"intent":"echo","confidence":1,"steps":[{"tool":"test.echo","args":{"text":"fictional"}}]}'
            ],
            "completed",
            1,
        ),
    ],
)
def test_invalid_plan_is_retried_once_then_asks_rephrase(responses, kind, calls):
    class Plans(FakeLLMAdapter):
        async def complete(self, req):
            self.requests.append(req)
            return ModelResponse(responses[len(self.requests) - 1])

    async def scenario():
        registry = ToolRegistry()
        registry.register(FakeTool())
        async with running(Plans(), registry=registry) as (flow, adapter, _, events):
            result = await approve(flow, await flow.submit(replace(request(), task="plan")))
            assert result.kind == kind
            assert len(adapter.requests) == calls
            assert not any(e["type"] == "confirm.request" for e in events)

    asyncio.run(scenario())


def test_actual_gateway_asgi_api_integrates_with_client_approval_and_payload(caplog):
    from gateway.config import Settings as GatewaySettings
    from gateway.llm import FakeLLM
    from gateway.main import create_app

    async def scenario():
        config = Settings(gateway_url="https://gateway.invalid", install_token="fictional-token")
        app = create_app(GatewaySettings(install_tokens={"fictional-token"}), FakeLLM())
        adapter = GatewayClient(config, transport=httpx.ASGITransport(app=app))
        async with running(adapter) as (flow, _, _, events):
            outcome = await approve(flow, await flow.submit(request()))
            assert outcome.kind == "completed"
            assert outcome.response.text.startswith("[fake]")
            assert "fictional-token" not in str(events)
            assert "fictional-token" not in caplog.text

    asyncio.run(scenario())


def test_real_client_health_retry_and_actual_gateway_fake_provider_work_together():
    from gateway.config import Settings as GatewaySettings
    from gateway.llm import FakeLLM
    from gateway.main import create_app

    class Flaky(FakeLLM):
        def __init__(self):
            self.calls = 0

        def complete(self, messages, params):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("private provider diagnostics")
            return super().complete(messages, params)

    async def scenario():
        provider = Flaky()
        config = Settings(gateway_url="https://gateway.invalid", install_token="fictional-token")
        app = create_app(GatewaySettings(install_tokens={"fictional-token"}), provider)
        adapter = GatewayClient(config, transport=httpx.ASGITransport(app=app))
        events = []

        async def emit(event):
            events.append(event)

        await adapter.start()
        flow = CloudFlow(config, adapter, adapter, emit)
        try:
            identifier = await flow.submit(request())
            assert provider.calls == 0  # Only a data-free health check before approval.
            result = await approve(flow, identifier)
            assert result.kind == "completed"
            assert provider.calls == 2
            assert sum(e.type == "cloud.approval_request" for e in events) == 1
            assert not any(e.type == "error" for e in events)
        finally:
            await flow.close()
            await adapter.close()

    asyncio.run(scenario())


def test_invalid_request_and_unexpected_network_errors_are_safe():
    async def scenario():
        async with running() as (flow, adapter, network, events):
            assert await flow.submit(replace(request(), max_tokens=0)) is None
            assert events[-2]["code"] == "invalid_cloud_request"
            assert adapter.requests == []

            async def broken():
                raise RuntimeError("private network diagnostics")

            network.is_online = broken
            assert await flow.submit(request()) is None
            assert "private network diagnostics" not in str(events)
            assert adapter.requests == []

    asyncio.run(scenario())


def test_slow_final_event_delivery_does_not_turn_success_into_fallback():
    async def scenario():
        async with running() as (flow, _, _, events):
            original = flow.emit

            async def slow(event):
                if event.type == "activity.entry":
                    await asyncio.sleep(0.03)
                await original(event)

            flow.emit = slow
            flow.settings = flow.settings.model_copy(update={"cloud_timeout_s": 0.02})
            assert (await approve(flow, await flow.submit(request()))).kind == "completed"
            assert not any(e["type"] == "error" for e in events)

    asyncio.run(scenario())
