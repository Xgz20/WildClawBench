#!/usr/bin/env python3
"""Prepare and persist recoverable Codex or API Judge scoring orchestration."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
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
STATE_REVISION = 6
DEFAULT_SCORE_SLOTS = 3
MAX_SCORE_SLOTS = 8
REGISTRATION_SCHEMA = "wildclawbench.codex-project-registration/v1"
PACKAGE_SCHEMA = "urn:wildclawbench:schema:general-e2e:package-manifest:v1"
SCORE_SCHEMA = "urn:wildclawbench:schema:general-e2e:score:v1"
SUBMISSION_SCHEMA = "urn:wildclawbench:schema:general-e2e:submission:v1"
REPORT_CONFIG_SCHEMA = "wildclawbench.general-e2e-report-config/v1"
PROMPT_PROTOCOL = "general-e2e-codex-scoring-prompt/v5"
LEGACY_CODEX_PROMPT_PROTOCOLS = {"general-e2e-codex-scoring-prompt/v3"}
FROZEN_SKILL_PROMPT_PROTOCOLS = {
    "general-e2e-codex-scoring-prompt/v4",
    PROMPT_PROTOCOL,
}
API_PROMPT_PROTOCOL = "general-e2e-api-scoring-orchestration/v1"
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
TERMINAL_PHASES = {"SCORE_RECORDED", "THREAD_FAILED", "UNSCORED"}
RULE_PHASES = {"RULES_READY", "RULES_RUNNING", "RULES_NEEDS_ATTENTION"}
TASK_PHASES = {
    *RULE_PHASES,
    "API_READY",
    "API_RUNNING",
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
BUSINESS_STATUSES = {
    "completed",
    "candidate_error",
    "timeout",
    "infrastructure_error",
    "cancelled",
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


def _validation_marker(acceptance_id: str | None) -> dict[str, str] | None:
    if acceptance_id is None:
        return None
    return {
        "mode": "acceptance",
        "acceptance_id": _identifier(acceptance_id, "acceptance_id"),
    }


def _validate_validation_marker(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or set(value) != {"mode", "acceptance_id"}
        or value.get("mode") != "acceptance"
    ):
        raise OrchestrationError("VALIDATION_MARKER_INVALID")
    return _validation_marker(value.get("acceptance_id"))


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


def _validate_contract(
    document: Mapping[str, Any], *, expected_schema_id: str
) -> None:
    skill_root = Path(__file__).resolve().parents[1]
    candidates = [
        skill_root / "vendor/e2e-shared/general-contracts/validator.py"
    ]
    # Development checkout fallback. Deterministic Skill packages always use
    # the vendored validator and never depend on the repository package path.
    for parent in skill_root.parents:
        candidate = parent / "eval_general_e2e/contracts/validator.py"
        if candidate.is_file():
            candidates.append(candidate)
            break
    validator_path = next((path for path in candidates if path.is_file()), None)
    try:
        if validator_path is not None:
            spec = importlib.util.spec_from_file_location(
                "wildclawbench_general_contracts_vendor", validator_path
            )
            if spec is None or spec.loader is None:
                raise ImportError(str(validator_path))
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            validate_contract = module.validate_contract
        else:
            from eval_general_e2e.contracts import (  # type: ignore
                validate_contract,
            )
    except (ImportError, OSError, AttributeError) as exc:
        raise OrchestrationError("CONTRACT_VALIDATOR_UNAVAILABLE", str(exc)) from exc
    try:
        validate_contract(document, expected_schema_id=expected_schema_id)
    except Exception as exc:
        code = getattr(exc, "code", type(exc).__name__)
        path = getattr(exc, "path", "$")
        message = getattr(exc, "message", str(exc))
        raise OrchestrationError(
            "CONTRACT_VALIDATION_FAILED",
            f"{code} at {path}: {message}",
        ) from exc


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
    lock: Mapping[str, Any],
    arguments: Sequence[str],
    *,
    credential_env: str | None = None,
) -> dict[str, Any]:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUTF8": "1",
    }
    if credential_env is not None:
        credential = os.environ.get(credential_env, "")
        if credential:
            environment[credential_env] = credential
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


def _execution_summary(
    record_path: Path,
    *,
    batch_id: str,
    unit_id: str,
    task_id: str,
) -> dict[str, Any]:
    record = _read_json(record_path, "EXECUTION_RECORD_INVALID")
    identity = record.get("identity")
    if not isinstance(identity, dict) or (
        identity.get("batch_id"),
        identity.get("unit_id"),
        identity.get("task_id"),
    ) != (batch_id, unit_id, task_id):
        raise OrchestrationError("EXECUTION_RECORD_IDENTITY_MISMATCH", task_id)
    execution_attempt_id = _identifier(
        identity.get("attempt_id"), "execution_attempt_id"
    )
    execution = record.get("execution")
    business_status = (
        execution.get("business_status") if isinstance(execution, dict) else None
    )
    if business_status not in BUSINESS_STATUSES:
        raise OrchestrationError("EXECUTION_RECORD_STATUS_INVALID", task_id)
    candidate = record.get("candidate")
    candidate = candidate if isinstance(candidate, dict) else {}
    candidate_sha = candidate.get("frozen_sha256")
    candidate_sha = (
        candidate_sha
        if isinstance(candidate_sha, str) and SHA256_RE.fullmatch(candidate_sha)
        else None
    )
    evidence = record.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    evidence_manifest = record_path.with_name("evidence-manifest.json")
    evidence_sha: str | None = None
    if evidence_manifest.is_file() and not evidence_manifest.is_symlink():
        evidence_document = _read_json(
            evidence_manifest, "EVIDENCE_MANIFEST_INVALID"
        )
        if evidence_document.get("identity") != identity:
            raise OrchestrationError("EVIDENCE_MANIFEST_IDENTITY_MISMATCH", task_id)
        evidence_sha = _sha256_file(evidence_manifest)
    failure: dict[str, str] | None = None
    if business_status != "completed":
        failure = {
            "code": "EXECUTION_NOT_COMPLETED",
            "message": f"execution business status is {business_status}",
        }
    elif record.get("phase") != "COMPLETED":
        failure = {
            "code": "EXECUTION_PHASE_NOT_COMPLETED",
            "message": f"execution phase is {record.get('phase')!r}",
        }
    elif evidence.get("completeness") != "complete":
        failure = {
            "code": "EXECUTION_EVIDENCE_INCOMPLETE",
            "message": "complete execution evidence is required for scoring",
        }
    elif candidate.get("drift_status") != "stable" or candidate_sha is None:
        failure = {
            "code": "EXECUTION_CANDIDATE_NOT_STABLE",
            "message": "a stable frozen candidate is required for scoring",
        }
    return {
        "attempt_id": execution_attempt_id,
        "business_status": business_status,
        "candidate_sha256": candidate_sha,
        "evidence_sha256": evidence_sha,
        "record_sha256": _sha256_file(record_path),
        "scorable": failure is None,
        "failure": failure,
    }


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
    if protocol not in {"codex-agent-judge-v1", "api-judge-v1"}:
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


def _prompt_text(
    task_id: str,
    attempt_id: str,
    judge: Mapping[str, Any],
    grading_type: str,
    validation: Mapping[str, str] | None,
    score_skill: Mapping[str, Any] | None = None,
    *,
    prompt_protocol: str = PROMPT_PROTOCOL,
) -> str:
    rule_instruction = (
        "本题是 hybrid；自动规则组件已由控制器在创建语义会话前运行并冻结。"
        "先复核现有 `rule-component.json`，不得重复运行规则；再准备语义证据、完成语义判定并合分。"
        if grading_type == "hybrid"
        else "本题是 llm_judge；不运行自动规则，只完成语义证据、判定、合分与校验。"
    )
    if validation is None:
        readiness_instruction = (
            "若当前 Skill 尚不能形成正式评分，保留输入并明确报告未就绪，"
            "不得调用旧 CLI 或切换到 API Judge。"
        )
        validation_identity = "- validation_mode：`production`"
    else:
        acceptance_id = validation["acceptance_id"]
        readiness_instruction = (
            f"这是显式冻结的 `{acceptance_id}` 验收运行。仅当 `attempt-manifest.json` 中的 "
            f"`validation.mode=acceptance` 与 `validation.acceptance_id={acceptance_id}` "
            "同时匹配时，允许当前 `interface_only` Skill 执行本次验收评分；仍须完整执行所有证据、"
            "查询、结构化判定、合分和 `verify-score` 门禁。产物只能作为该验收项证据，不能单独宣称生产就绪。"
            "标记缺失或不匹配时立即失败关闭，不得调用旧 CLI、修改候选或切换到 API Judge。"
        )
        validation_identity = (
            "- validation_mode：`acceptance`\n"
            f"- acceptance_id：`{acceptance_id}`"
        )
    if prompt_protocol in LEGACY_CODEX_PROMPT_PROTOCOLS:
        skill_instruction = "使用 `$score-general-e2e` 对当前 Codex 项目中的唯一 General E2E 任务进行评分。"
        frozen_skill_identity = ""
        skill_usage = "严格遵循已安装 `$score-general-e2e` 的能力门禁和证据要求"
    elif prompt_protocol in FROZEN_SKILL_PROMPT_PROTOCOLS:
        if score_skill is None:
            raise OrchestrationError("SCORE_SKILL_LOCK_MISSING")
        score_skill_root = _required_string(score_skill.get("path"), "score_skill.path")
        score_entrypoint = str(_score_entrypoint(score_skill))
        implementation_status = _required_string(
            score_skill.get("implementation_status"),
            "score_skill.implementation_status",
        )
        skill_instruction = "使用下列冻结的 `score-general-e2e` Skill 对当前 Codex 项目中的唯一 General E2E 任务进行评分。"
        frozen_skill_identity = f"""
