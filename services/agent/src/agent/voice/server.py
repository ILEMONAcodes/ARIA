"""The real voice transport reuses the v1 UI contract, with one microphone owner."""

from __future__ import annotations

import asyncio
import hmac
import re
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, Literal

import anyio
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import TypeAdapter

from agent.audio.pipeline import VoiceLoop
from agent.contracts.events import AgentEvent, UIEvent
from agent.interfaces import (
    AudioInput,
    Speaker,
    SpeechToText,
    VoiceActivityDetector,
    WakeWordDetector,
)
from agent.mock.scenarios import check_version

_ui: TypeAdapter[Any] = TypeAdapter(UIEvent)


def create_app(
    *,
    token: str,
    audio: AudioInput,
    vad: VoiceActivityDetector,
    stt: SpeechToText,
    speaker: Speaker,
    wake: WakeWordDetector | None = None,
    silence_ms: int = 700,
    profile: Literal["hosted", "local"] = "hosted",
    allowed_origins: tuple[str, ...] = (),
) -> FastAPI:
    if re.fullmatch(r"[a-zA-Z0-9_-]{16,}", token) is None:
        raise ValueError("A URL-safe session token of at least 16 characters is required")
    if "*" in allowed_origins:
        raise ValueError("Choose explicit UI origins")
    owner = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            for component in (stt, speaker, vad, wake, audio):
                if component is not None:
                    stack.push_async_callback(component.close)
                    await component.start()
            yield

    app = FastAPI(
        title="ARIA offline voice",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["GET"],
            allow_headers=["Authorization"],
        )

    def authorized(provided: str) -> bool:
        return hmac.compare_digest(provided.encode(), token.encode())

    @app.get("/api/health")
    def health(authorization: str | None = Header(default=None)) -> dict[str, str]:
        if (
            not authorization
            or not authorization.startswith("Bearer ")
            or not authorized(authorization[7:])
        ):
            raise HTTPException(401, "Unauthorized")
        return {"status": "ok", "mode": "voice-echo"}

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        origin = socket.headers.get("origin")
        if (
            not authorized(socket.query_params.get("token", ""))
            or (origin is not None and origin not in allowed_origins)
            or owner.locked()
        ):
            await socket.close(code=1008)
            return
        async with owner:
            await socket.accept()
            queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=128)

            async def emit(event: AgentEvent) -> None:
                await queue.put(event)

            loop = VoiceLoop(
                audio, vad, stt, speaker, emit, wake=wake, silence_ms=silence_ms, profile=profile
            )

            async def send() -> None:
                while True:
                    event = await queue.get()
                    await socket.send_json(event.model_dump(mode="json", exclude_none=True))

            async def receive() -> None:
                while True:
                    raw = await socket.receive_json()
                    await loop.handle(_ui.validate_python(check_version(raw)))

            workers: list[asyncio.Task[None]] = []
            try:
                await loop.start()
                workers = [asyncio.create_task(send()), asyncio.create_task(receive())]
                done, _ = await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
            except (ValueError, KeyError):
                await socket.close(code=1008, reason="Invalid or unsupported UI event")
            finally:
                # ASGI disconnect/shutdown may cancel the route's AnyIO scope.
                # Cleanup must still stop capture before releasing ownership.
                with anyio.CancelScope(shield=True):
                    for task in workers:
                        task.cancel()
                    await asyncio.gather(*workers, return_exceptions=True)
                    await loop.close()

    return app
