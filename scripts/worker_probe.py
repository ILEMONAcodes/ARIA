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


class PolicyProbeTool(ProbeTool):
    """Only creates fictional sources/cache inside the smoke test's temporary folder."""

    name = "test.policy_probe"

    def run(self, args: ProbeInput) -> ProbeOutput:
        from agent.fakes import FakeDatabaseKeys
        from agent.kb.library import PolicyLibrary, SearchInput
        from agent.store.database import open_database

        root = Path(args.directory)
        sources = root / "policies"
        sources.mkdir()
        (sources / "fictional.txt").write_text("# Eligibility\nFictional annual leave guidance.")
        with open_database(root / "policy.db", FakeDatabaseKeys()) as database:
            library = PolicyLibrary(sources, database)
            assert library.refresh().indexed == 1
            result = library.search(SearchInput(query="annual leave"))
            assert result.found and len(result.citations) == 1
            return ProbeOutput(message=result.citations[0].passage)
