"""Validated replay steps; scenarios contain fictional data, not executable actions."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    TypeAdapter,
    field_validator,
    model_validator,
)

from agent.contracts.events import (
    CONTRACT_VERSION,
    AgentEvent,
    CloudApprovalRequest,
    ConfirmRequest,
    UIEvent,
)

SCENARIO_DIR = Path(__file__).resolve().parents[5] / "tests" / "e2e" / "scenarios"
_ui_schema = TypeAdapter(UIEvent).json_schema()
UI_EVENT_TYPES = frozenset(_ui_schema["discriminator"]["mapping"])


class ScenarioError(ValueError):
    """Invalid fixture, without exposing its contents in diagnostics."""


def check_version(value: Any) -> Any:
    if (
        not isinstance(value, dict)
        or type(value.get("v")) is not int
        or value["v"] != CONTRACT_VERSION
    ):
        raise ValueError("An explicit supported contract version is required")
    return value


class SendStep(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    send: AgentEvent
    delay_ms: StrictInt = Field(default=0, ge=0, le=60000)

    @field_validator("send", mode="before")
    @classmethod
    def version_matches(cls, value: Any) -> Any:
        return check_version(value)


class WaitStep(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    wait_for: str
    match: UIEvent | None = None

    @field_validator("wait_for")
    @classmethod
    def known_event(cls, value: str) -> str:
        if value not in UI_EVENT_TYPES:
            raise ValueError("Unknown UI event type")
        return value

    @field_validator("match", mode="before")
    @classmethod
    def version_matches(cls, value: Any) -> Any:
        return check_version(value) if value is not None else None

    @model_validator(mode="after")
    def matching_type(self) -> WaitStep:
        if self.match is not None and self.match.type != self.wait_for:
            raise ValueError("Response example does not match wait_for")
        if self.wait_for in {"approval.response", "confirm.response"} and (
            self.match is None or self.match.model_dump().get("decision") != "yes"
        ):
            raise ValueError("Approval replay requires an explicit matching yes example")
        return self


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    name: str = Field(pattern=r"^[a-zA-Z0-9_-]+$")
    description: str = ""
    steps: list[SendStep | WaitStep] = Field(min_length=1)

    @model_validator(mode="after")
    def approval_ids_match_requests(self) -> Scenario:
        pending: dict[str, str] = {}
        for step in self.steps:
            if isinstance(step, SendStep):
                if isinstance(step.send, CloudApprovalRequest):
                    pending["approval_id"] = step.send.approval_id
                elif isinstance(step.send, ConfirmRequest):
                    pending["confirm_id"] = step.send.confirm_id
            elif step.wait_for in {"approval.response", "confirm.response"}:
                field = "approval_id" if step.wait_for == "approval.response" else "confirm_id"
                if step.match is None or step.match.model_dump().get(field) != pending.pop(
                    field, None
                ):
                    raise ValueError("Approval example must match a preceding request")
        return self


def validate_scenario(value: Any) -> Scenario:
    try:
        return Scenario.model_validate(value)
    except ValueError:
        raise ScenarioError("Scenario does not match the replay format or event contract") from None


def load_scenario(name: str, directory: Path = SCENARIO_DIR) -> dict[str, Any]:
    if re.fullmatch(r"[a-zA-Z0-9_-]+", name) is None:
        raise ScenarioError("Invalid scenario name")
    try:
        value = json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ScenarioError("Scenario file is unavailable or invalid JSON") from None
    return validate_scenario(value).model_dump(mode="json", exclude_none=True)
