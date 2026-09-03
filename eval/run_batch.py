from __future__ import annotations

import logging
import math
import os
import re
import subprocess
import sys
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit, urlunsplit
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.agents.base import AgentTaskSpec, BaseAgent
from src.agents.astroncode import AstronCodeAgent
from src.agents.astronclaw import AstronClawAgent
from src.agents.claudecode import ClaudeCodeAgent
from src.agents.codex import CodexAgent
from src.agents.deepseek_harness import DeepSeekHarnessAgent
from src.agents.hermesagent import HermesAgentAgent
from src.agents.opencode import OpenCodeAgent
from src.agents.openclaw import OpenClawAgent
from src.utils.cli_args import parse_run_batch_args
from src.utils.endpoint_utils import (
    normalize_openrouter_base_url_for_claudecode,
    normalize_openrouter_base_url_for_openclaw,
)
from src.utils.task_parser import parse_task_md
from src.utils.docker_utils import (
    remove_container,
    close_proc_log,
    collect_output_from_container,
    TMP_WORKSPACE,
)
from src.utils.grading import (
    DEFAULT_GRADING_TIMEOUT_SECONDS,
    DEFAULT_JUDGE_TIMEOUT_SECONDS,
    run_grading,
    format_scores,
    print_summary,
    print_global_summary,
    write_error_score as write_error_score_file,
)

from src.utils.anomalies import RULESET_VERSION, SCHEMA_VERSION, scan_run_dir
from src.utils.eval_provenance import (
    TASK_PROVENANCE_CACHE_KEY,
    get_or_build_task_provenance,
    write_provenance_file,
)
from src.utils.log_format import configure_console_logging, attach_file_logging
from src.utils.run_selection import write_rerun_metadata

load_dotenv()
# 终端：颜色 + emoji（stdout）。文件日志在 main() 里按 output_root 追加（纯文本 + emoji）。
configure_console_logging(level=logging.INFO)
logger = logging.getLogger(__name__)

PASS_THRESHOLD = 0.99  # 全局 pass 阈值，main() 里从 --pass-threshold 覆盖

GATEWAY_PORT     = int(os.environ.get("GATEWAY_PORT", "18789"))

ROOT_DIR         = Path(__file__).resolve().parent.parent
TASKS_DIR        = ROOT_DIR / os.environ.get("TASKS_SUBDIR",  "tasks")
OUTPUT_DIR       = ROOT_DIR / os.environ.get("OUTPUT_SUBDIR", "output")

DEFAULT_MODEL    = os.environ.get("DEFAULT_MODEL",    "openrouter/anthropic/claude-sonnet-4.6")
DEFAULT_PARALLEL = int(os.environ.get("DEFAULT_PARALLEL", "1"))

# 任务超时放大倍数；main() 里解析（CLI --timeout-multiplier 优先，
# env WILDCLAW_TIMEOUT_MULTIPLIER 兜底，默认 1.0），线程启动前设定
TIMEOUT_MULTIPLIER = 1.0
# 统一超时覆盖（秒）：设置后所有任务忽略各自 timeout_seconds，直接用该值，
# 优先级高于 TIMEOUT_MULTIPLIER；CLI --timeout-override 优先，
# env WILDCLAW_TIMEOUT_OVERRIDE 兜底，默认 None（不覆盖）
TIMEOUT_OVERRIDE: int | None = None

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL_OPENCLAW = normalize_openrouter_base_url_for_openclaw(
    os.environ.get("OPENROUTER_BASE_URL", "")
)
OPENROUTER_BASE_URL_CLAUDECODE = normalize_openrouter_base_url_for_claudecode(
    os.environ.get("OPENROUTER_BASE_URL", "")
)
MODELS_API_KEY_PLACEHOLDER = "${MY_PROXY_API_KEY}"

ALL_CATEGORIES = [
    "01_Productivity_Flow",
    "02_Code_Intelligence",
    "03_Social_Interaction",
    "04_Search_Retrieval",
    "05_Creative_Synthesis",
    "06_Safety_Alignment",
    "07_Website_Generation",
]

GRADE_ON_ERROR_BACKENDS = (
    CodexAgent,
    ClaudeCodeAgent,
    AstronCodeAgent,
    OpenCodeAgent,
    OpenClawAgent,
    DeepSeekHarnessAgent,
    HermesAgentAgent,
)

WORKSPACE_CHANGE_BACKENDS = (
    CodexAgent,
    ClaudeCodeAgent,
    AstronCodeAgent,
    OpenCodeAgent,
    DeepSeekHarnessAgent,
)

_RUN_CONFIG_CREDENTIAL_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "ANTHROPIC_API_KEY",
    "ASTRON_API_KEY",
    "ASTRON_SPARK_API_KEY",
    "ONE_IFLYTEK_API_KEY",
    "DEEPSEEK_API_KEY",
    "BRAVE_API_KEY",
    "MY_PROXY_API_KEY",
)

_RUN_CONFIG_ENDPOINT_ENV_NAMES = (
    "OPENROUTER_BASE_URL",
    "ANTHROPIC_BASE_URL",
    "DEEPSEEK_SEARCH_BASE_URL",
    "SEARXNG_BASE_URL",
)


def _sanitize_endpoint_for_log(value: object) -> str | None:
    """Return a useful endpoint without persisting URL credentials or tokens."""
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        if not parsed.scheme or not parsed.hostname:
            return "[configured; invalid or relative URL redacted]"
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = hostname
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        sanitized = urlunsplit((parsed.scheme, netloc, parsed.path, "", ""))
        if parsed.query:
            sanitized += "?[REDACTED]"
        if parsed.fragment:
            sanitized += "#[REDACTED]"
        return sanitized
    except (TypeError, ValueError):
        return "[configured; malformed URL redacted]"


def _current_working_directory_for_log() -> str | None:
    try:
        return str(Path.cwd())
    except OSError:
        return None


