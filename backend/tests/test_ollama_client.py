"""Tests for ollama_client.generate_response_ollama — uses mocked urllib.request."""
import json
import os
import sys
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_builds_correct_request_payload():
    from app.services.ollama_client import generate_response_ollama

    captured = {}

    def fake_urlopen(req, timeout):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse(json.dumps({"message": {"content": "ok"}}).encode("utf-8"))

    with patch("app.services.ollama_client.urllib.request.urlopen", side_effect=fake_urlopen):
        result = generate_response_ollama("SYS", "ctx with nik 3171234567890123", "hist", "Q?")

    assert result == "ok"
    assert captured["url"].endswith("/api/chat")
    assert captured["data"]["model"] == "qwen2.5:7b"
    assert captured["data"]["stream"] is False
    assert captured["timeout"] == 90
    msgs = captured["data"]["messages"]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[-1] == {"role": "user", "content": "Q?"}
    assert any("hist" in m["content"] for m in msgs)
    assert any("[REDACTED]" in m["content"] for m in msgs), "PII should be redacted in context"


def test_retries_on_http_error():
    from app.services.ollama_client import generate_response_ollama

    call_count = {"n": 0}

    def fake_urlopen(req, timeout):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise HTTPError(req.full_url, 500, "boom", {}, None)
        return FakeResponse(json.dumps({"message": {"content": "second try"}}).encode("utf-8"))

    with patch("app.services.ollama_client.urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("app.services.ollama_client.time.sleep") as _sleep:
            result = generate_response_ollama("SYS", "", "", "Q?")

    assert result == "second try"
    assert call_count["n"] == 2
    assert _sleep.call_count == 1


def test_raises_after_max_retries():
    from app.services.ollama_client import MAX_RETRIES, generate_response_ollama

    def fake_urlopen(req, timeout):
        raise HTTPError(req.full_url, 500, "permanent fail", {}, None)

    with patch("app.services.ollama_client.urllib.request.urlopen", side_effect=fake_urlopen):
        with patch("app.services.ollama_client.time.sleep"):
            try:
                generate_response_ollama("SYS", "", "", "Q?")
                assert False, "expected RuntimeError"
            except RuntimeError as e:
                assert f"{MAX_RETRIES} attempts" in str(e)
