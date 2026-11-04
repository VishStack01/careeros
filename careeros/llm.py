"""Bring your own model: one small client for the AI steps, using your own API key.

CareerOS never ships a key and never sends your data anywhere you didn't choose.
Pick a provider with environment variables (or a `.env` file in the folder you
run CareerOS from):

    CAREEROS_LLM=anthropic   ANTHROPIC_API_KEY=...
    CAREEROS_LLM=openai      OPENAI_API_KEY=...      [OPENAI_BASE_URL=...  any OpenAI-compatible API]
    CAREEROS_LLM=gemini      GEMINI_API_KEY=...
    CAREEROS_LLM=ollama      [OLLAMA_HOST=http://127.0.0.1:11434]   no key, runs on your machine

    CAREEROS_MODEL=...         optional: one model for every step
    CAREEROS_MODEL_QUICK=...   optional: a cheaper model for small steps

When CAREEROS_LLM is unset, the first provider with a key set is used. Standard
library only: no SDKs to install. Keys are read from the environment at call time
and never printed, logged or written to disk by CareerOS.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROVIDERS = ("anthropic", "openai", "gemini", "ollama")
KEY_VARS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "ollama": ""}
# Sensible defaults; set CAREEROS_MODEL to pin the exact model you want.
DEFAULT_MODELS = {
    "anthropic": {"quick": "claude-haiku-5-5", "default": "claude-sonnet-5-5", "complex": "claude-sonnet-5-5"},
    "openai": {"quick": "gpt-4.1-mini", "default": "gpt-4.1", "complex": "gpt-4.1"},
    "gemini": {"quick": "gemini-2.5-flash", "default": "gemini-2.5-flash", "complex": "gemini-2.5-pro"},
    "ollama": {"quick": "llama3.1", "default": "llama3.1", "complex": "llama3.1"},
}
TIERS = ("quick", "default", "complex")
MAX_PROMPT = 150_000  # characters


class LLMError(RuntimeError):
    """A readable failure: no key, a refused request, or a reply that isn't what was asked for."""


