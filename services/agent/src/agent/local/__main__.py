"""Run the offline local command service; no speech models or provider setup."""

import argparse
import asyncio
import os
import secrets
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn

from agent.config import Settings, load_settings
from agent.contracts.events import AgentEvent, ConfirmResponse, TextInput
from agent.local.config import load_tools
from agent.local.server import OfflineNetwork, create_app
from agent.planner.keywords import KeywordPlanner
from agent.router.executor import PlanExecutor
from agent.router.session import LocalSession
from agent.tools.base import ToolRegistry
from agent.tools.runner import ToolRunner


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


async def run_command(
    settings: Settings,
    registry: ToolRegistry,
    apps: dict[str, tuple[str, ...]],
    zone: ZoneInfo,
    command: str,
    *,
    runner: ToolRunner | None = None,
) -> bool:

    async def emit(event: AgentEvent) -> None:
        if event.type == "confirm.request":
            print("Confirmation requires the connected UI; this step was declined.", flush=True)
            await executor.confirm(
                ConfirmResponse(confirm_id=event.confirm_id, decision="no", via="key")
            )
        elif event.type in {"reply.text", "activity.entry"}:
            print(event.text, flush=True)
        elif event.type == "error":
            print(event.message, file=sys.stderr, flush=True)

    executor = PlanExecutor(registry, settings, OfflineNetwork(), emit, runner=runner)
    session = LocalSession(
        KeywordPlanner(registry, apps=apps, clock=SystemClock(), time_zone=zone), executor, emit
    )
    try:
        await session.handle(TextInput(text=command))
        outcome = await executor.wait()
        return outcome is not None and outcome.kind == "completed"
    finally:
        await session.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, required=True)
    parser.add_argument("--settings", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-origin", action="append", default=[])
    parser.add_argument("--command", help="Run one local text command without starting a server")
    args = parser.parse_args()
    try:
        settings = load_settings(args.settings).model_copy(update={"cloud_enabled": False})
        registry, apps, zone = load_tools(args.tools)
        if args.command is not None:
            completed = asyncio.run(run_command(settings, registry, apps, zone, args.command))
            return 0 if completed else 1
        token = os.environ.get("ARIA_SESSION_TOKEN") or secrets.token_urlsafe(32)
        app = create_app(
            settings,
            token=token,
            registry=registry,
            apps=apps,
            clock=SystemClock(),
            time_zone=zone,
            allowed_origins=tuple(args.allow_origin),
        )
    except (ValueError, OSError):
        parser.exit(1, "Local startup failed. Check settings and configured tool paths.\n")
    print(f"ARIA local commands: ws://127.0.0.1:{args.port}/ws?token={token}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="critical")
    return 0


if __name__ == "__main__":
    sys.exit(main())
