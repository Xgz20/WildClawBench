from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from src.agents.base import AgentExecution, AgentTaskSpec, BaseAgent
from src.agents.minimax_code.transcript import (
    McodeTraceFormatError,
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

SUPPORTED_MCODE_APIS = (
    "openai-completions",
    "openai-responses",
    "anthropic-messages",
)
DEFAULT_MCODE_API = "openai-completions"
DEFAULT_IMAGE = "wildclawbench-minimax-code-ubuntu:v0.0"
MCODE_DATA_DIR = "/tmp/wildclaw_mcode"
MCODE_SKILLS_DIR = f"{MCODE_DATA_DIR}/skills"
MCODE_DIAGNOSTICS_DIR = "/tmp/mcode-diagnostics"
MCODE_LAST_MESSAGE_PATH = "/tmp/mcode-last-message.txt"
MCODE_PROVIDER_LOG_PATH = "/tmp/mcode-provider.log"
OPENCLAW_TRANSCRIPT_PATH = "/root/.openclaw/agents/main/sessions/chat.jsonl"
SRC_MOUNT = "/mnt/wildclaw_src"
PROMPT_PATH = "/tmp/wildclaw_mcode_prompt.txt"
TRACE_FILE_NAME = "minimax_code_trace.jsonl"
HOST_TIMEOUT_GRACE_SECONDS = 120

_USAGE_INTEGER_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
    "provider_total_tokens",
    "request_count",
)


@dataclass(frozen=True)
class MiniMaxCodeConfig:
    image: str
    openrouter_api_key: str
    openrouter_base_url: str
    api: str


def _argument_or_env(
    value: str | None,
    env_name: str,
    default: str,
    environ: Mapping[str, str],
) -> str:
    return str(environ.get(env_name, default) if value is None else value).strip()


