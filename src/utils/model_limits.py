"""Candidate-model request limits shared by Harness runners.

The formal Judge has its own ``JUDGE_MAX_TOKENS`` setting and must not use
this module. This module only resolves the output limit for MaaS candidate
models. Unless an explicit ``MAAS_MAX_TOKENS`` override is present, the
limit is read from the same Astron model catalog used by AstronCode.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

MAAS_MAX_TOKENS_ENV = "MAAS_MAX_TOKENS"
MAAS_MAX_TOKENS_ENABLED_ENV = "WILDCLAW_MAAS_MAX_TOKENS_ENABLED"
ASTRON_MODELS_API_KEY_ENV = "ASTRON_MODELS_API_KEY"
ASTRON_MODELS_BASE_URL_ENV = "ASTRON_MODELS_BASE_URL"
DEFAULT_ASTRON_MODELS_BASE_URL = (
    "https://astronstudio-api-volces-prod.xf-yun.com/api/v1/model-manager"
)
MODEL_LIMIT_RESOLUTION_FILENAME = "model_limit_resolution.json"
MODEL_CATALOG_TIMEOUT_SECONDS = 8.0

# MaaS model IDs used by the benchmark. The endpoint check below also covers
# custom model IDs routed to a MaaS-compatible endpoint.
_MAAS_MODEL_PREFIXES = (
    "xop",
    "xspark",
    "xminimax",
    "xglm",
)
_MAAS_ENDPOINT_MARKERS = (
    "maas",
)
_CATALOG_API_KEY_ENV_NAMES = (
    ASTRON_MODELS_API_KEY_ENV,
    "ASTRON_API_KEY",
    "ASTRON_SPARK_API_KEY",
    "OPENROUTER_API_KEY",
)
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

_catalog_cache: dict[tuple[str, str], dict[str, Any]] = {}
_active_resolutions: dict[str, dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _bare_model_id(model: str) -> str:
    value = str(model or "").strip().lower()
    return value.split("/", 1)[1] if value.startswith("openrouter/") else value


def is_maas_model(model: str, base_url: str = "") -> bool:
    """Return whether a candidate model is routed through MaaS."""

    bare = _bare_model_id(model)
    if bare.startswith(_MAAS_MODEL_PREFIXES):
        return True
    try:
        hostname = (urlparse(str(base_url or "").strip()).hostname or "").lower()
    except ValueError:
        hostname = ""
    return any(marker in hostname for marker in _MAAS_ENDPOINT_MARKERS)


def parse_positive_int(raw: object, *, default: int | None = None) -> int | None:
    """Parse a positive integer, returning ``default`` for invalid values."""

    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def maas_max_tokens_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Return whether non-AstronCode Harnesses may inject a MaaS limit."""

    env = environ if environ is not None else os.environ
    raw = str(env.get(MAAS_MAX_TOKENS_ENABLED_ENV, "")).strip().lower()
    if not raw:
        return True
    if raw in _FALSE_VALUES:
        return False
    if raw in _TRUE_VALUES:
        return True
    logger.warning(
        "%s has an invalid value; treating it as enabled",
        MAAS_MAX_TOKENS_ENABLED_ENV,
    )
    return True


def _catalog_url(environ: Mapping[str, str]) -> str:
    base_url = (
        str(environ.get(ASTRON_MODELS_BASE_URL_ENV, "")).strip()
        or DEFAULT_ASTRON_MODELS_BASE_URL
    )
    try:
        parsed = urlsplit(base_url)
        path = parsed.path.rstrip("/")
        if not path.endswith("/models"):
            path += "/models"
        return urlunsplit(
            (parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment)
        )
    except ValueError:
        return f"{base_url.rstrip('/')}/models"


def _safe_url(value: str) -> str:
    """Remove URL credentials, query and fragment before persistence."""

    try:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.hostname:
            return "[configured; invalid URL redacted]"
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = hostname
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        return urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
    except (TypeError, ValueError):
        return "[configured; malformed URL redacted]"


