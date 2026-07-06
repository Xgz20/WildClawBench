"""OpenAI -> Anthropic judge shim (installed inside the grading container).

WildClawBench task graders call the LLM judge with an inline OpenAI client:

    from openai import OpenAI
    client = OpenAI(api_key=OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)
    resp = client.chat.completions.create(model=JUDGE_MODEL, messages=[...], ...)
    text = resp.choices[0].message.content

When the judge model is provided in Anthropic form (``anthropic/<model>``) and
the judge endpoint speaks the Anthropic Messages API (``/v1/messages``) rather
than OpenAI Chat Completions, those inline calls cannot reach it directly.

``install()`` shadows the ``openai`` module inside the grading process with a
drop-in ``OpenAI`` class. For ``anthropic/*`` models it transparently translates
the OpenAI Chat request (system extraction, ``image_url`` -> Anthropic image
blocks, ``max_tokens``) into an Anthropic Messages request and returns an
OpenAI-shaped response object. For any other model it delegates to the real
``openai`` package if it is installed.

This routes every grader's judge call to the Anthropic endpoint without editing
a single task file. Model routing / endpoint are driven purely by env:

    JUDGE_MODEL       e.g. anthropic/claude-sonnet-4-6   (prefix -> Anthropic)
    ANTHROPIC_API_KEY judge key
    ANTHROPIC_BASE_URL judge gateway base, endpoint = <base>/v1/messages
    ANTHROPIC_MODEL   (optional) exact model string to send; defaults to the
                      JUDGE_MODEL value with the ``anthropic/`` prefix stripped.
"""

from __future__ import annotations

import json
import os
import sys
import types
from typing import Any
from urllib import error, request

ANTHROPIC_PREFIX = "anthropic/"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"


# --- OpenAI-shaped response objects (only what graders actually read) ---------

class _Usage:
    def __init__(self, prompt_tokens: int = 0, completion_tokens: int = 0) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = prompt_tokens + completion_tokens


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content
        self.role = "assistant"


class _Choice:
    def __init__(self, content: str) -> None:
        self.index = 0
        self.finish_reason = "stop"
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str, model: str, usage: _Usage | None) -> None:
        self.id = "judge-shim"
        self.model = model
        self.choices = [_Choice(content)]
        self.usage = usage


# --- OpenAI -> Anthropic request translation ----------------------------------

def _image_url_to_anthropic(image_url: Any) -> dict[str, Any] | None:
    url = image_url.get("url") if isinstance(image_url, dict) else image_url
    if not isinstance(url, str) or not url:
        return None
    if url.startswith("data:"):
        try:
            head, data = url.split(",", 1)
            # head looks like: data:image/png;base64
            media_type = head[len("data:"):].split(";", 1)[0] or "image/png"
        except ValueError:
            return None
        return {
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": data},
        }
    # Remote URL (Anthropic supports url image source on recent API versions).
    return {"type": "image", "source": {"type": "url", "url": url}}


def _content_to_anthropic(content: Any) -> Any:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return "" if content is None else str(content)
    blocks: list[dict[str, Any]] = []
    for item in content:
        if isinstance(item, str):
            if item:
                blocks.append({"type": "text", "text": item})
            continue
        if not isinstance(item, dict):
            continue
        itype = item.get("type")
        if itype == "text":
            blocks.append({"type": "text", "text": item.get("text", "")})
        elif itype == "image_url":
            img = _image_url_to_anthropic(item.get("image_url"))
            if img:
                blocks.append(img)
        elif itype == "input_text":
            blocks.append({"type": "text", "text": item.get("text", "")})
        # unknown block types are dropped
    return blocks or ""


def _split_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    system_chunks: list[str] = []
    convo: list[dict[str, Any]] = []
    for msg in messages or []:
        role = msg.get("role", "user")
        content = msg.get("content")
        if role == "system":
            if isinstance(content, str):
                system_chunks.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        system_chunks.append(item.get("text", ""))
                    elif isinstance(item, str):
                        system_chunks.append(item)
            continue
        convo.append({"role": role, "content": _content_to_anthropic(content)})
    if not convo:
        convo = [{"role": "user", "content": ""}]
    return "\n".join(c for c in system_chunks if c), convo


