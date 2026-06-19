"""Tests for ollama_client.generate_response_ollama — uses mocked requests.post."""
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_builds_correct_request_payload():
    from app.services.ollama_client import generate_response_ollama

    captured = {}

    def fake_post(url, json, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        r = MagicMock()
        r.raise_for_status = MagicMock()
        r.json.return_value = {"message": {"content": "ok"}}
        return r

    with patch("app.services.ollama_client.requests.post", side_effect=fake_post):
        result = generate_response_ollama("SYS", "ctx with nik 3171234567890123", "hist", "Q?")

    assert result == "ok"
    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["model"] == "qwen2.5:7b"
    assert captured["json"]["stream"] is False
    assert captured["timeout"] == 90
    msgs = captured["json"]["messages"]
    assert msgs[0] == {"role": "system", "content": "SYS"}
    assert msgs[-1] == {"role": "user", "content": "Q?"}
    assert any("hist" in m["content"] for m in msgs)
    assert any("[REDACTED]" in m["content"] for m in msgs), "PII should be redacted in context"


def test_retries_on_http_error():
    from app.services.ollama_client import generate_response_ollama
    import requests as _req

    success = MagicMock()
    success.raise_for_status = MagicMock()
    success.json.return_value = {"message": {"content": "second try"}}

    call_count = {"n": 0}

    def fake_post(url, json, timeout):
        call_count["n"] += 1
        if call_count["n"] == 1:
            r = MagicMock()
            r.raise_for_status.side_effect = _req.HTTPError("boom")
            return r
        return success

    with patch("app.services.ollama_client.requests.post", side_effect=fake_post):
        with patch("app.services.ollama_client.time.sleep") as _sleep:
            result = generate_response_ollama("SYS", "", "", "Q?")

    assert result == "second try"
    assert call_count["n"] == 2
    assert _sleep.call_count == 1


def test_raises_after_max_retries():
    from app.services.ollama_client import MAX_RETRIES, generate_response_ollama
    import requests as _req

    def fake_post(url, json, timeout):
        r = MagicMock()
        r.raise_for_status.side_effect = _req.HTTPError("permanent fail")
        return r

    with patch("app.services.ollama_client.requests.post", side_effect=fake_post):
        with patch("app.services.ollama_client.time.sleep"):
            try:
                generate_response_ollama("SYS", "", "", "Q?")
                assert False, "expected RuntimeError"
            except RuntimeError as e:
                assert f"{MAX_RETRIES} attempts" in str(e)
