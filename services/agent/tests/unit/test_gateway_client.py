"""Gateway HTTP adapter tests use only in-memory transports, with sockets blocked."""

import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from agent.config import Settings
from agent.interfaces import LLMAdapter
from agent.interfaces.models import DataBlock, ModelMessage, ModelRequest
from agent.llm.gateway import GatewayClient, GatewayFailure
from agent.llm.wire import data_rule, snapshot

TOKEN = "fictional-install-token"


def settings(**overrides):
    return Settings(gateway_url="https://gateway.invalid", install_token=TOKEN, **overrides)


def request():
    return ModelRequest(
        task="summarise",
        messages=(ModelMessage("user", "Summarise the fictional circular."),),
        data_blocks=(
            DataBlock("sample", "circular", "This fictional policy allows five days of leave."),
        ),
        client_request_id="00000000-0000-4000-8000-000000000003",
    )


def response_for(req, **changes):
    return httpx.Response(
        200,
        json={
            "text": "Fictional summary.",
            "usage": {"input_tokens": 8, "output_tokens": 3},
            "model": "fake-gemma",
            "request_id": json.loads(req.content)["client_request_id"],
            **changes,
        },
    )


def test_payload_contains_only_allowed_fields_no_audio_no_credentials():
    calls = []

    def handle(req):
        calls.append(req)
        return response_for(req)

    async def scenario():
        adapter: LLMAdapter = GatewayClient(settings(), transport=httpx.MockTransport(handle))
        await adapter.start()
        assert calls == []
        result = await adapter.complete(request())
        assert result.text == "Fictional summary."
        assert (result.input_tokens, result.output_tokens) == (8, 3)
        await adapter.close()
        sent = calls[0]
        assert str(sent.url) == "https://gateway.invalid/v1/complete"
        assert sent.headers["authorization"] == "Bearer " + TOKEN
        body = json.loads(sent.content)
        assert set(body) == {"task", "messages", "data_blocks", "params", "client_request_id"}
        assert TOKEN not in sent.content.decode()
        assert body["params"]["reasoning"] is False
        assert body["data_blocks"][0]["text"] == request().data_blocks[0].text
        assert body["messages"][0] == {"role": "system", "content": data_rule()}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,retryable",
    [
        (401, False),
        (403, False),
        (422, False),
        (429, False),
        (307, False),
        (408, True),
        (500, True),
        (502, True),
        (503, True),
        (504, True),
    ],
)
def test_status_errors_are_classified_without_exposing_response_body(status, retryable):
    calls = []

    def handle(req):
        calls.append(req)
        return httpx.Response(
            status,
            text="private source " + TOKEN,
            headers={"Location": "https://different.invalid"},
        )

    async def scenario():
        adapter = GatewayClient(settings(), transport=httpx.MockTransport(handle))
        await adapter.start()
        with pytest.raises(GatewayFailure) as error:
            await adapter.complete(request())
        assert error.value.retryable is retryable
        assert TOKEN not in str(error.value)
        assert len(calls) == 1  # No automatic retry or redirect below CloudFlow.
        await adapter.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "changes",
    [
        {"text": ""},
        {"request_id": "wrong-request"},
        {"usage": {"input_tokens": -1, "output_tokens": 3}},
        {"unknown": "secret"},
    ],
)
def test_bad_gateway_response_fails_closed(changes):
    async def scenario():
        adapter = GatewayClient(
            settings(), transport=httpx.MockTransport(lambda req: response_for(req, **changes))
        )
        await adapter.start()
        with pytest.raises(GatewayFailure) as error:
            await adapter.complete(request())
        assert not error.value.retryable
        await adapter.close()

    asyncio.run(scenario())


@pytest.mark.parametrize("body", [b"not json", b"x" * 1048577])
def test_invalid_or_oversized_body_is_rejected(body):
    async def scenario():
        adapter = GatewayClient(
            settings(), transport=httpx.MockTransport(lambda req: httpx.Response(200, content=body))
        )
        await adapter.start()
        with pytest.raises(GatewayFailure):
            await adapter.complete(request())
        await adapter.close()

    asyncio.run(scenario())


def test_transport_error_and_total_attempt_timeout_are_sanitized():
    async def transport_error(req):
        raise httpx.ConnectError("private source " + TOKEN)

    async def hang(req):
        await asyncio.Event().wait()

    async def scenario():
        for handler in (transport_error, hang):
            adapter = GatewayClient(
                settings(cloud_timeout_s=0.02), transport=httpx.MockTransport(handler)
            )
            await adapter.start()
            with pytest.raises(GatewayFailure) as error:
                await adapter.complete(request())
            assert error.value.retryable
            assert str(error.value) == "Gateway request failed"
            await adapter.close()

    asyncio.run(scenario())


def test_unstarted_disabled_local_and_closed_client_never_sends():
    def forbidden(req):
        raise AssertionError("Cloud request must not occur")

    async def scenario():
        for configured in (settings(), settings(cloud_enabled=False), settings(profile="local")):
            adapter = GatewayClient(configured, transport=httpx.MockTransport(forbidden))
            with pytest.raises(GatewayFailure):
                await adapter.complete(request())
            await adapter.start()
            if not configured.cloud_enabled or configured.profile == "local":
                with pytest.raises(GatewayFailure):
                    await adapter.complete(request())
            await adapter.close()
            with pytest.raises(GatewayFailure):
                await adapter.complete(request())

    asyncio.run(scenario())


def test_approval_snapshot_copies_schema_and_produces_stable_bytes():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    original = replace(request(), json_schema=schema)
    frozen, preview = snapshot(original)
    schema["properties"].clear()
    assert frozen.json_schema["properties"]["name"]["type"] == "string"
    from agent.llm.wire import encode_request

    assert encode_request(frozen).decode() == preview
    assert "<data>" in preview  # Instructions visible in the exact approved JSON.


def test_health_probe_contacts_endpoint_without_task_data_or_credentials():
    calls = []

    def handle(req):
        calls.append(req)
        return httpx.Response(200, json={"status": "ok"})

    async def scenario():
        adapter = GatewayClient(settings(), transport=httpx.MockTransport(handle))
        assert not await adapter.is_online()
        await adapter.start()
        assert await adapter.is_online()
        assert str(calls[0].url) == "https://gateway.invalid/health"
        assert calls[0].method == "GET"
        assert not calls[0].content
        assert "authorization" not in calls[0].headers
        await adapter.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "status,body",
    [
        (503, b"private"),
        (307, b"redirect"),
        (200, b"not json"),
        (200, b"x" * 1025),
        (200, b'{"status":"wrong"}'),
    ],
)
def test_unhealthy_probe_returns_false(status, body):
    async def scenario():
        adapter = GatewayClient(
            settings(),
            transport=httpx.MockTransport(lambda req: httpx.Response(status, content=body)),
        )
        await adapter.start()
        assert not await adapter.is_online()
        await adapter.close()

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "change",
    [
        {"max_tokens": 0},
        {"temperature": float("nan")},
        {"client_request_id": "invalid"},
        {"messages": (ModelMessage("user", "x" * 65536),)},
    ],
)
def test_invalid_request_is_rejected_before_transport(change):
    async def scenario():
        adapter = GatewayClient(
            settings(),
            transport=httpx.MockTransport(lambda req: pytest.fail("invalid input must not send")),
        )
        await adapter.start()
        with pytest.raises(GatewayFailure):
            await adapter.complete(replace(request(), **change))
        await adapter.close()

    asyncio.run(scenario())
