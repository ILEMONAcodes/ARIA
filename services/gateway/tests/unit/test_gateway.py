from fastapi.testclient import TestClient

from gateway.config import Settings
from gateway.llm import FakeLLM
from gateway.main import create_app

TOKEN = "test-token"
BODY = {
    "task": "answer",
    "messages": [
        {"role": "system", "content": "Answer from passages."},
        {"role": "user", "content": "Leave?"},
    ],
    "data_blocks": [{"id": "d1", "label": "passage", "text": "Five days carry over."}],
}


def client(**kw):
    s = Settings(install_tokens={TOKEN}, fake_llm=True, **kw)
    return TestClient(create_app(s, FakeLLM()))


def auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_health_needs_no_token():
    assert client().get("/health").json() == {"status": "ok"}


def test_request_without_token_is_rejected():
    assert client().post("/v1/complete", json=BODY).status_code == 401


def test_request_with_wrong_token_is_rejected():
    assert client().post("/v1/complete", json=BODY, headers=auth("nope")).status_code == 401


def test_valid_request_returns_text_and_usage():
    r = client().post("/v1/complete", json=BODY, headers=auth())
    assert r.status_code == 200
    data = r.json()
    assert data["text"].startswith("[fake]")
    assert data["usage"]["input_tokens"] > 0
    assert data["model"] == "gemma-4-26b-a4b"


def test_audio_field_is_rejected():
    r = client().post("/v1/complete", json={**BODY, "audio": "AAAA"}, headers=auth())
    assert r.status_code == 422


def test_rate_limit_returns_429():
    c = client(rate_limit_per_min=2)
    assert c.post("/v1/complete", json=BODY, headers=auth()).status_code == 200
    assert c.post("/v1/complete", json=BODY, headers=auth()).status_code == 200
    r = c.post("/v1/complete", json=BODY, headers=auth())
    assert r.status_code == 429
    assert r.json()["detail"]["error"]["code"] == "rate_limited"


def test_spending_cap_blocks_requests_when_exceeded():
    c = client(
        daily_cap_usd_per_user=0.0000001, input_price_per_m=1000.0, output_price_per_m=1000.0
    )
    assert c.post("/v1/complete", json=BODY, headers=auth()).status_code == 200
    r = c.post("/v1/complete", json=BODY, headers=auth())
    assert r.status_code == 429
    assert r.json()["detail"]["error"]["code"] == "spending_cap"


def test_data_blocks_are_wrapped_in_data_tags():
    seen = {}

    class Spy(FakeLLM):
        def complete(self, messages, params):
            seen["messages"] = messages
            return super().complete(messages, params)

    c = TestClient(create_app(Settings(install_tokens={TOKEN}), Spy()))
    c.post("/v1/complete", json=BODY, headers=auth())
    assert '<data id="d1" label="passage">' in seen["messages"][-1]["content"]


def test_api_key_is_never_in_responses(monkeypatch):
    monkeypatch.setenv("GATEWAY_PROVIDER_API_KEY", "super-secret-key")
    r = client().post("/v1/complete", json=BODY, headers=auth())
    assert "super-secret-key" not in r.text
