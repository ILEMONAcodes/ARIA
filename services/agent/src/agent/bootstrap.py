"""Foundation lifecycle: configuration, diagnostics, storage and injected adapters.

No actions, cloud calls or microphone reads occur during startup. Native voice
and planner adapters are added in their phases; fakes are always explicit.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from agent.config import Settings, load_settings
from agent.interfaces import Clock, DatabaseKeyProvider, LocalStore, ModuleAdapters
from agent.logging_config import configure_logging
from agent.security.keys import OSVaultKeyProvider
from agent.store.local import SqlCipherStore
from agent.store.retention import timestamp_us
from agent.tools.base import ToolRegistry


class StartupError(RuntimeError):
    """A safe lifecycle failure message without user content or credentials."""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


@dataclass(frozen=True)
class AgentRuntime:
    settings: Settings
    store: LocalStore
    adapters: ModuleAdapters | None
    tools: ToolRegistry


async def _stop_worker(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _retention_worker(
    store: LocalStore,
    clock: Clock,
    sleep: Callable[[float], Awaitable[None]],
    interval: float,
    logger: logging.Logger,
) -> None:
    while True:
        await sleep(interval)
        try:
            store.purge(now=clock.now())
            logger.info("Retention complete", extra={"event": "operation.completed"})
        except Exception:  # noqa: BLE001 - native/store errors must never leak into logs
            logger.error("Retention failed", extra={"event": "operation.failed"})


@asynccontextmanager
async def start_agent(
    settings_file: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    store: LocalStore | None = None,
    keys: DatabaseKeyProvider | None = None,
    adapters: ModuleAdapters | None = None,
    clock: Clock | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    retention_interval_s: float = 86400,
    log_stream: TextIO | None = None,
) -> AsyncIterator[AgentRuntime]:
    """Own resources until context exit, including partial starts and cancellation.

    open performs initial retention. A background task repeats it at least daily.
    SQLite stays on this event-loop thread. No automatic fake/network fallback
    exists. Unavailable voice/model adapters remain absent in foundation mode.
    """
    logger = configure_logging(stream=log_stream)
    try:
        if not math.isfinite(retention_interval_s) or not 0 < retention_interval_s <= 86400:
            raise ValueError("Retention interval must be positive and at most one day")
        settings = load_settings(settings_file, environ=environ)
        logger.setLevel(settings.log_level)
        logger.info("Settings loaded", extra={"event": "settings.loaded"})
        selected_clock = clock if clock is not None else SystemClock()
        now = selected_clock.now()
        timestamp_us(now)  # Validate before opening files or accessing a vault.
        selected_store = (
            store
            if store is not None
            else SqlCipherStore(
                settings.db_path, keys if keys is not None else OSVaultKeyProvider()
            )
        )
        async with AsyncExitStack() as resources:
            resources.callback(selected_store.close)
            selected_store.open(now=now)
            if adapters is not None:
                started: set[int] = set()
                for component in adapters.components():
                    if id(component) in started:
                        continue
                    started.add(id(component))
                    resources.push_async_callback(component.close)
                    await component.start()
            worker = asyncio.create_task(
                _retention_worker(
                    selected_store, selected_clock, sleep, retention_interval_s, logger
                ),
                name="aria-retention",
            )
            resources.push_async_callback(_stop_worker, worker)
            runtime = AgentRuntime(settings, selected_store, adapters, ToolRegistry())
            logger.info("Foundations started", extra={"event": "component.started"})
            yield runtime
        logger.info("Foundations stopped", extra={"event": "component.stopped"})
    except Exception:  # noqa: BLE001 - sanitize settings, native and adapter failures
        logger.error("Agent lifecycle failed", extra={"event": "operation.failed"})
        raise StartupError(
            "Agent lifecycle failed; check configuration, storage and adapters"
        ) from None
