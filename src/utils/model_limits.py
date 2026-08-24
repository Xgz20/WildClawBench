"""Candidate-model request limits shared by Harness runners.

The formal Judge has its own ``JUDGE_MAX_TOKENS`` setting and must not use
this module.  This module only resolves the output limit for MaaS candidate
models, whose OpenAI-compatible request body uses ``max_tokens`` (or the
equivalent Harness configuration field).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlparse

DEFAULT_MAAS_MAX_TOKENS = 16384
MAAS_MAX_TOKENS_ENV = "MAAS_MAX_TOKENS"

# MaaS model IDs used by the benchmark.  The endpoint check below also covers
# custom model IDs routed to an iFlytek MaaS-compatible endpoint.
_MAAS_MODEL_PREFIXES = (
    "xop",
    "xspark",
    "xminimax",
    "xglm",
)
_MAAS_ENDPOINT_MARKERS = (
    "maas",
)


def _bare_model_id(model: str) -> str:
    value = str(model or "").strip().lower()
    return value.split("/", 1)[1] if value.startswith("openrouter/") else value


def is_maas_model(model: str, base_url: str = "") -> bool:
    """Return whether a candidate model is routed through MaaS.

    A model prefix alone is sufficient for the benchmark's ``xop*`` models;
    otherwise the endpoint hostname must carry an explicit MaaS/iFlytek
    marker.  This keeps ordinary OpenRouter, Anthropic, GPT and DeepSeek runs
    unchanged even when ``MAAS_MAX_TOKENS`` is present in the environment.
    """

    bare = _bare_model_id(model)
    if bare.startswith(_MAAS_MODEL_PREFIXES):
        return True
    try:
        hostname = (urlparse(str(base_url or "").strip()).hostname or "").lower()
    except ValueError:
        hostname = ""
    return any(marker in hostname for marker in _MAAS_ENDPOINT_MARKERS)


def parse_positive_int(raw: object, *, default: int = DEFAULT_MAAS_MAX_TOKENS) -> int:
    """Parse a positive integer, falling back safely for invalid values."""

    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def resolve_maas_max_tokens(
    model: str,
    base_url: str = "",
    *,
    environ: Mapping[str, str] | None = None,
) -> int | None:
    """Resolve the MaaS candidate output limit, or ``None`` for non-MaaS.

    ``MAAS_MAX_TOKENS`` is optional.  MaaS requests default to 16384 when it is
    absent, empty, invalid, or non-positive, as required by the evaluation
    contract.
    """

    if not is_maas_model(model, base_url):
        return None
    env = environ if environ is not None else os.environ
    raw = env.get(MAAS_MAX_TOKENS_ENV)
    if raw is None:
        return DEFAULT_MAAS_MAX_TOKENS
    return parse_positive_int(raw)
