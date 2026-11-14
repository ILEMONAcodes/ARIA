"""Session-owned approval and bounded retry/fallback orchestration; no tool execution."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from agent.config import Settings
from agent.contracts.events import (
    CONTRACT_VERSION,
    ActivityEntry,
    AgentEvent,
    ApprovalResponse,
    CloudApprovalRequest,
    ErrorEvent,
    PlanPreview,
    ReplyText,
    Status,
)
from agent.interfaces import LLMAdapter, Network
from agent.interfaces.models import ModelRequest, ModelResponse
from agent.llm.gateway import GatewayFailure
from agent.llm.wire import snapshot
from agent.planner.validation import PlanReview, PlanValidationError, validate_plan
from agent.tools.base import ToolRegistry

Emit = Callable[[AgentEvent], Awaitable[None]]


@dataclass(frozen=True)
class CloudOutcome:
    kind: Literal["completed", "clarify", "fallback", "declined", "cancelled"]
    response: ModelResponse | None = field(default=None, repr=False)
    review: PlanReview | None = field(default=None, repr=False)


@dataclass(frozen=True)
class Pending:
    approval_id: str
    task_id: str
    request: ModelRequest = field(repr=False)


class CloudFlow:
    """One instance per authenticated desktop session; adapters are lifecycle-owned outside."""

    def __init__(
        self,
        settings: Settings,
        adapter: LLMAdapter,
        network: Network,
        emit: Emit,
        *,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.settings, self.adapter, self.network, self.emit = settings, adapter, network, emit
        self.registry = registry if registry is not None else ToolRegistry()
        self._pending: Pending | None = None
        self._task: asyncio.Task[CloudOutcome] | None = None
        self._epoch = 0
        self.task_id: str | None = None

    def _allowed(self) -> bool:
        return self.settings.profile == "hosted" and self.settings.cloud_enabled

    async def _status(self, *, busy: bool, online: bool) -> None:
        await self.emit(
            Status(
                state="thinking" if busy else "idle", online=online, profile=self.settings.profile
            )
        )

    async def submit(self, request: ModelRequest) -> str | None:
        await self.cancel(announce=False)
        epoch = self._epoch
        task_id = str(uuid4())
        self.task_id = task_id
        if not self._allowed():
            await self._fallback(
                task_id, "cloud_disabled", "Cloud use is disabled for this profile."
            )
            return None
        try:
            online = await asyncio.wait_for(self.network.is_online(), self.settings.cloud_timeout_s)
        except Exception:  # noqa: BLE001 - network diagnostics must not expose private content
            online = False
        if epoch != self._epoch:
            return None
        if not online:
            await self._fallback(task_id, "cloud_offline", "The cloud connection is unavailable.")
            return None
        try:
            frozen, preview = snapshot(request)
        except (ValueError, TypeError, RecursionError, OSError):
            await self.emit(
                ErrorEvent(
                    code="invalid_cloud_request",
                    message="This request cannot be sent to the gateway.",
                )
            )
            await self._status(busy=False, online=True)
            return None
        approval_id = str(uuid4())
        self._pending = Pending(approval_id, task_id, frozen)
        await self.emit(CloudApprovalRequest(approval_id=approval_id, payload_preview=preview))
        return approval_id

    async def approve(self, response: ApprovalResponse) -> bool:
        pending = self._pending
        if (
            pending is None
            or pending.approval_id != response.approval_id
            or response.v != CONTRACT_VERSION
            or response.decision not in {"yes", "no"}
        ):
            return False
        self._pending = None  # Consume before scheduling: no replay/double-submit.
        if response.decision == "no":
            self._task = asyncio.create_task(self._declined())
            await self.emit(
                ReplyText(
                    task_id=pending.task_id,
                    text="Okay, I won't send this request to the cloud.",
                    spoken=False,
                )
            )
            await self._status(busy=False, online=True)
            return True
        self._task = asyncio.create_task(self._run(pending, self._epoch))
        return True

    async def _declined(self) -> CloudOutcome:
        return CloudOutcome("declined")

    async def wait(self) -> CloudOutcome | None:
        return await asyncio.shield(self._task) if self._task is not None else None

    async def _run(self, pending: Pending, epoch: int) -> CloudOutcome:
        await self._status(busy=True, online=True)
        budget = self.settings.cloud_timeout_s
        invalid_plan = False
        rephrase = False
        result: ModelResponse | None = None
        review: PlanReview | None = None
        blocked: tuple[str, str] | None = None
        try:
            # Only the request/retry work is timed; a slow UI cannot turn a successful
            # response into a fictitious gateway failure during final event delivery.
            async with asyncio.timeout(budget):
                for attempt in range(2):
                    if not self._allowed():
                        blocked = ("cloud_disabled", "Cloud use is disabled for this profile.")
                        break
                    if not await self.network.is_online():
                        blocked = ("cloud_offline", "The cloud connection is unavailable.")
                        break
                    try:
                        result = await asyncio.wait_for(
                            self.adapter.complete(pending.request), budget / 2
                        )
                        if pending.request.task == "plan":
                            review = validate_plan(
                                result.text,
                                self.registry,
                                confidence_threshold=self.settings.confidence_threshold,
                            )
                        break
                    except PlanValidationError:
                        result = None
                        invalid_plan = True
                        if attempt:
                            rephrase = True
                            break
                    except GatewayFailure as exc:
                        if not exc.retryable:
                            blocked = (
                                "cloud_rejected",
                                "The gateway could not complete this request.",
                            )
                            break
                        if attempt:
                            break
                    except (TimeoutError, OSError):
                        if attempt:
                            break
                    if not attempt:
                        await self.emit(
                            ReplyText(
                                task_id=pending.task_id,
                                text=(
                                    "The plan was invalid. Retrying once."
                                    if invalid_plan
                                    else "The cloud did not answer. Retrying once."
                                ),
                                spoken=False,
                            )
                        )
                        await asyncio.sleep(min(0.1, budget * 0.05))
        except TimeoutError:
            pass
        except Exception:  # noqa: BLE001 - adapter/network errors must never expose private content
            result = None
        if epoch != self._epoch:
            return CloudOutcome("cancelled")
        if blocked is not None:
            return await self._fallback(pending.task_id, *blocked)
        if result is not None:
            return await self._success(pending.task_id, result, review)
        if rephrase:
            await self.emit(
                ReplyText(
                    task_id=pending.task_id,
                    text="I could not make a valid plan. Could you rephrase your request?",
                    spoken=False,
                )
            )
            await self._status(busy=False, online=True)
            return CloudOutcome("clarify")
        return await self._fallback(
            pending.task_id, "cloud_unreachable", "The cloud model did not answer."
        )

    async def _success(
        self, task_id: str, response: ModelResponse, review: PlanReview | None
    ) -> CloudOutcome:
        kind: Literal["completed", "clarify"] = "completed"
        if review is None:
            await self.emit(ReplyText(task_id=task_id, text=response.text, spoken=False))
        elif review.requires_clarification:
            kind = "clarify"
            await self.emit(
                ReplyText(
                    task_id=task_id,
                    text="Could you rephrase your request with the missing details?",
                    spoken=False,
                )
            )
        else:
            await self.emit(
                PlanPreview(task_id=task_id, summary="Plan prepared; no actions have run.")
            )
        await self.emit(
            ActivityEntry(
                id=str(uuid4()),
                ts=datetime.now(UTC).isoformat(),
                text="Cloud response received; no actions were run.",
                undoable=False,
            )
        )
        await self._status(busy=False, online=True)
        return CloudOutcome(kind, response, review)

    async def _fallback(self, task_id: str, code: str, message: str) -> CloudOutcome:
        await self.emit(ErrorEvent(code=code, message=message))
        await self.emit(
            ReplyText(
                task_id=task_id,
                text="Try a local command, or retry this cloud request later.",
                spoken=False,
            )
        )
        await self.emit(
            ActivityEntry(
                id=str(uuid4()),
                ts=datetime.now(UTC).isoformat(),
                text="Cloud request failed; no actions were run.",
                undoable=False,
            )
        )
        await self._status(busy=False, online=False)
        return CloudOutcome("fallback")

    async def cancel(self, *, announce: bool = True) -> None:
        self._epoch += 1
        self.task_id = None
        self._pending = None
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if announce:
            await self._status(busy=False, online=False)

    async def close(self) -> None:
        await self.cancel(announce=False)
