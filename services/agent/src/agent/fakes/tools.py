"""A pure echo tool for registry tests, with no computer actions."""

from typing import ClassVar

from pydantic import BaseModel

from agent.contracts.plan import Risk
from agent.tools.base import Tool


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    text: str


class FakeTool(Tool[EchoInput, EchoOutput]):
    name = "test.echo"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 1.0
    input_model = EchoInput
    output_model = EchoOutput

    def dry_run(self, args: EchoInput) -> str:
        return "Echo test text in memory"

    def run(self, args: EchoInput) -> EchoOutput:
        return EchoOutput(text=args.text)
