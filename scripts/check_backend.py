"""Run the backend checks used locally, by pre-commit and in CI.

Run with: uv run --locked --all-packages --all-extras python scripts/check_backend.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, cwd: Path = ROOT) -> None:
    print(f"[{cwd.relative_to(ROOT)}] {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, *args], cwd=cwd, check=True)


def main() -> None:
    run("-m", "ruff", "check", "services", "scripts")
    run("-m", "ruff", "format", "--check", "services", "scripts")
    for service in ("agent", "gateway"):
        directory = ROOT / "services" / service
        run("-m", "mypy", "src", cwd=directory)
        run("-m", "pytest", "tests/unit", cwd=directory)
    run("scripts/gen_contract.py", "--check")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)
