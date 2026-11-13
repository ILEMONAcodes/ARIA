"""Validate untrusted plans without executing tools or changing the v1 schema."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from agent.contracts.plan import Plan
from agent.tools.base import ToolRegistry

_RANK = {"none": 0, "local_write": 1, "external_send": 2, "destructive": 3}


class PlanValidationError(ValueError):
    """Content-free validation failure, safe for diagnostics and retry decisions."""

    def __init__(self) -> None:
        super().__init__("Invalid plan")


@dataclass(frozen=True)
class PlanReview:
    # A review is data, never an execution or approval capability.
    plan: Plan = field(repr=False)
    requires_clarification: bool

    @property
    def first_missing(self) -> str | None:
        return self.plan.missing[0] if self.plan.missing else None


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, value in pairs:
        if name in result:
            raise PlanValidationError()
        result[name] = value
    return result


def _finite(value: Any) -> None:
    # Result bindings need an executor that resolves and revalidates each step.
    # Until that exists, never treat a binding as an executable literal argument.
    if isinstance(value, str) and value.startswith("$step"):
        raise PlanValidationError()
    if isinstance(value, float) and not math.isfinite(value):
        raise PlanValidationError()
    if isinstance(value, dict):
        for child in value.values():
            _finite(child)
    elif isinstance(value, list):
        for child in value:
            _finite(child)


def validate_plan(
    payload: str | dict[str, Any] | Plan,
    registry: ToolRegistry,
    *,
    confidence_threshold: float = 0.6,
) -> PlanReview:
    """Strictly validate shape, arguments and authoritative registered policy.

    No dry runs, model requests, tool runs, approval or reference interpolation.
    `$stepN.field` bindings fail closed until the executor can resolve and
    revalidate them before each step. The public plan schema is unchanged.
    """
    if (
        type(confidence_threshold) not in (int, float)
        or not math.isfinite(confidence_threshold)
        or not 0 <= confidence_threshold <= 1
    ):
        raise ValueError("Confidence threshold must be finite and between zero and one")
    try:
        raw = payload.model_dump(mode="python") if isinstance(payload, Plan) else payload
        if isinstance(raw, str):
            raw = json.loads(raw, object_pairs_hook=_object)
        _finite(raw)
        plan = Plan.model_validate(raw, strict=True, extra="forbid")
        if not plan.intent.strip() or any(not name.strip() for name in plan.missing):
            raise PlanValidationError()
        for step in plan.steps:
            spec = registry.spec(step.tool)
            registry.validate_args(step.tool, step.args)
            if _RANK[plan.risk] < _RANK[spec.risk]:
                raise PlanValidationError()
            if spec.needs_network and not plan.needs_network:
                raise PlanValidationError()
        return PlanReview(
            plan.model_copy(deep=True),
            bool(plan.confidence < confidence_threshold or plan.missing or not plan.steps),
        )
    except (ValidationError, ValueError, KeyError, TypeError, RecursionError):
        raise PlanValidationError() from None
