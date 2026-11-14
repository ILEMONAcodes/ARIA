"""Route validated UI requests to local planning/execution or explicit approved cloud flow."""

from __future__ import annotations

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

    async def start(self) -> None:
        await self.executor.status(False)

    async def handle(self, event: UIEvent) -> None:
        if event.type == "confirm.response":
            await self.executor.confirm(event)
        elif event.type == "approval.response" and self.cloud is not None:
            await self.cloud.approve(event)
        elif event.type == "task.cancel":
            if event.task_id == self.executor.task_id:
                await self.executor.cancel()
        elif event.type == "tts.stop":
            await self.cancel()
        elif event.type == "text.input":
            await self.executor.cancel(announce=False)
            if self.cloud is not None:
                await self.cloud.cancel(announce=False)
            await self.emit(TranscriptFinal(text=event.text))
            result = self.matcher.match(event.text)
            if result.kind == "cancel":
                await self.cancel()
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
        # An explicit assembly boundary, never an automatic unknown-text upload.
        settings = self.executor.settings
        if self.cloud is None or settings.profile == "local" or not settings.cloud_enabled:
            await self.emit(
                ErrorEvent(
                    code="cloud_disabled", message="Cloud requests are disabled in this session."
                )
            )
            return None
        return await self.cloud.submit(request)

    async def cancel(self) -> None:
        if self.cloud is not None:
            await self.cloud.cancel(announce=False)
        await self.executor.cancel()

    async def close(self) -> None:
        if self.cloud is not None:
            await self.cloud.close()
        await self.executor.close()