- score_skill_root：`{score_skill_root}`
- score_skill_entrypoint：`{score_entrypoint}`
- score_skill_version：`{score_skill['version']}`
- score_skill_entrypoint_sha256：`{score_skill['entrypoint_sha256']}`"""
        skill_usage = (
            f"先完整读取 `{score_skill_root}/SKILL.md` 及其为本题要求的引用文件，"
            f"所有评分命令只调用 `{score_entrypoint}`。不得使用项目、仓库或自动发现路径中的同名 Skill；"
            "冻结目录缺失、身份或哈希不匹配时立即停止"
        )
        if implementation_status == "operational" and validation is None:
            readiness_instruction = (
                "当前冻结 Skill 为 `operational`；按正式评分协议完成本题，"
                "不得调用旧 CLI 或切换到 API Judge。"
            )
        elif implementation_status == "operational":
            readiness_instruction = (
                f"这是显式冻结的 `{acceptance_id}` 验收运行。`attempt-manifest.json` 中的 "
                f"`validation.mode=acceptance` 与 `validation.acceptance_id={acceptance_id}` "
                "必须同时匹配；仍须完整执行所有证据、查询、结构化判定、合分和 `verify-score` 门禁。"
                "标记缺失或不匹配时立即失败关闭，不得调用旧 CLI、修改候选或切换到 API Judge。"
            )
    else:
        raise OrchestrationError("SCORING_PROMPT_PROTOCOL_UNSUPPORTED", prompt_protocol)
    return f"""{skill_instruction}

冻结身份：

- task_id：`{task_id}`
- scoring_attempt_id：`{attempt_id}`
- judge_protocol：`{judge['protocol']}`
- judge_model：`{judge['model']}`
- reasoning_effort：`{judge['reasoning_effort']}`
- prompt_protocol：`{prompt_protocol}`
{validation_identity}{frozen_skill_identity}

项目根目录就是本题私有评分 attempt。先读取 `attempt-manifest.json`，再{skill_usage}。只处理本题，不创建或调度其他任务，不执行被测 Harness，不修改 `candidate-original/`，不把自动规则组件冒充完整分数。{readiness_instruction}

{rule_instruction}

使用分页查询逐 criterion 查找支持证据和反例，把结构化判定写入新的响应文件并导入；必要证据不足时保留 `unresolved`，不得补零。提交响应前逐项执行以下自检：每个 `evidence_id` 都必须出现在对应 `query_ids` 的实际返回集合中；每个 `judged` criterion 都必须同时标记已检查支持证据和反例；任何“未发生”结论都必须使用无过滤条件分页覆盖完整 transcript，并将 `absence_claim` 与 `complete_event_range_checked` 都设为 `true`。若自检失败，先修正本题响应文件，不要提交会触发 `SEMANTIC_CITATION_NOT_QUERIED` 或 `SEMANTIC_ABSENCE_COVERAGE_REQUIRED` 的响应。只有 `verify-score` 通过后才把评分任务报告为完成。

评分运行注意事项：

