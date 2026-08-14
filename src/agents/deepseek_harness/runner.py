from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.utils.docker_utils import container_resource_args


SUPPORTED_DSH_APIS = ("openai-completions", "openai-responses")
DEFAULT_DSH_API = "openai-completions"
DEFAULT_IMAGE = "wildclawbench-deepseek-harness-ubuntu:v0.0"
DSH_HOME = "/root/.dsh"
DSH_SESSIONS_DIR = f"{DSH_HOME}/sessions"
DSH_SKILLS_DIR = f"{DSH_HOME}/skills"
OPENCLAW_TRANSCRIPT_PATH = "/root/.openclaw/agents/main/sessions/chat.jsonl"
SRC_MOUNT = "/mnt/wildclaw_src"
PROMPT_PATH = "/tmp/wildclaw_dsh_prompt.txt"


@dataclass(frozen=True)
class DeepSeekHarnessConfig:
    image: str
    openrouter_api_key: str
    openrouter_base_url: str
    deepseek_api_key: str
    api: str


def _argument_or_env(
    value: str | None,
    env_name: str,
    default: str,
    environ: Mapping[str, str],
) -> str:
    return str(environ.get(env_name, default) if value is None else value).strip()


def resolve_dsh_config(
    *,
    image: str | None = None,
    openrouter_api_key: str | None = None,
    openrouter_base_url: str | None = None,
    deepseek_api_key: str | None = None,
    api: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> DeepSeekHarnessConfig:
    env = os.environ if environ is None else environ
    resolved_api = _argument_or_env(api, "DSH_API", DEFAULT_DSH_API, env)
    if resolved_api not in SUPPORTED_DSH_APIS:
        supported = ", ".join(SUPPORTED_DSH_APIS)
        raise ValueError(f"Unsupported DSH API {resolved_api!r}; expected one of: {supported}")
    return DeepSeekHarnessConfig(
        image=_argument_or_env(
            image,
            "DOCKER_IMAGE_DEEPSEEK_HARNESS",
            DEFAULT_IMAGE,
            env,
        ),
        openrouter_api_key=_argument_or_env(
            openrouter_api_key,
            "OPENROUTER_API_KEY",
            "",
            env,
        ),
        openrouter_base_url=_argument_or_env(
            openrouter_base_url,
            "OPENROUTER_BASE_URL",
            "",
            env,
        ),
        deepseek_api_key=_argument_or_env(
            deepseek_api_key,
            "DEEPSEEK_API_KEY",
            "",
            env,
        ),
        api=resolved_api,
    )


def normalize_dsh_model_id(model: str) -> str:
    return model.strip().removeprefix("openrouter/")


def _env_args(values: Iterable[tuple[str, str]]) -> list[str]:
    args: list[str] = []
    for key, value in values:
        if value:
            args.extend(("-e", f"{key}={value}"))
    return args


def build_container_command(
    config: DeepSeekHarnessConfig,
    *,
    task_id: str,
    workspace_exec: Path,
    model: str,
    thinking: str | None = None,
    task_env_names: Iterable[str] = (),
    lobster_env_names: Iterable[str] = (),
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    env = os.environ if environ is None else environ
    proxy_http = str(env.get("HTTP_PROXY_INNER", "")).strip()
    proxy_https = str(env.get("HTTPS_PROXY_INNER", "")).strip()
    no_proxy = str(env.get("NO_PROXY_INNER", "")).strip() if proxy_http else ""
    values: list[tuple[str, str]] = [
        ("DSH_MODEL_ID", normalize_dsh_model_id(model)),
        ("DSH_API", config.api),
        ("OPENROUTER_API_KEY", config.openrouter_api_key),
        ("OPENROUTER_BASE_URL", config.openrouter_base_url),
        ("DEEPSEEK_API_KEY", config.deepseek_api_key),
        ("DSH_REASONING", (thinking or "").strip()),
        ("http_proxy", proxy_http),
        ("https_proxy", proxy_https),
        ("HTTP_PROXY", proxy_http),
        ("HTTPS_PROXY", proxy_https),
        ("no_proxy", no_proxy),
        ("PIP_BREAK_SYSTEM_PACKAGES", "1"),
    ]
    seen = {key for key, _ in values}
    for key in (*task_env_names, *lobster_env_names):
        name = str(key).strip()
        if name and name not in seen:
            values.append((name, str(env.get(name, ""))))
            seen.add(name)

    return [
        "docker",
        "run",
        "-d",
        "--name",
        task_id,
        *container_resource_args(),
        *_env_args(values),
        "-v",
        f"{Path(workspace_exec).expanduser().resolve()}:{SRC_MOUNT}:ro",
        "--entrypoint",
        "/bin/bash",
        config.image,
        "/bin/bash",
        "-c",
        "tail -f /dev/null",
    ]


def start_dsh_container(
    config: DeepSeekHarnessConfig,
    *,
    task_id: str,
    workspace_exec: Path,
    model: str,
    thinking: str | None = None,
    task_env_names: Iterable[str] = (),
    lobster_env_names: Iterable[str] = (),
    environ: Mapping[str, str] | None = None,
) -> None:
    if not config.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY must be set for DeepSeek Harness")
    command = build_container_command(
        config,
        task_id=task_id,
        workspace_exec=workspace_exec,
        model=model,
        thinking=thinking,
        task_env_names=task_env_names,
        lobster_env_names=lobster_env_names,
        environ=environ,
    )
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(f"Container startup failed: {completed.stderr.strip()}")


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def write_execution_status(output_dir: Path, **updates: Any) -> dict[str, Any]:
    output_dir = Path(output_dir)
    status_path = output_dir / "execution_status.json"
    current: dict[str, Any] = {}
    if status_path.is_file():
        try:
            loaded = json.loads(status_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                current = loaded
        except (OSError, json.JSONDecodeError):
            current = {}
    current.update(updates)
    _atomic_json_write(status_path, current)
    return current


def append_agent_log_event(output_dir: Path, event: dict[str, Any]) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "runner.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")
