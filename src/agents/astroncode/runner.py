from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import tarfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

from src.agents.base import AgentExecution, AgentTaskSpec, BaseAgent
from src.agents.astroncode.backend import (
    CODEX_PROMPT_PATH,
    load_skill_documents,
    prepare_codex_prompt,
    resolve_astroncode_native_web_search_mode,
    resolve_astroncode_cli_command,
)
from src.utils.docker_utils import container_resource_args, run_warmup, setup_skills, snapshot_workspace_state
from src.utils.endpoint_utils import normalize_openrouter_base_url_for_openclaw
from src.utils.model_limits import (
    DEFAULT_ASTRON_MODELS_BASE_URL,
    resolve_maas_max_tokens,
)
from src.utils.maas_proxy import (
    collect_maas_request_audit,
    start_maas_request_proxy,
)

logger = logging.getLogger(__name__)

ASTRONCODE_HOME = "/root/.acode"
ASTRONCODE_SESSIONS_DIR = f"{ASTRONCODE_HOME}/sessions"
ASTRONCODE_CONFIG_PATH = f"{ASTRONCODE_HOME}/config.toml"
ASTRONCODE_SEARCH_AGENT_CONFIG_PATH = "/opt/astroncode/search-agent.config.toml"
ASTRONCODE_SKILLS_DIR = f"{ASTRONCODE_HOME}/skills"
ASTRONCODE_TRACE_ROOT = "/tmp/rollout-traces"
ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH = "/tmp/astroncode_traces.tar.gz"
ASTRONCODE_TRACE_ARCHIVE_NAME = "astroncode_traces.tar.gz"
ASTRONCODE_INTERACTION_JSONL_NAME = "agent_interaction.jsonl"
ASTRONCODE_TRACE_EXPORT_TIMEOUT_SECONDS = 300
ASTRONCODE_TRACE_ROOT_ENV_KEYS = (
    "CODEX_ROLLOUT_TRACE_ROOT",
    "ACODE_ROLLOUT_TRACE_ROOT",
)
_TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
_FALSE_ENV_VALUES = {"0", "false", "no", "off"}
_RESERVED_CONTAINER_ENV_KEYS = frozenset(ASTRONCODE_TRACE_ROOT_ENV_KEYS)
DEFAULT_ONE_IFLYTEK_BASE_URL = "https://one.iflytek.com/api/llm/console/chat/v1"
VALID_ASTRONCODE_PROVIDERS = ("astron-spark", "one-iflytek", "openrouter")
ASTRON_MODEL_PREFIXES = ("xminimax", "xop", "xspark", "astronclaw-")
ASTRONCODE_MAAS_MAX_TOKENS_MODE_ENV = "ASTRONCODE_MAAS_MAX_TOKENS_MODE"
DEFAULT_ASTRONCODE_MAAS_MAX_TOKENS_MODE = "native"
VALID_ASTRONCODE_MAAS_MAX_TOKENS_MODES = ("native", "proxy")
OPENCLAW_TRANSCRIPT_DIR = "/root/.openclaw/agents/main/sessions"
OPENCLAW_TRANSCRIPT_PATH = f"{OPENCLAW_TRANSCRIPT_DIR}/chat.jsonl"
DEFAULT_REASONING_EFFORT = "medium" #"high"
ASTRONCODE_LOG_NOISE_MARKERS = (
    "ReasoningRawContentDelta without active item",
)