- 若出现 `Selected model is at capacity. Please try a different model.`，这是当前 Codex 评分任务的容量重试过程；Codex 本身会在同一任务内最多重试 5 次。不要要求控制器新建评分任务、切换模型、创建替代会话或重复提交本题。只有当前任务经过自身重试后形成明确终态，控制器才按该终态继续。
- 候选本身没有产物、产物错误或内容不满足题目，是被评测结果的一部分。按冻结 rubric 和现有证据给出零分、部分分或合法 unresolved；不得因此终止控制会话、停止后续题目、重跑 Harness 或补造产物。评测基础设施身份/证据损坏才按评测异常处理。
"""


def _queue_digest(state: Mapping[str, Any]) -> str:
    payload = {
        "kind": state.get("kind"),
        "identity": state.get("identity"),
        "judge": state.get("judge"),
        "validation": state.get("validation"),
        "prompt_protocol": state.get("prompt_protocol"),
        "score_timeout_seconds": state.get("score_timeout_seconds"),
        "score_slots": state.get("score_slots"),
        "score_skill": state.get("score_skill"),
        "sources": state.get("sources"),
        "tasks": [
            {
                "task_id": task.get("task_id"),
                "order": task.get("order"),
                "execution": task.get("execution"),
                "execution_record_path": task.get("execution_record_path"),
                "execution_record_sha256": task.get("execution_record_sha256"),
                "source": task.get("source"),
                "grading_type": task.get("grading_type"),
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


def _load_rescore_judge(
    report_config_path: Path,
    source_state: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    report = _read_json(report_config_path, "REPORT_CONFIG_INVALID")
    if report.get("schema_version") != REPORT_CONFIG_SCHEMA:
        raise OrchestrationError("REPORT_CONFIG_INVALID", "schema")
    identity = source_state.get("identity")
    if not isinstance(identity, dict):
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "identity")
    if (
        report.get("batch_id") != identity.get("batch_id")
        or report.get("dataset") != identity.get("dataset")
        or report.get("release") != identity.get("release")
    ):
        raise OrchestrationError("REPORT_CONFIG_IDENTITY_MISMATCH")
    units = report.get("units")
    if not isinstance(units, list) or len(
        [
            item
            for item in units
            if isinstance(item, dict) and item.get("unit_id") == identity.get("unit_id")
        ]
    ) != 1:
        raise OrchestrationError(
            "REPORT_CONFIG_UNIT_MISMATCH", str(identity.get("unit_id"))
        )
    judge = report.get("judge")
    if not isinstance(judge, dict):
        raise OrchestrationError("JUDGE_CONFIG_INVALID", "missing object")
    protocol = _required_string(judge.get("protocol"), "judge.protocol")
    if protocol not in {"codex-agent-judge-v1", "api-judge-v1"}:
        raise OrchestrationError("JUDGE_PROTOCOL_UNSUPPORTED", protocol)
    model = _required_string(judge.get("model"), "judge.model")
    if model.lower().startswith("unconfigured"):
        raise OrchestrationError("JUDGE_MODEL_UNCONFIGURED", model)
    reasoning_effort = _required_string(
        judge.get("reasoning_effort"), "judge.reasoning_effort"
    )
    if reasoning_effort not in REASONING_EFFORTS:
        raise OrchestrationError(
            "JUDGE_REASONING_EFFORT_UNSUPPORTED", reasoning_effort
        )
    return dict(identity), {
        "protocol": protocol,
        "model": model,
        "reasoning_effort": reasoning_effort,
    }


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
    api_runtime_config: Path | None = None,
    acceptance_id: str | None = None,
    score_timeout_seconds: int = 7200,
    score_slots: int = DEFAULT_SCORE_SLOTS,
    now: datetime | None = None,
) -> dict[str, Any]:
    if score_timeout_seconds < 1:
        raise OrchestrationError("SCORE_TIMEOUT_INVALID")
    if not 1 <= score_slots <= MAX_SCORE_SLOTS:
        raise OrchestrationError(
            "SCORE_SLOTS_UNSUPPORTED", f"expected 1..{MAX_SCORE_SLOTS}"
        )
    orchestration_id = _identifier(orchestration_id, "orchestration_id")
    unit_root = _regular_directory(unit_root, "UNIT_ROOT_INVALID")
    scoring_package = _regular_file(scoring_package, "SCORING_PACKAGE_INVALID")
    report_config = _regular_file(report_config, "REPORT_CONFIG_INVALID")
    score_skill = _score_skill_lock(score_skill_dir)
    identity, judge, selected = _load_identity(unit_root, report_config, task_ids)
    validation = _validation_marker(acceptance_id)
    if validation is not None and judge["protocol"] != "codex-agent-judge-v1":
        raise OrchestrationError("ACCEPTANCE_MODE_REQUIRES_CODEX_JUDGE")
    if judge["protocol"] == "api-judge-v1":
        if api_runtime_config is None:
            raise OrchestrationError("API_JUDGE_CONFIG_REQUIRED")
        api_runtime_config = _regular_file(
            api_runtime_config, "API_JUDGE_CONFIG_INVALID"
        )
    elif api_runtime_config is not None:
        raise OrchestrationError("API_JUDGE_CONFIG_UNEXPECTED")
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
    frozen_api_runtime: dict[str, Any] | None = None
    try:
        for index, task_id in enumerate(selected):
            record = _find_execution_record(unit_root, task_id, explicit)
            execution = _execution_summary(
                record,
                batch_id=identity["batch_id"],
                unit_id=identity["unit_id"],
                task_id=task_id,
            )
            frozen_record = staging / "execution-records" / f"{task_id}.json"
            frozen_record.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(record, frozen_record)
            if _sha256_file(frozen_record) != execution["record_sha256"]:
                raise OrchestrationError("EXECUTION_RECORD_COPY_MISMATCH", task_id)
            common_task = {
                "task_id": task_id,
                "order": index,
                "execution": execution,
                "execution_record_path": frozen_record.relative_to(staging).as_posix(),
                "execution_record_sha256": execution["record_sha256"],
                "project": None,
                "preflight": None,
                "thread": None,
                "score": None,
                "grading_type": None,
            }
            if not execution["scorable"]:
                tasks.append(
                    {
                        **common_task,
                        "scoring_attempt_id": None,
                        "attempt_path": None,
                        "attempt_manifest_sha256": None,
                        "prompt_path": None,
                        "prompt_sha256": None,
                        "phase": "UNSCORED",
                        "history": [
                            {
                                "at": _timestamp(created),
                                "event": "SCORING_NOT_STARTED",
                                "error": execution["failure"],
                            }
                        ],
                    }
                )
                continue
            attempt_id = f"{orchestration_id}-{index + 1:03d}"
            prepare_arguments = [
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
                ]
            if api_runtime_config is not None:
                prepare_arguments.extend(
                    ["--api-runtime-config", str(api_runtime_config)]
                )
            if validation is not None:
                prepare_arguments.extend(
                    ["--acceptance-id", validation["acceptance_id"]]
                )
            result = _run_score_command(score_skill, prepare_arguments)
            attempt_root = Path(result["attempt_root"]).resolve(strict=True)
            if not _inside(staging, attempt_root):
                raise OrchestrationError("ATTEMPT_PATH_ESCAPE", str(attempt_root))
            attempt_manifest = _read_json(
                attempt_root / "attempt-manifest.json", "ATTEMPT_MANIFEST_INVALID"
            )
            attempt_judge = attempt_manifest.get("judge")
            grading_type = (attempt_manifest.get("grading") or {}).get("type")
            if grading_type not in {"automated", "hybrid", "llm_judge"}:
                raise OrchestrationError("GRADING_TYPE_INVALID", str(grading_type))
            if not isinstance(attempt_judge, dict):
                raise OrchestrationError("JUDGE_CONFIG_INVALID", "attempt manifest")
            current_api_runtime = attempt_judge.get("api_runtime")
            if judge["protocol"] == "api-judge-v1":
                if not isinstance(current_api_runtime, dict):
                    raise OrchestrationError("API_JUDGE_CONFIG_INVALID", "not frozen")
                if frozen_api_runtime is None:
                    frozen_api_runtime = current_api_runtime
                elif frozen_api_runtime != current_api_runtime:
                    raise OrchestrationError("API_JUDGE_CONFIG_MISMATCH")
                prompt_path = None
                prompt_sha256 = None
                initial_phase = "API_READY"
            elif grading_type == "automated":
                prompt_path = None
                prompt_sha256 = None
                initial_phase = "RULES_READY"
            else:
                prompt_path = staging / "prompts" / f"{task_id}.md"
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(
                    _prompt_text(
                        task_id,
                        attempt_id,
                        judge,
                        grading_type,
                        validation,
                        score_skill,
                    ),
                    encoding="utf-8",
                    newline="\n",
                )
                prompt_sha256 = _sha256_file(prompt_path)
                initial_phase = (
                    "RULES_READY" if grading_type == "hybrid" else "AWAITING_PROJECT"
                )
            tasks.append(
                {
                    **common_task,
                    "grading_type": grading_type,
                    "scoring_attempt_id": attempt_id,
                    "attempt_path": attempt_root.relative_to(staging).as_posix(),
                    "attempt_manifest_sha256": _sha256_file(
                        attempt_root / "attempt-manifest.json"
                    ),
                    "prompt_path": (
                        prompt_path.relative_to(staging).as_posix()
                        if prompt_path is not None
                        else None
                    ),
                    "prompt_sha256": prompt_sha256,
                    "phase": initial_phase,
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
            "kind": "initial",
            "orchestration_id": orchestration_id,
            "created_at": _timestamp(created),
            "updated_at": _timestamp(created),
            "status": "RUNNING",
            "identity": identity,
            "judge": {
                **judge,
                **(
                    {"api_runtime": frozen_api_runtime}
                    if frozen_api_runtime is not None
                    else {}
                ),
            },
            "validation": validation,
            "prompt_protocol": (
                API_PROMPT_PROTOCOL
                if judge["protocol"] == "api-judge-v1"
                else PROMPT_PROTOCOL
            ),
            "score_timeout_seconds": score_timeout_seconds,
            "score_slots": score_slots,
            "score_skill": score_skill,
            "sources": {
                "unit_manifest_sha256": _sha256_file(unit_root / "manifest.json"),
                "report_config_sha256": _sha256_file(report_config),
                "scoring_package_sha256": _sha256_file(scoring_package),
                "api_runtime_config_sha256": (
                    _sha256_file(api_runtime_config)
                    if api_runtime_config is not None
                    else None
                ),
            },
            "tasks": tasks,
            "submission": None,
            "submission_replacements": [],
        }
        state["queue_digest"] = _queue_digest(state)
        _write_new_json(staging / "orchestration-state.json", state)
        os.replace(staging, final_root)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return status(final_root, now=created)


def initialize_rescore(
    *,
    source_orchestration_root: Path,
    report_config: Path,
    score_skill_dir: Path,
    output_root: Path,
    orchestration_id: str,
    task_ids: Sequence[str] = (),
    api_runtime_config: Path | None = None,
    acceptance_id: str | None = None,
    score_timeout_seconds: int = 7200,
    score_slots: int = DEFAULT_SCORE_SLOTS,
    now: datetime | None = None,
) -> dict[str, Any]:
    if score_timeout_seconds < 1:
        raise OrchestrationError("SCORE_TIMEOUT_INVALID")
    if not 1 <= score_slots <= MAX_SCORE_SLOTS:
        raise OrchestrationError(
            "SCORE_SLOTS_UNSUPPORTED", f"expected 1..{MAX_SCORE_SLOTS}"
        )
    orchestration_id = _identifier(orchestration_id, "orchestration_id")
    source_root = _state_root(source_orchestration_root)
    source_state = _verify_state(source_root)
    if _state_status(source_state) not in {"COMPLETED", "COMPLETED_WITH_FAILURES"}:
        raise OrchestrationError("RESCORE_SOURCE_NOT_TERMINAL")
    if source_state.get("submission") is None:
        raise OrchestrationError("RESCORE_SOURCE_SUBMISSION_REQUIRED")
    report_config = _regular_file(report_config, "REPORT_CONFIG_INVALID")
    identity, judge = _load_rescore_judge(report_config, source_state)
    validation = _validation_marker(acceptance_id)
    if validation is not None and judge["protocol"] != "codex-agent-judge-v1":
        raise OrchestrationError("ACCEPTANCE_MODE_REQUIRES_CODEX_JUDGE")
    score_skill = _score_skill_lock(score_skill_dir)
    source_tasks = source_state["tasks"]
    available = [
        task["task_id"]
        for task in source_tasks
        if task.get("phase") == "SCORE_RECORDED"
    ]
    selected = list(task_ids) if task_ids else available
    if (
        not selected
        or len(selected) != len(set(selected))
        or any(task_id not in available for task_id in selected)
    ):
        raise OrchestrationError("RESCORE_TASK_SELECTION_INVALID", repr(selected))
    selected_set = set(selected)
    selected = [
        task["task_id"] for task in source_tasks if task["task_id"] in selected_set
    ]
    if judge["protocol"] == "api-judge-v1":
        if api_runtime_config is None:
            raise OrchestrationError("API_JUDGE_CONFIG_REQUIRED")
        api_runtime_config = _regular_file(
            api_runtime_config, "API_JUDGE_CONFIG_INVALID"
        )
    elif api_runtime_config is not None:
        raise OrchestrationError("API_JUDGE_CONFIG_UNEXPECTED")

    final_root = output_root.expanduser().resolve() / orchestration_id
    if final_root.exists():
        raise OrchestrationError("ORCHESTRATION_EXISTS", str(final_root))
    final_root.parent.mkdir(parents=True, exist_ok=True)
    staging = final_root.parent / f".{orchestration_id}.staging-{uuid.uuid4().hex}"
    staging.mkdir(parents=False, exist_ok=False)
    created = now or _now()
    tasks: list[dict[str, Any]] = []
    frozen_api_runtime: dict[str, Any] | None = None
    source_state_path = source_root / "orchestration-state.json"
    source_submission_path = source_root / "submission.json"
    try:
        for index, task_id in enumerate(selected):
            source_task = _task_by_id(source_state, task_id)
            source_attempt_value = source_task.get("attempt_path")
            if not isinstance(source_attempt_value, str):
                raise OrchestrationError("RESCORE_SOURCE_ATTEMPT_MISSING", task_id)
            source_attempt = _regular_directory(
                source_root / source_attempt_value, "RESCORE_SOURCE_ATTEMPT_MISSING"
            )
            source_score = source_task.get("score")
            if not isinstance(source_score, dict):
                raise OrchestrationError("RESCORE_SOURCE_SCORE_MISSING", task_id)
            _run_score_command(
                source_state["score_skill"],
                ["verify-score", "--attempt-root", str(source_attempt)],
            )
            frozen_record = staging / "execution-records" / f"{task_id}.json"
            frozen_record.parent.mkdir(parents=True, exist_ok=True)
            source_record = source_root / source_task["execution_record_path"]
            shutil.copyfile(source_record, frozen_record)
            if _sha256_file(frozen_record) != source_task["execution_record_sha256"]:
                raise OrchestrationError("EXECUTION_RECORD_COPY_MISMATCH", task_id)

            attempt_id = f"{orchestration_id}-{index + 1:03d}"
            prepare_arguments = [
                "prepare-rescore",
                "--source-attempt-root",
                str(source_attempt),
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
            ]
            if api_runtime_config is not None:
                prepare_arguments.extend(
                    ["--api-runtime-config", str(api_runtime_config)]
                )
            if validation is not None:
                prepare_arguments.extend(
                    ["--acceptance-id", validation["acceptance_id"]]
                )
            result = _run_score_command(score_skill, prepare_arguments)
            attempt_root = Path(result["attempt_root"]).resolve(strict=True)
            if not _inside(staging, attempt_root):
                raise OrchestrationError("ATTEMPT_PATH_ESCAPE", str(attempt_root))
            attempt_manifest = _read_json(
                attempt_root / "attempt-manifest.json", "ATTEMPT_MANIFEST_INVALID"
            )
            attempt_judge = attempt_manifest.get("judge")
            grading_type = (attempt_manifest.get("grading") or {}).get("type")
            if grading_type not in {"automated", "hybrid", "llm_judge"}:
                raise OrchestrationError("GRADING_TYPE_INVALID", str(grading_type))
            if not isinstance(attempt_judge, dict):
                raise OrchestrationError("JUDGE_CONFIG_INVALID", "attempt manifest")
            current_api_runtime = attempt_judge.get("api_runtime")
            if judge["protocol"] == "api-judge-v1":
                if not isinstance(current_api_runtime, dict):
                    raise OrchestrationError("API_JUDGE_CONFIG_INVALID", "not frozen")
                if frozen_api_runtime is None:
                    frozen_api_runtime = current_api_runtime
                elif frozen_api_runtime != current_api_runtime:
                    raise OrchestrationError("API_JUDGE_CONFIG_MISMATCH")
                prompt_path = None
                prompt_sha256 = None
                initial_phase = "API_READY"
            elif grading_type == "automated":
                prompt_path = None
                prompt_sha256 = None
                initial_phase = "RULES_READY"
            else:
                prompt_path = staging / "prompts" / f"{task_id}.md"
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(
                    _prompt_text(
                        task_id,
                        attempt_id,
                        judge,
                        grading_type,
                        validation,
                        score_skill,
                    ),
                    encoding="utf-8",
                    newline="\n",
                )
                prompt_sha256 = _sha256_file(prompt_path)
                initial_phase = (
                    "RULES_READY" if grading_type == "hybrid" else "AWAITING_PROJECT"
                )
            tasks.append(
                {
                    "task_id": task_id,
                    "order": index,
                    "grading_type": grading_type,
                    "execution": dict(source_task["execution"]),
                    "execution_record_path": frozen_record.relative_to(staging).as_posix(),
                    "execution_record_sha256": source_task["execution_record_sha256"],
                    "source": {
                        "orchestration_id": source_state["orchestration_id"],
                        "scoring_attempt_id": source_task["scoring_attempt_id"],
                        "attempt_manifest_sha256": source_task["attempt_manifest_sha256"],
                        "score_sha256": source_score["sha256"],
                        "score_valid": source_score["valid"],
                    },
                    "scoring_attempt_id": attempt_id,
                    "attempt_path": attempt_root.relative_to(staging).as_posix(),
                    "attempt_manifest_sha256": _sha256_file(
                        attempt_root / "attempt-manifest.json"
                    ),
                    "prompt_path": (
                        prompt_path.relative_to(staging).as_posix()
                        if prompt_path is not None
                        else None
                    ),
                    "prompt_sha256": prompt_sha256,
                    "project": None,
                    "preflight": None,
                    "thread": None,
                    "score": None,
                    "phase": initial_phase,
                    "history": [
                        {
                            "at": _timestamp(created),
                            "event": "RESCORE_ATTEMPT_PREPARED",
                            "source_scoring_attempt_id": source_task[
                                "scoring_attempt_id"
                            ],
                        }
                    ],
                }
            )
        state: dict[str, Any] = {
            "schema_version": STATE_SCHEMA,
            "revision": STATE_REVISION,
            "kind": "rescore",
            "orchestration_id": orchestration_id,
            "created_at": _timestamp(created),
            "updated_at": _timestamp(created),
            "status": "RUNNING",
            "identity": identity,
            "judge": {
                **judge,
                **(
                    {"api_runtime": frozen_api_runtime}
                    if frozen_api_runtime is not None
                    else {}
                ),
            },
            "validation": validation,
            "prompt_protocol": (
                API_PROMPT_PROTOCOL
                if judge["protocol"] == "api-judge-v1"
                else PROMPT_PROTOCOL
            ),
            "score_timeout_seconds": score_timeout_seconds,
            "score_slots": score_slots,
            "score_skill": score_skill,
            "sources": {
                "source_orchestration_id": source_state["orchestration_id"],
                "source_state_sha256": _sha256_file(source_state_path),
                "source_submission_sha256": _sha256_file(source_submission_path),
                "report_config_sha256": _sha256_file(report_config),
                "api_runtime_config_sha256": (
                    _sha256_file(api_runtime_config)
                    if api_runtime_config is not None
                    else None
                ),
            },
            "tasks": tasks,
            "submission": None,
            "submission_replacements": [],
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


def _semantic_active_tasks(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    slots = int(state.get("score_slots", 0))
    candidates = [
        task
        for task in state.get("tasks", [])
        if task.get("grading_type") != "automated"
        and task.get("phase") not in TERMINAL_PHASES | RULE_PHASES
    ]
    return candidates[:slots]


def _active_task(state: Mapping[str, Any]) -> dict[str, Any] | None:
    active = _semantic_active_tasks(state)
    return active[0] if active else None


def _require_active(state: Mapping[str, Any], task_id: str) -> dict[str, Any]:
    task = _task_by_id(state, task_id)
    if task not in _semantic_active_tasks(state):
        raise OrchestrationError("TASK_NOT_ACTIVE", task_id)
    return task


def _verified_score_document(
    root: Path,
    state: Mapping[str, Any],
    task: Mapping[str, Any],
) -> tuple[dict[str, Any], Path]:
    attempt_value = task.get("attempt_path")
    if not isinstance(attempt_value, str):
        raise OrchestrationError("SCORE_ATTEMPT_MISSING", str(task.get("task_id")))
    attempt = (root / attempt_value).resolve(strict=True)
    verification = _run_score_command(
        state["score_skill"], ["verify-score", "--attempt-root", str(attempt)]
    )
    score_path = attempt / "score.json"
    score = _read_json(score_path, "SCORE_DOCUMENT_INVALID")
    _validate_contract(score, expected_schema_id=SCORE_SCHEMA)
    identity = score.get("identity")
    execution = score.get("execution")
    judge = score.get("judge")
    result = score.get("result")
    expected_identity = state.get("identity", {})
    task_execution = task.get("execution", {})
    if (
        not isinstance(identity, dict)
        or identity.get("batch_id") != expected_identity.get("batch_id")
        or identity.get("unit_id") != expected_identity.get("unit_id")
        or identity.get("task_id") != task.get("task_id")
        or identity.get("attempt_id") != task.get("scoring_attempt_id")
        or not isinstance(execution, dict)
        or execution.get("attempt_id") != task_execution.get("attempt_id")
        or execution.get("business_status") != task_execution.get("business_status")
        or execution.get("record_sha256") != task.get("execution_record_sha256")
        or not isinstance(judge, dict)
        or judge.get("protocol")
        not in {"codex-agent-judge-v1", "api-judge-v1", "not-required"}
        or not isinstance(result, dict)
        or not isinstance(result.get("valid"), bool)
        or verification.get("score_valid") is not result.get("valid")
    ):
        raise OrchestrationError(
            "SCORE_IDENTITY_MISMATCH", str(task.get("task_id"))
        )
    if result["valid"]:
        total = result.get("total_score")
        if isinstance(total, bool) or not isinstance(total, (int, float)):
            raise OrchestrationError(
                "SCORE_RESULT_INVALID", str(task.get("task_id"))
            )
    elif result.get("total_score") is not None:
        raise OrchestrationError(
            "SCORE_RESULT_INVALID", str(task.get("task_id"))
        )
    return score, score_path


def _submission_document(
    root: Path,
    state: Mapping[str, Any],
    *,
    created_at: str,
) -> dict[str, Any]:
    if any(task.get("phase") not in TERMINAL_PHASES for task in state["tasks"]):
        raise OrchestrationError("SUBMISSION_TASKS_NOT_TERMINAL")
    identity = state.get("identity")
    if not isinstance(identity, dict):
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "identity")
    dataset = identity.get("dataset")
    if not isinstance(dataset, dict):
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "dataset")
    dataset_document = {
        "id": _required_string(dataset.get("id"), "dataset.id"),
        "digest": _required_string(dataset.get("digest"), "dataset.digest"),
    }
    submission_tasks: list[dict[str, Any]] = []
    for task in state["tasks"]:
        execution = task["execution"]
        phase = task["phase"]
        if phase == "SCORE_RECORDED":
            score, score_path = _verified_score_document(root, state, task)
            result = score["result"]
            judge_protocol = score["judge"]["protocol"]
            semantic_catalog = (root / task["attempt_path"] / "semantic/evidence-catalog.json")
            evidence_sha = (
                _sha256_file(semantic_catalog)
                if semantic_catalog.is_file() and not semantic_catalog.is_symlink()
                else execution.get("evidence_sha256")
            )
            score_status = "valid" if result["valid"] else "evaluation_error"
            scoring_attempt_id = task["scoring_attempt_id"]
            score_relative = score_path.relative_to(root).as_posix()
            score_sha = _sha256_file(score_path)
        else:
            score_status = "unscored"
            scoring_attempt_id = None
            judge_protocol = None
            score_relative = None
            score_sha = None
            evidence_sha = execution.get("evidence_sha256")
        submission_tasks.append(
            {
                "task_id": task["task_id"],
                "execution_attempt_id": execution["attempt_id"],
                "execution_status": execution["business_status"],
                "scoring_attempt_id": scoring_attempt_id,
                "judge_protocol": judge_protocol,
                "score_status": score_status,
                "score_path": score_relative,
                "score_sha256": score_sha,
                "candidate_sha256": execution.get("candidate_sha256"),
                "evidence_sha256": evidence_sha,
            }
        )
    document = {
        "schema_id": SUBMISSION_SCHEMA,
        "schema_version": 1,
        "scope": {
            "batch_id": identity["batch_id"],
            "unit_id": identity["unit_id"],
        },
        "dataset": dataset_document,
        "created_at": created_at,
        "task_count": len(submission_tasks),
        "task_ids": [task["task_id"] for task in submission_tasks],
        "tasks": submission_tasks,
        "integrity": {
            "scope_matches": True,
            "identities_match": True,
            "hashes_verified": True,
            "valid": True,
        },
    }
    _validate_contract(document, expected_schema_id=SUBMISSION_SCHEMA)
    return document


def _late_completion_submission_recovery(
    root: Path,
    state: Mapping[str, Any],
    submission_document: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    created_at = _required_string(
        submission_document.get("created_at"), "submission.created_at"
    )
    submission_created_at = _parse_timestamp(created_at, "submission.created_at")
    previous_state = deepcopy(state)
    recovered_task_ids: list[str] = []
    for task in previous_state["tasks"]:
        late_events = [
            event
            for event in task.get("history", [])
            if isinstance(event, dict)
            and event.get("event") == "SCORE_RECORDED_LATE_COMPLETION"
            and _parse_timestamp(event.get("at"), "late completion event.at")
            > submission_created_at
        ]
        if not late_events:
            continue
        if len(late_events) != 1:
            raise OrchestrationError("SUBMISSION_CONTENT_MISMATCH")
        event = late_events[0]
        thread = task.get("thread")
        score = task.get("score")
        if (
            task.get("phase") != "SCORE_RECORDED"
            or not isinstance(thread, dict)
            or thread.get("status") != "COMPLETED"
            or not thread.get("timed_out_at")
            or not thread.get("finished_at")
            or not isinstance(score, dict)
            or event.get("valid") is not score.get("valid")
            or event.get("deadline_at") != thread.get("deadline_at")
            or event.get("timed_out_at") != thread.get("timed_out_at")
            or event.get("thread_finished_at") != thread.get("finished_at")
        ):
            raise OrchestrationError("SUBMISSION_CONTENT_MISMATCH")
        task["phase"] = "THREAD_FAILED"
        task["score"] = None
        recovered_task_ids.append(str(task["task_id"]))
    if not recovered_task_ids:
        raise OrchestrationError("SUBMISSION_CONTENT_MISMATCH")
    previous_document = _submission_document(
        root, previous_state, created_at=created_at
    )
    if submission_document != previous_document:
        raise OrchestrationError("SUBMISSION_CONTENT_MISMATCH")
    return previous_document, recovered_task_ids


def _verify_submission_replacements(
    root: Path,
    state: Mapping[str, Any],
) -> None:
    replacements = state.get("submission_replacements", [])
    if not isinstance(replacements, list):
        raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
    previous_replacement: Mapping[str, Any] | None = None
    known_task_ids = {str(task["task_id"]) for task in state["tasks"]}
    for index, replacement in enumerate(replacements):
        if (
            not isinstance(replacement, dict)
            or set(replacement)
            != {
                "event",
                "at",
                "recovered_task_ids",
                "previous",
                "replacement",
            }
            or replacement.get("event")
            != "SUBMISSION_REPLACED_AFTER_LATE_COMPLETION"
        ):
            raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
        _parse_timestamp(replacement.get("at"), f"submission replacement {index}.at")
        recovered_task_ids = replacement.get("recovered_task_ids")
        if (
            not isinstance(recovered_task_ids, list)
            or not recovered_task_ids
            or not all(isinstance(task_id, str) for task_id in recovered_task_ids)
            or len(recovered_task_ids) != len(set(recovered_task_ids))
            or any(task_id not in known_task_ids for task_id in recovered_task_ids)
        ):
            raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
        previous = replacement.get("previous")
        current = replacement.get("replacement")
        if not isinstance(previous, dict) or not isinstance(current, dict):
            raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
        for label, item in (("previous", previous), ("replacement", current)):
            if set(item) != {"path", "sha256", "created_at"}:
                raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
            if not isinstance(item.get("sha256"), str) or not SHA256_RE.fullmatch(
                str(item["sha256"])
            ):
                raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
            _parse_timestamp(
                item.get("created_at"),
                f"submission replacement {index}.{label}.created_at",
            )
        expected_archive = (
            Path("submission-history") / f"{previous['sha256']}.json"
        ).as_posix()
        archive = root / str(previous.get("path"))
        if (
            previous.get("path") != expected_archive
            or not _inside(root, archive.resolve())
            or archive.is_symlink()
            or not archive.is_file()
            or _sha256_file(archive) != previous.get("sha256")
        ):
            raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
        archived_document = _read_json(
            archive, "SUBMISSION_REPLACEMENT_AUDIT_INVALID"
        )
        _validate_contract(archived_document, expected_schema_id=SUBMISSION_SCHEMA)
        if archived_document.get("created_at") != previous.get("created_at"):
            raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
        if current.get("path") != "submission.json":
            raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
        if previous_replacement is not None and (
            previous.get("sha256") != previous_replacement.get("sha256")
            or previous.get("created_at")
            != previous_replacement.get("created_at")
        ):
            raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")
        previous_replacement = current
    submission = state.get("submission")
    if replacements and previous_replacement != submission:
        raise OrchestrationError("SUBMISSION_REPLACEMENT_AUDIT_INVALID")


def _verify_state(
    root: Path,
    *,
    allow_late_submission_recovery: bool = False,
) -> dict[str, Any]:
    state = _read_json(root / "orchestration-state.json", "ORCHESTRATION_STATE_INVALID")
    if state.get("schema_version") != STATE_SCHEMA or state.get("revision") != STATE_REVISION:
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "schema or revision")
    if state.get("kind") not in {"initial", "rescore"}:
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "kind")
    if "validation" not in state:
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "validation missing")
    validation = _validate_validation_marker(state.get("validation"))
    judge_protocol = state.get("judge", {}).get("protocol")
    prompt_protocol = state.get("prompt_protocol")
    expected_prompt_protocol = (
        prompt_protocol == API_PROMPT_PROTOCOL
        if judge_protocol == "api-judge-v1"
        else prompt_protocol in {*FROZEN_SKILL_PROMPT_PROTOCOLS, *LEGACY_CODEX_PROMPT_PROTOCOLS}
    )
    if (
        judge_protocol not in {"codex-agent-judge-v1", "api-judge-v1"}
        or not expected_prompt_protocol
        or validation is not None
        and judge_protocol != "codex-agent-judge-v1"
    ):
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "validation or prompt protocol")
    score_slots = state.get("score_slots")
    if (
        isinstance(score_slots, bool)
        or not isinstance(score_slots, int)
        or not 1 <= score_slots <= MAX_SCORE_SLOTS
    ):
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "score_slots")
    tasks = state.get("tasks")
    if not isinstance(tasks, list) or not tasks or not all(
        isinstance(task, dict) for task in tasks
    ):
        raise OrchestrationError("ORCHESTRATION_STATE_INVALID", "tasks")
    task_ids = [task.get("task_id") for task in tasks]
    if (
        not all(isinstance(task_id, str) and ID_RE.fullmatch(task_id) for task_id in task_ids)
        or len(task_ids) != len(set(task_ids))
        or [task.get("order") for task in tasks] != list(range(len(tasks)))
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
        record_value = task.get("execution_record_path")
        record = root / str(record_value)
        if (
            not isinstance(record_value, str)
            or not _inside(root, record.resolve())
            or record.is_symlink()
            or not record.is_file()
            or _sha256_file(record) != task.get("execution_record_sha256")
        ):
            raise OrchestrationError(
                "EXECUTION_RECORD_DRIFT", str(task.get("task_id"))
            )
        execution = task.get("execution")
        record_document = _read_json(record, "EXECUTION_RECORD_INVALID")
        record_identity = record_document.get("identity")
        record_execution = record_document.get("execution")
        record_candidate = record_document.get("candidate")
        if (
            not isinstance(execution, dict)
            or not isinstance(record_identity, dict)
            or record_identity.get("task_id") != task.get("task_id")
            or record_identity.get("batch_id") != state.get("identity", {}).get("batch_id")
            or record_identity.get("unit_id") != state.get("identity", {}).get("unit_id")
            or record_identity.get("attempt_id") != execution.get("attempt_id")
            or not isinstance(record_execution, dict)
            or record_execution.get("business_status")
            != execution.get("business_status")
            or (
                execution.get("candidate_sha256") is not None
                and (
                    not isinstance(record_candidate, dict)
                    or record_candidate.get("frozen_sha256")
                    != execution.get("candidate_sha256")
                )
            )
            or not isinstance(execution.get("scorable"), bool)
        ):
            raise OrchestrationError(
                "EXECUTION_RECORD_LOCK_MISMATCH", str(task.get("task_id"))
            )
        attempt_value = task.get("attempt_path")
        if attempt_value is None:
            if (
                task.get("phase") != "UNSCORED"
                or execution.get("scorable") is not False
                or task.get("scoring_attempt_id") is not None
                or task.get("attempt_manifest_sha256") is not None
                or task.get("prompt_path") is not None
                or task.get("prompt_sha256") is not None
                or task.get("project") is not None
                or task.get("thread") is not None
                or task.get("score") is not None
                or task.get("grading_type") is not None
            ):
                raise OrchestrationError(
                    "UNSCORED_TASK_INVALID", str(task.get("task_id"))
                )
            continue
        if not isinstance(attempt_value, str) or execution.get("scorable") is not True:
            raise OrchestrationError(
                "SCORING_ATTEMPT_STATE_INVALID", str(task.get("task_id"))
            )
        prompt_value = task.get("prompt_path")
        prompt = root / str(prompt_value) if prompt_value is not None else None
        attempt = root / attempt_value
        if (
            (prompt is not None and not _inside(root, prompt.resolve()))
            or not _inside(root, attempt.resolve())
        ):
            raise OrchestrationError("ORCHESTRATION_PATH_ESCAPE", str(task.get("task_id")))
        if prompt is None:
            prompt_not_required = (
                state.get("judge", {}).get("protocol") == "api-judge-v1"
                or task.get("grading_type") == "automated"
            )
            if not prompt_not_required or task.get("prompt_sha256") is not None:
                raise OrchestrationError("SCORING_PROMPT_DRIFT", str(task.get("task_id")))
        elif (
            prompt.is_symlink()
            or not prompt.is_file()
            or _sha256_file(prompt) != task.get("prompt_sha256")
            or prompt.read_text(encoding="utf-8")
            != _prompt_text(
                str(task.get("task_id")),
                str(task.get("scoring_attempt_id")),
                state["judge"],
                str(task.get("grading_type")),
                validation,
                state["score_skill"],
                prompt_protocol=str(state.get("prompt_protocol")),
            )
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
        manifest_document = _read_json(manifest, "ATTEMPT_MANIFEST_INVALID")
        manifest_identity = manifest_document.get("identity")
        manifest_judge = manifest_document.get("judge")
        manifest_grading_type = (manifest_document.get("grading") or {}).get("type")
        expected_judge = state.get("judge", {})
        if (
            not isinstance(manifest_identity, dict)
            or manifest_identity.get("batch_id") != state.get("identity", {}).get("batch_id")
            or manifest_identity.get("unit_id") != state.get("identity", {}).get("unit_id")
            or manifest_identity.get("task_id") != task.get("task_id")
            or manifest_identity.get("execution_attempt_id") != execution.get("attempt_id")
            or manifest_identity.get("scoring_attempt_id") != task.get("scoring_attempt_id")
            or manifest_grading_type != task.get("grading_type")
            or manifest_document.get("validation") != validation
            or not isinstance(manifest_judge, dict)
            or manifest_judge.get("protocol") != expected_judge.get("protocol")
            or manifest_judge.get("model") != expected_judge.get("model")
            or manifest_judge.get("reasoning_effort")
            != expected_judge.get("reasoning_effort")
        ):
            raise OrchestrationError(
                "SCORING_ATTEMPT_IDENTITY_MISMATCH", str(task.get("task_id"))
            )
        source = task.get("source")
        lineage = manifest_document.get("lineage")
        if state.get("kind") == "rescore":
            if (
                not isinstance(source, dict)
                or not isinstance(lineage, dict)
                or lineage.get("kind") != "rescore"
                or lineage.get("source_scoring_attempt_id")
                != source.get("scoring_attempt_id")
                or lineage.get("source_attempt_manifest_sha256")
                != source.get("attempt_manifest_sha256")
                or lineage.get("source_score_sha256") != source.get("score_sha256")
                or lineage.get("source_score_valid") != source.get("score_valid")
                or lineage.get("source_candidate_sha256")
                != execution.get("candidate_sha256")
            ):
                raise OrchestrationError(
                    "RESCORE_LINEAGE_MISMATCH", str(task.get("task_id"))
                )
        elif source is not None or lineage is not None:
            raise OrchestrationError(
                "INITIAL_LINEAGE_UNEXPECTED", str(task.get("task_id"))
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
            score_document, verified_score_path = _verified_score_document(
                root, state, task
            )
            result = score_document["result"]
            if (
                task.get("phase") != "SCORE_RECORDED"
                or verified_score_path != score_path
                or score.get("valid") is not result.get("valid")
                or score.get("total_score") != result.get("total_score")
            ):
                raise OrchestrationError(
                    "SCORE_STATE_MISMATCH", str(task.get("task_id"))
                )
        elif task.get("phase") == "SCORE_RECORDED":
            raise OrchestrationError(
                "SCORE_STATE_MISSING", str(task.get("task_id"))
            )
    submission = state.get("submission")
    if submission is not None:
        if not isinstance(submission, dict):
            raise OrchestrationError("SUBMISSION_STATE_INVALID")
        submission_path = root / str(submission.get("path", ""))
        if (
            submission_path != root / "submission.json"
            or submission_path.is_symlink()
            or not submission_path.is_file()
            or _sha256_file(submission_path) != submission.get("sha256")
        ):
            raise OrchestrationError("SUBMISSION_DRIFT")
        submission_document = _read_json(
            submission_path, "SUBMISSION_DOCUMENT_INVALID"
        )
        _validate_contract(
            submission_document, expected_schema_id=SUBMISSION_SCHEMA
        )
        created_at = submission_document.get("created_at")
        if created_at != submission.get("created_at"):
            raise OrchestrationError("SUBMISSION_STATE_INVALID", "created_at")
        expected_submission = _submission_document(
            root, state, created_at=_required_string(created_at, "submission.created_at")
        )
        if submission_document != expected_submission:
            if allow_late_submission_recovery:
                _late_completion_submission_recovery(
                    root, state, submission_document
                )
            else:
                raise OrchestrationError("SUBMISSION_CONTENT_MISMATCH")
    _verify_submission_replacements(root, state)
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
    rule_task = next(
        (task for task in state.get("tasks", []) if task.get("phase") in RULE_PHASES),
        None,
    )
    active_tasks = _semantic_active_tasks(state)
    automated_verification_tasks = [
        task
        for task in state.get("tasks", [])
        if task.get("grading_type") == "automated"
        and task.get("phase") == "SCORE_VERIFICATION_PENDING"
    ]
    if rule_task is None and not active_tasks and not automated_verification_tasks:
        if state.get("submission") is None:
            return [
                {
                    "action": "BUILD_SUBMISSION",
                    "command": [
                        "build-submission",
                        "--orchestration-root",
                        str(root),
                    ],
                }
            ]
        return []
    actions: list[dict[str, Any]] = []
    if rule_task is not None:
        actions.append(
            {
                "action": "RUN_RULE_COMPONENT",
                "task_id": rule_task["task_id"],
                "attempt_path": str((root / rule_task["attempt_path"]).resolve()),
                "resume": rule_task["phase"] != "RULES_READY",
                "grading_type": rule_task["grading_type"],
            }
        )
    for task in automated_verification_tasks:
        actions.extend(_recommended_actions_for_task(root, state, task, now))
    for task in active_tasks:
        actions.extend(_recommended_actions_for_task(root, state, task, now))
    return actions


def _recommended_actions_for_task(
    root: Path,
    state: Mapping[str, Any],
    task: Mapping[str, Any],
    now: datetime,
) -> list[dict[str, Any]]:
    task_id = task["task_id"]
    attempt = str((root / task["attempt_path"]).resolve())
    phase = task["phase"]
    if phase in {"API_READY", "API_RUNNING"}:
        return [
            {
                "action": "RUN_API_SCORE",
                "task_id": task_id,
                "attempt_path": attempt,
                "resume": phase == "API_RUNNING",
                "command": [
                    "run-api-score",
                    "--orchestration-root",
                    str(root),
                    "--task-id",
                    task_id,
                ],
            }
        ]
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
    terminal_count = sum(
        task.get("phase") in TERMINAL_PHASES for task in state["tasks"]
    )
    valid_score_count = sum(
        task.get("phase") == "SCORE_RECORDED"
        and (task.get("score") or {}).get("valid") is True
        for task in state["tasks"]
    )
    evaluation_error_count = sum(
        task.get("phase") == "SCORE_RECORDED"
        and (task.get("score") or {}).get("valid") is False
        for task in state["tasks"]
    )
    unscored_count = sum(
        task.get("phase") in {"THREAD_FAILED", "UNSCORED"}
        for task in state["tasks"]
    )
    return {
        "status": status_value,
        "orchestration_root": str(root),
        "orchestration_id": state["orchestration_id"],
        "queue_digest": state["queue_digest"],
        "judge": state["judge"],
        "validation": state["validation"],
        "score_slots": state["score_slots"],
        "task_count": len(state["tasks"]),
        "terminal_count": terminal_count,
        "completed_count": sum(
            task.get("phase") == "SCORE_RECORDED" for task in state["tasks"]
        ),
        "valid_score_count": valid_score_count,
        "evaluation_error_count": evaluation_error_count,
        "unscored_count": unscored_count,
        "failed_count": unscored_count,
        "submission_path": (
            str((root / state["submission"]["path"]).resolve())
            if state.get("submission") is not None
            else None
        ),
        "submission_replacement_count": len(
            state.get("submission_replacements", [])
        ),
        "tasks": [
            {
                "task_id": task["task_id"],
                "phase": task["phase"],
                "scoring_attempt_id": task["scoring_attempt_id"],
                "attempt_path": (
                    str((root / task["attempt_path"]).resolve())
                    if task.get("attempt_path") is not None
                    else None
                ),
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


def build_submission(
    orchestration_root: Path,
    *,
    replace_after_late_completion: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(
        root,
        allow_late_submission_recovery=replace_after_late_completion,
    )
    if any(task.get("phase") not in TERMINAL_PHASES for task in state["tasks"]):
        raise OrchestrationError("SUBMISSION_TASKS_NOT_TERMINAL")
    if state.get("submission") is not None:
        if not replace_after_late_completion:
            return _public_view(root, state, now or _now())
        destination = root / "submission.json"
        previous_metadata = state["submission"]
        previous_document = _read_json(
            destination, "SUBMISSION_DOCUMENT_INVALID"
        )
        current_document = _submission_document(
            root,
            state,
            created_at=_required_string(
                previous_metadata.get("created_at"), "submission.created_at"
            ),
        )
        if previous_document == current_document:
            return _public_view(root, state, now or _now())
        _, recovered_task_ids = _late_completion_submission_recovery(
            root, state, previous_document
        )
        previous_sha = _required_string(
            previous_metadata.get("sha256"), "submission.sha256"
        )
        archive = root / "submission-history" / f"{previous_sha}.json"
        archive.parent.mkdir(parents=True, exist_ok=True)
        if archive.exists() or archive.is_symlink():
            if (
                archive.is_symlink()
                or not archive.is_file()
                or _sha256_file(archive) != previous_sha
            ):
                raise OrchestrationError(
                    "SUBMISSION_ARCHIVE_CONFLICT", str(archive)
                )
        else:
            _write_new_json(archive, previous_document)
            if _sha256_file(archive) != previous_sha:
                raise OrchestrationError("SUBMISSION_ARCHIVE_MISMATCH")
        event_time = now or _now()
        created_at = _timestamp(event_time)
        replacement_document = _submission_document(
            root, state, created_at=created_at
        )
        _atomic_write_json(destination, replacement_document)
        replacement_metadata = {
            "path": destination.relative_to(root).as_posix(),
            "sha256": _sha256_file(destination),
            "created_at": created_at,
        }
        audit = {
            "event": "SUBMISSION_REPLACED_AFTER_LATE_COMPLETION",
            "at": created_at,
            "recovered_task_ids": recovered_task_ids,
            "previous": {
                "path": archive.relative_to(root).as_posix(),
                "sha256": previous_sha,
                "created_at": previous_metadata["created_at"],
            },
            "replacement": replacement_metadata,
        }
        state.setdefault("submission_replacements", []).append(audit)
        state["submission"] = replacement_metadata
        result = _save(root, state, event_time)
        result["submission_replacement"] = audit
        return result
    destination = root / "submission.json"
    if destination.exists() or destination.is_symlink():
        raise OrchestrationError("SUBMISSION_OUTPUT_CONFLICT", str(destination))
    event_time = now or _now()
    created_at = _timestamp(event_time)
    document = _submission_document(root, state, created_at=created_at)
    _write_new_json(destination, document)
    state["submission"] = {
        "path": destination.relative_to(root).as_posix(),
        "sha256": _sha256_file(destination),
        "created_at": created_at,
    }
    return _save(root, state, event_time)


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
    allow_late_completion: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    task_id = _identifier(task_id, "task_id")
    task = _task_by_id(state, task_id)
    late_completion = False
    if task.get("grading_type") != "automated":
        if (
            allow_late_completion
            and task.get("phase") == "THREAD_FAILED"
            and isinstance(task.get("thread"), dict)
            and task["thread"].get("status") == "COMPLETED"
            and task["thread"].get("timed_out_at")
        ):
            late_completion = True
        else:
            task = _require_active(state, task_id)
    if task.get("phase") != "SCORE_VERIFICATION_PENDING" and not late_completion:
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
            "event": (
                "SCORE_RECORDED_LATE_COMPLETION"
                if late_completion
                else "SCORE_RECORDED"
            ),
            "valid": score["result"]["valid"],
            **(
                {
                    "deadline_at": task["thread"].get("deadline_at"),
                    "timed_out_at": task["thread"].get("timed_out_at"),
                    "thread_finished_at": task["thread"].get("finished_at"),
                }
                if late_completion
                else {}
            ),
        }
    )
    return _save(root, state, event_time)


def run_rule_score_task(
    orchestration_root: Path,
    *,
    task_id: str,
    runtime_python: Path,
    rule_timeout_seconds: float = 120.0,
    playwright_browsers_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    task = _task_by_id(state, _identifier(task_id, "task_id"))
    grading_type = task.get("grading_type")
    if grading_type not in {"automated", "hybrid"}:
        raise OrchestrationError("RULE_COMPONENT_NOT_REQUIRED", task_id)
    if task.get("phase") not in RULE_PHASES:
        raise OrchestrationError("RULE_COMPONENT_NOT_EXPECTED", task_id)
    event_time = now or _now()
    attempt = (root / task["attempt_path"]).resolve(strict=True)
    if task["phase"] == "RULES_READY":
        task["phase"] = "RULES_RUNNING"
        task["history"].append(
            {"at": _timestamp(event_time), "event": "RULE_COMPONENT_STARTED"}
        )
        _save(root, state, event_time)
    rule_component = attempt / "rule-component.json"
    if not rule_component.is_file():
        arguments = [
            "run-rules",
            "--attempt-root",
            str(attempt),
            "--runtime-python",
            str(runtime_python),
            "--timeout-seconds",
            str(rule_timeout_seconds),
        ]
        if playwright_browsers_path is not None:
            arguments.extend(
                ["--playwright-browsers-path", str(playwright_browsers_path)]
            )
        try:
            _run_score_command(state["score_skill"], arguments)
        except BaseException as exc:
            task["phase"] = "RULES_NEEDS_ATTENTION"
            task["history"].append(
                {
                    "at": _timestamp(event_time),
                    "event": "RULE_COMPONENT_FAILED",
                    "error": str(exc),
                }
            )
            _save(root, state, event_time)
            raise
    _run_score_command(state["score_skill"], ["verify", "--attempt-root", str(attempt)])
    task["history"].append(
        {"at": _timestamp(event_time), "event": "RULE_COMPONENT_RECORDED"}
    )
    if grading_type == "hybrid":
        task["phase"] = "AWAITING_PROJECT"
        return _save(root, state, event_time)

    semantic_audit = attempt / "semantic/semantic-audit.json"
    if not semantic_audit.is_file():
        _run_score_command(
            state["score_skill"], ["prepare-semantics", "--attempt-root", str(attempt)]
        )
    score_path = attempt / "score.json"
    if not score_path.is_file():
        _run_score_command(state["score_skill"], ["finalize", "--attempt-root", str(attempt)])
    task["phase"] = "SCORE_VERIFICATION_PENDING"
    _save(root, state, event_time)
    return record_score(root, task_id=task_id, now=event_time)


def run_api_score_task(
    orchestration_root: Path,
    *,
    task_id: str,
    runtime_python: Path | None = None,
    rule_timeout_seconds: float = 120.0,
    playwright_browsers_path: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = _state_root(orchestration_root)
    state = _verify_state(root)
    if state.get("judge", {}).get("protocol") != "api-judge-v1":
        raise OrchestrationError("API_JUDGE_PROTOCOL_REQUIRED")
    task = _require_active(state, _identifier(task_id, "task_id"))
    if task.get("phase") not in {"API_READY", "API_RUNNING"}:
        raise OrchestrationError("API_SCORE_NOT_EXPECTED", task_id)
    event_time = now or _now()
    if task["phase"] == "API_READY":
        task["phase"] = "API_RUNNING"
        task["history"].append(
            {"at": _timestamp(event_time), "event": "API_SCORE_STARTED"}
        )
        _save(root, state, event_time)
    attempt = (root / task["attempt_path"]).resolve(strict=True)
    arguments = ["run-api-score", "--attempt-root", str(attempt)]
    if runtime_python is not None:
        arguments.extend(["--runtime-python", str(runtime_python)])
    arguments.extend(["--timeout-seconds", str(rule_timeout_seconds)])
    if playwright_browsers_path is not None:
        arguments.extend(
            ["--playwright-browsers-path", str(playwright_browsers_path)]
        )
    runtime = state["judge"].get("api_runtime")
    if not isinstance(runtime, dict):
        raise OrchestrationError("API_JUDGE_CONFIG_INVALID", "runtime missing")
    result = _run_score_command(
        state["score_skill"],
        arguments,
        credential_env=_required_string(
            runtime.get("credential_env"), "api credential_env"
        ),
    )
    if not isinstance(result.get("score_valid"), bool):
        raise OrchestrationError("SCORE_SKILL_OUTPUT_INVALID", "score_valid")
    task["phase"] = "SCORE_VERIFICATION_PENDING"
    task["history"].append(
        {
            "at": _timestamp(event_time),
            "event": "API_SCORE_COMMAND_COMPLETED",
            "score_valid": result["score_valid"],
        }
    )
    _save(root, state, event_time)
    return record_score(root, task_id=task_id, now=event_time)


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
    init.add_argument("--api-runtime-config", type=Path)
    init.add_argument("--acceptance-id")
    init.add_argument("--score-timeout-seconds", type=int, default=7200)
    init.add_argument("--score-slots", type=int, default=DEFAULT_SCORE_SLOTS)

    init_rescore = subparsers.add_parser("init-rescore")
    init_rescore.add_argument(
        "--source-orchestration-root", required=True, type=Path
    )
    init_rescore.add_argument("--report-config", required=True, type=Path)
    init_rescore.add_argument("--score-skill-dir", required=True, type=Path)
    init_rescore.add_argument("--output-root", required=True, type=Path)
    init_rescore.add_argument("--orchestration-id", required=True)
    init_rescore.add_argument("--task-id", action="append", default=[])
    init_rescore.add_argument("--api-runtime-config", type=Path)
    init_rescore.add_argument("--acceptance-id")
    init_rescore.add_argument("--score-timeout-seconds", type=int, default=7200)
    init_rescore.add_argument("--score-slots", type=int, default=DEFAULT_SCORE_SLOTS)

    for name in ("status", "resume"):
        _parse_common(subparsers.add_parser(name))

    build = subparsers.add_parser("build-submission")
    _parse_common(build)
    build.add_argument("--replace-after-late-completion", action="store_true")

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
    score.add_argument(
        "--allow-late-completion",
        action="store_true",
        help=(
            "已确认线程最终为 COMPLETED 时，忽略编排 deadline 仅登记已验证 score；"
            "保留迟到审计，不适用于未知线程终态"
        ),
    )

    rule_score = subparsers.add_parser("run-rule-score")
    _parse_common(rule_score)
    rule_score.add_argument("--task-id", required=True)
    rule_score.add_argument("--runtime-python", required=True, type=Path)
    rule_score.add_argument("--rule-timeout-seconds", type=float, default=120.0)
    rule_score.add_argument("--playwright-browsers-path", type=Path)

    api_score = subparsers.add_parser("run-api-score")
    _parse_common(api_score)
    api_score.add_argument("--task-id", required=True)
    api_score.add_argument("--runtime-python", type=Path)
    api_score.add_argument("--rule-timeout-seconds", type=float, default=120.0)
    api_score.add_argument("--playwright-browsers-path", type=Path)

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
                api_runtime_config=args.api_runtime_config,
                acceptance_id=args.acceptance_id,
                score_timeout_seconds=args.score_timeout_seconds,
                score_slots=args.score_slots,
            )
        elif args.command == "init-rescore":
            result = initialize_rescore(
                source_orchestration_root=args.source_orchestration_root,
                report_config=args.report_config,
                score_skill_dir=args.score_skill_dir,
                output_root=args.output_root,
                orchestration_id=args.orchestration_id,
                task_ids=args.task_id,
                api_runtime_config=args.api_runtime_config,
                acceptance_id=args.acceptance_id,
                score_timeout_seconds=args.score_timeout_seconds,
                score_slots=args.score_slots,
            )
        elif args.command in {"status", "resume"}:
            result = status(args.orchestration_root)
        elif args.command == "build-submission":
            result = build_submission(
                args.orchestration_root,
                replace_after_late_completion=args.replace_after_late_completion,
            )
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
        elif args.command == "record-score":
            result = record_score(
                args.orchestration_root,
                task_id=args.task_id,
                allow_late_completion=args.allow_late_completion,
            )
        elif args.command == "run-rule-score":
            result = run_rule_score_task(
                args.orchestration_root,
                task_id=args.task_id,
                runtime_python=args.runtime_python,
                rule_timeout_seconds=args.rule_timeout_seconds,
                playwright_browsers_path=args.playwright_browsers_path,
            )
        elif args.command == "run-api-score":
            result = run_api_score_task(
                args.orchestration_root,
                task_id=args.task_id,
                runtime_python=args.runtime_python,
                rule_timeout_seconds=args.rule_timeout_seconds,
                playwright_browsers_path=args.playwright_browsers_path,
            )
        else:
            raise OrchestrationError("COMMAND_UNSUPPORTED", str(args.command))
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
