#!/usr/bin/env python3
"""Prepare and persist recoverable Codex scoring task orchestration."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any, Mapping, Sequence
import uuid


STATE_SCHEMA = "wildclawbench.general-e2e-scoring-orchestration/v1"
STATE_REVISION = 2
REGISTRATION_SCHEMA = "wildclawbench.codex-project-registration/v1"
PACKAGE_SCHEMA = "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
REPORT_CONFIG_SCHEMA = "wildclawbench.general-e2e-report-config/v1"
PROMPT_PROTOCOL = "general-e2e-codex-scoring-prompt/v2"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
WAIT_STATUSES = {
    "RUNNING",
    "POLL_TIMEOUT",
    "NEEDS_ATTENTION",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "INTERRUPTED",
}
THREAD_PHASES = {"THREAD_RUNNING", "NEEDS_ATTENTION", "THREAD_TIMEOUT_PENDING"}
TERMINAL_PHASES = {"SCORE_RECORDED", "THREAD_FAILED"}
TASK_PHASES = {
    "AWAITING_PROJECT",
    "PROJECT_REGISTERED",
    "PREFLIGHT_PASSED",
    *THREAD_PHASES,
    "SCORE_VERIFICATION_PENDING",
    *TERMINAL_PHASES,
}
REASONING_EFFORTS = {
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
}
REGISTRATION_METHODS = {
    "direct-open-folder",
    "create-local-project-dialog",
    "create-project-dialog-on-this-computer",
    "add-project-then-open-folder",
    "renderer-bridge",
    "existing-project",
}


class OrchestrationError(ValueError):
    """Stable failure raised by the General E2E scoring controller."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise OrchestrationError("TIMESTAMP_INVALID", label)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrchestrationError("TIMESTAMP_INVALID", f"{label}={value!r}") from exc
    if parsed.tzinfo is None:
        raise OrchestrationError("TIMESTAMP_INVALID", f"{label} lacks timezone")
    return parsed.astimezone(timezone.utc)


def _identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise OrchestrationError("IDENTIFIER_INVALID", f"{label}={value!r}")
    return value


def _required_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OrchestrationError("STRING_REQUIRED", label)
    return value.strip()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _pretty_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _read_json(path: Path, code: str = "JSON_INVALID") -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OrchestrationError(code, f"{path}: {exc}") from exc
    if not isinstance(value, dict):
        raise OrchestrationError(code, f"{path}: top-level value must be an object")
    return value


def _write_new_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(_pretty_bytes(value))
    except FileExistsError as exc:
        raise OrchestrationError("OUTPUT_EXISTS", str(path)) from exc


def _atomic_write_json(path: Path, value: object) -> None:
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    try:
        with temporary.open("xb") as handle:
            handle.write(_pretty_bytes(value))
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _regular_file(path: Path, code: str) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise OrchestrationError(code, str(expanded))
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as exc:
        raise OrchestrationError(code, f"{path}: {exc}") from exc
    if not resolved.is_file():
        raise OrchestrationError(code, str(resolved))
    return resolved


def _regular_directory(path: Path, code: str) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise OrchestrationError(code, str(expanded))
    try:
        resolved = expanded.resolve(strict=True)
    except OSError as exc:
        raise OrchestrationError(code, f"{path}: {exc}") from exc
    if not resolved.is_dir():
        raise OrchestrationError(code, str(resolved))
    return resolved


