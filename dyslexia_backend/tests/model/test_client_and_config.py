import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from app.model.client import ModelCallError, call_model
from app.model.config import ModelConfig, ModelConfigError
from app.model.schemas import Recommendation, RecommendationList

BACKEND_DIR = Path(__file__).resolve().parents[2]  # dyslexia_backend/
MSGS = [{"role": "user", "content": "hi"}]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("MODEL_MOCK", "MODEL_BASE_URL", "MODEL_NAME", "MODEL_API_KEY", "MODEL_TIMEOUT"):
        monkeypatch.delenv(k, raising=False)


def fake_server(handler):
    return httpx.MockTransport(handler)


def ok_reply(content="hello"):
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": content}}]})


# ---- config ----

def test_defaults_point_at_local_ollama():
    c = ModelConfig.from_env()
    assert c.mock is False and c.base_url == "http://localhost:11434/v1" and c.api_key is None


@pytest.mark.parametrize("value,expected", [("1", True), ("true", True), ("YES", True), ("0", False), ("", False)])
def test_mock_flag_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("MODEL_MOCK", value)
    assert ModelConfig.from_env().mock is expected


def test_real_mode_needs_model_name():
    with pytest.raises(ModelConfigError, match="MODEL_NAME"):
        call_model(MSGS, task="text_recs", config=ModelConfig.from_env())


def test_api_key_is_not_in_repr(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY", "sk-secret-123")
    assert "sk-secret-123" not in repr(ModelConfig.from_env())


def test_bad_timeout(monkeypatch):
    monkeypatch.setenv("MODEL_TIMEOUT", "soon")
    with pytest.raises(ModelConfigError):
        ModelConfig.from_env()


# ---- mock mode ----

def test_mock_text_output_is_valid_recommendations(monkeypatch):
    monkeypatch.setenv("MODEL_MOCK", "1")
    parsed = RecommendationList.model_validate(json.loads(call_model(MSGS, task="text_recs")))
    assert parsed.recommendations and all(r.status == "pending" for r in parsed.recommendations)


def test_mock_layout_output_is_valid(monkeypatch):
    monkeypatch.setenv("MODEL_MOCK", "1")
    RecommendationList.model_validate(json.loads(call_model(MSGS, task="layout_recs")))


def test_mock_never_touches_the_network(monkeypatch):
    monkeypatch.setenv("MODEL_MOCK", "1")

    def boom(request):
        raise AssertionError("network used in mock mode")

    assert call_model(MSGS, task="text_recs", transport=fake_server(boom))


def test_mock_unknown_task(monkeypatch):
    monkeypatch.setenv("MODEL_MOCK", "1")
    with pytest.raises(KeyError):
        call_model(MSGS, task="nope")


# ---- real client against a faked HTTP server ----

def test_real_request_shape(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "some-model")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers.get("authorization")
        return ok_reply("pong")

    assert call_model(MSGS, task="text_recs", transport=fake_server(handler)) == "pong"
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["body"]["model"] == "some-model" and seen["body"]["messages"] == MSGS
    assert seen["auth"] is None


def test_real_sends_bearer_key_when_set(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "m")
    monkeypatch.setenv("MODEL_API_KEY", "k123")
    monkeypatch.setenv("MODEL_BASE_URL", "https://example.test/v1/")
    seen = {}

    def handler(request):
        seen["auth"], seen["url"] = request.headers["authorization"], str(request.url)
        return ok_reply()

    call_model(MSGS, task="text_recs", transport=fake_server(handler))
    assert seen["auth"] == "Bearer k123" and seen["url"] == "https://example.test/v1/chat/completions"


def test_http_error_becomes_clear_error(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "m")
    with pytest.raises(ModelCallError, match="500"):
        call_model(MSGS, task="text_recs", transport=fake_server(lambda r: httpx.Response(500)))


def test_unreachable_server_becomes_clear_error(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "m")

    def refuse(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ModelCallError, match="Could not reach"):
        call_model(MSGS, task="text_recs", transport=fake_server(refuse))


def test_wrong_reply_format_becomes_clear_error(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "m")
    with pytest.raises(ModelCallError, match="format"):
        call_model(MSGS, task="text_recs", transport=fake_server(lambda r: httpx.Response(200, json={"oops": 1})))


# ---- imports ----

def test_recommendation_is_theirs_not_a_copy():
    from app.schemas import Recommendation as Theirs
    assert Recommendation is Theirs


def test_importing_model_package_does_not_need_fastmcp():
    """Block fastmcp in a fresh interpreter, then import the whole model package."""
    code = (
        "import sys; sys.modules['fastmcp'] = None; sys.path.insert(0, '.');"
        "import app.model.client, app.model.schemas, app.model.config; print('ok')"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=BACKEND_DIR, capture_output=True, text=True)
    assert out.returncode == 0 and "ok" in out.stdout, out.stderr
