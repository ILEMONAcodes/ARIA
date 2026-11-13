"""Generate JSON Schema for the contract into apps/desktop/src/contract/schema.json.

Run after any change to services/agent/src/agent/contracts.
CI fails if the committed file is out of date. The frontend turns the schema
into TypeScript types with `pnpm gen:types` (json-schema-to-typescript).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "agent" / "src"))

from pydantic import TypeAdapter  # noqa: E402

from agent.contracts.events import CONTRACT_VERSION, AgentEvent, UIEvent  # noqa: E402
from agent.contracts.plan import Plan  # noqa: E402


def build() -> dict:
    return {
        "contract_version": CONTRACT_VERSION,
        "agent_events": TypeAdapter(AgentEvent).json_schema(),
        "ui_events": TypeAdapter(UIEvent).json_schema(),
        "plan": Plan.model_json_schema(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the schema is out of date")
    args = parser.parse_args()
    out = ROOT / "apps" / "desktop" / "src" / "contract" / "schema.json"
    expected = json.dumps(build(), indent=2, sort_keys=True) + "\n"
    if args.check:
        if not out.is_file() or out.read_text(encoding="utf-8") != expected:
            parser.exit(1, "Contract schema is out of date. Run python scripts/gen_contract.py\n")
        print("Contract schema is up to date")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(expected, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
