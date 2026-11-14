"""Private stdio worker. Never expose this trusted-object protocol on a socket."""

from __future__ import annotations

import contextlib
import json
import os
import pickle
import sys
from typing import Any

from agent.tools.base import Tool


def main() -> None:
    output = sys.stdout.buffer
    try:
        raw = sys.stdin.buffer.read(1048577)
        if len(raw) > 1048576:
            raise ValueError("Oversized job")
        # Only the trusted parent serializes registry objects into this private pipe.
        tool, values, mode = pickle.loads(raw)
        if not isinstance(tool, Tool) or mode not in {"dry_run", "run"}:
            raise ValueError("Invalid job")
        with (
            open(os.devnull, "w") as sink,
            contextlib.redirect_stdout(sink),
            contextlib.redirect_stderr(sink),
        ):
            args = tool.input_model.model_validate(values, strict=True, extra="forbid")
            value: Any
            if mode == "dry_run":
                value = tool.dry_run(args)
                if not isinstance(value, str) or not value.strip() or len(value) > 16000:
                    raise ValueError("Invalid dry run")
            else:
                result = tool.run(args)
                value = tool.output_model.model_validate(
                    result.model_dump(), strict=True, extra="forbid"
                ).model_dump(mode="json")
            encoded = json.dumps({"ok": True, "value": value}, allow_nan=False).encode()
            if len(encoded) > 262144:
                raise ValueError("Oversized result")
    except BaseException:  # noqa: BLE001 - never forward trusted-tool tracebacks/content
        encoded = b'{"ok":false}'
    output.write(encoded)
    output.flush()


if __name__ == "__main__":
    main()
