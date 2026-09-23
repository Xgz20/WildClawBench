from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.agents.base import AgentExecution, AgentTaskSpec, BaseAgent
from src.agents.mimocode.transcript import (
    MiMoCodeTraceFormatError,
    convert_trace,
    write_conversion,
)
from src.utils.docker_utils import (
    container_resource_args,
    run_warmup,
    setup_skills,
    snapshot_workspace_state,
)
from src.utils.model_limits import resolve_maas_max_tokens

logger = logging.getLogger(__name__)

SUPPORTED_MIMOCODE_APIS = (
    "openai-responses",
    "openai-chat-completions",
    "anthropic-messages",
)
DEFAULT_MIMOCODE_API = "openai-responses"
DEFAULT_IMAGE = "wildclawbench-mimocode-ubuntu:v0.0"
OPENCLAW_TRANSCRIPT_PATH = "/root/.openclaw/agents/main/sessions/chat.jsonl"
MIMOCODE_HOME = "/tmp/wildclaw_mimocode"
MIMOCODE_SKILLS_DIR = "/root/.agents/skills"
SRC_MOUNT = "/mnt/wildclaw_src"
PROMPT_PATH = "/tmp/wildclaw_mimocode_prompt.txt"
TRACE_FILE_NAME = "mimocode_trace.jsonl"
HOST_TIMEOUT_GRACE_SECONDS = 120

_USAGE_INTEGER_FIELDS = (
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "provider_total_tokens",
    "request_count",
)


@dataclass(frozen=True)
class MiMoCodeConfig:
    image: str
    openrouter_api_key: str
    openrouter_base_url: str
    api: str


def _argument_or_env(
    value: str | None, env_name: str, default: str, environ: Mapping[str, str]
) -> str:
    return str(environ.get(env_name, default) if value is None else value).strip()


