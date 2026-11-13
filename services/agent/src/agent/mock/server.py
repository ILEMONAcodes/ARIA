"""Mock agent: replays scenario files so the frontend never waits for the backend.

A scenario is JSON: {"name": "...", "steps": [...]}. Each step is one of:
  {"send": {<agent event>}, "delay_ms": 300}      the mock sends this event to the UI
  {"wait_for": "confirm.response"}               the mock waits for this UI event type
Run: python -m agent.mock --scenario policy_question
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from pydantic import TypeAdapter

from agent.contracts.events import AgentEvent, UIEvent

SCENARIO_DIR = Path(__file__).resolve().parents[5] / "tests" / "e2e" / "scenarios"
_agent_adapter: TypeAdapter[Any] = TypeAdapter(AgentEvent)
_ui_adapter: TypeAdapter[Any] = TypeAdapter(UIEvent)


def load_scenario(name: str, directory: Path = SCENARIO_DIR) -> dict[str, Any]:
    data = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
    for step in data["steps"]:
        if "send" in step:
            _agent_adapter.validate_python(step["send"])  # fail early on bad scenarios
    return data  # type: ignore[no-any-return]


def create_app(scenario: dict[str, Any]) -> FastAPI:
    app = FastAPI(title="ARIA mock agent")

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "mode": "mock", "scenario": scenario["name"]}

    @app.websocket("/ws")
    async def ws(socket: WebSocket) -> None:
        await socket.accept()
        try:
            for step in scenario["steps"]:
                if "send" in step:
                    await asyncio.sleep(step.get("delay_ms", 0) / 1000)
                    await socket.send_json(step["send"])
                elif "wait_for" in step:
                    while True:
                        msg = await socket.receive_json()
                        _ui_adapter.validate_python(msg)  # UI must obey the contract too
                        if msg["type"] == step["wait_for"]:
                            break
            await socket.close()
        except WebSocketDisconnect:
            return

    return app