def _inside(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _score_skill_lock(score_skill_dir: Path) -> dict[str, Any]:
    root = _regular_directory(score_skill_dir, "SCORE_SKILL_ROOT_INVALID")
    metadata_path = _regular_file(root / "skill-metadata.json", "SCORE_SKILL_METADATA_MISSING")
    metadata = _read_json(metadata_path, "SCORE_SKILL_METADATA_INVALID")
    if metadata.get("name") != "score-general-e2e":
        raise OrchestrationError("SCORE_SKILL_IDENTITY_MISMATCH")
    script = _regular_file(
        root / "scripts/score_general_e2e.py", "SCORE_SKILL_ENTRYPOINT_MISSING"
    )
    runtime_lock = _regular_file(
        root / "references/scoring-runtime-lock.json", "SCORE_RUNTIME_LOCK_MISSING"
    )
    return {
        "path": str(root),
        "name": "score-general-e2e",
        "version": _required_string(metadata.get("version"), "score skill version"),
        "implementation_status": _required_string(
            metadata.get("implementation_status"), "score skill status"
        ),
        "metadata_sha256": _sha256_file(metadata_path),
        "entrypoint_sha256": _sha256_file(script),
        "runtime_lock_sha256": _sha256_file(runtime_lock),
    }


def _score_entrypoint(lock: Mapping[str, Any]) -> Path:
    return Path(str(lock["path"])) / "scripts/score_general_e2e.py"


def _run_score_command(
    lock: Mapping[str, Any], arguments: Sequence[str]
) -> dict[str, Any]:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
    }
    completed = subprocess.run(
        [sys.executable, str(_score_entrypoint(lock)), *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise OrchestrationError("SCORE_SKILL_COMMAND_FAILED", detail[:2000])
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise OrchestrationError(
            "SCORE_SKILL_OUTPUT_INVALID", completed.stdout[:1000]
        ) from exc
    if not isinstance(value, dict) or value.get("status") != "PASS":
        raise OrchestrationError("SCORE_SKILL_OUTPUT_INVALID", repr(value))
    return value


def _execution_record_map(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise OrchestrationError("EXECUTION_RECORD_ARGUMENT_INVALID", value)
        task_id, raw_path = value.split("=", 1)
        task_id = _identifier(task_id, "execution record task_id")
        if task_id in result or not raw_path:
            raise OrchestrationError("EXECUTION_RECORD_ARGUMENT_INVALID", value)
        result[task_id] = Path(raw_path)
    return result


def _find_execution_record(
    unit_root: Path, task_id: str, explicit: Mapping[str, Path]
) -> Path:
    if task_id in explicit:
        path = _regular_file(explicit[task_id], "EXECUTION_RECORD_INVALID")
        if not _inside(unit_root, path):
            raise OrchestrationError("EXECUTION_RECORD_OUTSIDE_UNIT", str(path))
        return path
    task_root = unit_root / "evidence/tasks" / task_id
    candidates = sorted(task_root.glob("*/execution-record.json"))
    regular = [
        path.resolve(strict=True)
        for path in candidates
        if path.is_file() and not path.is_symlink()
    ]
    if any(not _inside(unit_root, path) for path in regular):
        raise OrchestrationError("EXECUTION_RECORD_OUTSIDE_UNIT", task_id)
    if len(regular) != 1:
        raise OrchestrationError(
            "EXECUTION_RECORD_SELECTION_REQUIRED",
            f"{task_id}: found {len(regular)}; pass --execution-record task=path",
        )
    return regular[0]


def _load_identity(
    unit_root: Path, report_config_path: Path, task_ids: Sequence[str]
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    manifest = _read_json(unit_root / "manifest.json", "UNIT_MANIFEST_INVALID")
    if (
        manifest.get("schema_id") != PACKAGE_SCHEMA
        or manifest.get("manifest_kind") != "execution"
    ):
        raise OrchestrationError("UNIT_MANIFEST_INVALID", "schema or kind")
    batch_id = _identifier(manifest.get("batch_id"), "batch_id")
    unit_id = _identifier(manifest.get("unit_id"), "unit_id")
    manifest_tasks = manifest.get("task_ids")
    if not isinstance(manifest_tasks, list) or not all(
        isinstance(item, str) for item in manifest_tasks
    ):
        raise OrchestrationError("UNIT_MANIFEST_INVALID", "task_ids")
    selected = list(task_ids) if task_ids else list(manifest_tasks)
    if len(selected) != len(set(selected)) or any(item not in manifest_tasks for item in selected):
        raise OrchestrationError("TASK_SELECTION_INVALID", repr(selected))
    selected = [item for item in manifest_tasks if item in set(selected)]
    if not selected:
        raise OrchestrationError("TASK_SELECTION_EMPTY")

    report = _read_json(report_config_path, "REPORT_CONFIG_INVALID")
    if report.get("schema_version") != REPORT_CONFIG_SCHEMA:
        raise OrchestrationError("REPORT_CONFIG_INVALID", "schema")
    if (
        report.get("batch_id") != batch_id
        or report.get("dataset") != manifest.get("dataset")
        or report.get("release") != manifest.get("release")
    ):
        raise OrchestrationError("REPORT_CONFIG_IDENTITY_MISMATCH")
    units = report.get("units")
    if not isinstance(units, list) or len(
        [item for item in units if isinstance(item, dict) and item.get("unit_id") == unit_id]
    ) != 1:
        raise OrchestrationError("REPORT_CONFIG_UNIT_MISMATCH", unit_id)
    judge = report.get("judge")
    if not isinstance(judge, dict):
        raise OrchestrationError("JUDGE_CONFIG_INVALID", "missing object")
    protocol = _required_string(judge.get("protocol"), "judge.protocol")
    if protocol != "codex-agent-judge-v1":
        raise OrchestrationError("JUDGE_PROTOCOL_UNSUPPORTED", protocol)
    model = _required_string(judge.get("model"), "judge.model")
    if model.lower().startswith("unconfigured"):
        raise OrchestrationError("JUDGE_MODEL_UNCONFIGURED", model)
    reasoning_effort = _required_string(
        judge.get("reasoning_effort"), "judge.reasoning_effort"
    )
    if reasoning_effort not in REASONING_EFFORTS:
        raise OrchestrationError("JUDGE_REASONING_EFFORT_UNSUPPORTED", reasoning_effort)
    frozen_judge = {
        "protocol": protocol,
        "model": model,
        "reasoning_effort": reasoning_effort,
    }
    identity = {
        "batch_id": batch_id,
        "unit_id": unit_id,
        "dataset": manifest.get("dataset"),
        "release": manifest.get("release"),
    }
    return identity, frozen_judge, selected


def _prompt_text(task_id: str, attempt_id: str, judge: Mapping[str, Any]) -> str:
    return f"""使用 `$score-general-e2e` 对当前 Codex 项目中的唯一 General E2E 任务进行评分。

冻结身份：

- task_id：`{task_id}`
- scoring_attempt_id：`{attempt_id}`
- judge_protocol：`{judge['protocol']}`
- judge_model：`{judge['model']}`
- reasoning_effort：`{judge['reasoning_effort']}`
- prompt_protocol：`{PROMPT_PROTOCOL}`

项目根目录就是本题私有评分 attempt。先读取 `attempt-manifest.json`，再严格遵循已安装 `$score-general-e2e` 的能力门禁和证据要求。只处理本题，不创建或调度其他任务，不执行被测 Harness，不修改 `candidate-original/`，不把自动规则组件冒充完整分数。若当前 Skill 尚不能形成正式评分，保留输入并明确报告未就绪，不得调用旧 CLI 或切换到 API Judge。

按 Skill 的单题流程执行：复核 attempt；按 grading type 运行所需自动规则；准备冻结语义证据目录；使用分页查询逐 criterion 查找支持证据和反例；把结构化判定写入新的响应文件并导入；最后合分并运行 `verify-score`。对纯 automated 任务不执行语义判断；必要证据不足时保留 `unresolved`，不得补零。只有 `verify-score` 通过后才把评分任务报告为完成。
"""


def _queue_digest(state: Mapping[str, Any]) -> str:
    payload = {
        "identity": state.get("identity"),
        "judge": state.get("judge"),
        "prompt_protocol": state.get("prompt_protocol"),
        "score_timeout_seconds": state.get("score_timeout_seconds"),
        "score_slots": state.get("score_slots"),
        "score_skill": state.get("score_skill"),
        "sources": state.get("sources"),
        "tasks": [
            {
                "task_id": task.get("task_id"),
                "order": task.get("order"),
                "execution_record_sha256": task.get("execution_record_sha256"),
                "scoring_attempt_id": task.get("scoring_attempt_id"),
                "attempt_path": task.get("attempt_path"),
                "attempt_manifest_sha256": task.get("attempt_manifest_sha256"),
                "prompt_path": task.get("prompt_path"),
                "prompt_sha256": task.get("prompt_sha256"),
            }
            for task in state.get("tasks", [])
        ],
    }
    return _sha256_bytes(_canonical_bytes(payload))


def initialize(
    *,
    unit_root: Path,
    scoring_package: Path,
    report_config: Path,
    score_skill_dir: Path,
    output_root: Path,
    orchestration_id: str,
    task_ids: Sequence[str] = (),
    execution_records: Mapping[str, Path] | None = None,
    score_timeout_seconds: int = 7200,
    score_slots: int = 1,
    now: datetime | None = None,
) -> dict[str, Any]:
    if score_timeout_seconds < 1:
        raise OrchestrationError("SCORE_TIMEOUT_INVALID")
    if score_slots != 1:
        raise OrchestrationError("SCORE_SLOTS_UNSUPPORTED", "G3-03 requires 1")
    orchestration_id = _identifier(orchestration_id, "orchestration_id")
    unit_root = _regular_directory(unit_root, "UNIT_ROOT_INVALID")
    scoring_package = _regular_file(scoring_package, "SCORING_PACKAGE_INVALID")
    report_config = _regular_file(report_config, "REPORT_CONFIG_INVALID")
    score_skill = _score_skill_lock(score_skill_dir)
    identity, judge, selected = _load_identity(unit_root, report_config, task_ids)
    explicit = execution_records or {}
    if set(explicit) - set(selected):
        raise OrchestrationError(
            "EXECUTION_RECORD_TASK_UNSELECTED", repr(sorted(set(explicit) - set(selected)))
        )
    final_root = output_root.expanduser().resolve() / orchestration_id
    if final_root.exists():
        raise OrchestrationError("ORCHESTRATION_EXISTS", str(final_root))
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = final_root.parent / f".{orchestration_id}.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    created = now or _now()
    tasks: list[dict[str, Any]] = []
    try:
        for index, task_id in enumerate(selected):
            record = _find_execution_record(unit_root, task_id, explicit)
            attempt_id = f"{orchestration_id}-{index + 1:03d}"
            result = _run_score_command(
                score_skill,
                [
                    "prepare",
                    "--unit-root",
                    str(unit_root),
                    "--execution-record",
                    str(record),
                    "--scoring-package",
                    str(scoring_package),
                    "--task-id",
                    task_id,
                    "--scoring-attempt-id",
                    attempt_id,
                    "--output-root",
                    str(staging / "attempts"),
                    "--judge-protocol",
                    judge["protocol"],
                    "--judge-model",
                    judge["model"],
                    "--judge-reasoning-effort",
                    judge["reasoning_effort"],
                    "--judge-attempt-id",
                    attempt_id,
                ],
            )
            attempt_root = Path(result["attempt_root"]).resolve(strict=True)
            if not _inside(staging, attempt_root):
                raise OrchestrationError("ATTEMPT_PATH_ESCAPE", str(attempt_root))
            prompt_path = staging / "prompts" / f"{task_id}.md"
            prompt_path.parent.mkdir(parents=True, exist_ok=True)
            prompt_path.write_text(
                _prompt_text(task_id, attempt_id, judge),
                encoding="utf-8",
                newline="\n",
            )
            tasks.append(
                {
                    "task_id": task_id,
                    "order": index,
                    "execution_record_sha256": _sha256_file(record),
                    "scoring_attempt_id": attempt_id,
                    "attempt_path": attempt_root.relative_to(staging).as_posix(),
                    "attempt_manifest_sha256": _sha256_file(
                        attempt_root / "attempt-manifest.json"
                    ),
                    "prompt_path": prompt_path.relative_to(staging).as_posix(),
                    "prompt_sha256": _sha256_file(prompt_path),
                    "phase": "AWAITING_PROJECT",
                    "project": None,
                    "preflight": None,
                    "thread": None,
                    "score": None,
                    "history": [
                        {
                            "at": _timestamp(created),
                            "event": "SCORING_ATTEMPT_PREPARED",
                        }
                    ],
                }
            )
        state: dict[str, Any] = {
            "schema_version": STATE_SCHEMA,
            "revision": STATE_REVISION,
            "orchestration_id": orchestration_id,
            "created_at": _timestamp(created),
            "updated_at": _timestamp(created),
            "status": "RUNNING",
            "identity": identity,
            "judge": judge,
            "prompt_protocol": PROMPT_PROTOCOL,
            "score_timeout_seconds": score_timeout_seconds,
            "score_slots": score_slots,
            "score_skill": score_skill,
            "sources": {
                "unit_manifest_sha256": _sha256_file(unit_root / "manifest.json"),
                "report_config_sha256": _sha256_file(report_config),
                "scoring_package_sha256": _sha256_file(scoring_package),
            },
            "tasks": tasks,
        }
        state["queue_digest"] = _queue_digest(state)
        _write_new_json(staging / "orchestration-state.json", state)
        os.replace(staging, final_root)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return status(final_root, now=created)


def _state_root(orchestration_root: Path) -> Path:
    return _regular_directory(orchestration_root, "ORCHESTRATION_ROOT_INVALID")


def _task_by_id(state: Mapping[str, Any], task_id: str) -> dict[str, Any]:
    matches = [task for task in state.get("tasks", []) if task.get("task_id") == task_id]
    if len(matches) != 1:
        raise OrchestrationError("TASK_NOT_FOUND", task_id)
    return matches[0]


def _active_task(state: Mapping[str, Any]) -> dict[str, Any] | None:
    return next(
        (task for task in state.get("tasks", []) if task.get("phase") not in TERMINAL_PHASES),
        None,
    )


def _require_active(state: Mapping[str, Any], task_id: str) -> dict[str, Any]:
    task = _task_by_id(state, task_id)
    active = _active_task(state)
    if active is None or active is not task:
        raise OrchestrationError("TASK_NOT_ACTIVE", task_id)
    return task


def _verify_state(root: Path) -> dict[str, Any]:
    state = _read_json(root / "orchestration-state.json", "ORCHESTRATION_STATE_INVALID")
    if state.get("schema_version") != STATE_SCHEMA or state.get("revision") != STATE_REVISION:
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "schema or revision")
    tasks = state.get("tasks")
    if not isinstance(tasks, list) or not tasks or not all(
        isinstance(task, dict) for task in tasks
    ):
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "tasks")
    task_ids = [task.get("task_id") for task in tasks]
    if (
        not all(isinstance(task_id, str) and ID_RE.fullmatch(task_id) for task_id in task_ids)
        or len(task_ids) != len(set(task_ids))
        or any(task.get("phase") not in TASK_PHASES for task in tasks)
    ):
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "task identity or phase")
    if state.get("queue_digest") != _queue_digest(state):
        raise OrchestrationError("QUEUE_DIGEST_MISMATCH")
    score_skill = state.get("score_skill")
    if not isinstance(score_skill, dict):
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "score_skill")
    current_skill = _score_skill_lock(Path(str(score_skill.get("path", ""))))
    if current_skill != state.get("score_skill"):
        raise OrchestrationError("SCORE_SKILL_DRIFT")
    for task in tasks:
        prompt = root / str(task.get("prompt_path", ""))
        attempt = root / str(task.get("attempt_path", ""))
        if not _inside(root, prompt.resolve()) or not _inside(root, attempt.resolve()):
            raise OrchestrationError("ORCHESTRATION_PATH_ESCAPE", str(task.get("task_id")))
        if (
            prompt.is_symlink()
            or not prompt.is_file()
            or _sha256_file(prompt) != task.get("prompt_sha256")
        ):
            raise OrchestrationError("SCORING_PROMPT_DRIFT", str(task.get("task_id")))
        manifest = attempt / "attempt-manifest.json"
        if (
            attempt.is_symlink()
            or manifest.is_symlink()
            or not manifest.is_file()
            or _sha256_file(manifest) != task.get("attempt_manifest_sha256")
        ):
            raise OrchestrationError("SCORING_ATTEMPT_MANIFEST_DRIFT", str(task.get("task_id")))
        _run_score_command(
            state["score_skill"], ["verify", "--attempt-root", str(attempt)]
        )
        project = task.get("project")
        if project is not None:
            evidence = root / str(project.get("evidence_path", ""))
            if (
                not _inside(root, evidence.resolve())
                or evidence.is_symlink()
                or not evidence.is_file()
                or _sha256_file(evidence) != project.get("evidence_sha256")
            ):
                raise OrchestrationError("PROJECT_REGISTRATION_DRIFT", str(task.get("task_id")))
        score = task.get("score")
        if score is not None:
            score_path = root / str(score.get("path", ""))
            if (
                not _inside(root, score_path.resolve())
                or score_path.is_symlink()
                or not score_path.is_file()
                or _sha256_file(score_path) != score.get("sha256")
            ):
                raise OrchestrationError("SCORE_ARTIFACT_DRIFT", str(task.get("task_id")))
            _run_score_command(
                state["score_skill"], ["verify-score", "--attempt-root", str(attempt)]
            )
    return state


