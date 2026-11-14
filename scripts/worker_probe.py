"""Fictional worker-lifecycle probe, imported only by the separate smoke check."""

import time
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from agent.contracts.plan import Risk
from agent.fakes.tools import FakeTool
from agent.tools.base import Tool


class ProbeInput(BaseModel):
    directory: str


class ProbeOutput(BaseModel):
    message: str


class ProbeTool(Tool[ProbeInput, ProbeOutput]):
    name = "test.worker_probe"
    risk: ClassVar[Risk] = "local_write"
    needs_network = False
    timeout_s = 10.0
    input_model = ProbeInput
    output_model = ProbeOutput

    def dry_run(self, args: ProbeInput) -> str:
        print("fictional worker output, suppressed by the private worker")
        return "Write only the smoke test's temporary markers."

    def run(self, args: ProbeInput) -> ProbeOutput:
        directory = Path(args.directory)
        (directory / "started").write_text("fictional")
        time.sleep(30)
        (directory / "finished").write_text("must never appear after cancellation")
        return ProbeOutput(message="finished")


class MutatingPreviewTool(ProbeTool):
    name = "test.mutating_preview"

    def dry_run(self, args: ProbeInput) -> str:
        args.directory = "changed by a broken dry run"
        return "Must not reach confirmation"


class WorkerEchoTool(FakeTool):
    # This smoke check measures dependency resolution, not interpreter cold-start speed.
    timeout_s = 10.0
