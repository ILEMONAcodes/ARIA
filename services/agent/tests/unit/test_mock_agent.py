import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent.mock.scenarios import ScenarioError
from agent.mock.server import SCENARIO_DIR, create_app, load_scenario

SCENARIOS = sorted(p.stem for p in SCENARIO_DIR.glob("*.json"))
TOKEN = "fictional-mock-session-token"
WS = f"/ws?token={TOKEN}"


def client_for(scenario):
    return TestClient(create_app(scenario, token=TOKEN, delay_scale=0))


@pytest.mark.parametrize("name", SCENARIOS)
def test_every_scenario_file_matches_the_contract(name):
    load_scenario(name)  # raises if any event breaks the contract


def test_mock_agent_replays_events_in_order():
    scenario = {
        "name": "t",
        "steps": [
            {
                "send": {
                    "v": 1,
                    "type": "status",
                    "state": "idle",
                    "online": True,
                    "profile": "hosted",
                }
            },
            {
                "send": {
                    "v": 1,
                    "type": "reply.text",
                    "task_id": "t1",
                    "text": "hello",
                    "spoken": True,
                }
            },
        ],
    }
    client = client_for(scenario)
    with client.websocket_connect(WS) as ws:
        assert ws.receive_json()["type"] == "status"
        assert ws.receive_json()["text"] == "hello"


def test_mock_agent_waits_for_ui_event():
    scenario = {
        "name": "t",
        "steps": [
            {"wait_for": "ptt.start"},
            {
                "send": {
                    "v": 1,
                    "type": "reply.text",
                    "task_id": "t1",
                    "text": "ok",
                    "spoken": False,
                }
            },
        ],
    }
    client = client_for(scenario)
    with client.websocket_connect(WS) as ws:
        ws.send_json({"v": 1, "type": "ptt.start"})
        assert ws.receive_json()["text"] == "ok"


def test_scenarios_directory_is_not_empty():
    assert len(SCENARIOS) >= 4


@pytest.mark.parametrize("name", SCENARIOS)
def test_every_mock_scenario_completes_with_its_documented_ui_responses(name):
    scenario = load_scenario(name)
    with client_for(scenario) as client:
        health = client.get("/api/health", headers={"Authorization": f"Bearer {TOKEN}"})
        assert health.status_code == 200
        assert health.json()["scenario"] == scenario["name"]
        with client.websocket_connect(WS) as ws:
            for step in scenario["steps"]:
                if "send" in step:
                    assert ws.receive_json() == step["send"]
                else:
                    ws.send_json(step["match"])
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
            assert closed.value.code == 1000


@pytest.mark.parametrize("path", ["/ws", "/ws?token=wrong", "/ws?token=%C3%A9"])
def test_mock_websocket_requires_the_session_token(path):
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        client_for(load_scenario("policy_question")).websocket_connect(path),
    ):
        pytest.fail("Unauthorized sockets must not be accepted")
    assert closed.value.code == 1008


def test_mock_rest_requires_the_session_token():
    client = client_for(load_scenario("policy_question"))
    assert client.get("/api/health").status_code == 401
    assert client.get("/api/health", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_explicit_ui_origin_allows_preflight_without_bypassing_health_authentication():
    origin = "http://localhost:5173"
    client = TestClient(
        create_app(load_scenario("policy_question"), token=TOKEN, allowed_origins=(origin,))
    )
    headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "Authorization",
    }
    preflight = client.options("/api/health", headers=headers)
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert client.get("/api/health", headers={"Origin": origin}).status_code == 401
    assert (
        client.options(
            "/api/health", headers={**headers, "Origin": "https://example.org"}
        ).status_code
        == 400
    )
    assert (
        "access-control-allow-origin"
        not in client.get("/api/health", headers={"Origin": "https://example.org"}).headers
    )


