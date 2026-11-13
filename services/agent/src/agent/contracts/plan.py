"""The plan object the planner returns. See docs/TECH_SPEC.md section 4."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

Risk = Literal["none", "local_write", "external_send", "destructive"]


class PlanStep(BaseModel):
    tool: str
    args: dict[str, Any] = {}


class Plan(BaseModel):
    intent: str
    confidence: float = Field(ge=0, le=1)
    slots: dict[str, Any] = {}
    missing: list[str] = []
    risk: Risk = "none"
    needs_confirmation: bool = False
    needs_network: bool = False
    steps: list[PlanStep] = []

    @model_validator(mode="after")
    def risk_requires_confirmation(self) -> Plan:
        if self.risk != "none" and not self.needs_confirmation:
            raise ValueError("risk above 'none' requires needs_confirmation=true")
        return self