def _state_status(state: Mapping[str, Any]) -> str:
    if any(task.get("phase") not in TERMINAL_PHASES for task in state.get("tasks", [])):
        return "RUNNING"
    return (
        "COMPLETED"
        if all(task.get("phase") == "SCORE_RECORDED" for task in state.get("tasks", []))
        else "COMPLETED_WITH_FAILURES"
    )


def _recommended_actions(
    root: Path, state: Mapping[str, Any], now: datetime
) -> list[dict[str, Any]]:
    task = _active_task(state)
    if task is None:
        return []
    task_id = task["task_id"]
    attempt = str((root / task["attempt_path"]).resolve())
    phase = task["phase"]
    if phase == "AWAITING_PROJECT":
        return [{"action": "REGISTER_PROJECT", "task_id": task_id, "project_path": attempt}]
    if phase == "PROJECT_REGISTERED":
        return [
            {
                "action": "PREFLIGHT_PROJECT",
                "task_id": task_id,
                "project_id": task["project"]["project_id"],
                "project_path": attempt,
            }
        ]
    if phase == "PREFLIGHT_PASSED":
        return [
            {
                "action": "CREATE_THREAD",
                "task_id": task_id,
                "project_id": task["project"]["project_id"],
                "host_id": task["project"]["host_id"],
                "target": {"type": "project", "environment": {"type": "local"}},
                "model": state["judge"]["model"],
                "thinking": state["judge"]["reasoning_effort"],
                "prompt_file": str((root / task["prompt_path"]).resolve()),
            }
        ]
    if phase == "SCORE_VERIFICATION_PENDING":
        return [
            {
                "action": "VERIFY_SCORE",
                "task_id": task_id,
                "attempt_path": attempt,
                "command": [
                    "verify-score",
                    "--attempt-root",
                    attempt,
                ],
            }
        ]
    thread = task.get("thread") or {}
    deadline = _parse_timestamp(thread.get("deadline_at"), "thread.deadline_at")
    if phase in {"THREAD_RUNNING", "NEEDS_ATTENTION"} and now >= deadline and not thread.get("timed_out_at"):
        return [
            {
                "action": "MARK_TIMEOUT",
                "task_id": task_id,
                "thread_id": thread.get("thread_id"),
                "deadline_at": thread.get("deadline_at"),
            }
        ]
    if phase == "NEEDS_ATTENTION":
        action = "INSPECT_THREAD"
    elif phase == "THREAD_TIMEOUT_PENDING":
        action = "WAIT_EXISTING_THREAD_AFTER_DEADLINE"
    else:
        action = "WAIT_EXISTING_THREAD"
    return [
        {
            "action": action,
            "task_id": task_id,
            "thread_id": thread.get("thread_id"),
            "host_id": thread.get("host_id"),
            "after_cursor": thread.get("cursor"),
            "next_wait_sequence": int(thread.get("wait_sequence", 0)) + 1,
            "deadline_at": thread.get("deadline_at"),
        }
    ]