def approval_scenario():
    return {
        "name": "fixture",
        "steps": [
            {
                "send": {
                    "v": 1,
                    "type": "cloud.approval_request",
                    "approval_id": "a1",
                    "payload_preview": "fixture",
                }
            },
            {
                "wait_for": "approval.response",
                "match": {
                    "v": 1,
                    "type": "approval.response",
                    "approval_id": "a1",
                    "decision": "yes",
                },
            },
            {
                "send": {
                    "v": 1,
                    "type": "reply.text",
                    "task_id": "t1",
                    "text": "fixture",
                    "spoken": False,
                }
            },
        ],
    }


def test_declined_cloud_approval_stops_replay_without_success_events():
    with client_for(approval_scenario()).websocket_connect(WS) as ws:
        assert ws.receive_json()["type"] == "cloud.approval_request"
        ws.send_json({"v": 1, "type": "approval.response", "approval_id": "a1", "decision": "no"})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1000


def test_wrong_approval_id_cannot_advance_the_replay():
    with client_for(approval_scenario()).websocket_connect(WS) as ws:
        ws.receive_json()
        ws.send_json(
            {"v": 1, "type": "approval.response", "approval_id": "wrong", "decision": "yes"}
        )
        ws.send_json({"v": 1, "type": "approval.response", "approval_id": "a1", "decision": "no"})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_declined_send_confirmation_does_not_replay_outbox_updates():
    scenario = load_scenario("offline_send_then_reconnect")
    with client_for(scenario).websocket_connect(WS) as ws:
        for step in scenario["steps"]:
            if "wait_for" in step:
                response = {**step["match"], "decision": "no"}
                ws.send_json(response)
                break
            ws.receive_json()
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1000


def test_keyboard_confirmation_replays_the_same_success_path_as_a_click():
    scenario = load_scenario("offline_send_then_reconnect")
    with client_for(scenario).websocket_connect(WS) as ws:
        for step in scenario["steps"]:
            if "send" in step:
                assert ws.receive_json() == step["send"]
            else:
                ws.send_json({**step["match"], "via": "key"})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1000


@pytest.mark.parametrize(
    "message",
    [
        {"v": 2, "type": "ptt.start"},
        {"type": "ptt.start"},
        {"v": 1, "type": "unknown"},
        {"v": 1, "type": "confirm.response", "confirm_id": "c1", "decision": "yes", "via": "voice"},
        None,
    ],
)
def test_invalid_or_unsupported_ui_events_close_safely(message):
    with client_for(approval_scenario()).websocket_connect(WS) as ws:
        ws.receive_json()
        ws.send_json(message)
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1008


def test_task_cancel_stops_a_waiting_replay():
    with client_for(approval_scenario()).websocket_connect(WS) as ws:
        ws.receive_json()
        ws.send_json({"v": 1, "type": "task.cancel", "task_id": "t1"})
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1000


@pytest.mark.parametrize(
    "step",
    [
        {"wait_for": "unknown"},
        {
            "send": {
                "v": 1,
                "type": "status",
                "state": "idle",
                "online": True,
                "profile": "hosted",
            },
            "delay_ms": -1,
        },
        {
            "send": {
                "v": 1,
                "type": "status",
                "state": "idle",
                "online": True,
                "profile": "hosted",
            },
            "delay_ms": True,
        },
        {"wait_for": "approval.response"},
        {"wait_for": "ptt.start", "match": {"v": 1, "type": "ptt.stop"}},
        {
            "wait_for": "approval.response",
            "match": {
                "v": 1,
                "type": "approval.response",
                "approval_id": "orphan",
                "decision": "yes",
            },
        },
        {
            "send": {
                "v": 1,
                "type": "reply.text",
                "task_id": "t",
                "text": "fictional-private-fixture",
            },
            "wait_for": "ptt.start",
        },
    ],
)
def test_malformed_scenarios_fail_early_without_exposing_fixture_data(step):
    with pytest.raises(ScenarioError) as error:
        client_for({"name": "fixture", "steps": [step]})
    assert "fictional-private-fixture" not in str(error.value)


@pytest.mark.parametrize("name", ["../.env", "policy/question", "", ".."])
def test_scenario_names_cannot_escape_the_fixture_directory(name):
    with pytest.raises(ScenarioError):
        load_scenario(name)
