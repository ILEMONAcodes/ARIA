"""Authenticated local text transport. No model, provider or audio startup required."""

from __future__ import annotations

import asyncio
import hmac
import re
from datetime import tzinfo
from typing import Any

import anyio
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import TypeAdapter

from agent.config import Settings
from agent.contracts.events import AgentEvent, UIEvent
from agent.interfaces import Clock
from agent.mock.scenarios import check_version
from agent.planner.keywords import KeywordPlanner
from agent.router.executor import PlanExecutor
from agent.router.session import LocalSession
from agent.tools.base import ToolRegistry
from agent.tools.runner import ToolRunner

_ui: TypeAdapter[Any] = TypeAdapter(UIEvent)


class OfflineNetwork:
    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def is_online(self) -> bool:
        return False


def create_app(
    settings: Settings,
    *,
    token: str,
    registry: ToolRegistry,
    apps: dict[str, tuple[str, ...]],
    clock: Clock,
    time_zone: tzinfo,
    runner: ToolRunner | None = None,
    allowed_origins: tuple[str, ...] = (),
) -> FastAPI:
    if re.fullmatch(r"[a-zA-Z0-9_-]{16,}", token) is None or "*" in allowed_origins:
        raise ValueError("Choose a session token and explicit origins")
    app = FastAPI(title="ARIA local commands", docs_url=None, redoc_url=None, openapi_url=None)
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_methods=["GET"],
            allow_headers=["Authorization"],
        )
    owner = asyncio.Lock()

    def authorized(value: str) -> bool:
        return hmac.compare_digest(value.encode(), token.encode())

    @app.get("/api/health")
    def health(authorization: str | None = Header(default=None)) -> dict[str, str]:
        if (
            not authorization
            or not authorization.startswith("Bearer ")
            or not authorized(authorization[7:])
        ):
            raise HTTPException(401, "Unauthorized")
        return {"status": "ok", "mode": "local-commands"}

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        origin = socket.headers.get("origin")
        if (
            not authorized(socket.query_params.get("token", ""))
            or owner.locked()
            or origin is not None
            and origin not in allowed_origins
        ):
            await socket.close(code=1008)
            return
        async with owner:
            await socket.accept()
            queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=128)

            async def emit(event: AgentEvent) -> None:
                await queue.put(event)

            executor = PlanExecutor(registry, settings, OfflineNetwork(), emit, runner=runner)
            matcher = KeywordPlanner(
                registry,
                apps=apps,
                clock=clock,
                time_zone=time_zone,
                confidence_threshold=settings.confidence_threshold,
            )
            session = LocalSession(matcher, executor, emit)

            async def send() -> None:
                while True:
                    await socket.send_json(
                        (await queue.get()).model_dump(mode="json", exclude_none=True)
                    )

            async def receive() -> None:
                while True:
                    raw = await socket.receive_json()
                    if (
                        raw.get("type") == "source.open"
                        and raw.get("page") is not None
                        and type(raw["page"]) is not int
                    ):
                        raise ValueError("Source page must be an integer")
                    await session.handle(_ui.validate_python(check_version(raw)))

            workers: list[asyncio.Task[None]] = []
            try:
                await session.start()
                workers = [asyncio.create_task(send()), asyncio.create_task(receive())]
                done, _ = await asyncio.wait(workers, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            except (WebSocketDisconnect, asyncio.CancelledError):
                pass
            except (ValueError, KeyError):
                await socket.close(code=1008, reason="Invalid UI event")
            finally:
                with anyio.CancelScope(shield=True):
                    # Discard cleanup events instead of blocking on a disconnected full queue.
                    async def discard(event: AgentEvent) -> None:
                        pass

                    executor.emit = discard
                    session.emit = discard
                    for task in workers:
                        task.cancel()
                    await asyncio.gather(*workers, return_exceptions=True)
                    await session.close()

    return app