def _catalog_api_key(environ: Mapping[str, str]) -> tuple[str, str | None]:
    for name in _CATALOG_API_KEY_ENV_NAMES:
        value = str(environ.get(name, "")).strip()
        if value:
            return value, name
    return "", None


def _extract_models(payload: object) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("models"), list):
        return [item for item in data["models"] if isinstance(item, dict)]
    if isinstance(payload.get("models"), list):
        return [item for item in payload["models"] if isinstance(item, dict)]
    return []


def _fetch_model_catalog(environ: Mapping[str, str]) -> dict[str, Any]:
    """Fetch and cache the Astron model catalog without persisting credentials."""

    url = _catalog_url(environ)
    api_key, credential_env = _catalog_api_key(environ)
    cache_key = (url, hashlib.sha256(api_key.encode("utf-8")).hexdigest())
    with _cache_lock:
        cached = _catalog_cache.get(cache_key)
        if cached is not None:
            return cached

        if not api_key:
            result = {
                "status": "catalog_credentials_missing",
                "catalog_url": _safe_url(url),
                "credential_env": None,
                "models": [],
                "catalog_sha256": None,
            }
            _catalog_cache[cache_key] = result
            return result

        try:
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "User-Agent": "WildClawBench/model-limit-resolver",
                },
                method="GET",
            )
            with urlopen(request, timeout=MODEL_CATALOG_TIMEOUT_SECONDS) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
            models = _extract_models(payload)
            result = {
                "status": "catalog_loaded",
                "catalog_url": _safe_url(url),
                "credential_env": credential_env,
                "models": models,
                "catalog_sha256": hashlib.sha256(raw).hexdigest(),
            }
        except (
            HTTPError,
            URLError,
            TimeoutError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            result = {
                "status": "catalog_unavailable",
                "catalog_url": _safe_url(url),
                "credential_env": credential_env,
                "models": [],
                "catalog_sha256": None,
                "error_type": type(exc).__name__,
            }
            logger.warning(
                "Astron model catalog lookup failed (%s); "
                "MaaS max token injection is disabled for this run",
                type(exc).__name__,
            )
        _catalog_cache[cache_key] = result
        return result


def _new_resolution(
    *,
    model: str,
    enabled: bool,
    status: str,
    source: str,
    max_tokens: int | None,
    catalog: Mapping[str, Any] | None = None,
    override_status: str = "unset",
) -> dict[str, Any]:
    catalog = catalog or {}
    return {
        "schema_version": 1,
        "resolved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "enabled": enabled,
        "model": _bare_model_id(model),
        "status": status,
        "source": source,
        "max_tokens": max_tokens,
        "override_status": override_status,
        "catalog_url": catalog.get("catalog_url"),
        "catalog_sha256": catalog.get("catalog_sha256"),
        "catalog_credential_env": catalog.get("credential_env"),
    }


def resolve_maas_max_tokens_details(
    model: str,
    base_url: str = "",
    *,
    environ: Mapping[str, str] | None = None,
    respect_enabled_switch: bool = True,
) -> dict[str, Any]:
    """Resolve a MaaS output limit and return non-secret provenance details."""

    env = environ if environ is not None else os.environ
    bare_model = _bare_model_id(model)
    with _cache_lock:
        active = _active_resolutions.get(bare_model)
    if active is not None:
        return dict(active)

    enabled = maas_max_tokens_enabled(env)
    if respect_enabled_switch and not enabled:
        return _new_resolution(
            model=model,
            enabled=False,
            status="disabled",
            source="none",
            max_tokens=None,
        )
    if not is_maas_model(model, base_url):
        return _new_resolution(
            model=model,
            enabled=enabled,
            status="not_maas",
            source="none",
            max_tokens=None,
        )

    raw_override = str(env.get(MAAS_MAX_TOKENS_ENV, "")).strip()
    override_status = "unset"
    if raw_override:
        override = parse_positive_int(raw_override)
        if override is not None:
            return _new_resolution(
                model=model,
                enabled=enabled,
                status="resolved",
                source="explicit_env",
                max_tokens=override,
                override_status="valid",
            )
        override_status = "invalid"
        logger.warning(
            "%s must be a positive integer; falling back to the Astron model catalog",
            MAAS_MAX_TOKENS_ENV,
        )

    catalog = _fetch_model_catalog(env)
    if catalog["status"] != "catalog_loaded":
        return _new_resolution(
            model=model,
            enabled=enabled,
            status=str(catalog["status"]),
            source="astron_model_catalog",
            max_tokens=None,
            catalog=catalog,
            override_status=override_status,
        )

    matched = next(
        (
            entry
            for entry in catalog["models"]
            if str(entry.get("slug", "")).strip().lower() == bare_model
        ),
        None,
    )
    if matched is None:
        return _new_resolution(
            model=model,
            enabled=enabled,
            status="model_not_found",
            source="astron_model_catalog",
            max_tokens=None,
            catalog=catalog,
            override_status=override_status,
        )

    max_tokens = parse_positive_int(matched.get("max_output_tokens"))
    if max_tokens is None:
        return _new_resolution(
            model=model,
            enabled=enabled,
            status="max_output_tokens_missing",
            source="astron_model_catalog",
            max_tokens=None,
            catalog=catalog,
            override_status=override_status,
        )
    return _new_resolution(
        model=model,
        enabled=enabled,
        status="resolved",
        source="astron_model_catalog",
        max_tokens=max_tokens,
        catalog=catalog,
        override_status=override_status,
    )


def resolve_maas_max_tokens(
    model: str,
    base_url: str = "",
    *,
    environ: Mapping[str, str] | None = None,
    respect_enabled_switch: bool = True,
) -> int | None:
    """Resolve the MaaS candidate output limit, or ``None`` when not injected."""

    return resolve_maas_max_tokens_details(
        model,
        base_url,
        environ=environ,
        respect_enabled_switch=respect_enabled_switch,
    )["max_tokens"]


def prepare_maas_max_tokens_resolution(
    model: str,
    base_url: str,
    output_root: Path,
    *,
    resume: bool = False,
    environ: Mapping[str, str] | None = None,
    respect_enabled_switch: bool = True,
    native_managed: bool = False,
) -> dict[str, Any]:
    """Resolve once for a run, persist provenance and prime all worker threads."""

    env = environ if environ is not None else os.environ
    path = Path(output_root) / MODEL_LIMIT_RESOLUTION_FILENAME
    bare_model = _bare_model_id(model)
    resolution: dict[str, Any] | None = None
    if resume and path.is_file():
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
            if (
                isinstance(candidate, dict)
                and candidate.get("schema_version") == 1
                and candidate.get("model") == bare_model
            ):
                resolution = candidate
                resolution["reused_from_snapshot"] = True
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Ignoring invalid model limit snapshot %s: %s", path, exc)

    if resolution is None:
        if native_managed:
            resolution = _new_resolution(
                model=model,
                enabled=maas_max_tokens_enabled(env),
                status="native_managed",
                source="astroncode_model_catalog",
                max_tokens=None,
            )
        else:
            resolution = resolve_maas_max_tokens_details(
                model,
                base_url,
                environ=environ,
                respect_enabled_switch=respect_enabled_switch,
            )
        resolution["reused_from_snapshot"] = False

    resolution["enabled_switch_applies"] = respect_enabled_switch
    resolution["catalog_url"] = resolution.get("catalog_url") or _safe_url(
        _catalog_url(env)
    )

    with _cache_lock:
        _active_resolutions[bare_model] = dict(resolution)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(resolution, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(path)
    except OSError as exc:
        logger.warning("Failed to write model limit resolution %s: %s", path, exc)
    return dict(resolution)


def clear_model_limit_caches() -> None:
    """Clear process caches. Intended for deterministic tests only."""

    with _cache_lock:
        _catalog_cache.clear()
        _active_resolutions.clear()
