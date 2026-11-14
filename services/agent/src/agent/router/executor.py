"""Session-owned execution: validation, per-step confirmation, timeout and cancellation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import uuid4

from agent.config import Settings
from agent.contracts.events import (
    CONTRACT_VERSION,
    ActivityEntry,
    AgentEvent,
    ConfirmRequest,
    ConfirmResponse,
    ErrorEvent,
    PlanPreview,
    ReplyText,
    ResultAnswer,
    Status,
)
from agent.contracts.plan import Plan
from agent.interfaces import Network
from agent.planner.references import resolve_args
from agent.planner.validation import PlanValidationError, validate_plan
from agent.tools.base import Tool, ToolRegistry, ToolSpec
from agent.tools.runner import Mode, ProcessToolRunner, ToolRunner

Emit = Callable[[AgentEvent], Awaitable[None]]


@dataclass(frozen=True)
class ExecutionOutcome:
    kind: Literal["completed", "clarify", "declined", "failed", "cancelled"]
    completed_steps: int = 0
    outputs: tuple[dict[str, Any], ...] = field(default=(), repr=False)


class ExecutionEngine(Protocol):
    settings: Settings
    task_id: str | None

    async def status(self, working: bool) -> None: ...
    async def submit(self, plan: Plan) -> str: ...
    async def confirm(self, response: ConfirmResponse) -> bool: ...
    async def wait(self) -> ExecutionOutcome | None: ...
    async def cancel(self, *, announce: bool = True) -> None: ...
    async def close(self) -> None: ...


class PlanExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        settings: Settings,
        network: Network,
        emit: Emit,
        *,
        runner: ToolRunner | None = None,
    ) -> None:
        self.registry, self.settings, self.network, self.emit = registry, settings, network, emit
        self.runner = runner if runner is not None else ProcessToolRunner()
        self.task_id: str | None = None
        self._task: asyncio.Task[ExecutionOutcome] | None = None
        self._confirmation: tuple[str, asyncio.Future[bool]] | None = None
        self._completed = 0
        self._running_step = False

    async def status(self, working: bool) -> None:
        await self.emit(
            Status(
                state="working" if working else "idle", online=False, profile=self.settings.profile
            )
        )

    async def submit(self, plan: Plan) -> str:
        await self.cancel(announce=False)
        self.task_id = str(uuid4())
        self._completed = 0
        # Never execute the caller's mutable Plan instance.
        try:
            review = validate_plan(
                plan, self.registry, confidence_threshold=self.settings.confidence_threshold
            )
        except PlanValidationError:
            await self.emit(ErrorEvent(code="invalid_plan", message="This plan cannot run."))
            await self.status(False)
            return self.task_id
        if review.requires_clarification:
            await self.emit(
                ReplyText(
                    task_id=self.task_id, spoken=False, text="Could you clarify your request?"
                )
            )
            await self.status(False)
            return self.task_id
        await self.emit(
            PlanPreview(
                task_id=self.task_id, summary=f"Run {len(review.plan.steps)} registered step(s)."
            )
        )
        self._task = asyncio.create_task(self._execute(review.plan, self.task_id))
        return self.task_id

    async def confirm(self, response: ConfirmResponse) -> bool:
        pending = self._confirmation
        if (
            pending is None
            or response.v != CONTRACT_VERSION
            or response.confirm_id != pending[0]
            or response.via not in {"click", "key"}
            or response.decision not in {"yes", "no"}
        ):
            return False
        self._confirmation = None
        if not pending[1].done():
            pending[1].set_result(response.decision == "yes")
        return True

    async def wait(self) -> ExecutionOutcome | None:
        return await asyncio.shield(self._task) if self._task is not None else None

    async def _activity(self, text: str) -> None:
        await self.emit(
            ActivityEntry(
                id=str(uuid4()), ts=datetime.now(UTC).isoformat(), text=text, undoable=False
            )
        )

    def _check_policy(self, tool: Tool[Any, Any], spec: ToolSpec) -> None:
        if (
            tool.name,
            tool.risk,
            tool.needs_network,
            tool.timeout_s,
            tool.input_model,
            tool.output_model,
        ) != (
            spec.name,
            spec.risk,
            spec.needs_network,
            spec.timeout_s,
            spec.input_model,
            spec.output_model,
        ):
            raise ValueError("Tool policy changed")

    async def _invoke(
        self, tool: Tool[Any, Any], args: dict[str, Any], mode: Mode, timeout: float
    ) -> Any:
        async with asyncio.timeout(timeout):
            return await self.runner.invoke(tool, args, mode=mode, timeout_s=timeout)

    async def _execute(self, plan: Plan, identifier: str) -> ExecutionOutcome:
        outputs: list[dict[str, Any]] = []
        await self.status(True)
        try:
            for step in plan.steps:
                spec = self.registry.spec(step.tool)
                tool = self.registry.get(step.tool)
                self._check_policy(tool, spec)
                resolved = resolve_args(step.args, outputs)
                args = self.registry.validate_args(step.tool, resolved).model_dump(mode="json")
                approved_args = json.dumps(args, sort_keys=True, allow_nan=False)
                risk = plan.risk if plan.risk != "none" else spec.risk
                if plan.needs_confirmation or risk != "none":
                    preview_args = deepcopy(args)
                    preview = await self._invoke(tool, preview_args, "dry_run", spec.timeout_s)
                    if json.dumps(preview_args, sort_keys=True, allow_nan=False) != approved_args:
                        raise ValueError("Dry run changed arguments")
                    if not isinstance(preview, str) or not preview.strip() or len(preview) > 16000:
                        raise ValueError("Invalid dry run")
                    confirmation = str(uuid4())
                    answer: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
                    self._confirmation = confirmation, answer
                    await self.emit(
                        ConfirmRequest(
                            confirm_id=confirmation,
                            task_id=identifier,
                            risk=risk if risk != "none" else "local_write",
                            dry_run_text=preview,
                            needs_click=True,
                        )
                    )
                    if not await answer:
                        await self._activity("Task declined; no further steps ran.")
                        return ExecutionOutcome("declined", self._completed, tuple(outputs))
                # Revalidate and recheck policy immediately before each step.
                self._check_policy(tool, spec)
                checked = self.registry.validate_args(step.tool, args).model_dump(mode="json")
                if json.dumps(checked, sort_keys=True, allow_nan=False) != approved_args:
                    raise ValueError("Arguments changed after preview")
                if (spec.needs_network or plan.needs_network) and not await asyncio.wait_for(
                    self.network.is_online(), min(8.0, spec.timeout_s)
                ):
                    await self.emit(
                        ErrorEvent(
                            code="tool_offline",
                            message="This step needs a connection. Nothing was queued.",
                        )
                    )
                    await self._activity(
                        f"Task stopped offline after {self._completed} completed step(s)."
                    )
                    return ExecutionOutcome("failed", self._completed, tuple(outputs))
                self._running_step = True
                value = await self._invoke(tool, deepcopy(checked), "run", spec.timeout_s)
                result = spec.output_model.model_validate(value, strict=True, extra="forbid")
                self._running_step = False
                if step.tool == "kb.search":
                    from agent.kb.library import SearchOutput

                    search = SearchOutput.model_validate(
                        result.model_dump(mode="json"), strict=True
                    )
                    await self.emit(ResultAnswer(text=search.message, citations=search.citations))
                outputs.append(result.model_dump(mode="json"))
                self._completed += 1
                await self._activity(f"Completed {step.tool}.")
            message = outputs[-1].get("message", "Completed the task.")
            await self.emit(
                ReplyText(
                    task_id=identifier,
                    text=message if isinstance(message, str) else "Completed the task.",
                    spoken=False,
                )
            )
            return ExecutionOutcome("completed", self._completed, tuple(outputs))
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - failures may include confidential tool arguments
            await self.emit(
                ErrorEvent(
                    code="tool_failed", message="The task stopped. Check any completed actions."
                )
            )
            uncertainty = " The current step may have taken effect." if self._running_step else ""
            await self._activity(
                f"Task failed after {self._completed} completed step(s)." + uncertainty
            )
            return ExecutionOutcome("failed", self._completed, tuple(outputs))
        finally:
            self._confirmation = None
            await self.status(False)

    async def cancel(self, *, announce: bool = True) -> None:
        task, self._task = self._task, None
        if self._confirmation is not None:
            self._confirmation[1].cancel()
            self._confirmation = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            uncertainty = (
                " An in-progress action may have taken effect." if self._running_step else ""
            )
            await self._activity(
                f"Task cancelled after {self._completed} completed step(s)." + uncertainty
            )
        self._running_step = False
        self.task_id = None
        if announce:
            await self.status(False)

    async def close(self) -> None:
        await self.cancel(announce=False)
