"""Launch only explicitly configured executables; no shell or user-supplied arguments."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from agent.contracts.plan import Risk
from agent.tools.base import Tool


class LaunchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str


class LaunchOutput(BaseModel):
    message: str
    pid: int


class AppLauncher(Tool[LaunchInput, LaunchOutput]):
    name = "apps.launch"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 5.0
    input_model = LaunchInput
    output_model = LaunchOutput

    def __init__(self, executables: dict[str, Path]) -> None:
        self.executables = dict(executables)
        if any(
            not path.is_absolute() or path.suffix.lower() != ".exe" for path in executables.values()
        ):
            raise ValueError("Configure absolute Windows executable paths")

    def _path(self, name: str) -> Path:
        path = self.executables[name]
        if path.resolve(strict=True) != path or not path.is_file():
            raise ValueError("Configured application is unavailable")
        return path

    def dry_run(self, args: LaunchInput) -> str:
        self._path(args.name)
        return f"Start the configured {args.name} application."

    def run(self, args: LaunchInput) -> LaunchOutput:
        path = self._path(args.name)
        if sys.platform != "win32":
            raise RuntimeError("Application launching requires Windows")
        # Do not pass ARIA installation credentials to launched applications.
        keys = {
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "PATHEXT",
            "USERPROFILE",
            "APPDATA",
            "LOCALAPPDATA",
            "TEMP",
            "TMP",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
        }
        environment = {key: value for key, value in os.environ.items() if key.upper() in keys}
        process = subprocess.Popen(
            [str(path)],
            shell=False,
            cwd=str(path.parent),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return LaunchOutput(message=f"Started {args.name}.", pid=process.pid)
