"""Killable workers for trusted synchronous tools. This is isolation, not a sandbox."""

from __future__ import annotations

import asyncio
import json
import os
import pickle
import subprocess
import sys
from typing import Any, Literal, Protocol

from agent.tools.base import Tool

Mode = Literal["dry_run", "run"]


class ToolFailure(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Tool operation failed")


class ToolRunner(Protocol):
    async def invoke(
        self, tool: Tool[Any, Any], args: dict[str, Any], *, mode: Mode, timeout_s: float
    ) -> Any: ...


class ProcessToolRunner:
    async def invoke(
        self, tool: Tool[Any, Any], args: dict[str, Any], *, mode: Mode, timeout_s: float
    ) -> Any:
        process: asyncio.subprocess.Process | None = None
        try:
            # Objects originate solely in the trusted registry, never from model/UI pickle data.
            data = pickle.dumps((tool, args, mode))
            if len(data) > 1048576:
                raise ToolFailure()
            async with asyncio.timeout(timeout_s):
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "agent.tools.worker",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                    env={
                        k: v
                        for k, v in os.environ.items()
                        if not k.startswith(("ARIA_", "GATEWAY_"))
                    },
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                assert process.stdin is not None and process.stdout is not None
                process.stdin.write(data)
                await process.stdin.drain()
                process.stdin.close()
                output = bytearray()
                while chunk := await process.stdout.read(65536):
                    if len(output) + len(chunk) > 262144:
                        raise ToolFailure()
                    output.extend(chunk)
                await process.wait()
                result = json.loads(output)
                if process.returncode != 0 or result.get("ok") is not True:
                    raise ToolFailure()
                return result["value"]
        except (TimeoutError, asyncio.CancelledError):
            raise
        except Exception:  # noqa: BLE001 - tool exceptions may contain private paths/content
            raise ToolFailure() from None
        finally:
            if process is not None and process.returncode is None:
                try:
                    process.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(process.wait(), 1)
                except TimeoutError:
                    process.kill()
                    await process.wait()
