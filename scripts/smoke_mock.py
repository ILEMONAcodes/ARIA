"""Live localhost-only integration check. Not a network-enabled unit test.

Run with the development environment: python scripts/smoke_mock.py
Starts its own mock process with fictional credentials and always stops it.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from websockets.exceptions import ConnectionClosedOK
from websockets.sync.client import connect

from agent.mock.server import load_scenario

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "fictional-live-mock-session-token"


def main() -> None:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        port = reservation.getsockname()[1]
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "agent.mock",
            "--scenario",
            "policy_question",
            "--no-delays",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env={**os.environ, "ARIA_MOCK_TOKEN": TOKEN},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        address = f"http://127.0.0.1:{port}/api/health"
        with httpx.Client(trust_env=False, timeout=0.5) as client:
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("The mock process exited before becoming ready")
                try:
                    response = client.get(address, headers={"Authorization": f"Bearer {TOKEN}"})
                    if response.status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.05)
            else:
                raise RuntimeError("The mock did not become ready within ten seconds")
            if client.get(address).status_code != 401:
                raise RuntimeError("Mock health did not enforce session authentication")
        with connect(
            f"ws://127.0.0.1:{port}/ws?token={TOKEN}", proxy=None, open_timeout=5, close_timeout=2
        ) as ws:
            for step in load_scenario("policy_question")["steps"]:
                if "send" in step:
                    if json.loads(ws.recv(timeout=5)) != step["send"]:
                        raise RuntimeError("Live mock events differ from the documented scenario")
                else:
                    ws.send(json.dumps(step["match"]))
            try:
                ws.recv(timeout=5)
            except ConnectionClosedOK:
                pass
            else:
                raise RuntimeError("The mock did not close after replay completion")
        print("Live policy mock replay passed (localhost only)")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


if __name__ == "__main__":
    main()
