"""Bring-your-own-key model client, the checked AI steps and the local /api/ai endpoint."""

import io
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from careeros import ai, llm

ROOT = Path(__file__).resolve().parents[1]
KEY = "sk-test-secret-123"


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def capture(monkeypatch, reply: dict):
    seen = {}

    def fake(req, timeout=0):
        seen["url"] = req.full_url
        seen["headers"] = {k.lower(): v for k, v in req.header_items()}
        seen["body"] = json.loads(req.data)
        return FakeResp(json.dumps(reply).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake)
    return seen


def test_config_picks_provider_and_never_exposes_the_key():
    assert llm.config({}) is None
    c = llm.config({"OPENAI_API_KEY": KEY})
    assert c.provider == "openai" and c.base_url == "https://api.openai.com/v1"
    c = llm.config({"CAREEROS_LLM": "anthropic", "ANTHROPIC_API_KEY": KEY, "CAREEROS_MODEL": "m1", "CAREEROS_MODEL_QUICK": "m0"})
    assert (c.model, c.quick_model, c.model_for("quick"), c.model_for("complex")) == ("m1", "m0", "m0", "m1")
    assert KEY not in json.dumps(llm.status({"CAREEROS_LLM": "anthropic", "ANTHROPIC_API_KEY": KEY}))
    assert llm.config({"OLLAMA_HOST": "http://box:11434"}).provider == "ollama"
    with pytest.raises(llm.LLMError, match="ANTHROPIC_API_KEY"):
        llm.config({"CAREEROS_LLM": "anthropic"})
    with pytest.raises(llm.LLMError, match="isn't supported"):
        llm.config({"CAREEROS_LLM": "nope"})
    assert llm.status({})["configured"] is False


@pytest.mark.parametrize("provider,env,reply,url_part,auth", [
    ("anthropic", {"ANTHROPIC_API_KEY": KEY}, {"content": [{"type": "text", "text": "hi"}]}, "api.anthropic.com/v1/messages", ("x-api-key", KEY)),
    ("openai", {"OPENAI_API_KEY": KEY, "OPENAI_BASE_URL": "https://router.example/v1/"}, {"choices": [{"message": {"content": "hi"}}]},
     "router.example/v1/chat/completions", ("authorization", f"Bearer {KEY}")),
    ("gemini", {"GEMINI_API_KEY": KEY}, {"candidates": [{"content": {"parts": [{"text": "h"}, {"text": "i"}]}}]},
     ":generateContent", ("x-goog-api-key", KEY)),
    ("ollama", {}, {"message": {"content": "hi"}}, "127.0.0.1:11434/api/chat", None),
])
def test_each_provider_request_and_reply(monkeypatch, provider, env, reply, url_part, auth):
    seen = capture(monkeypatch, reply)
    env = {"CAREEROS_LLM": provider, **env}
    assert llm.complete("hello", system="be brief", json_mode=True, env=env) == "hi"
    assert url_part in seen["url"]
    if auth:
        assert seen["headers"][auth[0]] == auth[1]
    assert "hello" in json.dumps(seen["body"])


def test_http_errors_are_readable_and_keyless(monkeypatch):
    def fail(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "no", {}, io.BytesIO(b'{"error":{"message":"invalid x-api-key"}}'))
    monkeypatch.setattr(urllib.request, "urlopen", fail)
    with pytest.raises(llm.LLMError) as e:
        llm.complete("x", env={"ANTHROPIC_API_KEY": KEY})
    assert "401" in str(e.value) and "Check your API key" in str(e.value) and KEY not in str(e.value)


def test_extract_json_handles_fences_and_chatter():
    assert llm.extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.extract_json('Sure! {"a": {"b": "x}"}} hope that helps') == {"a": {"b": "x}"}}
    assert llm.extract_json("[1, 2]") == [1, 2]
    with pytest.raises(llm.LLMError):
        llm.extract_json("no json here")