def resolve_mimocode_config(
    *,
    image: str | None = None,
    openrouter_api_key: str | None = None,
    openrouter_base_url: str | None = None,
    api: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> MiMoCodeConfig:
    env = os.environ if environ is None else environ
    resolved_api = _argument_or_env(api, "MIMOCODE_API", DEFAULT_MIMOCODE_API, env)
    if resolved_api not in SUPPORTED_MIMOCODE_APIS:
        raise ValueError(
            f"Unsupported MiMoCode API {resolved_api!r}; expected one of: {', '.join(SUPPORTED_MIMOCODE_APIS)}"
        )
    return MiMoCodeConfig(
        image=_argument_or_env(image, "DOCKER_IMAGE_MIMOCODE", DEFAULT_IMAGE, env),
        openrouter_api_key=_argument_or_env(
            openrouter_api_key, "OPENROUTER_API_KEY", "", env
        ),
        openrouter_base_url=_argument_or_env(
            openrouter_base_url, "OPENROUTER_BASE_URL", "", env
        ),
        api=resolved_api,
    )


def normalize_mimocode_model_id(model: str) -> str:
    return model.strip().removeprefix("openrouter/")


def _env_args(values: Iterable[tuple[str, str]]) -> list[str]:
    args: list[str] = []
    for key, value in values:
        if value:
            args.extend(("-e", f"{key}={value}"))
    return args


def _env_names(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        values = raw.splitlines()
    elif isinstance(raw, (list, tuple, set)):
        values = [str(value) for value in raw]
    else:
        values = []
    return tuple(
        value.strip()
        for value in values
        if value.strip() and not value.strip().startswith("#")
    )


def build_container_command(
    config: MiMoCodeConfig,
    *,
    task_id: str,
    workspace_exec: Path,
    model: str,
    timeout_seconds: int,
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
        ("MIMOCODE_MODEL_ID", normalize_mimocode_model_id(model)),
        ("MIMOCODE_API", config.api),
        ("MIMOCODE_TIMEOUT_SECONDS", str(timeout_seconds)),
        ("MIMOCODE_THINKING_REQUESTED", (thinking or "").strip()),
        (
            "MIMOCODE_OUTPUT_LIMIT",
            str(
                resolve_maas_max_tokens(model, config.openrouter_base_url, environ=env)
                or ""
            ),
        ),
        ("OPENROUTER_API_KEY", config.openrouter_api_key),
        ("OPENROUTER_BASE_URL", config.openrouter_base_url),
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
        "-c",
        "tail -f /dev/null",
    ]


def start_mimocode_container(config: MiMoCodeConfig, **kwargs: Any) -> None:
    if not config.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY must be set for MiMoCode")
    if not config.openrouter_base_url:
        raise ValueError("OPENROUTER_BASE_URL must be set for MiMoCode")
    completed = subprocess.run(
        build_container_command(config, **kwargs), capture_output=True, text=True
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Container startup failed: {completed.stderr.strip()}")


def _atomic_json_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
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
    status_path = Path(output_dir) / "execution_status.json"
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


def append_runner_event(output_dir: Path, event: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "runner.log").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n"
        )


class MiMoCodeAgent(BaseAgent):
    def __init__(
        self,
        image: str | None = None,
        openrouter_api_key: str | None = None,
        openrouter_base_url: str | None = None,
        api: str | None = None,
    ):
        self.config = resolve_mimocode_config(
            image=image,
            openrouter_api_key=openrouter_api_key,
            openrouter_base_url=openrouter_base_url,
            api=api,
        )
        self.image = self.config.image
        self.openrouter_api_key = self.config.openrouter_api_key
        self.openrouter_base_url = self.config.openrouter_base_url
        self.api = self.config.api

    @property
    def expects_gateway(self) -> bool:
        return False

    @property
    def transcript_container_path(self) -> str:
        return OPENCLAW_TRANSCRIPT_PATH

    def prepare_grading_transcript(self, task_id: str) -> str:
        _ = task_id
        return OPENCLAW_TRANSCRIPT_PATH

    def collect_usage(
        self, task_id: str, output_dir: Path, elapsed_time: float
    ) -> dict[str, Any]:
        _ = task_id
        usage: dict[str, Any] = {
            **{field: 0 for field in _USAGE_INTEGER_FIELDS},
            "cost_usd": 0.0,
            "elapsed_time": round(elapsed_time, 2),
            "cost_status": "unavailable",
            "cost_source": "none",
            "cost_scope": "model_tokens_only",
            "cost_reason": "MiMoCode usage unavailable",
            "usage_source": "unavailable",
            "usage_complete": False,
            "request_count_source": "unavailable",
        }
        try:
            loaded = json.loads(
                (Path(output_dir) / "usage.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return usage
        if not isinstance(loaded, dict):
            return usage
        for field in _USAGE_INTEGER_FIELDS:
            value = loaded.get(field)
            if value is None:
                usage[field] = None
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value >= 0
            ):
                usage[field] = int(value)
        for field in (
            "cost_status",
            "cost_source",
            "cost_scope",
            "cost_reason",
            "usage_source",
            "usage_scope",
            "usage_limitations",
            "request_count_source",
        ):
            if isinstance(loaded.get(field), str):
                usage[field] = loaded[field]
        if isinstance(loaded.get("usage_complete"), bool):
            usage["usage_complete"] = loaded["usage_complete"]
        if isinstance(loaded.get("session_count"), int):
            usage["session_count"] = loaded["session_count"]
        usage["elapsed_time"] = round(elapsed_time, 2)
        return usage

    def run_task(self, spec: AgentTaskSpec) -> AgentExecution:
        started_at = time.perf_counter()
        task_id = spec.task_id
        model = normalize_mimocode_model_id(spec.model)
        error: str | None = None
        exit_code: int | None = None
        timed_out = False
        failure_stage: str | None = None
        container_started = False
        spec.output_dir.mkdir(parents=True, exist_ok=True)
        (spec.output_dir / "agent.log").touch(exist_ok=True)
        write_execution_status(
            spec.output_dir,
            task_id=task_id,
            harness="mimocode",
            harness_version=None,
            image=self.image,
            api=self.api,
            model=model,
            thinking_requested=spec.thinking,
            thinking_forwarded=False,
            thinking_effective="provider_default",
            timeout_seconds=spec.timeout_seconds,
            status="validating_configuration",
            timed_out=False,
            exit_code=None,
            error=None,
            failure_stage=None,
        )
        try:
            if not self.openrouter_api_key or not self.openrouter_base_url:
                failure_stage = "validating_configuration"
                raise ValueError(
                    "OPENROUTER_API_KEY and OPENROUTER_BASE_URL must be set for MiMoCode"
                )
            exec_path = Path(spec.workspace_path).expanduser() / "exec"
            exec_path.mkdir(parents=True, exist_ok=True)
            failure_stage = "starting_container"
            write_execution_status(spec.output_dir, status=failure_stage)
            self._start_container(task_id, exec_path, spec)
            container_started = True
            write_execution_status(
                spec.output_dir,
                status="container_started",
                harness_version=self._probe_harness_version(task_id),
            )
            failure_stage = "preparing_workspace"
            write_execution_status(spec.output_dir, status=failure_stage)
            self._prepare_workspace(task_id, spec.workspace_path)
            failure_stage = "preparing_skills"
            write_execution_status(spec.output_dir, status=failure_stage)
            setup_skills(
                task_id,
                str(spec.task.get("skills", "")) if spec.task else "",
                str(spec.task.get("skills_path", "")) if spec.task else "",
                container_skills_root=MIMOCODE_SKILLS_DIR,
            )
            failure_stage = "preparing_warmup"
            write_execution_status(spec.output_dir, status=failure_stage)
            run_warmup(
                task_id,
                str(spec.task.get("warmup", "")) if spec.task else "",
                detach_background=True,
            )
            failure_stage = "snapshotting_workspace"
            write_execution_status(spec.output_dir, status=failure_stage)
            snapshot_workspace_state(task_id)
            failure_stage = "preparing_harness_input"
            write_execution_status(spec.output_dir, status=failure_stage)
            self._copy_prompt(task_id, spec.prompt)
            failure_stage = "running_harness"
            write_execution_status(spec.output_dir, status=failure_stage)
            completed = self._run_mimocode(
                task_id, spec.timeout_seconds, spec.output_dir
            )
            exit_code = completed.returncode
            if exit_code == 124:
                timed_out = True
                error = "MiMoCode run timed out"
            elif exit_code == 137:
                error = "MiMoCode was force-killed (timeout or OOM; inspect container diagnostics)"
            elif exit_code != 0:
                detail = (completed.stderr or "").strip()
                error = f"MiMoCode run failed (rc={exit_code})" + (
                    f": {detail}" if detail else ""
                )
            else:
                try:
                    outcome = convert_trace(
                        spec.output_dir / TRACE_FILE_NAME,
                        allow_incomplete=True,
                        exit_code=exit_code,
                    ).terminal_result
                except MiMoCodeTraceFormatError:
                    failure_stage = "collecting_artifacts"
                    raise
                if outcome and outcome["status"] != "succeeded":
                    error = f"MiMoCode did not finish the turn: {outcome}"
        except subprocess.TimeoutExpired:
            timed_out = True
            error = "MiMoCode host timeout expired"
            append_runner_event(
                spec.output_dir,
                {
                    "type": "runner.timeout",
                    "timeout_seconds": spec.timeout_seconds,
                    "message": error,
                },
            )
        except Exception as exc:
            error = str(exc)
            append_runner_event(
                spec.output_dir,
                {"type": "runner.error", "stage": failure_stage, "message": error},
            )
        finally:
            if container_started:
                try:
                    self._export_artifacts(
                        task_id,
                        spec.output_dir,
                        prompt=spec.prompt,
                        allow_incomplete=timed_out or error is not None,
                        exit_code=exit_code,
                    )
                except Exception as exc:
                    logger.warning(
                        "[%s] Failed to export MiMoCode artifacts: %s", task_id, exc
                    )
                    if not (spec.output_dir / "usage.json").is_file():
                        self._write_zero_usage(spec.output_dir)
                    if error is None:
                        error = f"MiMoCode artifact export failed: {exc}"
                        failure_stage = "collecting_artifacts"
            elapsed = time.perf_counter() - started_at
            status = "timed_out" if timed_out else ("error" if error else "finished")
            if status == "finished":
                failure_stage = None
            write_execution_status(
                spec.output_dir,
                status=status,
                timed_out=timed_out,
                elapsed_time=round(elapsed, 2),
                exit_code=exit_code,
                error=error,
                failure_stage=failure_stage,
            )
        return AgentExecution(
            elapsed_time=time.perf_counter() - started_at,
            error=error,
            gateway_proc=None,
            agent_proc=None,
        )

    def _start_container(
        self, task_id: str, exec_path: Path, spec: AgentTaskSpec
    ) -> None:
        start_mimocode_container(
            self.config,
            task_id=task_id,
            workspace_exec=exec_path,
            model=spec.model,
            timeout_seconds=spec.timeout_seconds,
            thinking=spec.thinking,
            task_env_names=_env_names(spec.task.get("env", "") if spec.task else ""),
            lobster_env_names=_env_names(
                spec.lobster.get("env", ()) if spec.lobster else ()
            ),
        )

    @staticmethod
    def _probe_harness_version(task_id: str) -> str:
        completed = subprocess.run(
            ["docker", "exec", task_id, "mimo", "--version"],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            return "unknown"
        return (completed.stdout or completed.stderr).strip() or "unknown"

    @staticmethod
    def _prepare_workspace(task_id: str, workspace_path: str | Path) -> None:
        completed = subprocess.run(
            [
                "docker",
                "exec",
                task_id,
                "/bin/bash",
                "-c",
                f"mkdir -p /tmp_workspace && cp -r {SRC_MOUNT}/. /tmp_workspace && chmod -R u+w /tmp_workspace",
            ],
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Workspace copy failed: {completed.stderr.strip()}")
        task_tmp = Path(workspace_path).expanduser() / "tmp"
        if task_tmp.exists():
            subprocess.run(
                ["docker", "exec", task_id, "mkdir", "-p", "/tmp_workspace/tmp"],
                check=True,
                capture_output=True,
                text=True,
            )
            copied = subprocess.run(
                ["docker", "cp", f"{task_tmp}/.", f"{task_id}:/tmp_workspace/tmp/"],
                capture_output=True,
                text=True,
            )
            if copied.returncode != 0:
                raise RuntimeError(
                    f"Task tmp input copy failed: {copied.stderr.strip()}"
                )

    @staticmethod
    def _copy_prompt(task_id: str, prompt: str) -> None:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            prefix="wildclaw-mimocode-prompt-",
            suffix=".txt",
            delete=False,
        ) as handle:
            handle.write(prompt)
            host_path = Path(handle.name)
        try:
            completed = subprocess.run(
                ["docker", "cp", str(host_path), f"{task_id}:{PROMPT_PATH}"],
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"Prompt copy failed: {completed.stderr.strip()}")
        finally:
            host_path.unlink(missing_ok=True)

    def _run_mimocode(
        self, task_id: str, timeout_seconds: int, output_dir: Path
    ) -> subprocess.CompletedProcess[str]:
        command = [
            "docker",
            "exec",
            task_id,
            "/bin/bash",
            "-lc",
            f'cd /tmp_workspace && echo $$ > /tmp/wildclaw_mimocode.pid && exec /usr/local/bin/wcb-mimocode "$(cat {PROMPT_PATH})"',
        ]
        trace_path = output_dir / TRACE_FILE_NAME
        log_path = output_dir / "agent.log"
        with (
            trace_path.open("w", encoding="utf-8", errors="replace") as trace,
            log_path.open("w", encoding="utf-8", errors="replace") as log,
        ):
            proc = subprocess.Popen(command, stdout=trace, stderr=log, text=True)
            try:
                return_code = proc.wait(
                    timeout=timeout_seconds + HOST_TIMEOUT_GRACE_SECONDS
                )
            except subprocess.TimeoutExpired:
                self._terminate_mimocode_processes(task_id)
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("[%s] docker exec did not exit after kill", task_id)
                raise
        return subprocess.CompletedProcess(
            command, return_code, "", self._read_text_tail(log_path)
        )

    @staticmethod
    def _collect_native_database(task_id: str, output_dir: Path) -> None:
        # Use SQLite online backup rather than copying a live DB without its WAL.
        # Copy only session storage, never auth.json or the provider configuration.
        snapshot_path = "/tmp/wildclaw_mimocode_snapshot.db"
        script = (
            "import sqlite3; "
            f"src=sqlite3.connect('file:{MIMOCODE_HOME}/data/mimocode.db?mode=ro', uri=True); "
            f"dst=sqlite3.connect('{snapshot_path}'); "
            "src.backup(dst); dst.close(); src.close()"
        )
        backup = subprocess.run(
            ["docker", "exec", task_id, "python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if backup.returncode != 0:
            raise RuntimeError(
                f"MiMoCode native database backup failed: {backup.stderr.strip()}"
            )
        copied = subprocess.run(
            [
                "docker",
                "cp",
                f"{task_id}:{snapshot_path}",
                str(output_dir / "mimocode.db"),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if copied.returncode != 0:
            raise RuntimeError(
                f"MiMoCode native database copy failed: {copied.stderr.strip()}"
            )

    @staticmethod
    def _terminate_mimocode_processes(task_id: str) -> None:
        subprocess.run(
            [
                "docker",
                "exec",
                task_id,
                "/bin/bash",
                "-lc",
                'if [ -s /tmp/wildclaw_mimocode.pid ]; then pid=$(cat /tmp/wildclaw_mimocode.pid); kill -TERM "$pid" 2>/dev/null || true; sleep 2; kill -KILL "$pid" 2>/dev/null || true; fi',
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )

    @staticmethod
    def _export_artifacts(
        task_id: str,
        output_dir: Path,
        *,
        prompt: str,
        allow_incomplete: bool,
        exit_code: int | None = None,
    ) -> None:
        database_error = None
        try:
            MiMoCodeAgent._collect_native_database(task_id, Path(output_dir))
        except Exception as exc:
            database_error = exc
        trace_path = Path(output_dir) / TRACE_FILE_NAME
        if not trace_path.is_file() or not trace_path.stat().st_size:
            raise MiMoCodeTraceFormatError(
                f"MiMoCode native trace is missing: {trace_path}"
            )
        write_conversion(
            trace_path,
            output_dir,
            prompt=prompt,
            allow_incomplete=allow_incomplete,
            exit_code=exit_code,
            database_path=Path(output_dir) / "mimocode.db"
            if database_error is None
            else None,
        )
        transcript_dir = str(Path(OPENCLAW_TRANSCRIPT_PATH).parent)
        subprocess.run(
            ["docker", "exec", task_id, "mkdir", "-p", transcript_dir],
            check=True,
            capture_output=True,
            text=True,
        )
        copied = subprocess.run(
            [
                "docker",
                "cp",
                str(Path(output_dir) / "chat.jsonl"),
                f"{task_id}:{OPENCLAW_TRANSCRIPT_PATH}",
            ],
            capture_output=True,
            text=True,
        )
        if copied.returncode != 0:
            raise RuntimeError(f"Transcript install failed: {copied.stderr.strip()}")
        if database_error is not None:
            raise database_error

    @staticmethod
    def _write_zero_usage(output_dir: Path) -> None:
        _atomic_json_write(
            Path(output_dir) / "usage.json",
            {
                **{field: 0 for field in _USAGE_INTEGER_FIELDS},
                "cost_usd": 0.0,
                "cost_status": "unavailable",
                "cost_source": "none",
                "cost_scope": "model_tokens_only",
                "cost_reason": "MiMoCode usage unavailable after trace export or conversion failure",
                "usage_source": "unavailable",
                "usage_complete": False,
                "request_count_source": "unavailable",
            },
        )

    @staticmethod
    def _read_text_tail(path: Path, max_chars: int = 20000) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return text if len(text) <= max_chars else text[-max_chars:]
