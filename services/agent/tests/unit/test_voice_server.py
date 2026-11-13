import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agent.fakes.components import FakeAudioInput, FakeSpeaker, FakeSpeechToText, FakeVAD
from agent.voice.server import create_app

TOKEN = "fictional_voice_session_token"


def app_for_test(**kwargs):
    audio = FakeAudioInput()
    return create_app(
        token=TOKEN,
        audio=audio,
        vad=FakeVAD(),
        stt=FakeSpeechToText(),
        speaker=FakeSpeaker(),
        **kwargs,
    ), audio


def test_voice_health_requires_bearer_token_and_models_start_once():
    app, audio = app_for_test()
    with TestClient(app) as client:
        assert audio.started == 1
        assert not audio.capturing
        assert client.get("/api/health").status_code == 401
        assert client.get("/api/health", headers={"Authorization": TOKEN}).status_code == 401
        assert client.get("/api/health", headers={"Authorization": f"Bearer {TOKEN}"}).json() == {
            "status": "ok",
            "mode": "voice-echo",
        }
        assert client.get("/docs").status_code == 404
        for _ in range(2):
            with client.websocket_connect(f"/ws?token={TOKEN}") as socket:
                assert socket.receive_json()["state"] == "idle"
        assert audio.started == 1
    assert audio.closed == 1
    assert not audio.capturing


@pytest.mark.parametrize(
    "url,headers",
    [
        ("/ws", {}),
        (f"/ws?token={TOKEN}", {"Origin": "https://untrusted.invalid"}),
    ],
)
def test_voice_ws_rejects_unauthorized_clients_before_mic_access(url, headers):
    app, audio = app_for_test()
    with (
        TestClient(app) as client,
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(url, headers=headers),
    ):
        pass
    assert not audio.capturing


def test_voice_ws_rejects_second_microphone_owner_and_bad_versions():
    app, audio = app_for_test()
    with TestClient(app) as client, client.websocket_connect(f"/ws?token={TOKEN}") as socket:
        assert socket.receive_json()["state"] == "idle"
        with pytest.raises(WebSocketDisconnect), client.websocket_connect(f"/ws?token={TOKEN}"):
            pass
        socket.send_json({"v": 1, "type": "ptt.start"})
        assert socket.receive_json()["state"] == "listening"
        socket.send_json({"v": 2, "type": "ptt.stop"})
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
    assert not audio.capturing


def test_voice_explicit_origin_gets_health_cors():
    app, _ = app_for_test(allowed_origins=("http://localhost:1420",))
    with TestClient(app) as client:
        response = client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:1420",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        assert response.headers["access-control-allow-origin"] == "http://localhost:1420"
        with client.websocket_connect(
            f"/ws?token={TOKEN}", headers={"Origin": "http://localhost:1420"}
        ) as socket:
            assert socket.receive_json()["state"] == "idle"


def test_voice_partial_startup_failure_closes_prepared_components():
    class BrokenVAD(FakeVAD):
        async def start(self):
            raise RuntimeError("native failure")

    audio, vad, stt, speaker = FakeAudioInput(), BrokenVAD(), FakeSpeechToText(), FakeSpeaker()
    app = create_app(token=TOKEN, audio=audio, vad=vad, stt=stt, speaker=speaker)
    with pytest.raises(RuntimeError), TestClient(app):
        pass
    assert (stt.closed, speaker.closed, vad.closed, audio.started) == (1, 1, 1, 0)
