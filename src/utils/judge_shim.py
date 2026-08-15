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

Legacy graders keep their task-defined JSON response shape. The declarative v2
grader opts into the fixed ``scores``/``notes`` tool schema with an internal
runner environment marker.
"""

from __future__ import annotations

import json
import os
import sys
import types
from pathlib import Path
from typing import Any
from urllib import error, request

ANTHROPIC_PREFIX = "anthropic/"
DEFAULT_ANTHROPIC_BASE_URL = "https://api.anthropic.com"
DEFAULT_JUDGE_TIMEOUT_SECONDS = 300.0


def _judge_timeout_seconds() -> float:
    raw = os.environ.get("WILDCLAW_JUDGE_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_JUDGE_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_JUDGE_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_JUDGE_TIMEOUT_SECONDS


# --- OpenAI-shaped response objects (only what graders actually read) ---------

class _Usage:
    def __init__(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.cache_read_tokens = cache_read_tokens
        self.cache_write_tokens = cache_write_tokens
        self.total_tokens = (
            prompt_tokens
            + completion_tokens
            + cache_read_tokens
            + cache_write_tokens
        )


class _Message:
    def __init__(self, content: str) -> None:
        self.content = content
        self.role = "assistant"


class _Choice:
    def __init__(self, content: str, finish_reason: str = "stop") -> None:
        self.index = 0
        self.finish_reason = finish_reason
        self.message = _Message(content)


class _Response:
    def __init__(
        self,
        content: str,
        model: str,
        usage: _Usage | None,
        *,
        response_id: str = "judge-shim",
        finish_reason: str = "stop",
        raw_response: dict[str, Any] | None = None,
    ) -> None:
        self.id = response_id
        self.model = model
        self.choices = [_Choice(content, finish_reason)]
        self.usage = usage
        self._raw_response = raw_response or {}


def _usage_dict(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if callable(getattr(usage, "model_dump", None)):
        value = usage.model_dump()
        if isinstance(value, dict):
            return value
    return {
        key: getattr(usage, key)
        for key in (
            "prompt_tokens",
            "completion_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "total_tokens",
        )
        if isinstance(getattr(usage, key, None), (int, float))
    }


def _response_audit_data(
    response: Any, *, parse_json: bool = True
) -> tuple[dict[str, Any], dict[str, Any]]:
    choice = response.choices[0]
    raw_text = str(getattr(choice.message, "content", "") or "")
    raw_response = getattr(response, "_raw_response", None)
    if raw_response is None and callable(getattr(response, "model_dump", None)):
        raw_response = response.model_dump()
    if not isinstance(raw_response, dict):
        raw_response = {}
    response_data = {
        "status": "success",
        "model": str(getattr(response, "model", "") or ""),
        "returned_model": str(getattr(response, "model", "") or ""),
        "response_id": str(getattr(response, "id", "") or ""),
        "raw_text": raw_text,
        "finish_reason": str(getattr(choice, "finish_reason", "") or ""),
        "usage": _usage_dict(getattr(response, "usage", None)),
        "raw": raw_response,
    }
    if not parse_json:
        return response_data, {
            "schema_status": "not_requested",
            "candidate_text": raw_text,
        }
    return response_data, _parse_audit_candidate(raw_text)


def _parse_audit_candidate(
    raw_text: str, wildclaw_judge_schema: str = ""
) -> dict[str, Any]:
    try:
        value = json.loads(_strip_json_fences(raw_text))
    except (TypeError, json.JSONDecodeError) as exc:
        return {
            "schema_status": "parse_error",
            "schema_error": str(exc),
            "candidate_text": raw_text,
        }
    if wildclaw_judge_schema == "scores_notes":
        if not isinstance(value, dict) or not isinstance(value.get("scores"), dict):
            return {
                "schema_status": "mismatch",
                "schema_error": "scores must be an object",
                "value": value,
            }
        if not isinstance(value.get("notes"), str):
            return {
                "schema_status": "mismatch",
                "schema_error": "notes must be a string",
                "value": value,
            }
        schema_status = "valid"
    else:
        schema_status = "not_enforced"
    return {"schema_status": schema_status, "value": value}


def _messages_expect_json(messages: list[dict[str, Any]]) -> bool:
    chunks: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            chunks.append(content)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
    text = "\n".join(chunks).lower()
    if "json" not in text:
        return False
    return any(marker in text for marker in (
        "return only",
        "respond strictly",
        "respond with exactly",
        "json object",
        "请严格",
        "请仅返回",
        "仅返回",
        "只返回",
        "json 对象",
        "json格式",
        "json 格式",
    ))


def _audit_functions():
    try:
        from _judge_audit import begin_attempt, finish_attempt
    except ImportError:
        from src.utils.judge_audit import begin_attempt, finish_attempt
    return begin_attempt, finish_attempt


def _begin_judge_audit(request_data: dict[str, Any]) -> tuple[Path, int] | None:
    audit_dir_raw = os.environ.get("WILDCLAW_JUDGE_AUDIT_DIR", "").strip()
    if not audit_dir_raw:
        return None
    try:
        begin_attempt, _ = _audit_functions()
        judge_dir = Path(audit_dir_raw)
        return judge_dir, begin_attempt(judge_dir, request_data)
    except Exception as exc:
        raise RuntimeError(f"judge audit initialization failed: {exc}") from exc


def _finish_judge_audit(
    audit_context: tuple[Path, int] | None,
    response_data: dict[str, Any],
    parsed_data: dict[str, Any],
) -> None:
    if audit_context is None:
        return
    try:
        _, finish_attempt = _audit_functions()
        finish_attempt(audit_context[0], audit_context[1], response_data, parsed_data)
    except Exception as exc:
        raise RuntimeError(f"judge audit write failed: {exc}") from exc


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
    timeout: float | None = None,
    wildclaw_judge_schema: str = "",
    **_ignored: Any,
) -> _Response:
    timeout = timeout if timeout is not None else _judge_timeout_seconds()
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

    wants_json = isinstance(response_format, dict) and response_format.get("type") == "json_object"
    force_scores_notes = wants_json and wildclaw_judge_schema == "scores_notes"
    if force_scores_notes:
        payload["tools"] = [{
            "name": "submit_grading",
            "description": "Submit the final rubric scores and concise grading notes.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "scores": {
                        "type": "object",
                        "additionalProperties": {"type": "number"},
                    },
                    "notes": {"type": "string"},
                },
                "required": ["scores", "notes"],
                "additionalProperties": False,
            },
        }]
        payload["tool_choice"] = {"type": "tool", "name": "submit_grading"}

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

    tool_inputs = [
        block.get("input")
        for block in data.get("content", [])
        if isinstance(block, dict)
        and block.get("type") == "tool_use"
        and block.get("name") == "submit_grading"
        and isinstance(block.get("input"), dict)
    ]
    text = "".join(
        block.get("text", "")
        for block in data.get("content", [])
        if isinstance(block, dict) and block.get("type") == "text"
    )

    if force_scores_notes and tool_inputs:
        text = json.dumps(tool_inputs[-1], ensure_ascii=False)
    elif wants_json:
        text = _strip_json_fences(text)

    usage_raw = data.get("usage") or {}
    usage = _Usage(
        prompt_tokens=int(usage_raw.get("input_tokens", 0) or 0),
        completion_tokens=int(usage_raw.get("output_tokens", 0) or 0),
        cache_read_tokens=int(usage_raw.get("cache_read_input_tokens", 0) or 0),
        cache_write_tokens=int(
            usage_raw.get("cache_creation_input_tokens", 0) or 0
        ),
    )
    return _Response(
        text,
        data.get("model", send_model),
        usage,
        response_id=data.get("id", "judge-shim"),
        finish_reason=data.get("stop_reason", "stop") or "stop",
        raw_response=data,
    )


# --- Drop-in OpenAI client ----------------------------------------------------

class _Completions:
    def __init__(self, client: "OpenAI") -> None:
        self._client = client

    def create(self, *, model: str, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        wildclaw_judge_schema = str(
            kwargs.pop("wildclaw_judge_schema", "")
            or os.environ.get("WILDCLAW_JUDGE_SCHEMA", "")
        )
        is_anthropic = isinstance(model, str) and model.startswith(ANTHROPIC_PREFIX)
        if is_anthropic:
            base_url = (
                os.environ.get("ANTHROPIC_BASE_URL", "").strip()
                or DEFAULT_ANTHROPIC_BASE_URL
            )
            endpoint_type = "anthropic_messages"
            endpoint = base_url.rstrip("/") + "/v1/messages"
        else:
            base_url = str(
                self._client._init_kwargs.get("base_url")
                or os.environ.get("OPENROUTER_BASE_URL", "").strip()
                or "https://api.openai.com/v1"
            )
            endpoint_type = "openai_chat_completions"
            endpoint = base_url.rstrip("/") + "/chat/completions"
        effective_requested_model = model
        if is_anthropic:
            effective_requested_model = (
                os.environ.get("ANTHROPIC_MODEL", "").strip()
                or model[len(ANTHROPIC_PREFIX):]
            )
        request_data = {
            "mode": "v2" if wildclaw_judge_schema else "legacy",
            "model": model,
            "input_model": model,
            "requested_model": effective_requested_model,
            "effective_requested_model": effective_requested_model,
            "endpoint_type": endpoint_type,
            "endpoint": endpoint,
            "timeout_seconds": self._client._timeout,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens"),
            "temperature": kwargs.get("temperature"),
            "response_format": kwargs.get("response_format"),
            "schema": wildclaw_judge_schema or None,
        }
        audit_context = _begin_judge_audit(request_data)
        try:
            if is_anthropic:
                timeout = kwargs.pop("timeout", None)
                if timeout is None:
                    timeout = self._client._timeout
                response = _anthropic_create(
                    model=model,
                    messages=messages,
                    timeout=timeout,
                    wildclaw_judge_schema=wildclaw_judge_schema,
                    **kwargs,
                )
            else:
                real = _REAL_OPENAI
                if real is None:
                    raise RuntimeError(
                        f"judge_shim: non-anthropic model {model!r} requested but the real "
                        "openai package is not available in the grading container"
                    )
                real_client = real.OpenAI(**self._client._init_kwargs)
                response = real_client.chat.completions.create(
                    model=model, messages=messages, **kwargs
                )
        except Exception as exc:
            _finish_judge_audit(
                audit_context,
                {
                    "status": "failed",
                    "model": "",
                    "returned_model": "",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "usage": {},
                },
                {"schema_status": "not_available"},
            )
            raise
        wants_json = (
            isinstance(kwargs.get("response_format"), dict)
            and kwargs["response_format"].get("type") == "json_object"
        ) or _messages_expect_json(messages)
        response_data, parsed_data = _response_audit_data(
            response, parse_json=wants_json
        )
        if wildclaw_judge_schema:
            parsed_data = _parse_audit_candidate(
                response_data["raw_text"], wildclaw_judge_schema
            )
        _finish_judge_audit(
            audit_context,
            response_data,
            parsed_data,
        )
        return response


class _Chat:
    def __init__(self, client: "OpenAI") -> None:
        self.completions = _Completions(client)


class OpenAI:
    """Drop-in replacement for ``openai.OpenAI`` used by task graders."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._init_kwargs = dict(kwargs)
        self._timeout = kwargs.get("timeout")
        if self._timeout is None:
            self._timeout = _judge_timeout_seconds()
            self._init_kwargs["timeout"] = self._timeout
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
