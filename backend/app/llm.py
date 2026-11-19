"""LLM access through OpenAI-compatible endpoints: Groq first, Gemini as backup.

The AI understands text and proposes options; it never decides feasibility.
"""
from __future__ import annotations

import json
import time
import re

import httpx

from .config import env, offline

PROVIDERS = {
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "key": "GROQ_API_KEY",
             "model": "GROQ_MODEL", "default": "openai/gpt-oss-120b"},
    "gemini": {"url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "key": "GEMINI_API_KEY",
               "model": "GEMINI_MODEL", "default": "gemini-flash-lite-latest"},
}


class LLMUnavailable(Exception):
    pass


def configured(vision: bool = False) -> list[str]:
    if offline():
        return []
    order = [p.strip() for p in env("LLM_PROVIDER_ORDER", "groq,gemini").split(",") if p.strip()]
    names = [p for p in order if p in PROVIDERS and env(PROVIDERS[p]["key"])]
    return [p for p in names if p == "gemini"] if vision else names


def status() -> dict:
    return {"providers": configured(), "vision": configured(vision=True)}


def _post(provider: str, body: dict, timeout: float = 60) -> dict:
    """One call; on a rate limit (429/503) wait as the service asks (max ~20 s) and retry up to twice."""
    import time
    cfg = PROVIDERS[provider]
    body = {"model": env(cfg["model"]) or cfg["default"], **body}
    from . import auth  # the activity monitor counts every AI call made for a request
    for attempt in range(3):
        t0 = time.time()
        try:
            r = httpx.post(cfg["url"], json=body, timeout=timeout,
                           headers={"Authorization": f"Bearer {env(cfg['key'])}", "Content-Type": "application/json"})
        except Exception:
            auth.track("ai", provider, (time.time() - t0) * 1000, ok=False)
            raise
        auth.track("ai", provider, (time.time() - t0) * 1000, ok=r.status_code < 400)
        if r.status_code in (429, 503) and attempt < 2:
            try:
                wait = float(r.headers.get("retry-after", "0"))
            except ValueError:
                wait = 0
            time.sleep(min(20.0, max(2.0, wait or 5.0 * (attempt + 1))))
            continue
        if r.status_code >= 400:
            raise httpx.HTTPStatusError(f"{r.status_code}: {r.text[:160]}", request=r.request, response=r)
        return r.json()["choices"][0]["message"]
    r.raise_for_status()
    return r.json()["choices"][0]["message"]


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < 0:
        raise ValueError("No JSON object in reply")
    return json.loads(text[start:end + 1])


def json_call(system: str, user: str | list, vision: bool = False, temperature: float = 0.2,
              max_tokens: int = 8000) -> tuple[dict, str]:
    """Ask for a JSON object. Returns (data, provider). Raises LLMUnavailable if every provider fails."""
    errors = []
    for p in configured(vision=vision):
        body = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "temperature": temperature, "max_tokens": max_tokens, "response_format": {"type": "json_object"}}
        for attempt in range(2):
            try:
                msg = _post(p, body)
                return _parse_json(msg.get("content") or ""), p
            except Exception as e:  # noqa: BLE001
                code = getattr(getattr(e, "response", None), "status_code", None)
                errors.append(f"{p}: {code or type(e).__name__}")
                body.pop("response_format", None)  # retry once without strict JSON mode
    raise LLMUnavailable("; ".join(errors) or "No AI provider configured")


def chat(messages: list, tools: list | None = None) -> tuple[dict, str]:
    errors = []
    for p in configured():
        body = {"messages": messages, "temperature": 0.3}
        if tools:
            body.update(tools=tools, tool_choice="auto")
        try:
            return _post(p, body), p
        except Exception as e:  # noqa: BLE001
            errors.append(f"{p}: {type(e).__name__}")
    raise LLMUnavailable("; ".join(errors) or "No AI provider configured")