def test_dotenv_does_not_override(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text('# comment\nexport CAREEROS_T1="from-file"\nCAREEROS_T2=file\n')
    monkeypatch.setenv("CAREEROS_T2", "shell")
    monkeypatch.delenv("CAREEROS_T1", raising=False)
    llm.load_dotenv(tmp_path / ".env")
    import os
    assert os.environ["CAREEROS_T1"] == "from-file" and os.environ["CAREEROS_T2"] == "shell"
    monkeypatch.delenv("CAREEROS_T1")


def test_profile_drops_values_the_resume_does_not_contain(monkeypatch):
    resume = "Asha Rao\nasha@example.com\nSoftware Engineer at Northwind, 2024-2025\nBuilt a FastAPI service with Redis caching"
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {
        "basics": {"name": "Asha Rao", "email": "asha@example.com"},
        "experience": [{"title": "Software Engineer", "company": "Northwind", "bullets": [
            "Built a FastAPI service with Redis caching", "Led a team of 12 engineers at Google"]}]})
    out = ai.profile(resume)
    assert out["basics"]["name"] == "Asha Rao"
    assert out["experience"][0]["bullets"] == ["Built a FastAPI service with Redis caching", ""]
    assert out["_checks"]["removedNotInResume"] == ["experience[0].bullets[1]"]


def test_posting_keeps_only_quoted_requirements(monkeypatch):
    jd = "We need 1+ years of Python in production. Kubernetes is nice to have."
    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: {"company": "Acme", "requirements": [
        {"text": "Python", "quote": "1+ years of Python in production", "mustHave": True},
        {"text": "Rust", "quote": "5 years of Rust", "mustHave": True}]})
    out = ai.posting(jd)
    assert [r["text"] for r in out["requirements"]] == ["Python"] and out["_checks"]["droppedUnquotedRequirements"] == 1


def test_evaluate_retries_with_the_check_errors_then_passes(monkeypatch):
    jd = (ROOT / "examples" / "jd.example.txt").read_text()
    good = json.loads((ROOT / "examples" / "evaluation.example.json").read_text())
    bad = dict(good, score=1.0)  # outside the dimensions' range
    prompts = []

    def fake(prompt, **k):
        prompts.append(prompt)
        return bad if len(prompts) == 1 else good
    monkeypatch.setattr(llm, "complete_json", fake)
    ev, _ = ai.evaluate(jd, "resume text")
    assert ev["score"] == good["score"] and len(prompts) == 2 and "failed these checks" in prompts[1]

    monkeypatch.setattr(llm, "complete_json", lambda *a, **k: bad)
    with pytest.raises(llm.LLMError, match="didn't pass"):
        ai.evaluate(jd, "resume text")


def test_server_ai_endpoint(monkeypatch, tmp_path):
    from http.server import ThreadingHTTPServer

    from careeros.server import make_handler
    from careeros.store import Store

    monkeypatch.setenv("CAREEROS_LLM", "ollama")
    monkeypatch.setattr(llm, "complete_json", lambda prompt, **k: {"echo": prompt})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Store(tmp_path / "db.sqlite"), tmp_path))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_port}"

    def post(headers, body=b'{"prompt": "hi", "json": true}'):
        req = urllib.request.Request(base + "/api/ai", data=body, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    try:
        with urllib.request.urlopen(base + "/api/health") as r:
            assert json.loads(r.read())["ai"] is True
        assert post({"Content-Type": "application/json"}) == (200, {"json": {"echo": "hi"}})
        assert post({"Content-Type": "application/json", "Origin": base}) == (200, {"json": {"echo": "hi"}})
        assert post({"Content-Type": "application/json", "Origin": "https://evil.example"})[0] == 403
        assert post({"Content-Type": "text/plain"})[0] == 403
    finally:
        httpd.shutdown()


def test_cli_llm_status(monkeypatch, capsys):
    from careeros.cli import main
    monkeypatch.setenv("CAREEROS_LLM", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    main(["llm"])
    out = capsys.readouterr().out
    assert "Provider: openai" in out and KEY not in out
