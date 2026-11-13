"""Base class for every tool. See docs/TECH_SPEC.md section 5.

A tool declares its schemas, risk, network need and timeout, and must
provide a dry_run() that describes what it would do without doing it.
"""

from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from agent.contracts.plan import Risk

In = TypeVar("In", bound=BaseModel)
Out = TypeVar("Out", bound=BaseModel)


class Tool(ABC, Generic[In, Out]):
    name: ClassVar[str]
    risk: ClassVar[Risk]
    needs_network: ClassVar[bool]
    timeout_s: ClassVar[float]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    @abstractmethod
    def dry_run(self, args: In) -> str:
        """Plain-language description of what run() would do. No side effects."""

    @abstractmethod
    def run(self, args: In) -> Out:
        """Do the work."""


class ToolRegistry:
    """Only registered tools can run. Plans naming other tools are rejected."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any, Any]] = {}
        self._specs: dict[str, ToolSpec] = {}

    def register(self, tool: Tool[Any, Any]) -> None:
        required = ("name", "risk", "needs_network", "timeout_s", "input_model", "output_model")
        missing = [a for a in required if not hasattr(tool, a)]
        if missing:
            raise ValueError(f"tool is missing declarations: {missing}")
        if not isinstance(tool, Tool):
            raise TypeError("Only Tool implementations can register")
        if (
            not isinstance(tool.name, str)
            or re.fullmatch(r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+", tool.name) is None
        ):
            raise ValueError("Tool names must be dotted lowercase identifiers")
        if not isinstance(tool.risk, str) or tool.risk not in {
            "none",
            "local_write",
            "external_send",
            "destructive",
        }:
            raise ValueError("Invalid tool risk")
        if type(tool.needs_network) is not bool:
            raise ValueError("Tool network declaration must be a boolean")
        if (
            type(tool.timeout_s) not in (int, float)
            or not math.isfinite(tool.timeout_s)
            or tool.timeout_s <= 0
        ):
            raise ValueError("Tool timeout must be finite and positive")
        for model in (tool.input_model, tool.output_model):
            if not isinstance(model, type) or not issubclass(model, BaseModel):
                raise TypeError("Tool schemas must be Pydantic model classes")
        if tool.name in self._tools:
            raise ValueError("A tool with this name is already registered")
        # Freeze policy at registration; model-provided plan flags cannot override it.
        spec = ToolSpec(
            tool.name,
            tool.risk,
            tool.needs_network,
            float(tool.timeout_s),
            tool.input_model,
            tool.output_model,
        )
        spec.input_model.model_json_schema()
        spec.output_model.model_json_schema()
        self._tools[tool.name] = tool
        self._specs[tool.name] = spec

    def get(self, name: str) -> Tool[Any, Any]:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def spec(self, name: str) -> ToolSpec:
        if name not in self._specs:
            raise KeyError("Unknown tool")
        return self._specs[name]

    def validate_args(self, name: str, args: dict[str, Any]) -> BaseModel:
        """Validation only: never call dry_run or run here."""
        return self.spec(name).input_model.model_validate(args, strict=True, extra="forbid")

    def describe(self) -> list[dict[str, Any]]:
        """Fresh schema dictionaries for the planner; never tool instances."""
        return [self.spec(name).describe() for name in self.names()]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    risk: Risk
    needs_network: bool
    timeout_s: float
    input_model: type[BaseModel]
    output_model: type[BaseModel]

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "risk": self.risk,
            "needs_network": self.needs_network,
            "timeout_s": self.timeout_s,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
        }
