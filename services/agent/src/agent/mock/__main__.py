import argparse
import os
import secrets

import uvicorn

from agent.mock.scenarios import ScenarioError
from agent.mock.server import create_app, load_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ARIA mock agent")
    parser.add_argument("--scenario")
    parser.add_argument("--list", action="store_true", help="List available scenario names")
    parser.add_argument(
        "--no-delays", action="store_true", help="Skip fixture pauses for a handoff check"
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        help="Allow a specific UI origin for browser health checks",
    )
    args = parser.parse_args()
    if args.list:
        from agent.mock.server import SCENARIO_DIR

        print("\n".join(sorted(path.stem for path in SCENARIO_DIR.glob("*.json"))))
        return
    if args.scenario is None or not 1 <= args.port <= 65535:
        parser.error("Choose --scenario and a port between 1 and 65535")
    token = os.environ.get("ARIA_MOCK_TOKEN", secrets.token_urlsafe(32))
    try:
        app = create_app(
            load_scenario(args.scenario),
            token=token,
            delay_scale=0 if args.no_delays else 1,
            allowed_origins=tuple(args.allow_origin),
        )
    except (ScenarioError, ValueError) as error:
        parser.error(str(error))
    print(f"Mock WebSocket: ws://127.0.0.1:{args.port}/ws?token={token}", flush=True)
    print("Health: /api/health with Authorization: Bearer <the same session token>", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