def _strip_json_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped[3:]
        if stripped[:4].lower() == "json":
            stripped = stripped[4:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    return stripped.strip()


def _anthropic_create(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int | None = None,
    temperature: float | None = None,
    response_format: Any = None,
    timeout: float = 120.0,
    **_ignored: Any,
) -> _Response:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set for the Anthropic judge")

    send_model = os.environ.get("ANTHROPIC_MODEL", "").strip() or model[len(ANTHROPIC_PREFIX):]
    system, convo = _split_messages(messages)

    payload: dict[str, Any] = {
        "model": send_model,
        "max_tokens": int(max_tokens or 2048),
        "messages": convo,
    }
    if system:
        payload["system"] = system
    if temperature is not None:
        payload["temperature"] = float(temperature)

    base_url = os.environ.get("ANTHROPIC_BASE_URL", "").strip() or DEFAULT_ANTHROPIC_BASE_URL
    endpoint = base_url.rstrip("/") + "/v1/messages"
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "x-api-key": api_key,
            "authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        raise RuntimeError(f"Anthropic judge HTTP {exc.code}: {body}") from exc

    text = "".join(
        block.get("text", "")
        for block in data.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    )

    wants_json = isinstance(response_format, dict) and response_format.get("type") == "json_object"
    if wants_json:
        text = _strip_json_fences(text)

    usage_raw = data.get("usage") or {}
    usage = _Usage(
        prompt_tokens=int(usage_raw.get("input_tokens", 0) or 0),
        completion_tokens=int(usage_raw.get("output_tokens", 0) or 0),
    )
    return _Response(text, data.get("model", send_model), usage)


# --- Drop-in OpenAI client ----------------------------------------------------

class _Completions:
    def __init__(self, client: "OpenAI") -> None:
        self._client = client

    def create(self, *, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        if isinstance(model, str) and model.startswith(ANTHROPIC_PREFIX):
            timeout = kwargs.pop("timeout", None) or self._client._timeout or 120.0
            return _anthropic_create(
                model=model, messages=messages, timeout=timeout, **kwargs
            )
        real = _REAL_OPENAI
        if real is None:
            raise RuntimeError(
                f"judge_shim: non-anthropic model {model!r} requested but the real "
                "openai package is not available in the grading container"
            )
        real_client = real.OpenAI(**self._client._init_kwargs)
        return real_client.chat.completions.create(model=model, messages=messages, **kwargs)


class _Chat:
    def __init__(self, client: "OpenAI") -> None:
        self.completions = _Completions(client)


class OpenAI:
    """Drop-in replacement for ``openai.OpenAI`` used by task graders."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._init_kwargs = kwargs
        self._timeout = kwargs.get("timeout")
        self.chat = _Chat(self)


_REAL_OPENAI = None


def install() -> None:
    """Shadow the ``openai`` module in this process with the judge shim."""
    global _REAL_OPENAI
    if getattr(sys.modules.get("openai"), "_wildclaw_judge_shim", False):
        return
    try:
        import openai as _real  # noqa: F401 - loads & caches the real package
        _REAL_OPENAI = _real
    except Exception:
        _REAL_OPENAI = None

    shim = types.ModuleType("openai")
    shim.OpenAI = OpenAI
    shim._wildclaw_judge_shim = True
    if _REAL_OPENAI is not None:
        # Preserve commonly-referenced attributes (e.g. exception classes) so
        # graders that touch them do not crash.
        for attr in ("APIError", "APIConnectionError", "APITimeoutError",
                     "RateLimitError", "BadRequestError", "OpenAIError"):
            if hasattr(_REAL_OPENAI, attr):
                setattr(shim, attr, getattr(_REAL_OPENAI, attr))
    sys.modules["openai"] = shim