def _public_view(root: Path, state: Mapping[str, Any], now: datetime) -> dict[str, Any]:
    status_value = _state_status(state)
    return {
        "status": status_value,
        "orchestration_root": str(root),
        "orchestration_id": state["orchestration_id"],
        "queue_digest": state["queue_digest"],
        "judge": state["judge"],
        "task_count": len(state["tasks"]),
        "completed_count": sum(
            task.get("phase") == "SCORE_RECORDED" for task in state["tasks"]
        ),
        "failed_count": sum(
            task.get("phase") == "THREAD_FAILED" for task in state["tasks"]
        ),
        "tasks": [
            {
                "task_id": task["task_id"],
                "phase": task["phase"],
                "scoring_attempt_id": task["scoring_attempt_id"],
                "attempt_path": str((root / task["attempt_path"]).resolve()),
                "project_id": (task.get("project") or {}).get("project_id"),
                "thread_id": (task.get("thread") or {}).get("thread_id"),
                "cursor": (task.get("thread") or {}).get("cursor"),
                "deadline_at": (task.get("thread") or {}).get("deadline_at"),
                "thread_status": (task.get("thread") or {}).get("status"),
                "score_valid": (task.get("score") or {}).get("valid"),
                "score_path": (
                    str((root / task["score"]["path"]).resolve())
                    if task.get("score") is not None
                    else None
                ),
            }
            for task in state["tasks"]
        ],
        "recommended_actions": _recommended_actions(root, state, now),
    }


