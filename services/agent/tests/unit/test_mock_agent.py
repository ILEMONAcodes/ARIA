
import pytest
from fastapi.testclient import TestClient

from agent.mock.server import SCENARIO_DIR, create_app, load_scenario

SCENARIOS = sorted(p.stem for p in SCENARIO_DIR.glob("*.json"))


@pytest.mark.parametrize("name", SCENARIOS)
def test_every_scenario_file_matches_the_contract(name):
    load_scenario(name)  # raises if any event breaks the contract


def test_mock_agent_replays_events_in_order():
    scenario = {
        "name": "t",
        "steps": [
            {"send": {"v": 1, "type": "status", "state": "idle", "online": True, "profile": "hosted"}},
            {"send": {"v": 1, "type": "reply.text", "task_id": "t1", "text": "hello", "spoken": True}},
        ],
    }
    client = TestClient(create_app(scenario))
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "status"
        assert ws.receive_json()["text"] == "hello"


def test_mock_agent_waits_for_ui_event():
    scenario = {
        "name": "t",
        "steps": [
            {"wait_for": "ptt.start"},
            {"send": {"v": 1, "type": "reply.text", "task_id": "t1", "text": "ok", "spoken": False}},
        ],
    }
    client = TestClient(create_app(scenario))
    with client.websocket_connect("/ws") as ws:
        ws.send_json({"v": 1, "type": "ptt.start"})
        assert ws.receive_json()["text"] == "ok"


def test_scenarios_directory_is_not_empty():
    assert len(SCENARIOS) >= 4
