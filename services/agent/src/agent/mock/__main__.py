import argparse

import uvicorn

from agent.mock.server import create_app, load_scenario


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the ARIA mock agent")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    app = create_app(load_scenario(args.scenario))
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
