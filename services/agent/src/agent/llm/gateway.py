"""One gateway HTTP attempt. Approval, retries and overall deadline live in CloudFlow."""

from __future__ import annotations

import asyncio
import json

import httpx
from pydantic import ValidationError

from agent.config import Settings
from agent.interfaces.models import ModelRequest, ModelResponse
from agent.llm.wire import Response, encode_request


class GatewayFailure(RuntimeError):
    def __init__(self, *, retryable: bool) -> None:
        super().__init__("Gateway request failed")
        self.retryable = retryable


class GatewayClient:
    """Implements LLMAdapter. Lifecycle prepares the client without contacting a server."""

    def __init__(
        self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self.settings, self._transport = settings, transport
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        if self._client is not None:
            return
        if self.settings.gateway_url is None or self.settings.install_token is None:
            raise ValueError("Gateway URL and installation token are required")
        self._client = httpx.AsyncClient(
            transport=self._transport,
            trust_env=False,
            follow_redirects=False,
            timeout=self.settings.cloud_timeout_s,
        )

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if (
            self._client is None
            or not self.settings.cloud_enabled
            or self.settings.profile != "hosted"
            or self.settings.gateway_url is None
            or self.settings.install_token is None
        ):
            raise GatewayFailure(retryable=False)
        try:
            body = encode_request(request)
            url = str(self.settings.gateway_url).rstrip("/") + "/v1/complete"
            # A total attempt bound supplements HTTPX's per-network-operation limits.
            async with asyncio.timeout(self.settings.cloud_timeout_s):
                async with self._client.stream(
                    "POST",
                    url,
                    content=body,
                    headers={
                        "Authorization": "Bearer " + self.settings.install_token.get_secret_value(),
                        "Content-Type": "application/json",
                    },
                ) as response:
                    if response.status_code != 200:
                        raise GatewayFailure(
                            retryable=response.status_code >= 500 or response.status_code == 408
                        )
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > 1048576:
                            raise GatewayFailure(retryable=False)
                        content.extend(chunk)
            parsed = Response.model_validate_json(bytes(content))
            # The gateway must correlate its reply to this particular request.
            if parsed.request_id != json.loads(body)["client_request_id"]:
                raise GatewayFailure(retryable=False)
            return ModelResponse(parsed.text, parsed.usage.input_tokens, parsed.usage.output_tokens)
        except (httpx.TransportError, TimeoutError):
            raise GatewayFailure(retryable=True) from None
        except httpx.HTTPError:
            raise GatewayFailure(retryable=False) from None
        except (ValidationError, ValueError, TypeError):
            raise GatewayFailure(retryable=False) from None

    async def is_online(self) -> bool:
        """Network interface: probe the real gateway endpoint, sending no task data/token."""
        if self._client is None or self.settings.gateway_url is None:
            return False
        try:
            url = str(self.settings.gateway_url).rstrip("/") + "/health"
            async with asyncio.timeout(min(2.0, self.settings.cloud_timeout_s)):
                async with self._client.stream("GET", url) as response:
                    if response.status_code != 200:
                        return False
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(content) + len(chunk) > 1024:
                            return False
                        content.extend(chunk)
            return bool(json.loads(content) == {"status": "ok"})
        except (httpx.HTTPError, TimeoutError, ValueError):
            return False

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            await client.aclose()
