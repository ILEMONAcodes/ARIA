"""Session-owned local execution and approved gateway-plan handoff."""

from __future__ import annotations

import asyncio

from agent.contracts.events import ErrorEvent, ReplyText, TranscriptFinal, UIEvent
from agent.interfaces import KeywordMatcher
from agent.interfaces.models import ModelRequest
from agent.llm.flow import CloudFlow
from agent.router.executor import Emit, ExecutionEngine


class LocalSession:
    def __init__(
        self,
        matcher: KeywordMatcher,
        executor: ExecutionEngine,
        emit: Emit,
        *,
        cloud: CloudFlow | None = None,
    ) -> None:
        self.matcher, self.executor, self.emit, self.cloud = matcher, executor, emit, cloud
        self._lock = asyncio.Lock()
        self._epoch = 0
        self._closed = False
        self._submission: asyncio.Task[str | None] | None = None
        self._handoff: asyncio.Task[None] | None = None

    async def start(self) -> None:
        await self.executor.status(False)

    def _cloud_allowed(self) -> bool:
        return self.cloud is not None and all(
            settings.profile == "hosted" and settings.cloud_enabled
            for settings in (self.executor.settings, self.cloud.settings)
        )

    async def _stop(self, *, announce: bool = False) -> None:
        """Called under the transition lock; observers never take that lock."""
        self._epoch += 1
        tasks = [task for task in (self._submission, self._handoff) if task is not None]
        self._submission = self._handoff = None
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if self.cloud is not None:
            await self.cloud.cancel(announce=False)
        # Join the observer first: it cannot start a tool after this cancellation.
        await self.executor.cancel(announce=announce)

    async def _consume_cloud(self, epoch: int) -> None:
        assert self.cloud is not None
        try:
            outcome = await self.cloud.wait()
            if self._closed or epoch != self._epoch:
                return
            if (
                outcome is None
                or outcome.kind != "completed"
                or outcome.review is None
                or outcome.review.requires_clarification
            ):
                return
            if not self._cloud_allowed():
                await self.emit(
                    ErrorEvent(code="cloud_disabled", message="Cloud plan execution is disabled.")
                )
                await self.executor.status(False)
                return
            # The executor copies and revalidates against its own current registry.
            # Payload approval never substitutes for individual tool confirmation.
            await self.executor.submit(outcome.review.plan)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - no model/tool arguments in diagnostics
            await self.emit(
                ErrorEvent(code="cloud_handoff_failed", message="The cloud plan could not start.")
            )
            await self.executor.cancel()

    async def handle(self, event: UIEvent) -> None:
        async with self._lock:
            if self._closed:
                return
            if event.type == "confirm.response":
                await self.executor.confirm(event)
            elif event.type == "approval.response" and self.cloud is not None:
                if await self.cloud.approve(event):
                    self._handoff = asyncio.create_task(self._consume_cloud(self._epoch))
            elif event.type == "task.cancel":
                cloud_id = self.cloud.task_id if self.cloud is not None else None
                if event.task_id in {self.executor.task_id, cloud_id}:
                    await self._stop(announce=True)
            elif event.type == "tts.stop":
                await self._stop(announce=True)
            elif event.type == "source.open":
                await self._stop()
                await self.executor.open_source(event)
            elif event.type == "text.input":
                await self._stop()
                await self.emit(TranscriptFinal(text=event.text))
                result = self.matcher.match(event.text)
                if result.kind == "cancel":
                    await self.executor.status(False)
                elif result.kind == "plan" and result.plan is not None:
                    await self.executor.submit(result.plan)
                else:
                    text = (
                        result.question
                        if result.kind == "clarify"
                        else "That command is not available locally yet."
                    )
                    await self.emit(
                        ReplyText(
                            task_id="local-request", text=text or "Could you clarify?", spoken=False
                        )
                    )
                    await self.executor.status(False)
            else:
                await self.emit(
                    ErrorEvent(
                        code="unsupported_event",
                        message="This local session accepts text commands and confirmations.",
                    )
                )

    async def request_cloud(self, request: ModelRequest) -> str | None:
        # An explicit trusted assembly boundary, never an unknown-text upload.
        async with self._lock:
            if self._closed:
                return None
            await self._stop()
            if not self._cloud_allowed():
                await self.emit(
                    ErrorEvent(
                        code="cloud_disabled",
                        message="Cloud requests are disabled in this session.",
                    )
                )
                return None
            assert self.cloud is not None
            # Connectivity can take time. Keep it cancellable without holding the lock.
            task = self._submission = asyncio.create_task(self.cloud.submit(request))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            caller = asyncio.current_task()
            if caller is not None and caller.cancelling():
                # Revoke only this caller's request, never a newer replacement.
                async with self._lock:
                    if self._submission is task:
                        await self._stop(announce=True)
                raise
            return None  # The session cancelled/replaced the owned submission.

    async def wait(self) -> None:
        """Wait for the current approved result handoff (not tool confirmation)."""
        if self._handoff is not None:
            await asyncio.shield(self._handoff)

    async def cancel(self) -> None:
        async with self._lock:
            await self._stop(announce=True)

    async def close(self) -> None:
        async with self._lock:
            self._closed = True
            await self._stop()
            if self.cloud is not None:
                await self.cloud.close()
            await self.executor.close()