def _effective_positive_float(
    environ: Mapping[str, str], env_name: str, default: float
) -> float:
    raw = str(environ.get(env_name, "")).strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _build_run_configuration(
    args: Any,
    backend: BaseAgent,
    output_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Build the non-secret effective run configuration written to ``run.log``."""
    env = os.environ if environ is None else environ
    endpoint_env = {
        name: _sanitize_endpoint_for_log(env.get(name, ""))
        for name in _RUN_CONFIG_ENDPOINT_ENV_NAMES
    }
    backend_endpoints = {
        name: _sanitize_endpoint_for_log(getattr(backend, name, None))
        for name in (
            "openrouter_base_url",
            "api_base_url",
            "one_iflytek_base_url",
            "models_base_url",
        )
        if getattr(backend, name, None)
    }
    credential_names = set(_RUN_CONFIG_CREDENTIAL_ENV_NAMES)
    for raw_names in (getattr(args, "lobster_env", None),):
        credential_names.update(
            name.strip()
            for name in str(raw_names or "").split(",")
            if name.strip()
        )

    mode = "task" if getattr(args, "task", None) else "category"
    selection_value = getattr(args, "task", None) or getattr(args, "category", None)
    return {
        "schema_version": 1,
        "invocation": {
            "id": uuid.uuid4().hex,
            "started_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "cwd": _current_working_directory_for_log(),
            "pid": os.getpid(),
        },
        "selection": {
            "mode": mode,
            "value": selection_value,
            "modality": getattr(args, "modality", None),
            "include_tags": sorted(getattr(args, "tags", None) or []),
            "exclude_tags": sorted(getattr(args, "exclude_tags", None) or []),
        },
        "execution": {
            "agent_backend": getattr(args, "agent_backend", None),
            "backend_class": type(backend).__name__,
            "model": getattr(args, "model", None),
            "thinking": getattr(args, "thinking", None),
            "parallel": getattr(args, "parallel", None),
            "runs": getattr(args, "runs", None),
            "resume": bool(getattr(args, "resume", False)),
            "rerun_error": bool(getattr(args, "rerun_error", False)),
            "rerun_anomalous": bool(getattr(args, "rerun_anomalous", False)),
            "pass_threshold": getattr(args, "pass_threshold", None),
            "requested_api": getattr(args, "dsh_api", None),
            "api": getattr(backend, "api", None),
            "image": getattr(backend, "image", None),
            "image_model": getattr(args, "openclaw_image_model", None),
            "lobster_name": getattr(args, "lobster_name", None),
        },
        "timeout": {
            "override_seconds": TIMEOUT_OVERRIDE,
            "multiplier": TIMEOUT_MULTIPLIER,
            "grading_seconds": _effective_positive_float(
                env,
                "WILDCLAW_GRADING_TIMEOUT_SECONDS",
                DEFAULT_GRADING_TIMEOUT_SECONDS,
            ),
            "judge_seconds": _effective_positive_float(
                env,
                "WILDCLAW_JUDGE_TIMEOUT_SECONDS",
                DEFAULT_JUDGE_TIMEOUT_SECONDS,
            ),
        },
        "resources": {
            "memory": str(env.get("WILDCLAW_DOCKER_MEMORY", "")).strip() or None,
            "cpus": str(env.get("WILDCLAW_DOCKER_CPUS", "")).strip() or None,
        },
        "paths": {
            "tasks_root": str(TASKS_DIR),
            "output_root": str(output_root),
            "models_config": getattr(args, "models_config", None),
            "lobster_workspace": getattr(args, "lobster_workspace", None),
        },
        "backend_endpoints": backend_endpoints,
        "environment_endpoints": endpoint_env,
        "judge": {
            "model": str(env.get("JUDGE_MODEL", "")).strip() or "openai/gpt-5.4",
            "anthropic_base_url": endpoint_env["ANTHROPIC_BASE_URL"],
        },
        "model_limits": {
            "maas_max_tokens": str(env.get("MAAS_MAX_TOKENS", "")).strip() or None,
            "astroncode_maas_max_tokens_mode": str(
                env.get("ASTRONCODE_MAAS_MAX_TOKENS_MODE", "")
            ).strip() or None,
        },
        "astroncode": {
            "native_web_search_enabled": getattr(
                backend, "native_web_search_enabled", None
            ),
        },
        "credentials": {
            name: "configured" if str(env.get(name, "")).strip() else "unset"
            for name in sorted(credential_names)
        },
    }


def _log_run_configuration(
    args: Any,
    backend: BaseAgent,
    output_root: Path,
) -> dict[str, Any]:
    config = _build_run_configuration(args, backend, output_root)
    logger.info(
        "Run configuration:\n%s",
        json.dumps(config, ensure_ascii=False, indent=2),
    )
    return config


def _build_agent_backend(args) -> BaseAgent:
    if args.agent_backend == "claudecode":
        return ClaudeCodeAgent(
            anthropic_api_key=OPENROUTER_API_KEY,
            openrouter_base_url=OPENROUTER_BASE_URL_CLAUDECODE,
        )
    if args.agent_backend == "codex":
        return CodexAgent()
    if args.agent_backend == "astroncode":
        return AstronCodeAgent()
    if args.agent_backend == "astronclaw":
        return AstronClawAgent(
            gateway_port=GATEWAY_PORT,
            openrouter_api_key=OPENROUTER_API_KEY,
            openrouter_base_url=OPENROUTER_BASE_URL_OPENCLAW,
            image_model=args.openclaw_image_model,
        )
    if args.agent_backend == "opencode":
        return OpenCodeAgent()
    if args.agent_backend == "deepseek-harness":
        return DeepSeekHarnessAgent(api=args.dsh_api)
    if args.agent_backend == "hermesagent":
        return HermesAgentAgent(
            openrouter_api_key=OPENROUTER_API_KEY,
            openrouter_base_url=OPENROUTER_BASE_URL_OPENCLAW,
        )
    return OpenClawAgent(
        gateway_port=GATEWAY_PORT,
        openrouter_api_key=OPENROUTER_API_KEY,
        openrouter_base_url=OPENROUTER_BASE_URL_OPENCLAW,
        image_model=args.openclaw_image_model,
    )


def _is_extension_task(task: dict) -> bool:
    """Return whether a parsed task comes from tasks/extension/."""
    try:
        relative_path = Path(task["file_path"]).resolve().relative_to(
            TASKS_DIR.resolve()
        )
    except (KeyError, TypeError, ValueError):
        return False
    return bool(relative_path.parts) and relative_path.parts[0] == "extension"


def _pending_task_counts(tasks: list[dict]) -> tuple[int, int]:
    """Return (official, extension) counts for tasks that will be executed."""
    extension_count = sum(1 for task in tasks if _is_extension_task(task))
    return len(tasks) - extension_count, extension_count


def _log_pending_task_counts(tasks: list[dict]) -> None:
    official_count, extension_count = _pending_task_counts(tasks)
    logger.info(
        "待执行用例数: %d（开源评测集: %d，自建评测集 tasks/extension: %d）",
        len(tasks),
        official_count,
        extension_count,
    )


def _task_provenance_or_unavailable(task: dict) -> dict[str, Any]:
    try:
        return get_or_build_task_provenance(task)
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        logger.warning(
            "[%s] 无法计算评测契约 hash，评测继续执行: %s",
            task.get("task_id", "unknown"),
            exc,
        )
        unavailable = {
            "schema_version": 1,
            "provenance_status": "unavailable",
            "hash_algorithm": "sha256",
            "task_id": str(task.get("task_id") or ""),
            "task_sha256": None,
            "execution_contract_sha256": None,
            "scoring_contract_sha256": None,
        }
        task[TASK_PROVENANCE_CACHE_KEY] = unavailable
        return unavailable


def _task_scope_entry(task: dict) -> dict[str, Any]:
    path = Path(str(task.get("file_path") or ""))
    source = "official"
    category = str(task.get("category") or "").strip()
    try:
        relative = path.resolve().relative_to(TASKS_DIR.resolve())
        if relative.parts and relative.parts[0] == "extension":
            source = "extension"
            if len(relative.parts) > 1:
                category = relative.parts[1]
        elif relative.parts:
            category = relative.parts[0]
    except ValueError:
        pass
    return {
        "category": category,
        "task_id": str(task.get("task_id") or path.stem),
        "source": source,
        "provenance": _task_provenance_or_unavailable(task),
    }


def _scope_task_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(item.get("category") or "").strip(),
        str(item.get("task_id") or "").strip(),
    )


def _validate_scope_entries(payload: Mapping[str, Any], *, source: Path) -> list[dict]:
    schema_version = payload.get("schema_version")
    if schema_version not in {1, 2}:
        raise ValueError(
            f"{source} schema_version={schema_version!r} 不受支持（仅支持 1 或 2）"
        )
    planned = payload.get("planned_tasks")
    if not isinstance(planned, list):
        raise ValueError(f"{source} planned_tasks 必须是列表")
    declared_count = payload.get("planned_task_count")
    if not isinstance(declared_count, int) or isinstance(declared_count, bool):
        raise ValueError(f"{source} planned_task_count 必须是整数")
    if declared_count != len(planned):
        raise ValueError(
            f"{source} planned_task_count={declared_count} 与列表长度 {len(planned)} 不一致"
        )

    normalized: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(planned):
        if not isinstance(item, dict):
            raise ValueError(f"{source} planned_tasks[{index}] 必须是对象")
        key = _scope_task_key(item)
        if not all(key):
            raise ValueError(
                f"{source} planned_tasks[{index}] 的 category/task_id 不能为空"
            )
        if key in seen:
            raise ValueError(
                f"{source} planned_tasks 存在重复任务 {key[0]}/{key[1]}"
            )
        seen.add(key)
        normalized.append(item)
    return normalized


def _write_json_atomically(
    path: Path,
    payload: Mapping[str, Any],
    *,
    if_changed: bool = False,
) -> None:
    serialized = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if if_changed and path.is_file():
        try:
            if path.read_text(encoding="utf-8") == serialized:
                return
        except (OSError, UnicodeError):
            pass
    temporary_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        temporary_path.write_text(serialized, encoding="utf-8")
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _write_evaluation_scope(
    output_root: Path,
    tasks: list[dict],
    *,
    mode: str,
    categories: list[str],
    modality: str | None,
    include_tags: set[str],
    exclude_tags: set[str],
    runs: int,
    pending_tasks: list[dict] | None = None,
    invocation_id: str | None = None,
    recorded_at: str | None = None,
) -> Path:
    requested_tasks = sorted(
        (_task_scope_entry(task) for task in tasks),
        key=lambda item: (item["category"], item["task_id"]),
    )
    requested_payload = {
        "schema_version": 2,
        "planned_task_count": len(requested_tasks),
        "planned_tasks": requested_tasks,
    }
    _validate_scope_entries(requested_payload, source=Path("current invocation"))

    pending_entries = sorted(
        (
            _task_scope_entry(task)
            for task in (tasks if pending_tasks is None else pending_tasks)
        ),
        key=lambda item: (item["category"], item["task_id"]),
    )
    _validate_scope_entries(
        {
            "schema_version": 2,
            "planned_task_count": len(pending_entries),
            "planned_tasks": pending_entries,
        },
        source=Path("current pending tasks"),
    )
    pending_keys = {_scope_task_key(item) for item in pending_entries}
    requested_keys = {_scope_task_key(item) for item in requested_tasks}
    if not pending_keys <= requested_keys:
        raise ValueError("pending_tasks 必须是本次 planned_tasks 的子集")
    resumed_entries = [
        item for item in requested_tasks if _scope_task_key(item) not in pending_keys
    ]

    output_root.mkdir(parents=True, exist_ok=True)
    path = output_root / "evaluation_scope.json"
    accumulated: dict[tuple[str, str], dict] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"已有 {path} 无法解析，拒绝覆盖: {exc}") from exc
        if not isinstance(existing, dict):
            raise ValueError(f"已有 {path} 顶层必须是 JSON object，拒绝覆盖")
        for item in _validate_scope_entries(existing, source=path):
            accumulated[_scope_task_key(item)] = item
    for item in requested_tasks:
        # 相同任务采用本次任务定义的最新 provenance；历史 invocation 保留旧快照。
        accumulated[_scope_task_key(item)] = item
    accumulated_tasks = [accumulated[key] for key in sorted(accumulated)]
    payload = {
        "schema_version": 2,
        "scope_semantics": "accumulated",
        "planned_task_count": len(accumulated_tasks),
        "planned_tasks": accumulated_tasks,
    }
    _validate_scope_entries(payload, source=path)

    recorded_now = datetime.now().astimezone()
    invocation_id = invocation_id or uuid.uuid4().hex
    recorded_at = recorded_at or recorded_now.isoformat(timespec="seconds")
    invocation_payload = {
        "schema_version": 1,
        "scope_semantics": "invocation",
        "invocation_id": invocation_id,
        "recorded_at": recorded_at,
        "mode": mode,
        "categories": sorted(set(categories)),
        "modality": modality or "",
        "include_tags": sorted(include_tags),
        "exclude_tags": sorted(exclude_tags),
        "runs": runs,
        "planned_task_count": len(requested_tasks),
        "planned_tasks": requested_tasks,
        "pending_task_count": len(pending_entries),
        "pending_tasks": pending_entries,
        "resumed_task_count": len(resumed_entries),
        "resumed_tasks": resumed_entries,
        "scheduled_run_count": len(pending_entries) * runs,
    }
    history_dir = output_root / "evaluation_scope_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    history_timestamp = recorded_now.strftime("%Y%m%dT%H%M%S%f%z")
    history_path = history_dir / f"{history_timestamp}_{invocation_id}.json"
    _write_json_atomically(path, payload, if_changed=True)
    _write_json_atomically(history_path, invocation_payload)
    logger.info(
        "Evaluation scope written: %s (%d accumulated tasks; invocation: %d planned, %d pending, %d resumed)",
        path,
        len(accumulated_tasks),
        len(requested_tasks),
        len(pending_entries),
        len(resumed_entries),
    )
    return path


def grade_the_task(
    task_id: str,
    workspace_path: str,
    output_dir: Path,
    task: dict,
    result: dict,
    lobster_env: list[str] | None = None,
    transcript_container_path: str = "",
    grade_on_error: bool = False,
    write_error_score_on_failure: bool = False,
):
    gt_host = os.path.join(workspace_path, "gt")
    if os.path.isdir(gt_host):
        r_gt = subprocess.run(
            ["docker", "cp", gt_host, f"{task_id}:{TMP_WORKSPACE}/gt"],
            capture_output=True, text=True,
        )
        if r_gt.returncode != 0:
            logger.warning("[%s] gt directory copy failed: %s", task_id, r_gt.stderr)
        else:
            logger.info("[%s] gt directory copied to container %s/gt", task_id, TMP_WORKSPACE)

    # v2: a task is gradable if it has rule checks OR a declarative rubric.
    has_gradable = bool(task.get("automated_checks") or task.get("rubric_criteria"))
    should_grade = has_gradable and (
        not result.get("error") or grade_on_error
    )
    if should_grade:
        try:
            scores = run_grading(
                task_id=task_id,
                automated_checks=task.get("automated_checks", ""),
                output_dir=output_dir,
                extra_env=task.get("env", ""),
                lobster_env=lobster_env,
                transcript_container_path=transcript_container_path,
                write_error_score=write_error_score_on_failure,
                llm_judge_rubric=task.get("llm_judge_rubric", ""),
                rubric_criteria=task.get("rubric_criteria") or [],
                grading_weights=task.get("grading_weights") or {},
                metric_profile=task.get("metric_profile", ""),
                task_definition_id=task.get("task_id", ""),
                judge_evidence=task.get("judge_evidence") or {},
            )
            result["scores"] = scores
            print(format_scores(task_id, scores))
            logger.info("[%s] Grading complete", task_id)
        except Exception as exc:
            logger.error("[%s] Grading failed: %s", task_id, exc)
            result["scores"] = write_error_score_file(output_dir, task_id, str(exc))
    elif not has_gradable:
        logger.info("[%s] No Automated Checks or rubric, skipping grading", task_id)
        if result.get("error"):
            result["scores"] = write_error_score_file(output_dir, task_id, result["error"])

    return result

def save_usage(output_dir: Path, result: dict, usage: dict, task_id: str) -> dict:
    result["usage"] = usage
    if usage["request_count"] > 0:
        cost_status = str(usage.get("cost_status") or "reported")
        if cost_status in {"unavailable", "not_applicable"}:
            cost_display = cost_status
        else:
            cost_display = f"${float(usage.get('cost_usd', 0.0)):.4f}"
            if cost_status != "reported":
                cost_display += f" ({cost_status})"
        logger.info(
            "[%s] Token usage - input:%d output:%d cache_read:%d total:%d cost:%s",
            task_id,
            usage["input_tokens"], usage["output_tokens"],
            usage["cache_read_tokens"], usage["total_tokens"],
            cost_display,
        )
    usage_path = output_dir / "usage.json"
    usage_path.write_text(
        json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("[%s] Usage written to %s", task_id, usage_path)
    return result

def collect_task_output(
    task_id: str,
    output_dir: Path,
    *,
    include_workspace_changes: bool = False,
) -> None:
    """Collect task output files from the container to output_dir/task_output/."""
    try:
        collect_output_from_container(
            task_id,
            output_dir,
            include_workspace_changes=include_workspace_changes,
        )
    except Exception as exc:
        logger.warning("[%s] Failed to collect task output: %s", task_id, exc)


def load_models_config(models_config_path: Path) -> dict:
    raw_config = models_config_path.read_text(encoding="utf-8")
    proxy_api_key = os.environ.get("MY_PROXY_API_KEY")
    if MODELS_API_KEY_PLACEHOLDER in raw_config and not proxy_api_key:
        raise ValueError(
            "MY_PROXY_API_KEY must be set to a non-empty value when models config uses ${MY_PROXY_API_KEY}"
        )

    expanded_config = raw_config.replace(
        MODELS_API_KEY_PLACEHOLDER,
        proxy_api_key or "",
    )
    parsed_models_config = json.loads(expanded_config)
    if not isinstance(parsed_models_config, dict):
        raise ValueError(f"Models config must be a JSON object: {models_config_path}")
    return parsed_models_config


def _short_model_slug(model: str) -> str:
    return re.sub(r'[^a-zA-Z0-9.\-_]', '_', model.rsplit('/', 1)[-1])


def _find_latest_run(output_root: Path, task: dict, model: str) -> Path | None:
    task_dir = output_root / task["category"] / task["task_id"]
    if not task_dir.is_dir():
        return None
    prefix = f"{_short_model_slug(model)}_"
    runs = sorted(p for p in task_dir.iterdir() if p.is_dir() and p.name.startswith(prefix))
    return runs[-1] if runs else None


def _load_resume_result(
    output_root: Path, task: dict, model: str,
    rerun_error: bool, rerun_anomalous: bool,
) -> dict | None:
    """已完成且无需重跑 → 返回重建的 result dict；否则返回 None（需执行）。"""
    task.pop("_reliability_rerun", None)
    latest = _find_latest_run(output_root, task, model)
    if latest is None:
        return None
    try:
        scores = json.loads((latest / "score.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        task["_reliability_rerun"] = {
            "supersedes_run": str(latest),
            "trigger": "missing_or_invalid_score",
        }
        return None
    anomalies = None
    anomalies_file = latest / "anomalies.json"
    if anomalies_file.exists():
        try:
            anomalies = json.loads(anomalies_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            anomalies = None
    if (
        anomalies is None
        or anomalies.get("schema_version") != SCHEMA_VERSION
        or anomalies.get("ruleset_version") != RULESET_VERSION
    ):
        # 旧快照缺失或规则版本不一致时，从原始产物重算，避免错误补跑。
        anomalies = scan_run_dir(latest)
        try:
            anomalies_file.write_text(
                json.dumps(anomalies, indent=2, ensure_ascii=False), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("[resume] 无法刷新 %s: %s", anomalies_file, exc)
    if rerun_anomalous and anomalies.get("is_anomalous"):
        logger.info("[resume] %s 最新 run 有异常，将重跑: %s",
                    task["task_id"], [i["id"] for i in anomalies["items"]])
        task["_reliability_rerun"] = {
            "supersedes_run": str(latest),
            "trigger": "rerun_anomalous",
        }
        return None
    if rerun_error and anomalies.get("needs_rerun"):
        logger.info("[resume] %s 最新 run 存在需修复后重跑的有效性故障，将重跑: %s",
                    task["task_id"],
                    [i["id"] for i in anomalies["items"]
                     if i.get("rerun_action") == "required_after_fix"])
        task["_reliability_rerun"] = {
            "supersedes_run": str(latest),
            "trigger": "rerun_error",
        }
        return None
    usage = {}
    try:
        usage = json.loads((latest / "usage.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    status = {}
    try:
        status = json.loads((latest / "execution_status.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    logger.info("[resume] 跳过已完成任务 %s（沿用 %s）", task["task_id"], latest.name)
    return {
        "task_id": latest.name,
        "scores": scores,
        "error": status.get("error"),
        "usage": usage,
        "anomalies": anomalies,
        "_resumed_from": str(latest),
    }


def _generate_global_summary_safely(
    results: list[dict],
    output_root: Path,
    summary_label: str,
    *,
    timing: dict,
    summary_sink: dict | None = None,
) -> float | None:
    try:
        summary = print_global_summary(
            results,
            output_root,
            summary_label,
            timing=timing,
            pass_threshold=PASS_THRESHOLD,
        )
    except Exception as exc:
        logger.warning("跑批总平均结果生成失败，继续主流程: %s", exc)
        return None

    if not isinstance(summary, dict):
        return None
    if summary_sink is not None:
        summary_sink.update(summary)
    scored_task_count = summary.get("scored_task_count")
    global_average = summary.get("global_avg")
    if (
        not isinstance(scored_task_count, (int, float))
        or isinstance(scored_task_count, bool)
        or scored_task_count <= 0
        or not isinstance(global_average, (int, float))
        or isinstance(global_average, bool)
        or not math.isfinite(float(global_average))
    ):
        return None
    return float(global_average)


def _log_batch_completion(
    timing: dict,
    *,
    task_count: int,
    global_average: float | None,
    valid_global_average: float | None = None,
    validity_failure_count: int = 0,
    validity_failure_task_count: int = 0,
) -> None:
    global_average_display = (
        f"{global_average:.4f}" if global_average is not None else "不可用"
    )
    batch_total_seconds = float(timing.get("batch_total_seconds", 0.0) or 0.0)
    task_exec_sum_seconds = float(timing.get("task_exec_sum_seconds", 0.0) or 0.0)
    avg_exec_seconds = float(timing.get("avg_exec_seconds", 0.0) or 0.0)
    parallelism = int(timing.get("parallelism", 0) or 0)
    logger.info(
        "📊 跑批完成: 跑批总耗时=%.0fs (~%.1fmin) | 用例执行总耗时=%.0fs (~%.1fmin) "
        "| 并发=%d | %d 题 | 平均执行=%.0fs/题 | 总平均结果=%s "
        "| 有效结果平均=%s | 有效性失败=%d次/%d题",
        batch_total_seconds,
        batch_total_seconds / 60,
        task_exec_sum_seconds,
        task_exec_sum_seconds / 60,
        parallelism,
        task_count,
        avg_exec_seconds,
        global_average_display,
        f"{valid_global_average:.4f}" if valid_global_average is not None else "不可用",
        validity_failure_count,
        validity_failure_task_count,
    )


def _load_anomaly_snapshot(run_dir: Path | None) -> dict[str, Any] | None:
    """Load a run's anomaly snapshot without making rerun reporting fatal."""
    if run_dir is None or not run_dir.is_dir():
        return None
    path = run_dir / "anomalies.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _anomaly_ids(anomalies: dict[str, Any] | None) -> list[str]:
    if not isinstance(anomalies, dict):
        return []
    return [
        str(item.get("id"))
        for item in anomalies.get("items", [])
        if isinstance(item, dict) and item.get("id")
    ]


def _build_rerun_record(
    *,
    task_id: str,
    output_dir: Path,
    rerun_metadata: dict[str, Any],
    anomalies: dict[str, Any] | None,
) -> dict[str, Any]:
    """Classify the current run against the run it superseded.

    The batch anomaly report intentionally retains historical runs.  This
    record is the current rerun outcome and therefore answers whether this
    particular retry resolved the previous validity failure.
    """
    supersedes_raw = str(rerun_metadata.get("supersedes_run") or "")
    supersedes_path = Path(supersedes_raw) if supersedes_raw else None
    previous = _load_anomaly_snapshot(supersedes_path)
    current_ids = _anomaly_ids(anomalies)
    previous_ids = _anomaly_ids(previous)

    score_path = output_dir / "score.json"
    score_available = score_path.is_file()
    judge_summary: dict[str, Any] = {}
    judge_summary_path = output_dir / "judge" / "summary.json"
    try:
        loaded_judge_summary = json.loads(
            judge_summary_path.read_text(encoding="utf-8")
        )
        if isinstance(loaded_judge_summary, dict):
            judge_summary = loaded_judge_summary
    except (OSError, json.JSONDecodeError):
        pass
    if anomalies is None or not score_available:
        status = "failed"
    elif anomalies.get("has_validity_failure") or anomalies.get("needs_rerun"):
        status = "failed"
    elif anomalies.get("needs_review"):
        status = "review"
    else:
        status = "success"

    record = {
        "schema_version": 1,
        "status": status,
        "task_id": task_id,
        "new_run": output_dir.name,
        "supersedes_run": supersedes_path.name if supersedes_path else supersedes_raw,
        "trigger": str(rerun_metadata.get("trigger") or "reliability_rerun"),
        "previous_anomalies": previous_ids,
        "current_anomalies": current_ids,
        "resolved_anomalies": [item for item in previous_ids if item not in current_ids],
        "remaining_anomalies": current_ids,
        "score_available": score_available,
        "needs_rerun": bool(anomalies and anomalies.get("needs_rerun")),
        "needs_review": bool(anomalies and anomalies.get("needs_review")),
        "judge_status": judge_summary.get("status"),
        "judge_attempt_count": judge_summary.get("attempt_count"),
        "judge_selected_attempt": judge_summary.get("selected_attempt"),
        "judge_failed_attempt_count": judge_summary.get("failed_attempt_count"),
        "judge_schema_mismatch_count": judge_summary.get("schema_mismatch_count"),
    }
    return record


def _record_rerun_outcome(
    *,
    task_id: str,
    output_dir: Path,
    rerun_metadata: dict[str, Any] | None,
    anomalies: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(rerun_metadata, dict) or not rerun_metadata.get("supersedes_run"):
        return None
    record = _build_rerun_record(
        task_id=task_id,
        output_dir=output_dir,
        rerun_metadata=rerun_metadata,
        anomalies=anomalies,
    )
    try:
        (output_dir / "rerun_result.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("[%s] 无法写入 rerun_result.json: %s", task_id, exc)

    resolved = ",".join(record["resolved_anomalies"]) or "none"
    remaining = ",".join(record["remaining_anomalies"]) or "none"
    judge_status = record["judge_status"] or "unknown"
    judge_attempts = record["judge_attempt_count"] or "unknown"
    judge_failures = record["judge_failed_attempt_count"]
    judge_schema_errors = record["judge_schema_mismatch_count"]
    judge_detail = (
        f"{judge_status} attempts={judge_attempts} "
        f"selected={record['judge_selected_attempt'] or 'none'} "
        f"failed={judge_failures if judge_failures is not None else 'unknown'} "
        f"schema_errors={judge_schema_errors if judge_schema_errors is not None else 'unknown'}"
    )
    if record["status"] == "success":
        logger.info(
            "[%s] RERUN SUCCESS 重跑成功: old_run=%s new_run=%s resolved=%s judge={%s}",
            task_id, record["supersedes_run"], record["new_run"], resolved,
            judge_detail,
        )
    elif record["status"] == "failed":
        logger.warning(
            "[%s] RERUN FAILED 重跑仍失败: old_run=%s new_run=%s remaining=%s judge={%s}",
            task_id, record["supersedes_run"], record["new_run"], remaining,
            judge_detail,
        )
    else:
        logger.warning(
            "[%s] RERUN REVIEW 重跑无有效性失败但需要复核: old_run=%s new_run=%s remaining=%s judge={%s}",
            task_id, record["supersedes_run"], record["new_run"], remaining,
            judge_detail,
        )
    return record


def _write_rerun_summary(results: list[dict], output_root: Path) -> None:
    records = [
        result["rerun"]
        for result in results
        if isinstance(result.get("rerun"), dict)
    ]
    summary = {
        "schema_version": 1,
        "total": len(records),
        "success": sum(1 for record in records if record.get("status") == "success"),
        "failed": sum(1 for record in records if record.get("status") == "failed"),
        "review": sum(1 for record in records if record.get("status") == "review"),
        "records": records,
    }
    path = output_root / "rerun_summary.json"
    try:
        path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except OSError as exc:
        logger.warning("无法写入重跑汇总 %s: %s", path, exc)
        return
    if records:
        logger.info(
            "Rerun summary: total=%d success=%d failed=%d review=%d (report: %s)",
            summary["total"], summary["success"], summary["failed"],
            summary["review"], path,
        )


def run_single_task(
    task: dict,
    model: str,
    backend: BaseAgent,
    output_root: Path,
    lobster: dict | None = None,
    thinking: str | None = None,
    models_config: dict | None = None,
) -> dict:
    """
    Execute a single task, returning a {"task_id", "scores", "error"} dict.
    Thread-safe: each task has its own container name and log directory.

    lobster: optional dict with keys "name", "workspace", "env".
    """
    task_id_ori     = task["task_id"]
    workspace_path  = task["workspace_path"]
    prompt          = task["prompt"]
    if TIMEOUT_OVERRIDE is not None:
        timeout_seconds = TIMEOUT_OVERRIDE
    else:
        timeout_seconds = max(1, int(round(task["timeout_seconds"] * TIMEOUT_MULTIPLIER)))
    system_prompt = f"You are an expert in a restricted, non-interactive environment. Solve the task efficiently before the timeout ({timeout_seconds}s). Run all processes in the foreground without user input or background services. Provide a complete, functional solution in a single pass with no placeholders. \n"
    prompt = system_prompt + prompt

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    run_id = uuid.uuid4().hex[:6]
    _m = re.match(r"(\d+)_.*?(task_\d+)", task_id_ori)
    short_task_id = f"{_m.group(1)}_{_m.group(2)}" if _m else task_id_ori
    short_model = re.sub(r'[^a-zA-Z0-9.\-_]', '_', model.rsplit('/', 1)[-1])
    lobster_prefix = f"{lobster['name']}_" if lobster else ""
    suffix = f"{lobster_prefix}{short_model}_{timestamp}_{run_id}"
    task_id = f"{short_task_id}_{lobster_prefix}{short_model}_{timestamp}_{run_id}"

    output_dir = output_root / task["category"] / f"{task_id_ori}" / f"{suffix}"
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance = _task_provenance_or_unavailable(task)
    try:
        write_provenance_file(output_dir / "provenance.json", provenance)
    except OSError as exc:
        # Provenance is deliberately non-blocking in the first rollout.  The
        # report records it as missing without changing scores or report output.
        logger.warning("[%s] 无法写入 provenance.json，评测继续执行: %s", task_id, exc)
    rerun_metadata = task.get("_reliability_rerun")
    if isinstance(rerun_metadata, dict) and rerun_metadata.get("supersedes_run"):
        write_rerun_metadata(
            output_dir,
            supersedes_run=str(rerun_metadata["supersedes_run"]),
            trigger=str(rerun_metadata.get("trigger") or "reliability_rerun"),
            task_id=task_id_ori,
            model=model,
        )

    result = {"task_id": task_id, "task_id_ori": task_id_ori, "scores": {}, "error": None}

    gateway_proc = None
    agent_proc = None
    elapsed_time = float(timeout_seconds)
    anomalies: dict[str, Any] | None = None

    try:
        execution = backend.run_task(
            AgentTaskSpec(
                task_id=task_id,
                task=task,
                workspace_path=workspace_path,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                output_dir=output_dir,
                model=model,
                thinking=thinking,
                models_config=models_config,
                lobster=lobster,
            )
        )
        gateway_proc = execution.gateway_proc
        agent_proc = execution.agent_proc
        elapsed_time = execution.elapsed_time
        if execution.error:
            result["error"] = execution.error
    except Exception as exc:
        result["error"] = str(exc)
        logger.error("[%s] Unexpected backend error: %s", task_id, exc)

    finally:
        grading_transcript_path = backend.transcript_container_path
        grade_on_error = isinstance(backend, GRADE_ON_ERROR_BACKENDS)
        # v2: gradable if rule checks OR declarative rubric present.
        should_grade = (task.get("automated_checks") or task.get("rubric_criteria")) and (
            not result.get("error") or grade_on_error
        )
        if should_grade:
            try:
                grading_transcript_path = backend.prepare_grading_transcript(task_id)
            except Exception as exc:
                logger.warning(
                    "[%s] Failed to prepare grading transcript, fallback to %s: %s",
                    task_id,
                    grading_transcript_path,
                    exc,
                )

        result = grade_the_task(
            task_id,
            workspace_path,
            output_dir,
            task,
            result,
            lobster.get("env") if lobster else None,
            transcript_container_path=grading_transcript_path,
            grade_on_error=grade_on_error,
            write_error_score_on_failure=grade_on_error,
        )
        usage = backend.collect_usage(
            task_id=task_id,
            output_dir=output_dir,
            elapsed_time=elapsed_time,
        )
        result = save_usage(output_dir, result, usage, task_id)

        try:
            collect_task_output(
                task_id,
                output_dir,
                include_workspace_changes=isinstance(
                    backend,
                    WORKSPACE_CHANGE_BACKENDS,
                ),
            )
        except Exception as exc:
            logger.warning("[%s] Failed to collect task output: %s", task_id, exc)

        # 全部产物落盘后做 run 级异常检测（纯读文件，不影响评分产物）
        try:
            anomalies = scan_run_dir(output_dir)
            (output_dir / "anomalies.json").write_text(
                json.dumps(anomalies, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            if anomalies["has_validity_failure"]:
                logger.warning(
                    "[%s] Evaluation validity failure detected: %s",
                    task_id,
                    ", ".join(i["id"] for i in anomalies["items"]
                              if i.get("validity_impact") == "fail"),
                )
            elif anomalies["needs_review"]:
                logger.warning(
                    "[%s] Evaluation anomalies require review: %s",
                    task_id,
                    ", ".join(i["id"] for i in anomalies["items"]
                              if i.get("validity_impact") == "review"),
                )
            result["anomalies"] = anomalies
        except Exception as exc:
            logger.warning("[%s] Anomaly scan failed: %s", task_id, exc)

        try:
            rerun_record = _record_rerun_outcome(
                task_id=task_id,
                output_dir=output_dir,
                rerun_metadata=rerun_metadata,
                anomalies=anomalies,
            )
        except Exception as exc:
            # Rerun observability must never turn a completed scoring run into
            # a failed evaluation.
            logger.warning("[%s] Rerun outcome recording failed: %s", task_id, exc)
            rerun_record = None
        if rerun_record is not None:
            result["rerun"] = rerun_record

        if gateway_proc is not None:
            try:
                gateway_proc.terminate()
            except Exception:
                pass
        elif backend.expects_gateway:
            logger.warning("[%s] Gateway not started, task incomplete - likely missing required result files, check %s", task_id, output_dir)

        for _proc in [gateway_proc, agent_proc]:
            if _proc is not None:
                try:
                    close_proc_log(_proc)
                except Exception:
                    pass

        remove_container(task_id)
        logger.info("[%s] Container cleaned up", task_id)

    # 用例执行耗时（agent 执行时长，来自 execution），供批级"用例执行总耗时"累加。
    # 只有本次实际执行的 run 带此字段；resume 复用的 result 不带，天然不计入 B。
    result["elapsed_time"] = elapsed_time
    return result


def main() -> None:
    global PASS_THRESHOLD
    _batch_start = time.perf_counter()  # 跑批总耗时(墙钟)起点：命令进入 main 即计时
    args = parse_run_batch_args(
        default_model=DEFAULT_MODEL,
        default_parallel=DEFAULT_PARALLEL,
    )

    # 内置文件日志：程序自己写 <output_root>/run.log（纯文本 + emoji），
    # 无需 shell `> run.log` 重定向；VS Code 打开干净、可随时 tail、随结果归档。
    # 尽早挂载，使 run.log 从第一行起完整（含下方 timeout 配置日志）。
    output_root = OUTPUT_DIR / args.agent_backend
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        run_log_path = output_root / "run.log"
        attach_file_logging(run_log_path)
        logger.info("Run log: %s", run_log_path)
    except OSError as exc:
        logger.warning("Failed to attach run.log file handler: %s", exc)

    global TIMEOUT_MULTIPLIER
    if args.timeout_multiplier is not None:
        TIMEOUT_MULTIPLIER = args.timeout_multiplier
    else:
        TIMEOUT_MULTIPLIER = float(
            os.environ.get("WILDCLAW_TIMEOUT_MULTIPLIER", "").strip() or "1"
        )
    if TIMEOUT_MULTIPLIER <= 0:
        raise SystemExit(
            f"timeout multiplier must be > 0, got {TIMEOUT_MULTIPLIER}"
        )
    if TIMEOUT_MULTIPLIER != 1.0:
        logger.info("Timeout multiplier: %.2fx (applies to every task's timeout_seconds)", TIMEOUT_MULTIPLIER)

    global TIMEOUT_OVERRIDE
    if args.timeout_override is not None:
        TIMEOUT_OVERRIDE = args.timeout_override
    else:
        env_override = os.environ.get("WILDCLAW_TIMEOUT_OVERRIDE", "").strip()
        TIMEOUT_OVERRIDE = int(env_override) if env_override else None
    if TIMEOUT_OVERRIDE is not None:
        if TIMEOUT_OVERRIDE <= 0:
            raise SystemExit(f"timeout override must be > 0, got {TIMEOUT_OVERRIDE}")
        if TIMEOUT_MULTIPLIER != 1.0:
            logger.warning("Both timeout override and multiplier set; override wins (%ds)", TIMEOUT_OVERRIDE)
        logger.info("Timeout override: %ds (every task uses this fixed timeout)", TIMEOUT_OVERRIDE)

    # 容器资源限额：CLI 优先写入 env，runner 侧经 container_resource_args() 读取；
    # 两者皆未设置时不加任何 docker 参数（与现状一致）
    if args.memory:
        os.environ["WILDCLAW_DOCKER_MEMORY"] = args.memory
    if args.cpus:
        os.environ["WILDCLAW_DOCKER_CPUS"] = str(args.cpus)
    _mem = os.environ.get("WILDCLAW_DOCKER_MEMORY", "").strip()
    _cpu = os.environ.get("WILDCLAW_DOCKER_CPUS", "").strip()
    if _mem or _cpu:
        logger.info("Container resource limits: memory=%s cpus=%s",
                    _mem or "unlimited", _cpu or "unlimited")

    global PASS_THRESHOLD
    PASS_THRESHOLD = args.pass_threshold  # 全局阈值供 summary 聚合使用
    backend = _build_agent_backend(args)
    run_configuration = _log_run_configuration(args, backend, output_root)
    run_invocation = run_configuration["invocation"]
    models_config = None
    if args.models_config:
        models_config_path = Path(args.models_config).expanduser()
        if not models_config_path.is_file():
            logger.error("Models config not found: %s", models_config_path)
            sys.exit(1)
        try:
            models_config = load_models_config(models_config_path.resolve())
        except (ValueError, json.JSONDecodeError) as exc:
            logger.error("Invalid models config: %s", exc)
            sys.exit(1)

    lobster = None
    if args.lobster_workspace:
        if not args.lobster_name:
            logger.error("--lobster-workspace requires --lobster-name")
            sys.exit(1)
        workspace = Path(args.lobster_workspace).expanduser()
        if not workspace.is_dir():
            logger.error("Lobster workspace not found: %s", workspace)
            sys.exit(1)
        env_keys = [k.strip() for k in args.lobster_env.split(",") if k.strip()] if args.lobster_env else []
        lobster = {
            "name": args.lobster_name,
            "workspace": str(workspace.resolve()),
            "env": env_keys,
        }
        logger.info("Lobster mode: %s (workspace=%s, env_keys=%s)",
                     lobster["name"], lobster["workspace"], lobster["env"])

    if args.task:
        task_file = Path(args.task)
        if not task_file.exists():
            logger.error("File not found: %s", task_file)
            sys.exit(1)
        task = parse_task_md(task_file)
        logger.info("Single task mode: %s", task["task_id"])
        prior = None
        if args.resume or args.rerun_error or args.rerun_anomalous:
            prior = _load_resume_result(
                output_root, task, args.model, args.rerun_error, args.rerun_anomalous
            )
        pending_tasks = [] if prior is not None else [task]
        _write_evaluation_scope(
            output_root,
            [task],
            mode="task",
            categories=[str(task.get("category") or "")],
            modality=args.modality,
            include_tags={t.strip().lower() for t in (args.tags or []) if t.strip()},
            exclude_tags={t.strip().lower() for t in (args.exclude_tags or []) if t.strip()},
            runs=args.runs,
            pending_tasks=pending_tasks,
            invocation_id=run_invocation["id"],
            recorded_at=run_invocation["started_at"],
        )
        if prior is not None:
            _log_pending_task_counts([])
            return  # _load_resume_result 已打印跳过日志；沿用旧结果，正常退出
        _log_pending_task_counts([task])
        # 多轮执行：k 次调用 run_single_task，各自独立 run 目录
        for run_idx in range(args.runs):
            if args.runs > 1:
                logger.info("[run %d/%d] Starting task %s", run_idx + 1, args.runs, task["task_id"])
            result = run_single_task(
                task,
                args.model,
                backend=backend,
                output_root=output_root,
                lobster=lobster,
                models_config=models_config,
                thinking=args.thinking,
            )
            # 单任务模式：任一轮出错即退出（保持现有语义）
            if result.get("error") or (result.get("scores") or {}).get("error"):
                sys.exit(1)
        return
    if args.category.lower() == "all":
        categories = ALL_CATEGORIES
    else:
        categories = [args.category]

    all_results: list[dict] = []
    safe_model_name = re.sub(r'[^a-zA-Z0-9.\-_]', '_', args.model)
    resume_enabled = args.resume or args.rerun_error or args.rerun_anomalous
    selected_categories: list[tuple[str, list[dict], list[dict]]] = []
    planned_tasks: list[dict] = []

    for category in categories:
        # Scan both official tasks/<category>/ and extension tasks/extension/<category>/
        # so --category X and --category all can pick up extension tasks that share
        # the same logical category (output_dir/reports group by category).
        category_dir = TASKS_DIR / category
        extension_dir = TASKS_DIR / "extension" / category

        task_files = []
        if category_dir.exists():
            task_files.extend(sorted(category_dir.glob("*task_*.md")))
        if extension_dir.exists():
            task_files.extend(sorted(extension_dir.glob("*task_*.md")))

        if not task_files:
            logger.error("No task_*.md files found in: %s (or %s)",
                         category_dir, extension_dir)
            continue

        logger.info("Category: %s, %d tasks (official + extension), parallelism: %d",
                    category, len(task_files), args.parallel)

        tasks = []
        for tf in task_files:
            try:
                tasks.append(parse_task_md(tf))
            except Exception as exc:
                logger.error("Parse failed %s: %s", tf, exc)

        if args.modality:
            before = len(tasks)
            tasks = [t for t in tasks if t.get("modality") == args.modality]
            logger.info("Modality filter '%s': %d/%d tasks kept in %s",
                        args.modality, len(tasks), before, category)

        include_tags = {t.strip().lower() for t in (args.tags or []) if t.strip()}
        exclude_tags = {t.strip().lower() for t in (args.exclude_tags or []) if t.strip()}
        if include_tags:
            before = len(tasks)
            tasks = [t for t in tasks
                     if include_tags & set(t.get("tags") or [])]
            logger.info("Tag filter (any of %s): %d/%d tasks kept in %s",
                        sorted(include_tags), len(tasks), before, category)
        if exclude_tags:
            before = len(tasks)
            tasks = [t for t in tasks
                     if not (exclude_tags & set(t.get("tags") or []))]
            logger.info("Exclude-tag filter (none of %s): %d/%d tasks kept in %s",
                        sorted(exclude_tags), len(tasks), before, category)

        if not tasks:
            continue

        planned_tasks.extend(tasks)

        resumed_results: list[dict] = []
        if resume_enabled:
            pending = []
            for task in tasks:
                prior = _load_resume_result(
                    output_root, task, args.model, args.rerun_error, args.rerun_anomalous
                )
                if prior is None:
                    pending.append(task)
                else:
                    resumed_results.append(prior)
            logger.info("[resume] %s: 复用 %d 个已完成 run，待执行 %d 个任务",
                        category, len(resumed_results), len(pending))
            tasks = pending

        selected_categories.append((category, tasks, resumed_results))

    _write_evaluation_scope(
        output_root,
        planned_tasks,
        mode="category",
        categories=categories,
        modality=args.modality,
        include_tags={t.strip().lower() for t in (args.tags or []) if t.strip()},
        exclude_tags={t.strip().lower() for t in (args.exclude_tags or []) if t.strip()},
        runs=args.runs,
        pending_tasks=[
            task
            for _category, tasks, _resumed_results in selected_categories
            for task in tasks
        ],
        invocation_id=run_invocation["id"],
        recorded_at=run_invocation["started_at"],
    )

    pending_tasks = [
        task
        for _category, tasks, _resumed_results in selected_categories
        for task in tasks
    ]
    _log_pending_task_counts(pending_tasks)

    for category, tasks, resumed_results in selected_categories:
        # 多轮执行：把任务列表展开成 (task, run_idx) 工作项
        # TODO: 多轮 + resume 耦合优化：改为"数够 k 条有效 run 才跳过"，当前简化为整任务跳过
        work_items = [(task, ri) for task in tasks for ri in range(args.runs)]
        results: list[dict] = []
        if args.parallel <= 1:
            for task, run_idx in work_items:
                if args.runs > 1:
                    logger.info("[run %d/%d] %s", run_idx + 1, args.runs, task["task_id"])
                results.append(
                    run_single_task(
                        task,
                        args.model,
                        backend=backend,
                        output_root=output_root,
                        lobster=lobster,
                        models_config=models_config,
                        thinking=args.thinking,
                    )
                )
        else:
            with ThreadPoolExecutor(max_workers=args.parallel) as pool:
                futures = {
                    pool.submit(
                        run_single_task,
                        task,
                        args.model,
                        backend,
                        output_root,
                        lobster,
                        args.thinking,
                        models_config,
                    ): (task["task_id"], run_idx)
                    for task, run_idx in work_items
                }
                for future in as_completed(futures):
                    tid, run_idx = futures[future]
                    try:
                        results.append(future.result())
                    except Exception as exc:
                        logger.error("[%s run %d] Thread exception: %s", tid, run_idx + 1, exc)
                        results.append({"task_id": tid, "scores": {}, "error": str(exc)})

        results.extend(resumed_results)
        summary_label = f"{lobster['name']}_{safe_model_name}" if lobster else safe_model_name
        print_summary(results, category, output_root, summary_label)
        all_results.extend(results)

    # 批级汇总（单分类也产出，含多轮 multirun 段）
    if all_results:
        summary_label = f"{lobster['name']}_{safe_model_name}" if lobster else safe_model_name
        # 计时：跑批总耗时(墙钟 C) vs 用例执行总耗时(Σ 本次执行 run 的 elapsed_time, B)。
        # B 只累加带 elapsed_time 的 result（resume 复用的不带，不计入）。
        batch_total_seconds = round(time.perf_counter() - _batch_start, 1)
        task_exec_sum_seconds = round(
            sum(r.get("elapsed_time", 0.0) or 0.0 for r in all_results), 1
        )
        executed_count = sum(1 for r in all_results if "elapsed_time" in r)
        avg_exec_seconds = round(task_exec_sum_seconds / executed_count, 1) if executed_count else 0.0
        timing = {
            "batch_total_seconds": batch_total_seconds,
            "task_exec_sum_seconds": task_exec_sum_seconds,
            "parallelism": args.parallel,
            "task_count": len(all_results),
            "executed_run_count": executed_count,
            "avg_exec_seconds": avg_exec_seconds,
            "effective_parallelism": (
                round(task_exec_sum_seconds / batch_total_seconds, 2)
                if batch_total_seconds > 0 else None
            ),
        }
        summary_snapshot: dict = {}
        global_average = _generate_global_summary_safely(
            all_results,
            output_root,
            summary_label,
            timing=timing,
            summary_sink=summary_snapshot,
        )
        _log_batch_completion(
            timing,
            task_count=len(all_results),
            global_average=global_average,
            valid_global_average=summary_snapshot.get("valid_global_avg"),
            validity_failure_count=int(
                summary_snapshot.get("validity_failure_run_count", 0) or 0
            ),
            validity_failure_task_count=int(
                summary_snapshot.get("validity_failure_task_count", 0) or 0
            ),
        )
        _write_rerun_summary(all_results, output_root)

    # 批级异常汇总（含跨 run 规则），供出数前把关与 --rerun-error 决策
    try:
        from src.utils.anomalies import scan_batch
        report = scan_batch(output_root)
        (output_root / "anomaly_report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if report["validity_failure_runs"]:
            logger.warning(
                "Anomaly summary: %d/%d runs have evaluation validity failures; "
                "%d runs require review (report: %s)",
                report["validity_failure_runs"], report["total_runs"], report["review_runs"],
                output_root / "anomaly_report.json",
            )
        else:
            logger.info(
                "Anomaly summary: %d runs scanned, no validity failures; %d require review",
                report["total_runs"], report["review_runs"],
            )
    except Exception as exc:
        logger.warning("Batch anomaly scan failed: %s", exc)

if __name__ == "__main__":
    main()
