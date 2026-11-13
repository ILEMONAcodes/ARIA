"""Run foundation startup checks or keep the core lifecycle running."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path

from agent.bootstrap import StartupError, start_agent


async def _run(args: argparse.Namespace) -> None:
    if args.fake:
        from agent.fakes import FakeClock, FakeStore, fake_adapters

        context = start_agent(
            args.settings, store=FakeStore(), adapters=fake_adapters(), clock=FakeClock()
        )
    else:
        context = start_agent(args.settings)
    async with context:
        mode = "fake adapters" if args.fake else "encrypted storage"
        print(
            f"ARIA foundations started ({mode}); voice and request serving are not enabled.",
            flush=True,
        )
        if not args.check:
            await asyncio.Event().wait()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, help="Explicit TOML settings file")
    parser.add_argument(
        "--fake", action="store_true", help="Use in-memory test adapters and storage"
    )
    parser.add_argument(
        "--check", action="store_true", help="Check startup and shutdown, then exit"
    )
    args = parser.parse_args(argv)
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 0
    except StartupError:
        print(
            "Agent startup or shutdown failed. Check configuration and encrypted storage.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