def status(orchestration_root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    return _public_view(root, state, now or _now())


def _save(root: Path, state: dict[str, Any], now: datetime) -> dict[str, Any]:
    state["updated_at"] = _timestamp(now)
    state["status"] = _state_status(state)
    _atomic_write_json(root / "orchestration-state.json", state)
    return _public_view(root, state, now)


def record_project(
    orchestration_root: Path,
    *,
    task_id: str,
    project_id: str,
    host_id: str,
    project_path: Path,
    registration_evidence: Path | None = None,
    desktop_version: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    task = _require_active(state, _identifier(task_id, "task_id"))
    if task.get("phase") != "AWAITING_PROJECT":
        raise OrchestrationError("PROJECT_ALREADY_RECORDED", task_id)
    expected_path = (root / task["attempt_path"]).resolve(strict=True)
    actual_path = _regular_directory(project_path, "PROJECT_PATH_INVALID")
    if actual_path != expected_path:
        raise OrchestrationError("PROJECT_PATH_MISMATCH", str(actual_path))
    if registration_evidence is None:
        desktop_version = _required_string(desktop_version, "desktop_version")
        method = "existing-project"
        evidence = {
            "schema_version": REGISTRATION_SCHEMA,
            "status": "EXISTING_PROJECT_REUSED",
            "desktop_version": desktop_version,
            "projects": [
                {
                    "canonical_path": str(actual_path),
                    "ui_method": method,
                    "project_id": _required_string(project_id, "project_id"),
                    "host_id": _required_string(host_id, "host_id"),
                }
            ],
        }
    else:
        evidence_path = _regular_file(
            registration_evidence, "PROJECT_REGISTRATION_EVIDENCE_INVALID"
        )
        evidence = _read_json(evidence_path, "PROJECT_REGISTRATION_EVIDENCE_INVALID")
        if evidence.get("schema_version") != REGISTRATION_SCHEMA or evidence.get("status") not in {
            "UI_REGISTRATION_COMPLETED",
            "RENDERER_BRIDGE_REGISTRATION_COMPLETED",
        }:
            raise OrchestrationError("PROJECT_REGISTRATION_EVIDENCE_INVALID", "schema or status")
        projects = evidence.get("projects")
        matches = [
            item
            for item in projects or []
            if isinstance(item, dict)
            and Path(str(item.get("canonical_path", ""))).resolve() == actual_path
        ]
        if len(matches) != 1:
            raise OrchestrationError("PROJECT_REGISTRATION_PATH_MISMATCH")
        method = _required_string(matches[0].get("ui_method"), "registration ui_method")
        if method not in REGISTRATION_METHODS - {"existing-project"}:
            raise OrchestrationError("PROJECT_REGISTRATION_METHOD_INVALID", method)
        evidence_desktop_version = _required_string(
            evidence.get("desktop_version"), "registration desktop_version"
        )
        if desktop_version is not None and desktop_version != evidence_desktop_version:
            raise OrchestrationError("DESKTOP_VERSION_MISMATCH")
        desktop_version = evidence_desktop_version
    destination = root / "registration" / f"{task_id}.json"
    _write_new_json(destination, evidence)
    event_time = now or _now()
    task["project"] = {
        "project_id": _required_string(project_id, "project_id"),
        "host_id": _required_string(host_id, "host_id"),
        "canonical_path": str(actual_path),
        "desktop_version": desktop_version,
        "registration_method": method,
        "evidence_path": destination.relative_to(root).as_posix(),
        "evidence_sha256": _sha256_file(destination),
        "recorded_at": _timestamp(event_time),
    }
    task["phase"] = "PROJECT_REGISTERED"
    task["history"].append({"at": _timestamp(event_time), "event": "PROJECT_RECORDED"})
    return _save(root, state, event_time)


def preflight(
    orchestration_root: Path,
    *,
    task_id: str,
    desktop_version: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    task = _require_active(state, _identifier(task_id, "task_id"))
    if task.get("phase") != "PROJECT_REGISTERED":
        raise OrchestrationError("PROJECT_NOT_READY_FOR_PREFLIGHT", task_id)
    desktop_version = _required_string(desktop_version, "desktop_version")
    if desktop_version != task["project"]["desktop_version"]:
        raise OrchestrationError("DESKTOP_VERSION_MISMATCH")
    attempt = (root / task["attempt_path"]).resolve(strict=True)
    verification = _run_score_command(
        state["score_skill"], ["verify", "--attempt-root", str(attempt)]
    )
    event_time = now or _now()
    task["preflight"] = {
        "status": "PASSED",
        "checked_at": _timestamp(event_time),
        "desktop_version": desktop_version,
        "candidate_sha256": verification.get("candidate_sha256"),
        "queue_digest": state["queue_digest"],
    }
    task["phase"] = "PREFLIGHT_PASSED"
    task["history"].append({"at": _timestamp(event_time), "event": "PREFLIGHT_PASSED"})
    return _save(root, state, event_time)


def record_thread(
    orchestration_root: Path,
    *,
    task_id: str,
    thread_id: str,
    host_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    task = _require_active(state, _identifier(task_id, "task_id"))
    if task.get("phase") != "PREFLIGHT_PASSED":
        raise OrchestrationError("THREAD_NOT_EXPECTED", task_id)
    event_time = now or _now()
    deadline = event_time + timedelta(seconds=int(state["score_timeout_seconds"]))
    host_id = _required_string(host_id, "host_id")
    if host_id != task["project"]["host_id"]:
        raise OrchestrationError("THREAD_HOST_MISMATCH", host_id)
    task["thread"] = {
        "thread_id": _required_string(thread_id, "thread_id"),
        "host_id": host_id,
        "started_at": _timestamp(event_time),
        "deadline_at": _timestamp(deadline),
        "cursor": None,
        "wait_sequence": 0,
        "status": "RUNNING",
        "timed_out_at": None,
        "finished_at": None,
        "error": None,
    }
    task["phase"] = "THREAD_RUNNING"
    task["history"].append({"at": _timestamp(event_time), "event": "THREAD_RECORDED"})
    return _save(root, state, event_time)


def record_wait(
    orchestration_root: Path,
    *,
    task_id: str,
    wait_sequence: int,
    wait_cursor: str,
    wait_status: str,
    wait_error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    task = _require_active(state, _identifier(task_id, "task_id"))
    if task.get("phase") not in THREAD_PHASES:
        raise OrchestrationError("THREAD_WAIT_NOT_EXPECTED", task_id)
    thread = task.get("thread")
    if not isinstance(thread, dict):
        raise OrchestrationError("THREAD_STATE_INVALID", task_id)
    if wait_sequence != int(thread.get("wait_sequence", 0)) + 1:
        raise OrchestrationError("WAIT_SEQUENCE_MISMATCH", str(wait_sequence))
    wait_cursor = _required_string(wait_cursor, "wait_cursor")
    wait_status = _required_string(wait_status, "wait_status").upper()
    if wait_status not in WAIT_STATUSES:
        raise OrchestrationError("WAIT_STATUS_INVALID", wait_status)
    event_time = now or _now()
    deadline = _parse_timestamp(thread.get("deadline_at"), "thread.deadline_at")
    if event_time >= deadline and not thread.get("timed_out_at"):
        thread["timed_out_at"] = _timestamp(event_time)
        task["history"].append(
            {"at": _timestamp(event_time), "event": "DEADLINE_REACHED_DURING_WAIT"}
        )
    thread["wait_sequence"] = wait_sequence
    thread["cursor"] = wait_cursor
    thread["status"] = wait_status
    thread["error"] = wait_error
    task["history"].append(
        {
            "at": _timestamp(event_time),
            "event": "THREAD_WAIT_RECORDED",
            "sequence": wait_sequence,
            "status": wait_status,
            "cursor": wait_cursor,
        }
    )
    if wait_status == "NEEDS_ATTENTION":
        task["phase"] = "NEEDS_ATTENTION"
    elif wait_status in {"RUNNING", "POLL_TIMEOUT"}:
        task["phase"] = (
            "THREAD_TIMEOUT_PENDING" if thread.get("timed_out_at") else "THREAD_RUNNING"
        )
    else:
        thread["finished_at"] = _timestamp(event_time)
        if wait_status == "COMPLETED" and not thread.get("timed_out_at"):
            task["phase"] = "SCORE_VERIFICATION_PENDING"
        else:
            task["phase"] = "THREAD_FAILED"
    return _save(root, state, event_time)


def record_score(
    orchestration_root: Path,
    *,
    task_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    task = _require_active(state, _identifier(task_id, "task_id"))
    if task.get("phase") != "SCORE_VERIFICATION_PENDING":
        raise OrchestrationError("SCORE_VERIFICATION_NOT_EXPECTED", task_id)
    attempt = (root / task["attempt_path"]).resolve(strict=True)
    verification = _run_score_command(
        state["score_skill"], ["verify-score", "--attempt-root", str(attempt)]
    )
    score_path = attempt / "score.json"
    score = _read_json(score_path, "SCORE_DOCUMENT_INVALID")
    if verification.get("score_valid") is not score.get("result", {}).get("valid"):
        raise OrchestrationError("SCORE_VERIFICATION_MISMATCH", task_id)
    event_time = now or _now()
    task["score"] = {
        "path": score_path.relative_to(root).as_posix(),
        "sha256": _sha256_file(score_path),
        "valid": score["result"]["valid"],
        "total_score": score["result"]["total_score"],
        "recorded_at": _timestamp(event_time),
    }
    task["phase"] = "SCORE_RECORDED"
    task["history"].append(
        {
            "at": _timestamp(event_time),
            "event": "SCORE_RECORDED",
            "valid": score["result"]["valid"],
        }
    )
    return _save(root, state, event_time)


def mark_timeout(
    orchestration_root: Path,
    *,
    task_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    task = _require_active(state, _identifier(task_id, "task_id"))
    if task.get("phase") not in {"THREAD_RUNNING", "NEEDS_ATTENTION"}:
        raise OrchestrationError("THREAD_TIMEOUT_NOT_EXPECTED", task_id)
    thread = task.get("thread")
    if not isinstance(thread, dict):
        raise OrchestrationError("THREAD_STATE_INVALID", task_id)
    event_time = now or _now()
    deadline = _parse_timestamp(thread.get("deadline_at"), "thread.deadline_at")
    if event_time < deadline:
        raise OrchestrationError("THREAD_DEADLINE_NOT_REACHED", thread["deadline_at"])
    thread["timed_out_at"] = _timestamp(event_time)
    thread["status"] = "TIMED_OUT_PENDING_THREAD_TERMINAL"
    task["phase"] = "THREAD_TIMEOUT_PENDING"
    task["history"].append({"at": _timestamp(event_time), "event": "DEADLINE_REACHED"})
    return _save(root, state, event_time)


def _parse_common(subparser: argparse.ArgumentParser) -> None:
    subparser.add_argument("--orchestration-root", required=True, type=Path)


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="General E2E Codex 评分项目与可恢复任务编排器"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.add_argument("--unit-root", required=True, type=Path)
    init.add_argument("--scoring-package", required=True, type=Path)
    init.add_argument("--report-config", required=True, type=Path)
    init.add_argument("--score-skill-dir", required=True, type=Path)
    init.add_argument("--output-root", required=True, type=Path)
    init.add_argument("--orchestration-id", required=True)
    init.add_argument("--task-id", action="append", default=[])
    init.add_argument("--execution-record", action="append", default=[])
    init.add_argument("--score-timeout-seconds", type=int, default=7200)
    init.add_argument("--score-slots", type=int, default=1)

    for name in ("status", "resume"):
        _parse_common(subparsers.add_parser(name))

    project = subparsers.add_parser("record-project")
    _parse_common(project)
    project.add_argument("--task-id", required=True)
    project.add_argument("--project-id", required=True)
    project.add_argument("--host-id", required=True)
    project.add_argument("--project-path", required=True, type=Path)
    project.add_argument("--registration-evidence", type=Path)
    project.add_argument("--desktop-version")

    check = subparsers.add_parser("preflight")
    _parse_common(check)
    check.add_argument("--task-id", required=True)
    check.add_argument("--desktop-version", required=True)

    thread = subparsers.add_parser("record-thread")
    _parse_common(thread)
    thread.add_argument("--task-id", required=True)
    thread.add_argument("--thread-id", required=True)
    thread.add_argument("--host-id", required=True)

    wait = subparsers.add_parser("record-wait")
    _parse_common(wait)
    wait.add_argument("--task-id", required=True)
    wait.add_argument("--wait-sequence", required=True, type=int)
    wait.add_argument("--wait-cursor", required=True)
    wait.add_argument("--wait-status", required=True)
    wait.add_argument("--wait-error")

    timeout = subparsers.add_parser("mark-timeout")
    _parse_common(timeout)
    timeout.add_argument("--task-id", required=True)

    score = subparsers.add_parser("record-score")
    _parse_common(score)
    score.add_argument("--task-id", required=True)

    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            result = initialize(
                unit_root=args.unit_root,
                scoring_package=args.scoring_package,
                report_config=args.report_config,
                score_skill_dir=args.score_skill_dir,
                output_root=args.output_root,
                orchestration_id=args.orchestration_id,
                task_ids=args.task_id,
                execution_records=_execution_record_map(args.execution_record),
                score_timeout_seconds=args.score_timeout_seconds,
                score_slots=args.score_slots,
            )
        elif args.command in {"status", "resume"}:
            result = status(args.orchestration_root)
        elif args.command == "record-project":
            result = record_project(
                args.orchestration_root,
                task_id=args.task_id,
                project_id=args.project_id,
                host_id=args.host_id,
                project_path=args.project_path,
                registration_evidence=args.registration_evidence,
                desktop_version=args.desktop_version,
            )
        elif args.command == "preflight":
            result = preflight(
                args.orchestration_root,
                task_id=args.task_id,
                desktop_version=args.desktop_version,
            )
        elif args.command == "record-thread":
            result = record_thread(
                args.orchestration_root,
                task_id=args.task_id,
                thread_id=args.thread_id,
                host_id=args.host_id,
            )
        elif args.command == "record-wait":
            result = record_wait(
                args.orchestration_root,
                task_id=args.task_id,
                wait_sequence=args.wait_sequence,
                wait_cursor=args.wait_cursor,
                wait_status=args.wait_status,
                wait_error=args.wait_error,
            )
        elif args.command == "mark-timeout":
            result = mark_timeout(
                args.orchestration_root,
                task_id=args.task_id,
            )
        else:
            result = record_score(
                args.orchestration_root,
                task_id=args.task_id,
            )
        _print(result)
        return 0
    except OrchestrationError as exc:
        print(
            json.dumps(
                {"status": "FAIL", "error": {"code": exc.code, "detail": exc.detail}},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
