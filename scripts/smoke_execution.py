"""Real worker-process checks, separate from network-blocked unit tests.

Run from the repo root. Uses fictional data and its own temporary marker files,
never launches an application, reads credentials, uses models or accesses a network.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.config import Settings  # noqa: E402
from agent.contracts.events import AgentEvent, ApprovalResponse  # noqa: E402
from agent.contracts.plan import Plan  # noqa: E402
from agent.fakes import FakeLLMAdapter, FakeNetwork, FakeTool  # noqa: E402
from agent.interfaces.models import KeywordResult, ModelMessage, ModelRequest  # noqa: E402
from agent.llm.flow import CloudFlow  # noqa: E402
from agent.router.executor import PlanExecutor  # noqa: E402
from agent.router.session import LocalSession  # noqa: E402
from agent.tools import ToolRegistry  # noqa: E402
from agent.tools.runner import ProcessToolRunner, ToolFailure  # noqa: E402
from scripts.worker_probe import MutatingPreviewTool, ProbeTool, WorkerEchoTool  # noqa: E402


async def main() -> None:
    runner = ProcessToolRunner()
    result = await runner.invoke(FakeTool(), {"text": "fictional"}, mode="run", timeout_s=10)
    assert result == {"text": "fictional"}
    registry = ToolRegistry()
    registry.register(WorkerEchoTool())

    async def discard(event: AgentEvent) -> None:
        pass

    executor = PlanExecutor(registry, Settings(), FakeNetwork(), discard, runner=runner)
    try:
        await executor.submit(
            Plan(
                intent="dependent_echo",
                confidence=1,
                steps=[
                    {"tool": "test.echo", "args": {"text": "fictional"}},
                    {"tool": "test.echo", "args": {"text": "$step1.text"}},
                    {"tool": "test.echo", "args": {"text": "$step2.text"}},
                ],
            )
        )
        outcome = await executor.wait()
        assert outcome is not None and outcome.kind == "completed"
        assert outcome.outputs[-1] == {"text": "fictional"}
    finally:
        await executor.close()

    # Approved fake model -> session handoff -> actual isolated dependent workers.
    class NoMatch:
        def match(self, text: str) -> KeywordResult:
            return KeywordResult("no_match")

    network = FakeNetwork(online=True)
    adapter = FakeLLMAdapter(
        Plan(
            intent="cloud_dependent_echo",
            confidence=1,
            steps=[
                {"tool": "test.echo", "args": {"text": "fictional cloud result"}},
                {"tool": "test.echo", "args": {"text": "$step1.text"}},
            ],
        ).model_dump_json()
    )
    await adapter.start()
    await network.start()
    executor = PlanExecutor(registry, Settings(), network, discard, runner=runner)
    cloud = CloudFlow(Settings(), adapter, network, discard, registry=registry)
    session = LocalSession(NoMatch(), executor, discard, cloud=cloud)
    try:
        approval = await session.request_cloud(
            ModelRequest(task="plan", messages=(ModelMessage("user", "Fictional echo"),))
        )
        assert approval is not None and adapter.requests == []
        await session.handle(ApprovalResponse(approval_id=approval, decision="yes"))
        await session.wait()
        outcome = await executor.wait()
        assert outcome is not None and outcome.completed_steps == 2
        assert outcome.outputs[-1] == {"text": "fictional cloud result"}
    finally:
        await session.close()
        await network.close()
        await adapter.close()
    with TemporaryDirectory(prefix="aria-worker-smoke-") as folder:
        root = Path(folder)
        tool = ProbeTool()
        preview = await runner.invoke(tool, {"directory": folder}, mode="dry_run", timeout_s=10)
        assert preview == "Write only the smoke test's temporary markers."
        assert list(root.iterdir()) == []
        try:
            await runner.invoke(
                MutatingPreviewTool(), {"directory": folder}, mode="dry_run", timeout_s=10
            )
        except ToolFailure:
            pass
        else:
            raise AssertionError("Mutating dry run was accepted")
        try:
            await runner.invoke(tool, {"directory": folder}, mode="run", timeout_s=3)
        except TimeoutError:
            pass
        else:
            raise AssertionError("Tool timeout was not enforced")
        assert (root / "started").exists()
        assert not (root / "finished").exists()
        (root / "started").unlink()
        task = asyncio.create_task(
            runner.invoke(tool, {"directory": folder}, mode="run", timeout_s=10)
        )
        try:
            async with asyncio.timeout(8):
                while not (root / "started").exists():
                    await asyncio.sleep(0.02)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        assert not (root / "finished").exists()
    print("Worker execution, cloud handoff, dry-run, timeout and cancellation checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