def load_dotenv(path: str | Path = ".env") -> None:
    """Read KEY=value lines from a .env file into the environment, without overriding what's already set."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip().removeprefix("export ").strip()
        v = v.strip().strip('"').strip("'")
        if re.fullmatch(r"[A-Z_][A-Z0-9_]*", k) and k not in os.environ:
            os.environ[k] = v


@dataclass(frozen=True)
class Config:
    provider: str
    model: str
    quick_model: str
    base_url: str

    def model_for(self, tier: str) -> str:
        return self.quick_model if tier == "quick" else self.model

    def public(self) -> dict:
        """What is safe to show: never the key."""
        return {"configured": True, "provider": self.provider, "model": self.model, "quickModel": self.quick_model,
                "local": self.provider == "ollama"}


def config(env: dict | None = None) -> Config | None:
    """The provider and models to use, or None when nothing is configured."""
    env = os.environ if env is None else env
    provider = (env.get("CAREEROS_LLM") or "").strip().lower()
    if provider and provider not in PROVIDERS:
        raise LLMError(f"CAREEROS_LLM={provider!r} isn't supported. Use one of: {', '.join(PROVIDERS)}.")
    if not provider:
        provider = next((p for p in ("anthropic", "openai", "gemini") if env.get(KEY_VARS[p])), "")
        if not provider and env.get("OLLAMA_HOST"):
            provider = "ollama"
    if not provider:
        return None
    if KEY_VARS[provider] and not env.get(KEY_VARS[provider]):
        raise LLMError(f"CAREEROS_LLM is {provider} but {KEY_VARS[provider]} isn't set.")
    d = DEFAULT_MODELS[provider]
    model = env.get("CAREEROS_MODEL") or d["default"]
    quick = env.get("CAREEROS_MODEL_QUICK") or env.get("CAREEROS_MODEL") or d["quick"]
    base = {
        "anthropic": env.get("ANTHROPIC_BASE_URL") or "https://api.anthropic.com",
        "openai": env.get("OPENAI_BASE_URL") or "https://api.openai.com/v1",
        "gemini": env.get("GEMINI_BASE_URL") or "https://generativelanguage.googleapis.com",
        "ollama": env.get("OLLAMA_HOST") or "http://127.0.0.1:11434",
    }[provider].rstrip("/")
    return Config(provider, model, quick, base)


def status(env: dict | None = None) -> dict:
    try:
        c = config(env)
    except LLMError as e:
        return {"configured": False, "error": str(e)}
    return c.public() if c else {"configured": False, "error": "No model configured. Set CAREEROS_LLM and your API key (see .env.example)."}


def _post(url: str, body: dict, headers: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "careeros", **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            payload = json.loads(e.read().decode("utf-8", "replace"))
            err = payload.get("error", payload)
            detail = err.get("message") if isinstance(err, dict) else str(err)
        except Exception:  # noqa: BLE001 - any unreadable body
            pass
        hint = {401: " Check your API key.", 403: " Your key can't use this model.", 404: " Check the model name.",
                429: " Rate limited or out of credit; try again later."}.get(e.code, "")
        raise LLMError(f"The model provider refused the request (HTTP {e.code}).{hint} {detail}"[:400].strip()) from None
    except urllib.error.URLError as e:
        raise LLMError(f"Couldn't reach the model provider: {e.reason}") from None
    except (TimeoutError, json.JSONDecodeError) as e:
        raise LLMError(f"No usable reply from the model provider: {e}") from None


def complete(prompt: str, tier: str = "default", system: str = "", max_tokens: int = 4096,
             json_mode: bool = False, cfg: Config | None = None, timeout: float = 180, env: dict | None = None) -> str:
    """Send one prompt to your configured model and return its text."""
    env = os.environ if env is None else env
    cfg = cfg or config(env)
    if cfg is None:
        raise LLMError("No model configured. Set CAREEROS_LLM and your API key (see .env.example).")
    if tier not in TIERS:
        tier = "default"
    prompt = str(prompt)[:MAX_PROMPT]
    model = cfg.model_for(tier)
    p = cfg.provider
    if p == "anthropic":
        body = {"model": model, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        if system:
            body["system"] = system
        r = _post(f"{cfg.base_url}/v1/messages", body,
                  {"x-api-key": env.get("ANTHROPIC_API_KEY", ""), "anthropic-version": "2023-06-01"}, timeout)
        text = "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")
    elif p == "openai":
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        body = {"model": model, "messages": msgs}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = _post(f"{cfg.base_url}/chat/completions", body, {"Authorization": f"Bearer {env.get('OPENAI_API_KEY', '')}"}, timeout)
        text = ((r.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    elif p == "gemini":
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": {"maxOutputTokens": max_tokens}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if json_mode:
            body["generationConfig"]["responseMimeType"] = "application/json"
        r = _post(f"{cfg.base_url}/v1beta/models/{model}:generateContent", body, {"x-goog-api-key": env.get("GEMINI_API_KEY", "")}, timeout)
        parts = (((r.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
        text = "".join(x.get("text", "") for x in parts)
    else:  # ollama
        msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        body = {"model": model, "messages": msgs, "stream": False}
        if json_mode:
            body["format"] = "json"
        r = _post(f"{cfg.base_url}/api/chat", body, {}, timeout)
        text = (r.get("message") or {}).get("content") or ""
    if not text.strip():
        raise LLMError("The model returned an empty reply.")
    return text


def extract_json(text: str):
    """The JSON object or array in a model reply, with or without a ```json fence or chatter around it."""
    t = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.S)
    if fence:
        t = fence.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    start = min([i for i in (t.find("{"), t.find("[")) if i >= 0], default=-1)
    if start < 0:
        raise LLMError("The model didn't return JSON.")
    open_ch = t[start]
    close_ch = "}" if open_ch == "{" else "]"
    depth, in_str, esc = 0, False, False
    for i in range(start, len(t)):
        c = t[i]
        if in_str:
            esc = (c == "\\") and not esc
            if c == '"' and not esc:
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c == open_ch:
            depth += 1
        elif c == close_ch:
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(t[start:i + 1])
                except json.JSONDecodeError as e:
                    raise LLMError(f"The model's JSON didn't parse: {e}") from None
    raise LLMError("The model's JSON was cut off.")


def complete_json(prompt: str, tier: str = "default", system: str = "", **kw):
    """complete(), asking for and returning JSON. One retry when the first reply doesn't parse."""
    text = complete(prompt, tier=tier, system=system, json_mode=True, **kw)
    try:
        return extract_json(text)
    except LLMError:
        text = complete(prompt + "\n\nReturn only the JSON, with nothing before or after it.", tier=tier, system=system, json_mode=True, **kw)
        return extract_json(text)
