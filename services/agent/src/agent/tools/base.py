"""Base class for every tool. See docs/TECH_SPEC.md section 5.

A tool declares its schemas, risk, network need and timeout, and must
provide a dry_run() that describes what it would do without doing it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

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
        self._tools: dict[str, Tool] = {}  # type: ignore[type-arg]

    def register(self, tool: Tool) -> None:  # type: ignore[type-arg]
        required = ("name", "risk", "needs_network", "timeout_s", "input_model", "output_model")
        missing = [a for a in required if not hasattr(tool, a)]
        if missing:
            raise ValueError(f"tool is missing declarations: {missing}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:  # type: ignore[type-arg]
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)
