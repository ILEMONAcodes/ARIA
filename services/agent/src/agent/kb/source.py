"""Open only unchanged cited policy sources in explicitly configured Windows viewers."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol

from pydantic import BaseModel, ConfigDict, model_validator

from agent.contracts.plan import Risk
from agent.kb.library import PolicyLibrary, SourceReceipt, document_fingerprint
from agent.kb.reader import MAX_BYTES
from agent.security.keys import OSVaultKeyProvider
from agent.store.database import open_database
from agent.tools.base import Tool

Issue = Literal["changed", "missing", "invalid", "unavailable"]
_MESSAGES: dict[Issue, str] = {
    "changed": "This source has changed. Search the policy library again.",
    "missing": "This source is missing. Search the policy library again.",
    "invalid": "Choose a source from the latest policy search results.",
    "unavailable": "The source viewer is unavailable. Check the configured document viewer.",
}


class SourceIssue(ValueError):
    def __init__(self, code: Issue) -> None:
        super().__init__(_MESSAGES[code])
        self.code = code


@dataclass(frozen=True)
class Viewer:
    executable: Path
    kind: Literal["file", "sumatra"] = "file"


@dataclass(frozen=True)
class ViewerLaunch:
    pid: int
    page_navigation: bool


class SourceViewer(Protocol):
    def open(self, path: Path, page: int | None, *, check: Callable[[], None]) -> ViewerLaunch: ...


class WindowsSourceViewer:
    def __init__(self, viewers: dict[str, Viewer]) -> None:
        if any(
            suffix not in {".pdf", ".docx", ".txt"}
            or not viewer.executable.is_absolute()
            or viewer.executable.suffix.casefold() != ".exe"
            or viewer.kind not in {"file", "sumatra"}
            or viewer.kind == "sumatra"
            and suffix != ".pdf"
            for suffix, viewer in viewers.items()
        ):
            raise ValueError("Configure local Windows viewers for supported policy formats")
        self.viewers = dict(viewers)

    def open(self, path: Path, page: int | None, *, check: Callable[[], None]) -> ViewerLaunch:
        try:
            viewer = self.viewers[path.suffix.casefold()]
            executable = viewer.executable
            if (
                sys.platform != "win32"
                or str(executable).startswith(("\\\\", "//"))
                or not executable.is_file()
                or executable.resolve(strict=True) != executable
            ):
                raise SourceIssue("unavailable")
            navigation = viewer.kind == "sumatra" and page is not None
            command = [str(executable)]
            if viewer.kind == "sumatra":
                command.append("-restrict")
            if navigation:
                command.extend(["-page", str(page)])
            command.append(str(path))
            # Validate the cited snapshot immediately before requesting a launch.
            check()
            allowed = {
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
            environment = {
                key: value for key, value in os.environ.items() if key.upper() in allowed
            }
            process = subprocess.Popen(
                command,
                shell=False,
                cwd=str(executable.parent),
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return ViewerLaunch(process.pid, navigation)
        except SourceIssue:
            raise
        except Exception:  # noqa: BLE001 - native errors must not disclose paths/arguments
            raise SourceIssue("unavailable") from None


def validate_source(library: PolicyLibrary, source: SourceReceipt) -> Path:
    """Compare the issued snapshot, current index and current bytes/metadata."""
    path = Path(source.file_path)
    try:
        if (
            not path.is_absolute()
            or str(path).startswith(("\\\\", "//"))
            or not path.is_relative_to(library.root)
            or path.suffix.casefold() not in {".pdf", ".docx", ".txt"}
        ):
            raise SourceIssue("invalid")
        if not path.exists():
            raise SourceIssue("missing")
        if path.is_symlink() or path.resolve(strict=True) != path or not path.is_file():
            raise SourceIssue("invalid")
        relative = path.relative_to(library.root).as_posix()
        rows = library.db.fetch_all(
            "SELECT d.fingerprint FROM kb_documents d JOIN kb_passages p ON p.document_id=d.id WHERE d.root=? AND d.path=? AND d.error IS NULL AND p.page IS ? LIMIT 1",
            (str(library.root), relative, source.page),
        )
        if not rows or rows[0][0] != source.fingerprint:
            raise SourceIssue("changed")
        with path.open("rb") as stream:
            content = stream.read(MAX_BYTES + 1)
        if len(content) > MAX_BYTES:
            raise SourceIssue("changed")
        meta = library.source_metadata(relative)
        fingerprint = document_fingerprint(content, meta)
        if fingerprint != source.fingerprint:
            raise SourceIssue("changed")
        if path.is_symlink() or path.resolve(strict=True) != path:
            raise SourceIssue("changed")
        return path
    except SourceIssue:
        raise
    except FileNotFoundError:
        raise SourceIssue("missing") from None
    except Exception:  # noqa: BLE001
        raise SourceIssue("changed") from None


class SourceOpenInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: SourceReceipt


class SourceOpenOutput(BaseModel):
    message: str
    opened: bool
    pid: int | None = None
    code: Issue | None = None

    @model_validator(mode="after")
    def consistent(self) -> SourceOpenOutput:
        if self.opened != (self.pid is not None and self.pid > 0) or self.opened != (
            self.code is None
        ):
            raise ValueError("Invalid source opening result")
        return self


class PolicySourceOpen(Tool[SourceOpenInput, SourceOpenOutput]):
    name = "files.open"
    risk: ClassVar[Risk] = "none"
    needs_network = False
    timeout_s = 8.0
    input_model = SourceOpenInput
    output_model = SourceOpenOutput

    def __init__(self, folder: Path, database: Path, viewer: SourceViewer) -> None:
        self.folder, self.database, self.viewer = (
            folder.resolve(strict=True),
            database.resolve(),
            viewer,
        )
        if not self.folder.is_dir() or self.database.is_relative_to(self.folder):
            raise ValueError("The policy cache must stay outside the source folder")

    def dry_run(self, args: SourceOpenInput) -> str:
        return "Open the unchanged cited policy source in its configured viewer."

    def run(self, args: SourceOpenInput) -> SourceOpenOutput:
        try:
            if not self.database.is_file():
                raise SourceIssue("unavailable")
            with open_database(self.database, OSVaultKeyProvider()) as database:
                library = PolicyLibrary(self.folder, database)
                path = validate_source(library, args.source)

                def check() -> None:
                    validate_source(library, args.source)

                launch = self.viewer.open(path, args.source.page, check=check)
            if args.source.page is None:
                message = "Started the source viewer. Use the cited section to locate the passage."
            elif launch.page_navigation:
                message = f"Started the source viewer; requested page {args.source.page}."
            else:
                message = "Started the source viewer. This viewer cannot jump to the cited page."
            return SourceOpenOutput(message=message, opened=True, pid=launch.pid)
        except SourceIssue as exc:
            return SourceOpenOutput(message=str(exc), opened=False, code=exc.code)
        except Exception:  # noqa: BLE001
            return SourceOpenOutput(
                message=_MESSAGES["unavailable"], opened=False, code="unavailable"
            )
