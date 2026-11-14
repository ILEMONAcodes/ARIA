"""Validate untrusted plans without executing tools or changing the v1 schema."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from agent.contracts.plan import Plan
from agent.planner.references import references, validate_bindings, validate_template
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

    No dry runs, model requests, tool runs or approval. Bindings are checked
    structurally here; the executor resolves and fully validates before each step.
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
        if (
            any(references(plan.slots))
            or "$step" in plan.intent
            or any("$step" in m for m in plan.missing)
        ):
            raise PlanValidationError()
        for position, step in enumerate(plan.steps, start=1):
            spec = registry.spec(step.tool)
            if validate_bindings(step.args, position=position, plan=plan, registry=registry):
                validate_template(spec.input_model, step.args)
            else:
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
