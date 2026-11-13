"""Mock agent: replays scenario files so the frontend never waits for the backend.

A scenario is JSON: {"name": "...", "steps": [...]}. Each step is one of:
  {"send": {<agent event>}, "delay_ms": 300}      the mock sends this event to the UI
  {"wait_for": "confirm.response"}               the mock waits for this UI event type
Run: python -m agent.mock --scenario policy_question
"""

from __future__ import annotations

import asyncio
import hmac
import math
import re
from typing import Any

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import TypeAdapter

from agent.contracts.events import UIEvent
from agent.mock.scenarios import (
    SCENARIO_DIR,
    SendStep,
    check_version,
    load_scenario,
    validate_scenario,
)

_ui_adapter: TypeAdapter[Any] = TypeAdapter(UIEvent)
__all__ = ["SCENARIO_DIR", "create_app", "load_scenario"]


def create_app(
    scenario: dict[str, Any],
    *,
    token: str,
    delay_scale: float = 1,
    allowed_origins: tuple[str, ...] = (),
) -> FastAPI:
    if re.fullmatch(r"[a-zA-Z0-9_-]{16,}", token) is None:
        raise ValueError("A URL-safe mock session token of at least 16 characters is required")
    if not math.isfinite(delay_scale) or delay_scale < 0:
        raise ValueError("A finite nonnegative delay scale is required")
    replay = validate_scenario(scenario)
    app = FastAPI(title="ARIA mock agent", docs_url=None, redoc_url=None, openapi_url=None)
    if "*" in allowed_origins:
        raise ValueError("Choose explicit UI origins")
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
            raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})
        return {"status": "ok", "mode": "mock", "scenario": replay.name}

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        if not authorized(socket.query_params.get("token", "")):
            await socket.close(code=1008)
            return
        await socket.accept()
        try:
            for step in replay.steps:
                if isinstance(step, SendStep):
                    await asyncio.sleep(step.delay_ms * delay_scale / 1000)
                    await socket.send_json(step.send.model_dump(mode="json", exclude_none=True))
                else:
                    while True:
                        try:
                            raw = await socket.receive_json()
                            message = _ui_adapter.validate_python(check_version(raw))
                        except (ValueError, KeyError):
                            await socket.close(code=1008, reason="Invalid or unsupported UI event")
                            return
                        if message.type == "task.cancel":
                            await socket.close()
                            return
                        if message.type != step.wait_for:
                            continue
                        payload = message.model_dump(mode="json", exclude_none=True)
                        if step.match is None:
                            break
                        expected = step.match.model_dump(mode="json", exclude_none=True)
                        if message.type in {"approval.response", "confirm.response"}:
                            identifier = (
                                "approval_id"
                                if message.type == "approval.response"
                                else "confirm_id"
                            )
                            if payload.get(identifier) != expected.get(identifier):
                                continue
                            if payload.get("decision") == "no":
                                await socket.close()
                                return
                            # Click and key are both explicit on-screen approvals.
                            if message.type == "confirm.response":
                                payload.pop("via", None)
                                expected.pop("via", None)
                        if payload == expected:
                            break
            await socket.close()
        except WebSocketDisconnect:
            return

    return app