def parse_env_flag(name: str, *, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default
    normalized = raw_value.strip().lower()
    if normalized in _TRUE_ENV_VALUES:
        return True
    if normalized in _FALSE_ENV_VALUES:
        return False
    raise ValueError(
        f"{name} must be one of: 1, true, yes, on, 0, false, no, off"
    )


def resolve_astroncode_maas_max_tokens_mode(raw_value: str | None = None) -> str:
    """Resolve whether AstronCode uses its native limit or the legacy proxy."""

    configured = (
        os.environ.get(ASTRONCODE_MAAS_MAX_TOKENS_MODE_ENV, "")
        if raw_value is None
        else raw_value
    )
    mode = str(configured or "").strip().lower()
    if not mode:
        return DEFAULT_ASTRONCODE_MAAS_MAX_TOKENS_MODE
    if mode not in VALID_ASTRONCODE_MAAS_MAX_TOKENS_MODES:
        allowed = ", ".join(VALID_ASTRONCODE_MAAS_MAX_TOKENS_MODES)
        raise ValueError(
            f"{ASTRONCODE_MAAS_MAX_TOKENS_MODE_ENV} must be one of: {allowed}"
        )
    return mode


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_agent_log_event(output_dir: Path, event: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    enriched = {"timestamp": _now_iso(), **event}
    with (output_dir / "agent.log").open("a", encoding="utf-8") as log_file:
        log_file.write(json.dumps(enriched, ensure_ascii=False) + "\n")


def write_execution_status(output_dir: Path, **updates: Any) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    status_path = output_dir / "execution_status.json"
    status: dict[str, Any] = {}
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            status = {}
    previous_stage = str(status.get("status") or "")
    next_status = str(updates.get("status") or "")
    if (
        next_status in {"error", "timed_out"}
        and "failure_stage" not in updates
        and previous_stage
        and previous_stage not in {"error", "timed_out", "finished"}
    ):
        updates["failure_stage"] = previous_stage
    status.update(updates)
    status["updated_at"] = _now_iso()
    serialized = json.dumps(status, indent=2, ensure_ascii=False)
    existing_stat = None
    try:
        existing_stat = status_path.stat()
    except FileNotFoundError:
        pass

    temporary_path: Path | None = None
    temporary_fd = -1
    try:
        open_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_CLOEXEC"):
            open_flags |= os.O_CLOEXEC
        for _ in range(100):
            candidate = output_dir / (
                f".{status_path.name}.{os.urandom(12).hex()}.tmp"
            )
            try:
                temporary_fd = os.open(candidate, open_flags, 0o666)
            except FileExistsError:
                continue
            temporary_path = candidate
            break
        else:
            raise FileExistsError(
                f"could not allocate temporary status file in {output_dir}"
            )

        if existing_stat is not None:
            os.fchown(temporary_fd, existing_stat.st_uid, existing_stat.st_gid)
            os.fchmod(temporary_fd, stat.S_IMODE(existing_stat.st_mode))

        temporary_file = os.fdopen(temporary_fd, "w", encoding="utf-8")
        temporary_fd = -1
        with temporary_file:
            written = temporary_file.write(serialized)
            if written != len(serialized):
                raise OSError(
                    f"short execution status write: {written}/{len(serialized)}"
                )
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, status_path)
        temporary_path = None
    finally:
        if temporary_fd >= 0:
            try:
                os.close(temporary_fd)
            except OSError:
                pass
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
    return status


def initialize_host_run_artifacts(
    output_dir: Path,
    task_id: str,
    model: str,
    timeout_seconds: int,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "agent.log").touch(exist_ok=True)
    write_execution_status(
        output_dir,
        task_id=task_id,
        model=model,
        timeout_seconds=timeout_seconds,
        status="created",
        started_at=_now_iso(),
        timed_out=False,
        exit_code=None,
        error=None,
    )
    append_agent_log_event(
        output_dir,
        {
            "type": "runner.status",
            "stage": "created",
            "message": "Host-side run artifacts initialized before container startup.",
        },
    )


def sanitize_agent_log(log_path: Path) -> None:
    if not log_path.exists():
        return
    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return
    kept = [
        line for line in lines
        if not any(marker in line for marker in ASTRONCODE_LOG_NOISE_MARKERS)
    ]
    if len(kept) != len(lines):
        log_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")


def toml_basic_string(value: str) -> str:
    escapes = {
        '"': '\\"',
        "\\": "\\\\",
        "\b": "\\b",
        "\t": "\\t",
        "\n": "\\n",
        "\f": "\\f",
        "\r": "\\r",
    }
    escaped: list[str] = []
    for character in value:
        if character in escapes:
            escaped.append(escapes[character])
            continue
        codepoint = ord(character)
        if codepoint <= 0x1F or codepoint == 0x7F:
            escaped.append(f"\\u{codepoint:04X}")
        else:
            escaped.append(character)
    return f'"{"".join(escaped)}"'


class AstronCodeAgent(BaseAgent):
    def __init__(
        self,
        image: str | None = None,
        openrouter_api_key: str = "",
        openrouter_base_url: str = "",
        reasoning_effort_default: str = DEFAULT_REASONING_EFFORT,
        cli_command: str | None = None,
    ) -> None:
        resolved_image = (
            image
            or os.environ.get("DOCKER_IMAGE_ASTRONCODE")
            or "wildclawbench-astroncode-ubuntu:v0.6"
        )
        self.image: str = resolved_image
        self.cli_command = resolve_astroncode_cli_command(cli_command)
        self.openrouter_api_key = (
            openrouter_api_key or os.environ.get("OPENROUTER_API_KEY", "")
        ).strip()
        configured_openrouter_base_url = (
            openrouter_base_url or os.environ.get("OPENROUTER_BASE_URL", "")
        ).strip()
        self.openrouter_base_url = normalize_openrouter_base_url_for_openclaw(
            configured_openrouter_base_url
        )
        self.astron_primary_api_key = os.environ.get("ASTRON_API_KEY", "").strip()
        self.astron_spark_api_key = os.environ.get(
            "ASTRON_SPARK_API_KEY", ""
        ).strip()
        self.astron_api_key = (
            self.astron_primary_api_key
            or self.astron_spark_api_key
            or self.openrouter_api_key
        )
        self.astron_uid = os.environ.get("ASTRON_UID", "").strip()
        self.one_iflytek_api_key = (
            os.environ.get("ONE_IFLYTEK_API_KEY", "").strip()
            or self.openrouter_api_key
        )
        self.one_iflytek_base_url = (
            os.environ.get("ONE_IFLYTEK_BASE_URL", "").strip()
            or configured_openrouter_base_url
            or DEFAULT_ONE_IFLYTEK_BASE_URL
        )
        self.models_base_url = (
            os.environ.get("ASTRON_MODELS_BASE_URL", "").strip()
            or DEFAULT_ASTRON_MODELS_BASE_URL
        )
        self.trace_enabled = parse_env_flag(
            "ASTRONCODE_TRACE_ENABLED",
            default=True,
        )
        self.native_web_search_mode = resolve_astroncode_native_web_search_mode()
        self.native_web_search_enabled = (
            self.native_web_search_mode == "live"
        )
        self.maas_max_tokens_mode = resolve_astroncode_maas_max_tokens_mode()
        provider_override = (
            os.environ.get("ASTRONCODE_MODEL_PROVIDER", "").strip().lower()
        )
        if provider_override and provider_override not in VALID_ASTRONCODE_PROVIDERS:
            allowed = ", ".join(VALID_ASTRONCODE_PROVIDERS)
            raise ValueError(
                "ASTRONCODE_MODEL_PROVIDER must be one of: " + allowed
            )
        self.model_provider_override = provider_override or None
        self.reasoning_effort_default = reasoning_effort_default

    @property
    def expects_gateway(self) -> bool:
        return False

    @property
    def transcript_container_path(self) -> str:
        return ASTRONCODE_SESSIONS_DIR

    def run_task(self, spec: AgentTaskSpec) -> AgentExecution:
        elapsed_time = float(spec.timeout_seconds)
        start_time = time.perf_counter()
        task_id = spec.task_id
        initialize_host_run_artifacts(
            output_dir=spec.output_dir,
            task_id=task_id,
            model=spec.model,
            timeout_seconds=spec.timeout_seconds,
        )

        try:
            try:
                write_execution_status(spec.output_dir, status="starting_container")
                self._start_container(task_id, spec.workspace_path, spec.task, spec.lobster)
                # Record harness identity/version for traceability (which
                # AstronCode build produced these scores).
                write_execution_status(
                    spec.output_dir,
                    status="container_started",
                    harness="astroncode",
                    harness_version=self._probe_harness_version(task_id),
                    image=self.image,
                )
                write_execution_status(spec.output_dir, status="preparing_workspace")
                self._prepare_workspace(task_id, spec.workspace_path)
                skills_text = spec.task.get("skills", "") if spec.task else ""
                skills_path = spec.task.get("skills_path", "") if spec.task else ""
                setup_skills(
                    task_id,
                    skills_text,
                    skills_path,
                    container_skills_root=ASTRONCODE_SKILLS_DIR,
                )
                skill_docs = load_skill_documents(
                    skills_text,
                    skills_path,
                    container_skill_root=ASTRONCODE_SKILLS_DIR,
                )
                run_warmup(
                    task_id,
                    spec.task.get("warmup", "") if spec.task else "",
                    detach_background=True,
                )
                self._write_codex_config(
                    task_id=task_id,
                    model=spec.model,
                    reasoning_effort=spec.thinking
                    or self._default_reasoning_effort_for_model(spec.model),
                    wire_api=self._default_wire_api_for_model(spec.model),
                    output_dir=spec.output_dir,
                )
                image_helper_enabled = self._should_enable_image_helper(
                    spec.prompt, spec.workspace_path
                )
                if image_helper_enabled:
                    self._install_image_helper(task_id, spec.model)
                snapshot_workspace_state(task_id)
                write_execution_status(spec.output_dir, status="preparing_harness_input")
                self._run_prompt(
                    task_id=task_id,
                    prompt=self._build_task_prompt(
                        spec.prompt,
                        image_helper_enabled=image_helper_enabled,
                        skill_docs=skill_docs,
                    ),
                    timeout_seconds=spec.timeout_seconds,
                    output_dir=spec.output_dir,
                )
                elapsed_time = time.perf_counter() - start_time
                write_execution_status(
                    spec.output_dir,
                    status="finished",
                    timed_out=False,
                    elapsed_time=round(elapsed_time, 2),
                    exit_code=0,
                )
                return AgentExecution(
                    elapsed_time=elapsed_time, error=None, gateway_proc=None, agent_proc=None
                )
            except subprocess.TimeoutExpired:
                logger.info("[%s] AstronCode timed out...", task_id)
                elapsed_time = float(spec.timeout_seconds)
                append_agent_log_event(
                    spec.output_dir,
                    {
                        "type": "runner.timeout",
                        "message": f"AstronCode timed out after {spec.timeout_seconds} seconds.",
                        "timeout_seconds": spec.timeout_seconds,
                        "elapsed_time": elapsed_time,
                    },
                )
                write_execution_status(
                    spec.output_dir,
                    status="timed_out",
                    timed_out=True,
                    elapsed_time=round(elapsed_time, 2),
                    error="AstronCode run timed out",
                )
                return AgentExecution(
                    elapsed_time=elapsed_time,
                    error="AstronCode run timed out",
                    gateway_proc=None,
                    agent_proc=None,
                )
            except Exception as exc:
                elapsed_time = time.perf_counter() - start_time
                logger.error("[%s] AstronCode execution error: %s", task_id, exc)
                append_agent_log_event(
                    spec.output_dir,
                    {
                        "type": "runner.error",
                        "stage": "astroncode_execution",
                        "message": str(exc),
                        "elapsed_time": round(elapsed_time, 2),
                    },
                )
                write_execution_status(
                    spec.output_dir,
                    status="error",
                    error=str(exc),
                    elapsed_time=round(elapsed_time, 2),
                )
                return AgentExecution(
                    elapsed_time=elapsed_time,
                    error=str(exc),
                    gateway_proc=None,
                    agent_proc=None,
                )
        finally:
            sanitize_agent_log(spec.output_dir / "agent.log")
            try:
                self._install_openclaw_transcript_shim(task_id, spec.output_dir)
            except Exception as exc:
                logger.warning("[%s] OpenClaw transcript shim failed: %s", task_id, exc)

    def collect_usage(
        self, task_id: str, output_dir: Path, elapsed_time: float
    ) -> dict[str, Any]:
        usage = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
            "time_to_first_token_ms": None,
            "elapsed_time": round(elapsed_time, 2),
        }
        output_dir.mkdir(parents=True, exist_ok=True)
        collect_maas_request_audit(task_id, output_dir)
        self._collect_rollout_trace_archive(task_id, output_dir)

        sessions_dest = output_dir / "astroncode_sessions"
        sessions_dest.mkdir(parents=True, exist_ok=True)
        self._copy_dir_from_container(task_id, f"{ASTRONCODE_SESSIONS_DIR}/.", sessions_dest)

        latest = self._find_latest_session(task_id)
        chat_dest = output_dir / "chat.jsonl"
        if latest:
            self._copy_file_from_container(
                task_id, f"{ASTRONCODE_SESSIONS_DIR}/{latest}", chat_dest
            )

        parsed = self._extract_usage_from_jsonl(chat_dest)
        if parsed["total_tokens"] == 0 and parsed["input_tokens"] == 0:
            chat_ttft = parsed.get("time_to_first_token_ms")
            parsed = self._extract_usage_from_session_dir(sessions_dest)
            if parsed.get("time_to_first_token_ms") is None:
                parsed["time_to_first_token_ms"] = chat_ttft

        if self._run_has_explicit_execution_failure(output_dir):
            parsed["time_to_first_token_ms"] = None

        if parsed["cost_usd"] == 0.0:
            parsed["cost_usd"] = round(self._estimate_cost(parsed), 6)

        usage.update(parsed)
        usage["elapsed_time"] = round(elapsed_time, 2)
        return usage

    @staticmethod
    def _record_trace_export(output_dir: Path, result: dict[str, Any]) -> None:
        try:
            write_execution_status(output_dir, trace_export=result)
        except Exception as exc:
            logger.warning(
                "AstronCode trace export status recording failed: %s",
                AstronCodeAgent._trace_export_error("status recording", exc),
            )
        try:
            append_agent_log_event(
                output_dir,
                {"type": "runner.trace_export", **result},
            )
        except Exception as exc:
            logger.warning(
                "AstronCode trace export event recording failed: %s",
                AstronCodeAgent._trace_export_error("event recording", exc),
            )

    @staticmethod
    def _remove_partial_trace_archive(archive_path: Path) -> OSError | None:
        try:
            archive_path.unlink(missing_ok=True)
        except OSError as exc:
            return exc
        return None

    @staticmethod
    def _trace_export_error(stage: str, exc: Exception) -> str:
        detail = str(exc).strip()
        message = f"{stage} failed"
        if detail:
            message += f": {detail}"
        return message[:1000]

    @staticmethod
    def _load_trace_archive_json(
        archive: tarfile.TarFile,
        member_name: str,
    ) -> Any:
        member = archive.getmember(member_name)
        if not member.isfile():
            raise ValueError(f"trace archive member is not a file: {member_name}")
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError(f"trace archive member cannot be read: {member_name}")
        with stream:
            return json.load(stream)

    @staticmethod
    def _load_trace_archive_jsonl(
        archive: tarfile.TarFile,
        member_name: str,
    ) -> list[dict[str, Any]]:
        member = archive.getmember(member_name)
        if not member.isfile():
            raise ValueError(f"trace archive member is not a file: {member_name}")
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError(f"trace archive member cannot be read: {member_name}")
        with stream:
            return [
                json.loads(line)
                for line in stream.read().decode("utf-8").splitlines()
                if line.strip()
            ]

    @classmethod
    def _load_trace_payload(
        cls,
        archive: tarfile.TarFile,
        trace_dir: str,
        reference: dict[str, Any],
        payload_cache: dict[str, Any],
    ) -> Any:
        relative_path = PurePosixPath(str(reference.get("path", "")))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError(f"invalid trace payload path: {relative_path}")
        member_name = str(PurePosixPath(trace_dir) / relative_path)
        if member_name not in payload_cache:
            payload_cache[member_name] = cls._load_trace_archive_json(
                archive,
                member_name,
            )
        return payload_cache[member_name]

    @staticmethod
    def _extract_response_text(output_items: Any) -> str:
        text_parts: list[str] = []
        if not isinstance(output_items, list):
            return ""
        for item in output_items:
            if not isinstance(item, dict):
                continue
            if item.get("type") not in {"message", "output_text"} and item.get(
                "role"
            ) != "assistant":
                continue
            content = item.get("content")
            if isinstance(content, str):
                text_parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        text_parts.append(block["text"])
        return "\n".join(part for part in text_parts if part).strip()

    @classmethod
    def _build_agent_interaction_records(
        cls,
        archive: tarfile.TarFile,
    ) -> list[dict[str, Any]]:
        trace_dirs = sorted(
            {
                str(PurePosixPath(member.name).parent)
                for member in archive.getmembers()
                if member.isfile() and member.name.endswith("/trace.jsonl")
            }
        )
        ordered_records: list[tuple[int, int, int, str, dict[str, Any]]] = []
        event_type_names = {
            "inference_started": "model_request",
            "inference_completed": "model_response",
        }

        for trace_dir in trace_dirs:
            manifest = cls._load_trace_archive_json(
                archive,
                f"{trace_dir}/manifest.json",
            )
            trace_events = cls._load_trace_archive_jsonl(
                archive,
                f"{trace_dir}/trace.jsonl",
            )
            trace_events = sorted(trace_events, key=lambda event: event.get("seq", 0))
            payload_cache: dict[str, Any] = {}
            trace_id = manifest.get("trace_id")
            first_request: tuple[dict[str, Any], dict[str, Any], Any] | None = None
            last_response: tuple[dict[str, Any], dict[str, Any], Any] | None = None
            last_event_wall_time = 0
            last_event_seq = 0

            for event in trace_events:
                event_payload = event.get("payload", {})
                if not isinstance(event_payload, dict):
                    event_payload = {}
                event_type = event_payload.get("type", "unknown")
                raw_payloads: dict[str, Any] = {}
                for key, reference in event_payload.items():
                    if not key.endswith("_payload") or not isinstance(reference, dict):
                        continue
                    if "path" not in reference:
                        continue
                    raw_payloads[key] = {
                        **reference,
                        "data": cls._load_trace_payload(
                            archive,
                            trace_dir,
                            reference,
                            payload_cache,
                        ),
                    }

                record = {
                    "record_type": event_type_names.get(event_type, event_type),
                    "event_type": event_type,
                    "trace_id": trace_id,
                    "seq": event.get("seq"),
                    "wall_time_unix_ms": event.get("wall_time_unix_ms"),
                    "rollout_id": event.get("rollout_id"),
                    "thread_id": event.get("thread_id"),
                    "codex_turn_id": event.get("codex_turn_id"),
                    "inference_call_id": event_payload.get("inference_call_id"),
                    "tool_call_id": event_payload.get("tool_call_id"),
                    "response_id": event_payload.get("response_id"),
                    "event": event_payload,
                    "raw_payloads": raw_payloads,
                }
                wall_time = int(event.get("wall_time_unix_ms") or 0)
                seq = int(event.get("seq") or 0)
                last_event_wall_time = max(last_event_wall_time, wall_time)
                last_event_seq = max(last_event_seq, seq)
                ordered_records.append((wall_time, seq, 0, str(trace_id), record))

                if (
                    first_request is None
                    and event_type == "inference_started"
                    and raw_payloads.get("request_payload")
                ):
                    first_request = (event, raw_payloads["request_payload"], event_payload)
                if event_type == "inference_completed" and raw_payloads.get(
                    "response_payload"
                ):
                    last_response = (event, raw_payloads["response_payload"], event_payload)

            if first_request is not None:
                event, request_ref, request_event = first_request
                request_data = request_ref["data"]
                request_input = request_data.get("input") if isinstance(request_data, dict) else None
                if isinstance(request_input, list):
                    user_items = [
                        item
                        for item in request_input
                        if isinstance(item, dict) and item.get("role") == "user"
                    ]
                else:
                    user_items = request_input
                user_record = {
                    "record_type": "user_input",
                    "trace_id": trace_id,
                    "seq": event.get("seq"),
                    "wall_time_unix_ms": event.get("wall_time_unix_ms"),
                    "inference_call_id": request_event.get("inference_call_id"),
                    "request_payload": request_ref,
                    "input": request_input,
                    "user_items": user_items,
                }
                ordered_records.append(
                    (
                        int(event.get("wall_time_unix_ms") or 0),
                        int(event.get("seq") or 0),
                        -1,
                        str(trace_id),
                        user_record,
                    )
                )

            if last_response is not None:
                event, response_ref, response_event = last_response
                response_data = response_ref["data"]
                output_items = (
                    response_data.get("output_items")
                    if isinstance(response_data, dict)
                    else None
                )
                final_record = {
                    "record_type": "final_output",
                    "trace_id": trace_id,
                    "seq": event.get("seq"),
                    "wall_time_unix_ms": event.get("wall_time_unix_ms"),
                    "inference_call_id": response_event.get("inference_call_id"),
                    "response_id": response_event.get("response_id"),
                    "text": cls._extract_response_text(output_items),
                    "output_items": output_items,
                    "response_payload": response_ref,
                }
                ordered_records.append(
                    (
                        last_event_wall_time + 1,
                        last_event_seq + 1,
                        1,
                        str(trace_id),
                        final_record,
                    )
                )

        ordered_records.sort(key=lambda item: item[:4])
        return [record for _, _, _, _, record in ordered_records]

    @classmethod
    def _export_agent_interaction_jsonl(
        cls,
        archive_path: Path,
        output_path: Path,
    ) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = output_path.with_name(
            f".{output_path.name}.{os.urandom(12).hex()}.tmp"
        )
        try:
            with tarfile.open(archive_path, "r:gz") as archive:
                records = cls._build_agent_interaction_records(archive)
            with temporary_path.open("w", encoding="utf-8") as output:
                for record in records:
                    output.write(json.dumps(record, ensure_ascii=False) + "\n")
                output.flush()
                os.fsync(output.fileno())
            temporary_path.chmod(0o600)
            os.replace(temporary_path, output_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    def _collect_rollout_trace_archive(
        self,
        task_id: str,
        output_dir: Path,
    ) -> None:
        archive_path = output_dir / ASTRONCODE_TRACE_ARCHIVE_NAME
        interaction_path = output_dir / ASTRONCODE_INTERACTION_JSONL_NAME
        cleanup_error = self._remove_partial_trace_archive(archive_path)
        if cleanup_error is None:
            cleanup_error = self._remove_partial_trace_archive(interaction_path)
        if cleanup_error is not None:
            error = self._trace_export_error("host trace artifact cleanup", cleanup_error)
            self._record_trace_export(
                output_dir,
                {
                    "enabled": self.trace_enabled,
                    "status": "failed",
                    "archive": None,
                    "trace_count": 0,
                    "interaction_jsonl": None,
                    "error": error,
                },
            )
            logger.warning("[%s] AstronCode trace export failed: %s", task_id, error)
            return
        if not self.trace_enabled:
            self._record_trace_export(
                output_dir,
                {
                    "enabled": False,
                    "status": "disabled",
                    "archive": None,
                    "trace_count": 0,
                    "interaction_jsonl": None,
                    "error": None,
                },
            )
            return

        trace_root = Path(ASTRONCODE_TRACE_ROOT)
        archive_command = (
            "set -e; "
            "umask 077; "
            f"mkdir -p {shlex.quote(str(trace_root))}; "
            "trace_count=0; "
            f"for trace_dir in {shlex.quote(str(trace_root))}/trace-*; do "
            'if [ -d "$trace_dir" ] && [ ! -L "$trace_dir" ]; then '
            "trace_count=$((trace_count + 1)); "
            "fi; "
            "done; "
            f"rm -f {shlex.quote(ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH)}; "
            f"tar -C {shlex.quote(str(trace_root.parent))} -czf "
            f"{shlex.quote(ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH)} "
            f"{shlex.quote(trace_root.name)}; "
            'printf "%s" "$trace_count"'
        )
        stage = "archive command"

        try:
            archived = subprocess.run(
                ["docker", "exec", task_id, "/bin/sh", "-c", archive_command],
                capture_output=True,
                text=True,
                timeout=ASTRONCODE_TRACE_EXPORT_TIMEOUT_SECONDS,
            )
            if archived.returncode != 0:
                raise RuntimeError((archived.stderr or "").strip())

            stage = "trace count parsing"
            trace_count = int((archived.stdout or "0").strip() or "0")

            stage = "archive copy"
            copied = subprocess.run(
                [
                    "docker",
                    "cp",
                    f"{task_id}:{ASTRONCODE_TRACE_ARCHIVE_CONTAINER_PATH}",
                    str(archive_path),
                ],
                capture_output=True,
                text=True,
                timeout=ASTRONCODE_TRACE_EXPORT_TIMEOUT_SECONDS,
            )
            if copied.returncode != 0:
                raise RuntimeError((copied.stderr or "").strip())

            stage = "archive chmod"
            archive_path.chmod(0o600)
            stage = "interaction JSONL export"
            self._export_agent_interaction_jsonl(archive_path, interaction_path)
            logger.info(
                "[%s] AstronCode agent interaction JSONL exported: %s",
                task_id,
                interaction_path,
            )
            result = {
                "enabled": True,
                "status": "exported",
                "archive": ASTRONCODE_TRACE_ARCHIVE_NAME,
                "trace_count": trace_count,
                "interaction_jsonl": ASTRONCODE_INTERACTION_JSONL_NAME,
                "error": None,
            }
            if trace_count == 0:
                warning = (
                    "no rollout traces found; verify AstronCode trace environment "
                    "variable compatibility"
                )
                result["warning"] = warning
                logger.warning("[%s] AstronCode trace export warning: %s", task_id, warning)
            self._record_trace_export(output_dir, result)
            logger.info(
                "[%s] AstronCode trace archive exported (%d traces): %s",
                task_id,
                trace_count,
                archive_path,
            )
        except Exception as exc:
            error = self._trace_export_error(stage, exc)
            cleanup_error = self._remove_partial_trace_archive(archive_path)
            if cleanup_error is not None:
                cleanup_message = self._trace_export_error(
                    "host archive cleanup",
                    cleanup_error,
                )
                error = f"{error}; {cleanup_message}"[:1000]
            self._record_trace_export(
                output_dir,
                {
                    "enabled": True,
                    "status": "failed",
                    "archive": None,
                    "trace_count": 0,
                    "interaction_jsonl": None,
                    "error": error,
                },
            )
            logger.warning("[%s] AstronCode trace export failed: %s", task_id, error)

    def _start_container(
        self,
        task_id: str,
        workspace_path: str,
        task: dict[str, Any],
        lobster: dict[str, Any] | None,
    ) -> None:
        workspace = Path(workspace_path).expanduser()
        exec_path = workspace / "exec"
        if not exec_path.is_dir():
            # Some tasks (e.g. 01/task_1_arxiv_digest) ship no input files, so the
            # HF dataset has no workspace dir for them. Auto-create an empty exec
            # dir, but warn loudly in case the dataset upload is actually incomplete.
            logger.warning(
                "[%s] Workspace exec dir missing, auto-creating empty dir "
                "(assuming task has no input files; verify dataset if unexpected): %s",
                task_id,
                exec_path,
            )
            exec_path.mkdir(parents=True, exist_ok=True)

        proxy_http = os.environ.get("HTTP_PROXY_INNER", "").strip()
        proxy_https = os.environ.get("HTTPS_PROXY_INNER", "").strip()
        no_proxy = "" if not proxy_http else os.environ.get("NO_PROXY_INNER", "").strip()
        trace_root_value = ASTRONCODE_TRACE_ROOT if self.trace_enabled else ""
        env_map: dict[str, str] = {
            "OPENROUTER_API_KEY": self.openrouter_api_key,
            "ASTRON_API_KEY": self.astron_primary_api_key,
            "ASTRON_SPARK_API_KEY": (
                self.astron_spark_api_key or self.openrouter_api_key
            ),
            "OPENROUTER_BASE_URL": self.openrouter_base_url,
            "OPENROUTER_IMAGE_MODEL": os.environ.get("OPENROUTER_IMAGE_MODEL", "").strip(),
            "WILDCLAW_IMAGE_MODEL": os.environ.get("WILDCLAW_IMAGE_MODEL", "").strip(),
            "BRAVE_API_KEY": os.environ.get("BRAVE_API_KEY", ""),
            **{
                trace_env_key: trace_root_value
                for trace_env_key in ASTRONCODE_TRACE_ROOT_ENV_KEYS
            },
            "http_proxy": proxy_http,
            "https_proxy": proxy_https,
            "HTTP_PROXY": proxy_http,
            "HTTPS_PROXY": proxy_https,
            "no_proxy": no_proxy,
        }

        env_args: list[str] = []
        docker_environment = os.environ.copy()
        for key, value in env_map.items():
            if value:
                env_args += ["-e", key]
                docker_environment[key] = value

        extra_env = task.get("env", "") if task else ""
        for line in extra_env.splitlines():
            key = line.strip()
            if not key or key.startswith("#"):
                continue
            declared_key = key.partition("=")[0].strip()
            if declared_key in _RESERVED_CONTAINER_ENV_KEYS:
                raise ValueError(
                    f"Task environment variable {declared_key} is reserved for AstronCode"
                )
            value = os.environ.get(key, "").strip()
            env_args += ["-e", key]
            docker_environment[key] = value
            masked = (value[:4] + "***") if value else "(empty)"
            logger.info("[%s] Injecting env var: %s=%s", task_id, key, masked)

        for key in (lobster or {}).get("env", []) or []:
            declared_key = key.partition("=")[0].strip()
            if declared_key in _RESERVED_CONTAINER_ENV_KEYS:
                raise ValueError(
                    f"Lobster environment variable {declared_key} is reserved for AstronCode"
                )
            value = os.environ.get(key, "").strip()
            if not value:
                logger.warning(
                    "[%s] Lobster env key %s not found, skipping", task_id, key
                )
                continue
            env_args += ["-e", key]
            docker_environment[key] = value
            logger.info("[%s] Injecting lobster env: %s=%s***", task_id, key, value[:4])

        cmd = [
            "docker",
            "run",
            "-d",
            "--name",
            task_id,
            *container_resource_args(),
            *env_args,
            "-v",
            f"{exec_path}:/workspace:ro",
            self.image,
            "/bin/bash",
            "-c",
            "tail -f /dev/null",
        ]
        logger.info("[%s] Starting AstronCode container (%s)", task_id, self.image)
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=docker_environment,
        )
        if r.returncode != 0:
            raise RuntimeError(f"AstronCode container startup failed:\n{r.stderr}")
        logger.info("[%s] Container ID: %s", task_id, r.stdout.strip()[:12])

    def _probe_harness_version(self, task_id: str) -> str:
        """Read the AstronCode CLI version from inside the running container.

        Returns the version string or "" if it can't be read. Non-fatal:
        version is metadata, never blocks the run.
        """
        try:
            r = subprocess.run(
                ["docker", "exec", task_id, self.cli_command, "--version"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (subprocess.SubprocessError, OSError) as exc:
            logger.warning(
                "[%s] %s --version probe failed: %s",
                task_id,
                self.cli_command,
                exc,
            )
            return ""
        if r.returncode != 0:
            logger.warning(
                "[%s] %s --version returned %s: %s",
                task_id,
                self.cli_command,
                r.returncode,
                (r.stderr or r.stdout).strip(),
            )
            return ""
        out = (r.stdout or "").strip()
        return out.splitlines()[0].strip().split()[-1] if out else ""

    def _prepare_workspace(self, task_id: str, workspace_path: str) -> None:
        trace_directory_command = (
            f"&& mkdir -p {shlex.quote(ASTRONCODE_TRACE_ROOT)} "
            if self.trace_enabled
            else ""
        )
        r = subprocess.run(
            [
                "docker",
                "exec",
                task_id,
                "/bin/bash",
                "-c",
                (
                    "mkdir -p /tmp_workspace "
                    f"&& mkdir -p {ASTRONCODE_HOME} {ASTRONCODE_SESSIONS_DIR} "
                    f"{trace_directory_command}"
                    "&& cp -r /workspace/. /tmp_workspace "
                    "&& chmod -R u+w /tmp_workspace"
                ),
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"AstronCode workspace copy failed:\n{r.stderr}")

        tmp_path = Path(workspace_path) / "tmp"
        if tmp_path.exists():
            mkdir_tmp = subprocess.run(
                ["docker", "exec", task_id, "mkdir", "-p", "/tmp_workspace/tmp"],
                capture_output=True,
                text=True,
            )
            if mkdir_tmp.returncode != 0:
                raise RuntimeError(f"AstronCode tmp mkdir failed:\n{mkdir_tmp.stderr}")

            copied = subprocess.run(
                ["docker", "cp", f"{tmp_path}/.", f"{task_id}:/tmp_workspace/tmp/"],
                capture_output=True,
                text=True,
            )
            if copied.returncode != 0:
                raise RuntimeError(f"AstronCode tmp copy failed:\n{copied.stderr}")

    def _default_reasoning_effort_for_model(self, model: str) -> str | None:
        """Return an explicit reasoning override if one is configured.

        By default we let AstronCode CLI and the underlying model choose their
        native reasoning settings. The only automatic override we keep is the
        explicit ``ASTRONCODE_REASONING_EFFORT`` env knob, which is useful for
        controlled experiments or emergency rollouts.
        """
        override = os.environ.get("ASTRONCODE_REASONING_EFFORT", "").strip().lower()
        if override:
            return override
        return None

    def _default_wire_api_for_model(self, model: str) -> str | None:
        """Return an explicit wire API override.

        AstronCode v0.121 rejects provider-level ``wire_api = "chat"``. Keep this
        as an emergency knob only; do not default MiniMax to chat here.
        """
        _ = model
        override = os.environ.get("ASTRONCODE_WIRE_API", "").strip().lower()
        if override == "chat":
            logger.warning("ASTRONCODE_WIRE_API=chat ignored: AstronCode CLI no longer supports it")
            return None
        return override or None

    @staticmethod
    def _is_minimax_model(model: str) -> bool:
        bare_model = model.split("/", 1)[1] if model.startswith("openrouter/") else model
        return bare_model.lower().startswith("minimax/")

    def _write_codex_config(
        self,
        task_id: str,
        model: str,
        reasoning_effort: str | None,
        wire_api: str | None,
        output_dir: Path,
    ) -> None:
        bare_model = model.split("/", 1)[1] if model.startswith("openrouter/") else model
        provider = self._provider_for_model(model)
        provider_api_key = self._resolve_provider_api_key(provider)
        if not provider_api_key:
            key_hints = {
                "astron-spark": (
                    "ASTRON_API_KEY, ASTRON_SPARK_API_KEY, or OPENROUTER_API_KEY"
                ),
                "one-iflytek": "ONE_IFLYTEK_API_KEY or OPENROUTER_API_KEY",
                "openrouter": "OPENROUTER_API_KEY",
            }
            raise RuntimeError(
                f"AstronCode provider {provider} requires {key_hints[provider]}."
            )
        search_agent_config, search_agent_server_names = (
            self._read_search_agent_config_fragment(task_id)
        )
        maas_max_tokens = None
        if self.maas_max_tokens_mode == "proxy":
            maas_max_tokens = resolve_maas_max_tokens(
                model,
                self.openrouter_base_url,
                respect_enabled_switch=False,
            )
        request_base_url = None
        if maas_max_tokens is not None:
            request_base_url = start_maas_request_proxy(
                task_id,
                upstream_base_url=self.openrouter_base_url,
                max_tokens=maas_max_tokens,
            )
        config_toml = self._render_codex_config(
            model=model,
            reasoning_effort=reasoning_effort,
            wire_api=wire_api,
            provider_api_key=provider_api_key,
            redact_secrets=False,
            request_base_url=request_base_url,
        )
        debug_config_toml = self._render_codex_config(
            model=model,
            reasoning_effort=reasoning_effort,
            wire_api=wire_api,
            provider_api_key=provider_api_key,
            redact_secrets=True,
            request_base_url=request_base_url,
        )
        if search_agent_config:
            config_toml += "\n" + search_agent_config
            debug_config_toml += "\n" + "".join(
                f"[mcp_servers.{toml_basic_string(server_name)}]\n"
                for server_name in search_agent_server_names
            )

        # Mirror a redacted config host-side so future debugging is trivial.
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "config.toml").write_text(debug_config_toml, encoding="utf-8")

        config_write_command = (
            f"umask 077; mkdir -p {shlex.quote(ASTRONCODE_HOME)} "
            f"&& : > {shlex.quote(ASTRONCODE_CONFIG_PATH)} "
            f"&& chmod 600 {shlex.quote(ASTRONCODE_CONFIG_PATH)} "
            f"&& cat > {shlex.quote(ASTRONCODE_CONFIG_PATH)}"
        )
        r = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                task_id,
                "/bin/sh",
                "-c",
                config_write_command,
            ],
            input=config_toml,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(
                f"AstronCode config write failed (stage=write, rc={r.returncode})"
            )
        logger.info(
            "[%s] AstronCode config written "
            "(model=%s, provider=%s, reasoning=%s, wire_api=%s)",
            task_id,
            bare_model,
            provider,
            reasoning_effort or "model-default",
            wire_api or "default",
        )

    def _read_search_agent_config_fragment(
        self, task_id: str
    ) -> tuple[str, tuple[str, ...]]:
        path = shlex.quote(ASTRONCODE_SEARCH_AGENT_CONFIG_PATH)
        read_command = (
            f"path={path}; "
            'if [ -L "$path" ]; then exit 45; fi; '
            'if [ ! -e "$path" ]; then exit 44; fi; '
            'if [ ! -f "$path" ]; then exit 45; fi; '
            'cat "$path"'
        )
        result = subprocess.run(
            ["docker", "exec", task_id, "/bin/sh", "-c", read_command],
            capture_output=True,
            text=True,
        )
        if result.returncode == 44:
            return "", ()
        if result.returncode != 0:
            raise RuntimeError(
                "AstronCode SearchAgent config read failed "
                f"(path={ASTRONCODE_SEARCH_AGENT_CONFIG_PATH}, "
                f"stage=read, rc={result.returncode})"
            )

        fragment = result.stdout
        try:
            parsed = tomllib.loads(fragment)
        except tomllib.TOMLDecodeError:
            raise RuntimeError(
                "AstronCode SearchAgent config invalid "
                f"(path={ASTRONCODE_SEARCH_AGENT_CONFIG_PATH}, stage=parse)"
            ) from None
        if set(parsed) != {"mcp_servers"}:
            raise RuntimeError(
                "AstronCode SearchAgent config invalid "
                f"(path={ASTRONCODE_SEARCH_AGENT_CONFIG_PATH}, "
                "stage=validate-top-level)"
            )
        mcp_servers = parsed["mcp_servers"]
        if not isinstance(mcp_servers, dict) or not mcp_servers:
            raise RuntimeError(
                "AstronCode SearchAgent config invalid "
                f"(path={ASTRONCODE_SEARCH_AGENT_CONFIG_PATH}, "
                "stage=validate-mcp-servers)"
            )
        if any(not isinstance(server, dict) for server in mcp_servers.values()):
            raise RuntimeError(
                "AstronCode SearchAgent config invalid "
                f"(path={ASTRONCODE_SEARCH_AGENT_CONFIG_PATH}, "
                "stage=validate-mcp-server-tables)"
            )
        return fragment.rstrip("\r\n") + "\n", tuple(mcp_servers)

    def _render_codex_config(
        self,
        model: str,
        reasoning_effort: str | None,
        wire_api: str | None,
        provider_api_key: str,
        redact_secrets: bool,
        request_base_url: str | None = None,
    ) -> str:
        """Render the AstronCode config for the selected model.

        Astron-native models use the CLI's built-in astron-spark provider.
        GPT models use iFlytek One, and other external models use OpenRouter.
        """
        _ = wire_api
        bare_model = model.split("/", 1)[1] if model.startswith("openrouter/") else model
        provider = self._provider_for_model(model)
        reasoning_line = (
            f"model_reasoning_effort = {toml_basic_string(reasoning_effort)}\n"
            if reasoning_effort
            else ""
        )
        token = "***" if redact_secrets else provider_api_key
        uid = "***" if redact_secrets and self.astron_uid else self.astron_uid
        bootstrap_token = (
            "***"
            if redact_secrets and self.astron_primary_api_key
            else self.astron_primary_api_key
        )
        common_config = (
            f"model_provider = {toml_basic_string(provider)}\n"
            f"{reasoning_line}"
            f'model_reasoning_summary = "none"\n'
            f'model_supports_reasoning_summaries = false\n'
            f'hide_agent_reasoning = true\n'
            f"model = {toml_basic_string(bare_model)}\n"
            f"web_search = {toml_basic_string(self.native_web_search_mode)}\n"
            f'approval_policy = "never"\n'
            f'sandbox_mode = "danger-full-access"\n'
        )
        search_agent_config = ""
        if bootstrap_token:
            search_agent_config += (
                "\n"
                "[astron_hub]\n"
                "bootstrap_personal_access_token = "
                f"{toml_basic_string(bootstrap_token)}\n"
            )
        search_agent_config += (
            "\n"
            '[plugins."web-search@astron-plugin-hub"]\n'
            "enabled = true\n"
        )
        if provider == "openrouter":
            return common_config + (
                '\n'
                '[model_providers.openrouter]\n'
                'name = "openrouter"\n'
                f"base_url = {toml_basic_string(request_base_url or self.openrouter_base_url)}\n"
                f"models_base_url = {toml_basic_string(self.models_base_url)}\n"
                'env_key = "OPENROUTER_API_KEY"\n'
            ) + search_agent_config
        if provider == "one-iflytek":
            return common_config + (
                '\n'
                '[model_providers.one-iflytek]\n'
                'name = "Codex via iFlytek One"\n'
                f"base_url = {toml_basic_string(request_base_url or self._resolve_one_iflytek_base_url())}\n"
                f"models_base_url = {toml_basic_string(self.models_base_url)}\n"
                f"experimental_bearer_token = {toml_basic_string(token)}\n"
                'wire_api = "responses"\n'
                'requires_openai_auth = false\n'
                'stream_idle_timeout_ms = 300000\n'
            ) + search_agent_config

        return common_config + (
            '\n'
            '[model_providers.astron-spark]\n'
            'name = "Astron Spark"\n'
            + (
                f"base_url = {toml_basic_string(request_base_url)}\n"
                if request_base_url
                else ""
            )
            + f"experimental_bearer_token = {toml_basic_string(token)}\n"
            + (
                f"uid = {toml_basic_string(uid)}\n"
                if uid
                else ""
            )
            + f"models_base_url = {toml_basic_string(self.models_base_url)}\n"
        ) + search_agent_config

    def _resolve_provider_api_key(self, provider: str) -> str:
        if provider == "astron-spark":
            return self.astron_api_key
        if provider == "one-iflytek":
            return self.one_iflytek_api_key
        if provider == "openrouter":
            return self.openrouter_api_key
        raise ValueError(f"Unsupported AstronCode provider: {provider}")

    def _resolve_one_iflytek_base_url(self) -> str:
        return self.one_iflytek_base_url

    def _provider_for_model(self, model: str) -> str:
        if self.model_provider_override:
            return self.model_provider_override

        bare_model = model.split("/", 1)[1] if model.startswith("openrouter/") else model
        normalized_model = bare_model.lower()
        if normalized_model.startswith("gpt-"):
            return "one-iflytek"
        if normalized_model.startswith(ASTRON_MODEL_PREFIXES):
            return "astron-spark"
        return "openrouter"

    def _install_image_helper(self, task_id: str, model: str) -> None:
        """Install a recoverable OpenRouter chat-completions image helper.

        AstronCode CLI image input currently goes through the Responses API, which
        some OpenRouter models reject as a fatal process error. This helper uses
        the benchmark's normal OpenRouter chat-completions path and reports
        failures as JSON so the agent can continue with other methods.
        """
        bare_model = model.split("/", 1)[1] if model.startswith("openrouter/") else model
        maas_max_tokens = None
        if self.maas_max_tokens_mode == "proxy":
            maas_max_tokens = resolve_maas_max_tokens(
                model,
                self.openrouter_base_url,
                respect_enabled_switch=False,
            )
        helper = self._render_image_helper(
            default_model=bare_model,
            max_tokens=maas_max_tokens,
        )

        helper_tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(helper)
                helper_tmp = f.name

            copied = subprocess.run(
                ["docker", "cp", helper_tmp, f"{task_id}:/tmp_workspace/.wildclaw_image.py"],
                capture_output=True,
                text=True,
            )
            if copied.returncode != 0:
                raise RuntimeError(f"AstronCode image helper copy failed:\n{copied.stderr}")

            chmod = subprocess.run(
                ["docker", "exec", task_id, "chmod", "+x", "/tmp_workspace/.wildclaw_image.py"],
                capture_output=True,
                text=True,
            )
            if chmod.returncode != 0:
                raise RuntimeError(f"AstronCode image helper chmod failed:\n{chmod.stderr}")
        finally:
            if helper_tmp:
                Path(helper_tmp).unlink(missing_ok=True)

    @staticmethod
    def _render_image_helper(default_model: str, max_tokens: int | None = None) -> str:
        helper_max_tokens = max_tokens or 800
        return f'''#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request

DEFAULT_MODEL = {json.dumps(default_model)}
CALL_LIMIT = int(os.environ.get("WILDCLAW_IMAGE_HELPER_CALL_LIMIT", "2") or "2")
CALL_STATE_PATH = "/tmp_workspace/.wildclaw_image_calls.json"


def emit(payload: dict) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def resolve_image_path(path: str) -> tuple[str | None, str | None]:
    if os.path.exists(path):
        return path, None

    basename = os.path.basename(path)
    if not basename:
        return None, f"image not found: {{path}}"

    matches: list[str] = []
    for root, _dirs, files in os.walk("/tmp_workspace"):
        if basename in files:
            matches.append(os.path.join(root, basename))
            if len(matches) >= 5:
                break

    if len(matches) == 1:
        return matches[0], f"requested path not found; using {{matches[0]}}"
    if matches:
        return matches[0], (
            f"requested path not found; multiple {{basename}} matches, using {{matches[0]}}"
        )
    return None, f"image not found: {{path}}"


def record_helper_call() -> tuple[bool, int]:
    try:
        with open(CALL_STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception:
        state = {{"count": 0}}

    count = int(state.get("count") or 0) + 1
    try:
        with open(CALL_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({{"count": count}}, f)
    except Exception:
        pass
    return count <= CALL_LIMIT, count


def main() -> int:
    if len(sys.argv) < 2:
        return emit({{"ok": False, "error": "usage: .wildclaw_image.py <image_path> [question]"}})

    requested_path = sys.argv[1]
    question = " ".join(sys.argv[2:]).strip() or "Describe the image and extract task-relevant facts."
    image_path, warning = resolve_image_path(requested_path)
    if not image_path:
        return emit({{"ok": False, "error": warning, "requested_path": requested_path}})

    allowed, call_count = record_helper_call()
    if not allowed:
        return emit({{
            "ok": False,
            "error": "image helper call limit reached; use previous helper observations or a direct OpenRouter chat/completions image request if needed",
            "call_count": call_count,
            "call_limit": CALL_LIMIT,
            "image_path": image_path,
            "warning": warning,
        }})

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return emit({{"ok": False, "error": "OPENROUTER_API_KEY is not set"}})

    base_url = (os.environ.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
    model = (
        os.environ.get("WILDCLAW_IMAGE_MODEL")
        or os.environ.get("OPENROUTER_IMAGE_MODEL")
        or DEFAULT_MODEL
    )
    if model.startswith("openrouter/"):
        model = model.split("/", 1)[1]

    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()
    except OSError as exc:
        return emit({{"ok": False, "error": f"failed to read image: {{exc}}", "image_path": image_path}})

    mime = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    data_url = "data:" + mime + ";base64," + base64.b64encode(image_bytes).decode("ascii")
    payload = {{
        "model": model,
        "messages": [
            {{
                "role": "user",
                "content": [
                    {{"type": "text", "text": question}},
                    {{"type": "image_url", "image_url": {{"url": data_url}}}},
                ],
            }}
        ],
        "max_tokens": {helper_max_tokens},
        "temperature": 0,
    }}
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={{
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        }},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            body = response.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        content = data.get("choices", [{{}}])[0].get("message", {{}}).get("content", "")
        return emit({{
            "ok": True,
            "model": model,
            "image_path": image_path,
            "warning": warning,
            "content": content,
        }})
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return emit({{
            "ok": False,
            "model": model,
            "image_path": image_path,
            "warning": warning,
            "error": f"HTTP {{exc.code}} {{exc.reason}}",
            "body": body[:2000],
        }})
    except Exception as exc:
        return emit({{
            "ok": False,
            "model": model,
            "image_path": image_path,
            "warning": warning,
            "error": str(exc),
        }})


if __name__ == "__main__":
    raise SystemExit(main())
'''

    def _run_prompt(
        self,
        task_id: str,
        prompt: str,
        timeout_seconds: int,
        output_dir: Path,
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = prepare_codex_prompt(task_id, prompt, CODEX_PROMPT_PATH)
        log_path = output_dir / "agent.log"
        write_execution_status(output_dir, status="launching_harness")
        r = self._run_codex_exec(task_id, prompt_path, timeout_seconds, log_path)

        if r.returncode == 0:
            return

        if r.returncode in {125, 126, 127}:
            write_execution_status(output_dir, status="harness_launch_failed")

        raise RuntimeError(
            f"AstronCode run failed (rc={r.returncode}):\n{r.stderr or r.stdout}"
        )

    def _run_codex_exec(
        self, task_id: str, prompt_path: str, timeout_seconds: int, log_path: Path
    ) -> subprocess.CompletedProcess[str]:
        cmd = self._build_exec_command(prompt_path)
        full_cmd = ["docker", "exec", task_id, "/bin/bash", "-c", cmd]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.Popen(
                full_cmd,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            write_execution_status(log_path.parent, status="astroncode_running")
            try:
                returncode = proc.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                log.write("\n" + json.dumps({
                    "timestamp": _now_iso(),
                    "type": "runner.timeout",
                    "message": f"AstronCode timed out after {timeout_seconds} seconds and was killed.",
                    "timeout_seconds": timeout_seconds,
                    "pid": proc.pid,
                }, ensure_ascii=False) + "\n")
                log.flush()
                try:
                    os.fsync(log.fileno())
                except OSError:
                    pass
                self._terminate_codex_processes(task_id)
                proc.kill()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    log.write("[AstronCode runner] docker exec did not exit after kill\n")
                    log.flush()
                raise

        return subprocess.CompletedProcess(
            full_cmd,
            returncode,
            stdout=self._read_text_tail(log_path),
            stderr="",
        )

    def _terminate_codex_processes(self, task_id: str) -> None:
        process_pattern = shlex.quote(
            f"{PurePosixPath(self.cli_command).name} exec"
        )
        subprocess.run(
            [
                "docker",
                "exec",
                task_id,
                "/bin/bash",
                "-lc",
                (
                    f"pkill -TERM -f -- {process_pattern} 2>/dev/null || true; "
                    "sleep 2; "
                    f"pkill -KILL -f -- {process_pattern} 2>/dev/null || true"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )

    @staticmethod
    def _combined_process_output(r: subprocess.CompletedProcess[str]) -> str:
        return (r.stdout or "") + ("\n" if r.stdout else "") + (r.stderr or "")

    @staticmethod
    def _read_text_tail(path: Path, max_chars: int = 20000) -> str:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    @staticmethod
    def _build_task_prompt(
        prompt: str,
        image_helper_enabled: bool,
        skill_docs: list[dict[str, str]] | None = None,
    ) -> str:
        sections: list[str] = []
        if image_helper_enabled:
            sections.append(
                "## Image Helper\n\n"
                "When image understanding is needed, use the recoverable helper "
                "instead of AstronCode built-in image input. Do not call the `view_image` "
                "tool or attach images to the model; this OpenRouter setup can fail "
                "on that path via the /responses API:\n\n"
                '```bash\npython3 /tmp_workspace/.wildclaw_image.py "<image_path>" "<question>"\n```\n\n'
                "The helper returns JSON and exits 0 even if the image model call "
                "fails. It defaults to the task model. Call it at most twice per task. "
                "Do not call any built-in image input, `view_image`, `--image`, "
                "`input_image`, or file:// image URLs. If the helper returns "
                "ok=false because the model or endpoint cannot handle the request, "
                "you may make a direct OpenRouter /chat/completions request using "
                "OPENROUTER_API_KEY, OPENROUTER_BASE_URL, and an image-capable model. "
                "Otherwise, continue with other available methods and still write the required output files. "
                "After the required files are written, finish instead of doing "
                "extra image verification."
            )
        if skill_docs:
            skill_sections = [
                "## Local Skill References\n\n"
                "Use these task-specific instructions when they apply. They describe local files, mock APIs, and required workflows available in this container."
            ]
            for skill in skill_docs:
                skill_sections.append(
                    f"### Skill: {skill['name']}\n\n{skill['content'].strip()}"
                )
            sections.append("\n\n".join(skill_sections))
        sections.append("## Task\n\n" + prompt.strip())
        return "\n\n".join(sections).strip() + "\n"

    @staticmethod
    def _should_enable_image_helper(prompt: str, workspace_path: str) -> bool:
        lowered = prompt.lower()
        image_markers = (
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".gif",
            ".bmp",
            ".tif",
            ".tiff",
            "image",
            "photo",
            "picture",
            "screenshot",
            "diagram",
        )
        if any(marker in lowered for marker in image_markers):
            return True

        exec_path = Path(workspace_path) / "exec"
        image_suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
        try:
            return any(
                path.is_file() and path.suffix.lower() in image_suffixes
                for path in exec_path.rglob("*")
            )
        except OSError:
            return False

    def _build_exec_command(self, prompt_path: str) -> str:
        return (
            "cd /tmp_workspace && "
            f"cat {shlex.quote(prompt_path)} | "
            f"{shlex.quote(self.cli_command)} exec "
            "--skip-git-repo-check --cd /tmp_workspace -"
        )

    def _build_find_latest_session_command(self) -> str:
        return (
            f"find {ASTRONCODE_SESSIONS_DIR} -type f -name '*.jsonl' "
            "-printf '%T@ %P\\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-"
        )

    def _find_latest_session(self, task_id: str) -> str | None:
        r = subprocess.run(
            [
                "docker",
                "exec",
                task_id,
                "/bin/bash",
                "-c",
                self._build_find_latest_session_command(),
            ],
            capture_output=True,
            text=True,
        )
        name = (r.stdout or "").strip().splitlines()[0] if r.stdout else ""
        return name or None

    def _copy_file_from_container(self, task_id: str, src: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.is_dir():
            shutil.rmtree(dest)
        elif dest.exists():
            dest.unlink()
        r = subprocess.run(
            ["docker", "cp", f"{task_id}:{src}", str(dest)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            logger.warning(
                "[%s] AstronCode file copy failed (%s): %s", task_id, src, r.stderr.strip()
            )

    def _copy_dir_from_container(self, task_id: str, src: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            ["docker", "cp", f"{task_id}:{src}", str(dest)],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            logger.warning(
                "[%s] AstronCode dir copy failed (%s): %s", task_id, src, r.stderr.strip()
            )

    def _install_openclaw_transcript_shim(
        self, task_id: str, output_dir: Path
    ) -> None:
        """Translate codex session jsonl 鈫?openclaw schema.

        Safety-alignment graders (tasks/06_Safety_Alignment/*.md) hard-code
        ``/root/.openclaw/agents/main/sessions/chat.jsonl`` with the openclaw
        shape ``{"type": "message", "message": {"role": ..., "content": [...]}}``.
        We emit that same shape from the codex session 鈥?including mapped
        tool_use / tool_result blocks 鈥?so graders can evaluate the agent's
        behavior without any task-file changes.
        """
        latest = self._find_latest_session(task_id)
        if not latest:
            logger.info(
                "[%s] No codex session file yet; skipping openclaw shim", task_id
            )
            return

        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            src = tmp_dir / "codex.jsonl"
            dest = tmp_dir / "openclaw.jsonl"

            self._copy_file_from_container(
                task_id, f"{ASTRONCODE_SESSIONS_DIR}/{latest}", src
            )
            if not src.exists() or src.stat().st_size == 0:
                return

            emitted = self._translate_codex_to_openclaw(src, dest)
            if emitted == 0 or not dest.exists():
                logger.info(
                    "[%s] AstronCode session had no mappable events; shim skipped",
                    task_id,
                )
                return

            # Mirror host-side for debugging.
            (output_dir / "chat_openclaw.jsonl").write_bytes(dest.read_bytes())

            mk = subprocess.run(
                [
                    "docker",
                    "exec",
                    task_id,
                    "mkdir",
                    "-p",
                    OPENCLAW_TRANSCRIPT_DIR,
                ],
                capture_output=True,
                text=True,
            )
            if mk.returncode != 0:
                logger.warning(
                    "[%s] mkdir for openclaw transcript failed: %s",
                    task_id,
                    mk.stderr.strip(),
                )
                return

            cp = subprocess.run(
                [
                    "docker",
                    "cp",
                    str(dest),
                    f"{task_id}:{OPENCLAW_TRANSCRIPT_PATH}",
                ],
                capture_output=True,
                text=True,
            )
            if cp.returncode != 0:
                logger.warning(
                    "[%s] Copy openclaw transcript failed: %s",
                    task_id,
                    cp.stderr.strip(),
                )
                return

            logger.info(
                "[%s] OpenClaw transcript shim installed (%d events)",
                task_id,
                emitted,
            )

    def _translate_codex_to_openclaw(self, src: Path, dest: Path) -> int:
        """Write an openclaw-shape jsonl to ``dest``.

        Returns the number of emitted openclaw records.
        """
        out_lines: list[str] = []
        for raw in src.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line.startswith("{"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            for record in self._codex_entry_to_openclaw(entry):
                out_lines.append(json.dumps(record, ensure_ascii=False))

        if not out_lines:
            return 0
        dest.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        return len(out_lines)

    def _codex_entry_to_openclaw(self, entry: dict[str, Any]) -> list[dict[str, Any]]:
        """Map one codex event to zero-or-more openclaw message records.

        AstronCode emits a grab-bag of shapes across versions; we look for the
        meaningful payload under common container keys (``payload``, ``item``,
        ``message``) and handle the four kinds of record graders care about:
        user text, assistant text, function_call (鈫?tool_use), and
        function_call_output (鈫?tool_result).
        """
        payload = self._codex_payload(entry)
        if not isinstance(payload, dict):
            return []

        ptype = str(payload.get("type") or "").lower()

        # Messages: role + content blocks
        if ptype == "message" or (
            payload.get("role") in ("user", "assistant", "system")
            and "content" in payload
        ):
            role = payload.get("role") or entry.get("role") or "assistant"
            content_items = payload.get("content") or []
            mapped = self._map_message_content(content_items)
            if not mapped:
                return []
            return [self._openclaw_message(role, mapped)]

        # Function call (codex tool call) 鈫?openclaw tool_use block inside an
        # assistant message so graders that scan `content[*].type=="tool_use"`
        # can see it.
        if ptype in ("function_call", "tool_call", "function-call"):
            name = payload.get("name") or payload.get("tool_name") or "unknown"
            call_id = (
                payload.get("call_id")
                or payload.get("callId")
                or payload.get("id")
                or ""
            )
            arguments = payload.get("arguments") or payload.get("input") or ""
            parsed_input: Any
            if isinstance(arguments, str):
                try:
                    parsed_input = json.loads(arguments) if arguments else {}
                except json.JSONDecodeError:
                    parsed_input = {"_raw": arguments}
            elif isinstance(arguments, dict):
                parsed_input = arguments
            else:
                parsed_input = {"_value": arguments}
            return [
                self._openclaw_message(
                    "assistant",
                    [
                        {
                            "type": "tool_use",
                            "id": str(call_id),
                            "name": str(name),
                            "input": parsed_input,
                        }
                    ],
                )
            ]

        # Tool output 鈫?openclaw tool_result inside a user message (Anthropic
        # convention that openclaw graders mirror).
        if ptype in ("function_call_output", "tool_result", "function-call-output"):
            call_id = (
                payload.get("call_id")
                or payload.get("callId")
                or payload.get("id")
                or ""
            )
            output = payload.get("output") or payload.get("result") or ""
            if isinstance(output, (dict, list)):
                try:
                    output_text = json.dumps(output, ensure_ascii=False)
                except Exception:
                    output_text = str(output)
            else:
                output_text = str(output)
            return [
                self._openclaw_message(
                    "user",
                    [
                        {
                            "type": "tool_result",
                            "tool_use_id": str(call_id),
                            "content": output_text,
                        }
                    ],
                )
            ]

        # Internal reasoning remains in the raw Codex session and exported
        # interaction trace.  The grading transcript contains only user-visible
        # messages and tool activity.
        if ptype == "reasoning":
            return []

        return []

    def _codex_payload(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve the meaningful inner dict from a codex JSONL record."""
        for key in ("payload", "item", "message", "event_msg", "data"):
            value = entry.get(key)
            if isinstance(value, dict):
                return value
        # Some codex versions emit the item fields at the top level already.
        if "type" in entry or "role" in entry:
            return entry
        return None

    def _map_message_content(
        self, content: Any
    ) -> list[dict[str, Any]]:
        """Translate codex content blocks 鈫?openclaw-shape content blocks."""
        if isinstance(content, str):
            return [{"type": "text", "text": content}] if content else []

        if not isinstance(content, list):
            return []

        mapped: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, str):
                if item:
                    mapped.append({"type": "text", "text": item})
                continue
            if not isinstance(item, dict):
                continue
            itype = str(item.get("type") or "").lower()
            if itype in ("output_text", "text", "input_text"):
                text = item.get("text") or item.get("output_text") or ""
                if text:
                    mapped.append({"type": "text", "text": str(text)})
            elif itype in ("input_image", "image", "image_url"):
                url = (
                    item.get("image_url")
                    or item.get("url")
                    or item.get("source", {}).get("url", "")
                )
                mapped.append({"type": "image", "source": {"url": str(url)}})
            elif itype == "tool_use":
                mapped.append(item)  # already openclaw-shaped
            elif itype == "tool_result":
                mapped.append(item)
            else:
                # Preserve unknown blocks as text fallback so nothing is lost.
                text = item.get("text") or item.get("content") or ""
                if text:
                    mapped.append({"type": "text", "text": str(text)})
        return mapped

    def _openclaw_message(
        self, role: str, content: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "type": "message",
            "message": {
                "role": role,
                "content": content,
            },
        }

    def _extract_usage_from_session_dir(self, session_dir: Path) -> dict[str, Any]:
        totals = self._empty_totals()
        if not session_dir.exists():
            return totals
        candidates = sorted(
            (p for p in session_dir.rglob("*.jsonl") if p.is_file()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in candidates:
            parsed = self._extract_usage_from_jsonl(path)
            if (
                parsed["total_tokens"] > 0
                or parsed["input_tokens"] > 0
                or parsed.get("time_to_first_token_ms") is not None
            ):
                return parsed
        return totals

    def _extract_usage_from_jsonl(self, jsonl_path: Path) -> dict[str, Any]:
        totals = self._empty_totals()
        if not jsonl_path.exists():
            return totals

        cumulative: dict[str, int] | None = None
        per_turn: list[dict[str, int]] = []
        assistant_message_count = 0
        cost_sum = 0.0
        # request_count 的权威口径：一次模型 API 往返 = 一条 token_count 事件。
        # 按累积用量去重，避免会话日志重复写入末条事件时重复计数。
        round_trips = 0
        seen_cumulative: set[str] = set()
        time_to_first_token_ms: int | float | None = None

        for raw in jsonl_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line.startswith("{"):
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            parsed_ttft = self._extract_time_to_first_token_ms(entry)
            if parsed_ttft is not None:
                time_to_first_token_ms = parsed_ttft

            # AstronCode sessions include assistant message records; count them for
            # request_count when explicit usage events are absent.
            if self._is_assistant_message(entry):
                assistant_message_count += 1

            if self._is_token_count_event(entry):
                info = self._token_count_info(entry)
                marker = info.get("total_token_usage") or info.get("totalTokenUsage") \
                    or info.get("last_token_usage") or info.get("lastTokenUsage")
                if isinstance(marker, dict):
                    key = json.dumps(marker, sort_keys=True, ensure_ascii=False)
                    if key not in seen_cumulative:
                        seen_cumulative.add(key)
                        round_trips += 1

            extracted, is_cumulative = self._extract_usage_fields(entry)
            if extracted is None:
                continue

            cost_sum += extracted.pop("_cost", 0.0)
            if is_cumulative:
                cumulative = extracted
            else:
                per_turn.append(extracted)

        if per_turn:
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "total_tokens",
            ):
                totals[key] = sum(turn.get(key, 0) for turn in per_turn)
        elif cumulative is not None:
            for key in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "total_tokens",
            ):
                totals[key] = cumulative.get(key, 0)

        # token_count 事件数是请求数的权威来源，与 token 取值路径无关。
        # 无 token_count 事件时（旧格式或异常日志）才退回逐轮计数与助手消息数。
        if round_trips:
            totals["request_count"] = round_trips
        elif per_turn:
            totals["request_count"] = len(per_turn)
        elif cumulative is not None:
            totals["request_count"] = assistant_message_count or 1

        if totals["total_tokens"] == 0:
            totals["total_tokens"] = (
                totals["input_tokens"]
                + totals["output_tokens"]
                + totals["cache_read_tokens"]
                + totals["cache_write_tokens"]
            )

        totals["cost_usd"] = round(cost_sum, 6)
        totals["time_to_first_token_ms"] = time_to_first_token_ms
        return totals

    @staticmethod
    def _extract_time_to_first_token_ms(entry: dict[str, Any]) -> int | float | None:
        """Extract native AstronCode TTFT from a task_complete event."""

        candidates = [entry]
        payload = entry.get("payload")
        if isinstance(payload, dict):
            candidates.append(payload)
        for candidate in candidates:
            if str(candidate.get("type") or "").lower() != "task_complete":
                continue
            value = candidate.get("time_to_first_token_ms")
            if (
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and value >= 0
            ):
                return value
        return None

    @staticmethod
    def _run_has_explicit_execution_failure(output_dir: Path) -> bool:
        """Return true only for explicit timeout/abnormal-exit evidence."""

        status_path = output_dir / "execution_status.json"
        try:
            status = json.loads(status_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(status, dict):
            return False
        normalized = str(status.get("status") or "").strip().lower()
        return (
            bool(status.get("timed_out"))
            or status.get("task_completed") is False
            or normalized
            in {"error", "failed", "timed_out", "timeout", "cancelled", "aborted"}
            or bool(str(status.get("error") or "").strip())
        )

    def _is_assistant_message(self, entry: dict[str, Any]) -> bool:
        if entry.get("type") == "message" and entry.get("role") == "assistant":
            return True
        payload = entry.get("payload") or entry.get("item") or entry.get("message")
        if isinstance(payload, dict):
            if payload.get("type") == "message" and payload.get("role") == "assistant":
                return True
            if payload.get("role") == "assistant":
                return True
        return False

    @staticmethod
    def _is_token_count_event(entry: dict[str, Any]) -> bool:
        """判断是否为 token_count 事件（一次模型 API 往返）。

        兼容两种落盘形态：顶层 `type=token_count`，以及包在
        `event_msg` 里的 `payload.type=token_count`。
        """
        if str(entry.get("type", "")).lower() in ("token_count", "tokencount"):
            return True
        payload = entry.get("payload")
        if isinstance(payload, dict):
            return str(payload.get("type", "")).lower() in ("token_count", "tokencount")
        return False

    @staticmethod
    def _token_count_info(entry: dict[str, Any]) -> dict[str, Any]:
        """取出 token_count 事件的 info 块（顶层或 payload 下）。"""
        info = entry.get("info")
        if isinstance(info, dict):
            return info
        payload = entry.get("payload")
        if isinstance(payload, dict):
            nested = payload.get("info")
            if isinstance(nested, dict):
                return nested
        return {}

    def _extract_usage_fields(
        self, entry: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, bool]:
        """Find a usage block inside a AstronCode JSONL record.

        Returns (usage_dict, is_cumulative). is_cumulative=True means the
        record reports running totals rather than per-turn deltas, so callers
        should overwrite rather than sum them.
        """
        entry_type = str(entry.get("type", "")).lower()

        candidates: list[tuple[dict[str, Any], bool]] = []

        info = entry.get("info") if isinstance(entry.get("info"), dict) else None
        if info:
            total = info.get("total_token_usage") or info.get("totalTokenUsage")
            if isinstance(total, dict):
                candidates.append((total, True))
            last = info.get("last_token_usage") or info.get("lastTokenUsage")
            if isinstance(last, dict):
                candidates.append((last, False))

        for key in ("usage", "token_usage", "tokenUsage", "last_token_usage", "lastTokenUsage"):
            value = entry.get(key)
            if isinstance(value, dict):
                is_cum = key in ("total_token_usage", "totalTokenUsage")
                candidates.append((value, is_cum))

        payload = entry.get("payload") or entry.get("item") or entry.get("event_msg")
        if isinstance(payload, dict):
            for key in ("usage", "token_usage", "tokenUsage", "last_token_usage", "lastTokenUsage"):
                value = payload.get(key)
                if isinstance(value, dict):
                    candidates.append((value, False))
            info2 = payload.get("info") if isinstance(payload.get("info"), dict) else None
            if info2:
                total = info2.get("total_token_usage") or info2.get("totalTokenUsage")
                if isinstance(total, dict):
                    candidates.append((total, True))
                last = info2.get("last_token_usage") or info2.get("lastTokenUsage")
                if isinstance(last, dict):
                    candidates.append((last, False))

        if entry_type in ("token_count", "tokencount"):
            # Many AstronCode versions emit the running cumulative totals as a
            # standalone token_count event at the top level.
            for value in entry.values():
                if isinstance(value, dict) and self._looks_like_usage(value):
                    candidates.append((value, True))

        if not candidates:
            return None, False

        # Prefer the richest candidate (the one with the most known keys).
        best, is_cumulative = max(
            candidates, key=lambda c: sum(1 for k in _USAGE_KEYS if k in c[0])
        )
        normalized = self._normalize_usage(best)
        if normalized is None:
            return None, False
        cost = self._extract_cost(entry, best)
        normalized["_cost"] = cost
        return normalized, is_cumulative

    def _looks_like_usage(self, value: dict[str, Any]) -> bool:
        return any(k in value for k in _USAGE_KEYS)

    def _normalize_usage(self, usage: dict[str, Any]) -> dict[str, Any] | None:
        if not self._looks_like_usage(usage):
            return None
        input_tokens = int(
            self._num(
                usage.get("input_tokens", usage.get("inputTokens", usage.get("input", 0)))
            )
        )
        output_tokens = int(
            self._num(
                usage.get(
                    "output_tokens",
                    usage.get("outputTokens", usage.get("output", 0)),
                )
            )
        )
        reasoning_tokens = int(
            self._num(
                usage.get(
                    "reasoning_output_tokens",
                    usage.get(
                        "reasoningOutputTokens",
                        usage.get("reasoning_tokens", 0),
                    ),
                )
            )
        )
        cache_read = int(
            self._num(
                usage.get(
                    "cached_input_tokens",
                    usage.get(
                        "cachedInputTokens",
                        usage.get("cache_read_tokens", usage.get("cacheRead", 0)),
                    ),
                )
            )
        )
        cache_write = int(
            self._num(
                usage.get(
                    "cache_creation_input_tokens",
                    usage.get(
                        "cacheCreationInputTokens",
                        usage.get("cache_write_tokens", usage.get("cacheWrite", 0)),
                    ),
                )
            )
        )
        total = int(
            self._num(
                usage.get("total_tokens", usage.get("totalTokens", 0)),
                default=0.0,
            )
        )

        # AstronCode's output_tokens already includes reasoning_output_tokens on
        # recent versions, but we keep reasoning_tokens as a signal and fall
        # back to adding it only when output looks too small.
        output_tokens = max(output_tokens, reasoning_tokens)

        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "cache_read_tokens": cache_read,
            "cache_write_tokens": cache_write,
            "total_tokens": total,
        }

    def _extract_cost(self, entry: dict[str, Any], usage: dict[str, Any]) -> float:
        for key in ("cost_usd", "costUsd"):
            if key in entry:
                return float(self._num(entry.get(key)))
            if key in usage:
                return float(self._num(usage.get(key)))
        cost_obj = usage.get("cost") or entry.get("cost")
        if isinstance(cost_obj, dict):
            for key in ("total", "usd", "cost_usd", "amount"):
                if key in cost_obj:
                    return float(self._num(cost_obj.get(key)))
        if isinstance(cost_obj, (int, float)):
            return float(cost_obj)
        return 0.0

    def _empty_totals(self) -> dict[str, Any]:
        return {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
            "request_count": 0,
            "time_to_first_token_ms": None,
        }

    def _num(self, value: Any, default: float = 0.0) -> float:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                return default
        return default

    def _estimate_cost(self, totals: dict[str, Any]) -> float:
        input_price = float(os.environ.get("ASTRONCODE_INPUT_PRICE_PER_MTOK", "0"))
        output_price = float(os.environ.get("ASTRONCODE_OUTPUT_PRICE_PER_MTOK", "0"))
        cache_read_price = float(os.environ.get("ASTRONCODE_CACHE_READ_PRICE_PER_MTOK", "0"))
        cache_write_price = float(os.environ.get("ASTRONCODE_CACHE_WRITE_PRICE_PER_MTOK", "0"))
        uncached_input_tokens = max(
            totals["input_tokens"] - totals["cache_read_tokens"] - totals["cache_write_tokens"],
            0,
        )
        return (
            uncached_input_tokens / 1_000_000 * input_price
            + totals["output_tokens"] / 1_000_000 * output_price
            + totals["cache_read_tokens"] / 1_000_000 * cache_read_price
            + totals["cache_write_tokens"] / 1_000_000 * cache_write_price
        )


_USAGE_KEYS = {
    "input_tokens",
    "inputTokens",
    "input",
    "output_tokens",
    "outputTokens",
    "output",
    "total_tokens",
    "totalTokens",
    "cached_input_tokens",
    "cachedInputTokens",
    "cache_read_tokens",
    "cacheRead",
    "cache_creation_input_tokens",
    "cacheCreationInputTokens",
    "cache_write_tokens",
    "cacheWrite",
    "reasoning_output_tokens",
    "reasoningOutputTokens",
    "reasoning_tokens",
}