def resolve_mcode_config(
    *,
    image: str | None = None,
    openrouter_api_key: str | None = None,
    openrouter_base_url: str | None = None,
    api: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> MiniMaxCodeConfig:
    env = os.environ if environ is None else environ
    resolved_api = _argument_or_env(api, "MCODE_API", DEFAULT_MCODE_API, env)
    if resolved_api not in SUPPORTED_MCODE_APIS:
        supported = ", ".join(SUPPORTED_MCODE_APIS)
        raise ValueError(
            f"Unsupported MiniMax Code API {resolved_api!r}; expected one of: {supported}"
        )
    return MiniMaxCodeConfig(
        image=_argument_or_env(
            image,
            "DOCKER_IMAGE_MINIMAX_CODE",
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
        api=resolved_api,
    )


def normalize_mcode_model_id(model: str) -> str:
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
    config: MiniMaxCodeConfig,
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
        ("MCODE_MODEL_ID", normalize_mcode_model_id(model)),
        ("MCODE_API", config.api),
        ("MCODE_TIMEOUT_SECONDS", str(timeout_seconds)),
        ("MCODE_THINKING_REQUESTED", (thinking or "").strip()),
        (
            "MCODE_OUTPUT_LIMIT",
            str(
                resolve_maas_max_tokens(
                    model, config.openrouter_base_url, environ=env
                )
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


def start_mcode_container(
    config: MiniMaxCodeConfig,
    *,
    task_id: str,
    workspace_exec: Path,
    model: str,
    timeout_seconds: int,
    thinking: str | None = None,
    task_env_names: Iterable[str] = (),
    lobster_env_names: Iterable[str] = (),
    environ: Mapping[str, str] | None = None,
) -> None:
    if not config.openrouter_api_key:
        raise ValueError("OPENROUTER_API_KEY must be set for MiniMax Code")
    command = build_container_command(
        config,
        task_id=task_id,
        workspace_exec=workspace_exec,
        model=model,
        timeout_seconds=timeout_seconds,
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


def append_runner_event(output_dir: Path, event: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "runner.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        handle.write("\n")


class MiniMaxCodeAgent(BaseAgent):
    def __init__(
        self,
        image: str | None = None,
        openrouter_api_key: str | None = None,
        openrouter_base_url: str | None = None,
        api: str | None = None,
    ) -> None:
        self.config = resolve_mcode_config(
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
        self,
        task_id: str,
        output_dir: Path,
        elapsed_time: float,
    ) -> dict[str, Any]:
        _ = task_id
        usage: dict[str, Any] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "provider_total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
            "elapsed_time": round(elapsed_time, 2),
            "cost_status": "not_applicable",
            "cost_source": "none",
            "cost_scope": "none",
            "cost_reason": "",
        }
        try:
            loaded = json.loads((Path(output_dir) / "usage.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return usage
        if not isinstance(loaded, dict):
            return usage
        for field in _USAGE_INTEGER_FIELDS:
            value = loaded.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                usage[field] = int(value)
        cost = loaded.get("cost_usd")
        if isinstance(cost, (int, float)) and not isinstance(cost, bool) and cost >= 0:
            usage["cost_usd"] = float(cost)
        for field in (
            "cost_status",
            "cost_source",
            "cost_scope",
            "cost_reason",
            "usage_source",
            "request_count_source",
        ):
            if isinstance(loaded.get(field), str):
                usage[field] = loaded[field]
        if isinstance(loaded.get("usage_complete"), bool):
            usage["usage_complete"] = loaded["usage_complete"]
        usage["elapsed_time"] = round(elapsed_time, 2)
        return usage

    def run_task(self, spec: AgentTaskSpec) -> AgentExecution:
        start_time = time.perf_counter()
        task_id = spec.task_id
        normalized_model = normalize_mcode_model_id(spec.model)
        error: str | None = None
        exit_code: int | None = None
        timed_out = False
        failure_stage: str | None = None
        container_started = False
        trace_path = spec.output_dir / TRACE_FILE_NAME

        spec.output_dir.mkdir(parents=True, exist_ok=True)
        (spec.output_dir / "agent.log").touch(exist_ok=True)
        write_execution_status(
            spec.output_dir,
            task_id=task_id,
            harness="minimax-code",
            harness_version=None,
            image=self.image,
            api=self.api,
            model=normalized_model,
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
            if not self.openrouter_api_key:
                failure_stage = "validating_configuration"
                raise ValueError("OPENROUTER_API_KEY must be set for MiniMax Code")

            failure_stage = "preparing_workspace"
            write_execution_status(spec.output_dir, status=failure_stage)
            exec_path = Path(spec.workspace_path).expanduser() / "exec"
            if not exec_path.is_dir():
                logger.warning(
                    "[%s] Workspace exec dir missing, auto-creating empty directory: %s",
                    task_id,
                    exec_path,
                )
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
                container_skills_root=MCODE_SKILLS_DIR,
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
            completed = self._run_mcode(
                task_id,
                spec.timeout_seconds,
                spec.output_dir,
            )
            exit_code = completed.returncode
            terminal = convert_trace(
                trace_path,
                prompt=spec.prompt,
                allow_incomplete=True,
            ).terminal_result
            terminal_status = str((terminal or {}).get("status") or "")
            if terminal_status == "timeout":
                timed_out = True
                error = "MiniMax Code run timed out"
            elif terminal_status and terminal_status != "succeeded":
                detail = self._terminal_error_message(terminal)
                error = f"MiniMax Code run {terminal_status}"
                if detail:
                    error += f": {detail}"
            elif exit_code != 0:
                detail = (completed.stderr or "").strip()
                suffix = f": {detail}" if detail else ""
                error = f"MiniMax Code run failed (rc={exit_code}){suffix}"
        except subprocess.TimeoutExpired:
            timed_out = True
            error = "MiniMax Code host timeout expired"
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
                        allow_incomplete=timed_out,
                    )
                except Exception as exc:
                    logger.warning("[%s] Failed to export MiniMax Code artifacts: %s", task_id, exc)
                    self._write_zero_usage(spec.output_dir)
                    if error is None:
                        error = f"MiniMax Code artifact export failed: {exc}"
                        failure_stage = "collecting_artifacts"

            elapsed_time = time.perf_counter() - start_time
            if timed_out:
                status = "timed_out"
            elif error is not None:
                status = "error"
            else:
                status = "finished"
                failure_stage = None
            write_execution_status(
                spec.output_dir,
                status=status,
                timed_out=timed_out,
                elapsed_time=round(elapsed_time, 2),
                exit_code=exit_code,
                error=error,
                failure_stage=failure_stage,
            )

        return AgentExecution(
            elapsed_time=time.perf_counter() - start_time,
            error=error,
            gateway_proc=None,
            agent_proc=None,
        )

    def _start_container(self, task_id: str, exec_path: Path, spec: AgentTaskSpec) -> None:
        start_mcode_container(
            self.config,
            task_id=task_id,
            workspace_exec=exec_path,
            model=spec.model,
            timeout_seconds=spec.timeout_seconds,
            thinking=spec.thinking,
            task_env_names=_env_names(spec.task.get("env", "") if spec.task else ""),
            lobster_env_names=_env_names(spec.lobster.get("env", ()) if spec.lobster else ()),
        )

    @staticmethod
    def _probe_harness_version(task_id: str) -> str:
        completed = subprocess.run(
            ["docker", "exec", task_id, "mcode", "--version"],
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
        if not task_tmp.exists():
            return
        mkdir_tmp = subprocess.run(
            ["docker", "exec", task_id, "mkdir", "-p", "/tmp_workspace/tmp"],
            capture_output=True,
            text=True,
        )
        if mkdir_tmp.returncode != 0:
            raise RuntimeError(f"Task tmp directory creation failed: {mkdir_tmp.stderr.strip()}")
        copied = subprocess.run(
            ["docker", "cp", f"{task_tmp}/.", f"{task_id}:/tmp_workspace/tmp/"],
            capture_output=True,
            text=True,
        )
        if copied.returncode != 0:
            raise RuntimeError(f"Task tmp input copy failed: {copied.stderr.strip()}")

    @staticmethod
    def _copy_prompt(task_id: str, prompt: str) -> None:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            prefix="wildclaw-mcode-prompt-",
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

    @staticmethod
    def _build_exec_command() -> str:
        return (
            "cd /tmp_workspace && "
            "echo $$ > /tmp/wildclaw_mcode.pid && "
            f'exec /usr/local/bin/wcb-mcode "$(cat {PROMPT_PATH})"'
        )

    def _run_mcode(
        self,
        task_id: str,
        timeout_seconds: int,
        output_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            "docker",
            "exec",
            task_id,
            "/bin/bash",
            "-lc",
            self._build_exec_command(),
        ]
        trace_path = output_dir / TRACE_FILE_NAME
        log_path = output_dir / "agent.log"
        with trace_path.open("w", encoding="utf-8", errors="replace") as trace, log_path.open(
            "w", encoding="utf-8", errors="replace"
        ) as log:
            proc = subprocess.Popen(command, stdout=trace, stderr=log, text=True)
            try:
                return_code = proc.wait(
                    timeout=timeout_seconds + HOST_TIMEOUT_GRACE_SECONDS
                )
            except subprocess.TimeoutExpired:
                self._terminate_mcode_processes(task_id)
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning("[%s] docker exec did not exit after kill", task_id)
                raise
        detail = self._read_text_tail(log_path)
        return subprocess.CompletedProcess(command, return_code, "", detail)

    @staticmethod
    def _terminate_mcode_processes(task_id: str) -> None:
        subprocess.run(
            [
                "docker",
                "exec",
                task_id,
                "/bin/bash",
                "-lc",
                (
                    "if [ -s /tmp/wildclaw_mcode.pid ]; then "
                    "pid=$(cat /tmp/wildclaw_mcode.pid); "
                    "kill -TERM \"$pid\" 2>/dev/null || true; "
                    "sleep 2; kill -KILL \"$pid\" 2>/dev/null || true; fi"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )

    @staticmethod
    def _copy_optional_artifact(
        task_id: str,
        container_path: str,
        destination: Path,
        *,
        directory: bool = False,
    ) -> None:
        kind = "-d" if directory else "-f"
        exists = subprocess.run(
            ["docker", "exec", task_id, "test", kind, container_path],
            capture_output=True,
            text=True,
        )
        if exists.returncode != 0:
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        if directory:
            destination.mkdir(parents=True, exist_ok=True)
            source = f"{task_id}:{container_path}/."
        else:
            source = f"{task_id}:{container_path}"
        copied = subprocess.run(
            ["docker", "cp", source, str(destination)],
            capture_output=True,
            text=True,
        )
        if copied.returncode != 0:
            raise RuntimeError(
                f"Artifact copy failed for {container_path}: {copied.stderr.strip()}"
            )

    @staticmethod
    def _export_artifacts(
        task_id: str,
        output_dir: Path,
        *,
        prompt: str,
        allow_incomplete: bool,
    ) -> None:
        output_dir = Path(output_dir)
        MiniMaxCodeAgent._copy_optional_artifact(
            task_id,
            MCODE_DIAGNOSTICS_DIR,
            output_dir / "minimax_code_diagnostics",
            directory=True,
        )
        MiniMaxCodeAgent._copy_optional_artifact(
            task_id,
            MCODE_LAST_MESSAGE_PATH,
            output_dir / "minimax_code_last_message.txt",
        )
        MiniMaxCodeAgent._copy_optional_artifact(
            task_id,
            MCODE_PROVIDER_LOG_PATH,
            output_dir / "minimax_code_provider.log",
        )
        trace_path = output_dir / TRACE_FILE_NAME
        if not trace_path.is_file() or not trace_path.stat().st_size:
            raise McodeTraceFormatError(f"MiniMax Code native trace is missing: {trace_path}")
        write_conversion(
            trace_path,
            output_dir,
            prompt=prompt,
            allow_incomplete=allow_incomplete,
        )
        transcript_dir = str(Path(OPENCLAW_TRANSCRIPT_PATH).parent)
        mkdir_result = subprocess.run(
            ["docker", "exec", task_id, "mkdir", "-p", transcript_dir],
            capture_output=True,
            text=True,
        )
        if mkdir_result.returncode != 0:
            raise RuntimeError(
                f"Transcript directory creation failed: {mkdir_result.stderr.strip()}"
            )
        copy_result = subprocess.run(
            [
                "docker",
                "cp",
                str(output_dir / "chat.jsonl"),
                f"{task_id}:{OPENCLAW_TRANSCRIPT_PATH}",
            ],
            capture_output=True,
            text=True,
        )
        if copy_result.returncode != 0:
            raise RuntimeError(f"Transcript install failed: {copy_result.stderr.strip()}")

    @staticmethod
    def _terminal_error_message(result: dict[str, Any] | None) -> str:
        if not isinstance(result, dict) or not isinstance(result.get("error"), dict):
            return ""
        return str(result["error"].get("message") or "").strip()

    @staticmethod
    def _write_zero_usage(output_dir: Path) -> None:
        _atomic_json_write(
            Path(output_dir) / "usage.json",
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
                "total_tokens": 0,
                "provider_total_tokens": 0,
                "cost_usd": 0.0,
                "request_count": 0,
                "cost_status": "unavailable",
                "cost_source": "none",
                "cost_scope": "model_tokens_only",
                "cost_reason": "MiniMax Code usage unavailable after trace export or conversion failure",
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
