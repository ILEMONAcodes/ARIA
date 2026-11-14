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

from agent.fakes import FakeTool  # noqa: E402
from agent.tools.runner import ProcessToolRunner  # noqa: E402
from scripts.worker_probe import ProbeTool  # noqa: E402


async def main() -> None:
    runner = ProcessToolRunner()
    result = await runner.invoke(FakeTool(), {"text": "fictional"}, mode="run", timeout_s=10)
    assert result == {"text": "fictional"}
    with TemporaryDirectory(prefix="aria-worker-smoke-") as folder:
        root = Path(folder)
        tool = ProbeTool()
        preview = await runner.invoke(tool, {"directory": folder}, mode="dry_run", timeout_s=10)
        assert preview == "Write only the smoke test's temporary markers."
        assert list(root.iterdir()) == []
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
    print("Worker execution, dry-run, timeout and cancellation checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
