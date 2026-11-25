"""Versioned execution contracts shared by scripts, Skills and platform adapters."""

from __future__ import annotations

from . import preprocessing

from collections import Counter
from datetime import datetime
import json
import os
from pathlib import Path
import socket
from urllib.parse import urlsplit

from .common import E2EError, digest, file_sha256, inside, read_json
from .preparation import (
    canonical_script,
    normalize_plan,
    _general_catalog,
    _current_general,
    _web_catalog,
    _select,
    _revision,
)

API_VERSION = 1
TERMINAL_PHASES = {"COMPLETED", "FAILED", "CANCELLED"}


def envelope(kind: str, data: dict) -> dict:
    return {
        "schema": "wildclawbench.e2e-api/v1",
        "api_version": API_VERSION,
        "type": kind,
        "data": data,
    }


def profiles() -> list[dict]:
    """Operators may publish template/model metadata with the executor release."""
    source = os.environ.get("WCB_E2E_CAPABILITIES_FILE")
    from .controller_catalog import default_profiles
    values = read_json(Path(source))["profiles"] if source else default_profiles()
    from .backend import DRIVERS

    result = []
    for value in values:
        row = dict(value)
        if not all(
            row.get(key)
            for key in (
                "id",
                "harness",
                "template",
                "models",
                "reasoning_efforts",
                "scenarios",
            )
        ):
            raise E2EError("EXECUTOR_PROFILE_INVALID")
        if "chatgpt_scoring_auth" in row and (
            row["harness"] != "chatgpt-desktop"
            or row["chatgpt_scoring_auth"] not in ("gateway", "subscription")
        ):
            raise E2EError("CHATGPT_SCORING_AUTH_PROFILE_INVALID")
        row["enabled"] = bool(
            row.get("enabled", True)
            and (row.get("backend", "agentcube"), row["harness"]) in DRIVERS
        )
        result.append(row)
    return result


def describe(repo: Path) -> dict:
    return {
        "supported_api_versions": [API_VERSION],
        "engine_revision": _revision(repo),
        "capabilities": [
            "catalog",
            "case-library-v1",
            "managed-agentcube-templates-v1",
            "preflight",
            "runtime-preflight",
            "workbuddy-permission",
            "environment-status",
            "windows-astudio-runtime-bootstrap",
            preprocessing.CAPABILITY,
            preprocessing.PROMPT_CAPABILITY,
            "windows-preprocess-validation",
            "managed-preprocess-validation-template-v1",
            "execution",
            "case-round-rerun-v1",
            "failed-sandbox-retention-v1",
            "execution-version-history-v1",
            "versioned-result-export-v1",
            "events",
            "artifacts",
            "resume",
            "creation-reconciliation",
            "cancel",
            "restore",
            "offline-export",
            "offline-parent-report-inputs",
            "headless-general-scoring",
            "agentcube-desktop-scoring-v1",
            "agentcube-desktop-scoring-effort-v1",
            "agentcube-desktop-scoring-models-v1",
            "agentcube-chatgpt-desktop-scoring-v1",
            "agentcube-chatgpt-subscription-scoring-v1",
            "canonical-general-reports",
            "canonical-general-round-reports",
        ],
        "scenarios": [
            {"id": "general", "display_name": "通用场景", "dataset_required": True},
            {"id": "web", "display_name": "Web站点", "dataset_required": False},
            {"id": "all", "display_name": "通用与Web", "dataset_required": True},
        ],
        "profiles": profiles(),
        "parameters": [
            {
                "key": "failure_retention_seconds",
                "display_name": "异常沙箱保留时间（秒，0为立即回收）",
                "value_type": "integer",
                "default": 1800,
                "minimum": 0,
                "maximum": 86400,
            },
            {
                "key": "execution_concurrency",
                "display_name": "执行并发",
                "value_type": "integer",
                "default": 3,
                "minimum": 1,
            },
            {
                "key": "runs",
                "display_name": "每题run数",
                "value_type": "integer",
                "default": 1,
                "minimum": 1,
            },
            {
                "key": "timeout_override",
                "display_name": "执行预算（秒）",
                "value_type": "integer",
                "default": 10800,
                "minimum": 1,
            },
        ],
        "contracts": {
            name: f"schemas/e2e-api-v1/{name}.schema.json"
            for name in ("plan", "snapshot", "event", "artifact", "package")
        },
    }


def catalog(repo: Path, scenario: str = "general", dataset: str | None = None,
            library_dataset: str | None = None) -> dict:
    from eval_general_e2e.datasets.bundle import (
        DATASETS,
        dataset_manifest_path,
        load_manifest_lock,
    )

    if library_dataset:
        from src.case_catalog import index
        group = index(repo, library_dataset, dataset)["datasets"][0]
        if group["scene"] != scenario or "e2e" not in group["modes"]:
            raise E2EError("CASE_LIBRARY_MODE_UNSUPPORTED")
        categories = Counter(row["category"] for row in group["cases"])
        return {"datasets": group["releases"], "cases": group["cases"],
                "categories": [{"id": key, "count": value} for key, value in categories.items()],
                "profiles": profiles()}

    datasets = []
    for dataset_id in DATASETS:
        manifest = load_manifest_lock(dataset_manifest_path(dataset_id))
        datasets.append(
            {
                "id": dataset_id,
                "digest": manifest["dataset_digest"],
                "task_count": manifest["task_count"],
            }
        )
    tasks = []
    if scenario in {"general", "all"} and dataset:
        tasks.extend(_general_catalog(repo, dataset)[0])
    if scenario in {"web", "all"}:
        web = canonical_script(
            repo,
            "web-e2e",
            "prepare-web-e2e-workspaces",
            "prepare_web_e2e_workspaces.py",
        )
        tasks.extend(_web_catalog(repo, web))
    cases = [
        {
            key: task.get(key)
            for key in (
                "task_id",
                "name",
                "scene",
                "category",
                "difficulty",
                "modality",
                "tags",
                "dataset",
                "metric_profile",
            )
        }
        for task in tasks
    ]
    categories = Counter(task["category"] for task in tasks)
    return {
        "datasets": datasets,
        "cases": cases,
        "categories": [
            {"id": key, "count": value} for key, value in categories.items()
        ],
        "profiles": profiles(),
    }


def resolve(
    repo: Path, raw: dict
) -> tuple[dict, list[dict], dict, dict | None, object]:
    from src.case_catalog import dataset_entry, releases, runnable
    plan = normalize_plan(raw)
    selection = plan["selection"]
    library_dataset = selection.get("library_dataset")
    if library_dataset:
        entry = dataset_entry(repo, library_dataset)
        if entry["scene"] != selection["scenario"] or "e2e" not in entry["modes"]:
            raise E2EError("CASE_LIBRARY_MODE_UNSUPPORTED")
        if selection.get("dataset") and selection["dataset"] not in {item["id"] for item in releases(repo, entry)}:
            raise E2EError("CASE_LIBRARY_RELEASE_UNKNOWN")
    web = canonical_script(
        repo, "web-e2e", "prepare-web-e2e-workspaces", "prepare_web_e2e_workspaces.py"
    )
    tasks, members, manifest = [], {}, None
    scene = plan["selection"]["scenario"]
    if scene in {"general", "all"}:
        if library_dataset and not selection.get("dataset"):
            general, members, manifest = _current_general(repo, library_dataset, selection, web)
        else:
            general, members, manifest = _general_catalog(repo, selection["dataset"])
        tasks.extend(general)
    if scene in {"web", "all"}:
        tasks.extend(_web_catalog(repo, web, library_dataset))
    eligible = [task for task in tasks if runnable(task.get("tags") or [], selection.get("include_drafts", False))]
    selected = eligible if library_dataset and scene == "general" and not selection.get("dataset") else _select(eligible, selection, repo, web)
    for task in selected:
        if task["scene"] == "web":
            parsed = web.parse_task(repo, task["task_id"])
            task["source"]["workspace_sha256"] = parsed["workspace_sha256"]
    if len({task["task_id"] for task in selected}) != len(selected):
        raise E2EError("CROSS_SCENE_TASK_ID_AMBIGUOUS")
    return plan, selected, members, manifest, web


def preflight(repo: Path, raw: dict, config_path: Path | None = None, *, check_runtime: bool = False) -> dict:
    plan, tasks, members, _, _ = resolve(repo, raw)
    preprocess_selection = preprocessing.selection(plan["units"], tasks)
    issues = []
    warnings = []
    published = profiles()
    for unit in plan["units"]:
        binding = unit.get("template_binding")
        matches = [
            profile
            for profile in published
            if profile["harness"] == unit["harness"]
            and (profile["id"] == binding["profile_id"] if binding else profile["template"] == unit["template"])
            and profile["enabled"]
        ]
        if len(matches) != 1:
            issues.append(
                {"code": "EXECUTOR_PROFILE_UNAVAILABLE", "unit_id": unit["unit_id"]}
            )
            continue
        profile = matches[0]
        if unit["harness"] == "chatgpt-desktop" and unit.get("chatgpt_permission", "ask for approval") != profile.get("default_permission", "ask for approval"):
            issues.append({"code": "CHATGPT_DESKTOP_PERMISSION_NOT_PUBLISHED", "unit_id": unit["unit_id"]})
        if unit["model"].casefold().startswith(("custom/","third-party/")) or "://" in unit["model"]:
            issues.append({"code":"CUSTOM_TESTED_MODELS_NOT_SUPPORTED","unit_id":unit["unit_id"]})
        elif unit["model"] not in {model["id"] for model in profile["models"]}:
            if profile.get("allow_unlisted_builtin_models"):
                warnings.append({"code":"BUILTIN_MODEL_REQUIRES_NATIVE_MENU_READBACK","unit_id":unit["unit_id"]})
            else: issues.append({"code": "MODEL_NOT_PUBLISHED", "unit_id": unit["unit_id"]})
        selected_model=next((model for model in profile["models"] if model["id"]==unit["model"]),{})
        allowed_efforts=selected_model.get("reasoning_efforts") or profile["reasoning_efforts"]
        if unit.get("max_mode") and not profile.get("max_mode_supported",False):
            issues.append({"code":"WORKBUDDY_MAX_MODE_NOT_PUBLISHED","unit_id":unit["unit_id"]})
        if (
            unit.get("reasoning_effort") is not None
            and unit["reasoning_effort"] not in allowed_efforts
        ):
            issues.append(
                {"code": "REASONING_NOT_PUBLISHED", "unit_id": unit["unit_id"]}
            )
        selected_scenarios = {task["scene"] for task in tasks}
        if not selected_scenarios.issubset(profile["scenarios"]):
            issues.append(
                {"code": "SCENARIO_NOT_PUBLISHED", "unit_id": unit["unit_id"]}
            )
    for task in tasks:
        if task["scene"] == "general":
            contract = json.loads(
                members[task["bundle"]["execution_contract_path"]].data
            )
            for key in ("env", "skills", "warmup"):
                if str(contract.get(key, "")).strip().casefold() not in {
                    "",
                    "none",
                    "null",
                    "n/a",
                    "无",
                    "{}",
                    "[]",
                }:
                    issues.append(
                        {
                            "task_id": task["task_id"],
                            "code": "TASK_RUNTIME_REQUIREMENT_NEEDS_ADAPTER",
                            "requirement": key,
                        }
                    )
    runtime_checks = {"credentials": "not_checked", "dns": "not_checked"}
    config = None
    if config_path or check_runtime:
        from .agentcube import AgentCubeConfig

        try:
            config = AgentCubeConfig.load(config_path)
            runtime_checks["credentials"] = "passed"
        except E2EError as exc:
            if not check_runtime:
                raise
            runtime_checks["credentials"] = "failed"
            issues.append({"code": "AGENTCUBE_RUNTIME_CONFIG_INVALID", "message": str(exc)})
    if config:
        if any(unit["harness"] == "chatgpt-desktop" for unit in plan["units"]):
            if not config.chatgpt_gateway_url:
                issues.append({"code": "CHATGPT_GATEWAY_URL_REQUIRED"})
            if not os.environ.get("WCB_CHATGPT_API_KEY", "").strip():
                issues.append({"code": "WCB_CHATGPT_API_KEY_REQUIRED"})
        if any(
            config.required_expire_ttl(unit["timeout_override"], preprocessing.budget(unit), plan.get("failure_retention_seconds", 0)) > config.expire_ttl
            for unit in plan["units"]
        ):
            issues.append({"code": "PLATFORM_TTL_TOO_SHORT_FOR_TIMEOUT"})
        if check_runtime:
            runtime_checks["dns"] = "passed"
            checked = set()
            for field in ("workload_manager_url", "router_url"):
                try:
                    endpoint = urlsplit(getattr(config, field))
                    host = endpoint.hostname
                    if host in checked:
                        continue
                    checked.add(host)
                    if not host:
                        raise OSError("endpoint has no hostname")
                    socket.getaddrinfo(host, endpoint.port or (443 if endpoint.scheme == "https" else 80),
                                       type=socket.SOCK_STREAM)
                except (OSError, ValueError):
                    runtime_checks["dns"] = "failed"
                    issues.append({"code": "AGENTCUBE_ENDPOINT_UNRESOLVABLE", "field": field,
                                   "message": "沙箱平台地址无法解析，请检查地址及公司内网或 VPN 连接"})
    groups = {(task["scene"], task["metric_profile"]) for task in tasks}
    return {
        "valid": not issues,
        "runtime_checks": runtime_checks,
        "warnings": warnings,
        "issues": issues,
        "plan": preprocessing.public_plan(plan),
        "plan_sha256": digest(preprocessing.public_plan(plan)),
        "selection_sha256": digest(tasks),
        "selected_task_count": len(tasks),
        "draft_task_count": sum("draft" in (task.get("tags") or []) for task in tasks),
        "unit_count": len(plan["units"]) * len(groups),
        "planned_execution_count": len(tasks) * len(plan["units"]) * plan["runs"],
        **preprocess_selection,
        "cases": [
            {
                key: task.get(key)
                for key in (
                    "task_id",
                    "name",
                    "scene",
                    "category",
                    "dataset",
                    "metric_profile",
                )
            }
            for task in tasks
        ],
    }


def public_event(row: dict, batch_id: str) -> dict:
    return {
        "api_version": API_VERSION,
        "batch_id": batch_id,
        "cursor": row["sequence"],
        "at": row["at"],
        "event_type": row["type"],
        "execution_key": row.get("key"),
        "payload": row.get("details", {}),
    }


def events(batch: Path, after: int) -> dict:
    from .engine import load_batch
    from .store import BatchStore

    load_batch(batch)
    rows = [public_event(row, batch.name) for row in BatchStore(batch).events(after)]
    return {
        "batch_id": batch.name,
        "events": rows,
        "cursor": rows[-1]["cursor"] if rows else after,
    }


def snapshot(batch: Path, *, execution_rows=None) -> dict:
    from .engine import load_batch
    from .store import BatchStore
    from .retention import retained

    manifest = load_batch(batch)
    raw = BatchStore(batch).summary()
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    tasks = {task["task_id"]: task for task in manifest["tasks"]}
    executions = []
    history_counts = BatchStore(batch).history_counts()
    for row in raw["executions"] if execution_rows is None else execution_rows:
        execution = inside(batch, row["execution_root"])
        source = execution / "original"
        pointer = execution.parent.parent / "restores" / row["attempt_id"] / "current.json"
        legacy_pointer = execution.parent.parent / "restores/current.json"
        if not pointer.exists() and legacy_pointer.exists():
            legacy = read_json(legacy_pointer)
            if row.get("execution_version", 1) == 1 or legacy.get("identity", {}).get("attempt_id") == row["attempt_id"]:
                pointer = legacy_pointer
        if pointer.exists():
            restoration = read_json(pointer)
            receipt = read_json(execution / "backups/backup-receipt.json")
            restored = Path(restoration["destination"]).resolve()
            if (
                restoration["identity"] != receipt["identity"]
                or restoration["source_archive_sha256"] != receipt["archive_sha256"]
                or not restored.is_relative_to(
                    (execution.parent.parent / "restores").resolve()
                )
                or file_sha256(restored / ".execution-seal.json")
                != receipt["seal_sha256"]
            ):
                raise E2EError("RESTORED_ARTIFACT_SOURCE_INVALID")
            source = restored
        ready_path = execution / "execution-ready.json"
        ready = read_json(ready_path) if ready_path.exists() else {}
        backup = execution / "backups/backup-receipt.json"
        final = source / "final-response.md"
        binding_path = source / "metadata/native-binding.json"
        binding = read_json(binding_path) if binding_path.exists() else {}
        error = row.get("error")
        for collected in ("collect", "failure-quiesced-collect"):
            diagnostics = source / collected / "evidence/diagnostics.json"
            if diagnostics.is_file():
                failure = read_json(diagnostics).get("failure")
                if failure:
                    error = {**(error or {}), "product_failure": failure}
        trace_status = ready.get("trace_status")
        if not trace_status:
            if any((source / "native").glob("*/*.jsonl")):
                trace_status = "partial"
            else:
                trace_status = "missing" if source.exists() else "unavailable"
        references = []
        for kind, path in (
            ("original_backup", execution / "backups/execution-original.zip"),
            ("backup_receipt", backup),
            ("final_response", final),
            ("trace", source / "trace"),
            ("trace", source / "native/failure-quiesced"),
            ("workspace", source / "collect/workspace"),
            ("failure_workspace", source / "failure-quiesced-collect/workspace"),
        ):
            if path.exists():
                references.append(
                    {
                        "kind": kind,
                        "path": path.relative_to(batch).as_posix(),
                        "is_dir": path.is_dir(),
                    }
                )
        start, finish = row.get("dispatch_armed_at"), row.get("finished_at")
        duration = None
        try:
            if start and finish:
                seconds = (datetime.fromisoformat(finish) - datetime.fromisoformat(start)).total_seconds()
                if seconds >= 0:
                    duration = seconds
        except (TypeError, ValueError):
            pass
        executions.append(
            {
                "execution_key": row["key"],
                "task_id": row["task_id"],
                "name": tasks[row["task_id"]].get("name") or row["task_id"],
                "unit_id": row["unit_id"],
                "run_index": row["run_index"],
                "attempt_id": row["attempt_id"],
                "execution_version": row.get("execution_version", 1),
                "history_count": history_counts.get(row["key"], 0),
                "is_final": row.get("is_final", True),
                "executor_revision": row.get("executor_revision") or manifest.get("source_revision"),
                "previous_attempt_id": row.get("previous_attempt_id"),
                "started_at": start, "finished_at": finish, "duration_seconds": duration,
                "stage": row["phase"],
                "terminal": row["phase"] in TERMINAL_PHASES
                and (not row["resource_held"] or retained(row)),
                "resource_held": row["resource_held"],
                **({"sandbox_retention": row["sandbox_retention"]} if row.get("sandbox_retention") else {}),
                "session_id": row.get("session_id"),
                "error": error,
                **({"preprocessing": row["preprocess_receipt"]} if row.get("preprocess_receipt") else {}),
                **({"prompt": {key: value for key, value in row["prompt"].items()
                               if key in {"changed", "plugin_mentions", "base_prompt_sha256", "effective_prompt_sha256"}}}
                   if row.get("prompt") else {}),
                "harness": units[row["unit_id"]]["harness"],
                "requested_model": units[row["unit_id"]]["model"],
                "actual_model": ready.get("actual_model")
                or binding.get("actual_model"),
                "reasoning_effort": units[row["unit_id"]].get("reasoning_effort"),
                "max_mode": units[row["unit_id"]].get("max_mode"),
                **({"workbuddy_full_access": units[row["unit_id"]]["workbuddy_full_access"]}
                   if "workbuddy_full_access" in units[row["unit_id"]] else {}),
                "scene": tasks[row["task_id"]].get("scene", "general"),
                "trace_completeness": trace_status,
                "backup_status": "verified" if backup.exists() else "pending",
                "exportable": backup.exists(),
                "artifact_root": str(source.relative_to(batch))
                if source.exists()
                else str(execution.relative_to(batch)),
                "final_response": str(final.relative_to(batch))
                if final.is_file()
                else None,
                "artifacts": references,
            }
        )
    counts = Counter(row["stage"] for row in executions)
    terminal = all(row["terminal"] for row in executions)
    held = sum(row["resource_held"] for row in executions)
    execution_held = raw.get("execution_resources_held", held)
    state = "running"
    if counts.get("NEEDS_ATTENTION") or (
        execution_held and all(row["stage"] in TERMINAL_PHASES for row in executions)
    ):
        state = "needs_attention"
    elif terminal:
        if counts.get("COMPLETED") == len(executions):
            state = "completed"
        elif counts.get("CANCELLED") == len(executions):
            state = "cancelled"
        else:
            state = "partial" if counts.get("COMPLETED") else "failed"
    elif counts.get("PENDING") == len(executions):
        state = "prepared"
    actions = (
        ["export"] if terminal or any(row["exportable"] for row in executions) else []
    )
    lease = raw.get("controllers", {}).get("execution") or {}
    if lease.get("lease_status") != "fresh":
        if not terminal:
            actions.append("resume")
        if held:
            actions.append("cleanup")
        if any(row["exportable"] for row in executions):
            actions.append("restore")
    if not terminal:
        actions.append("cancel")
    return {
        "batch_id": batch.name,
        "state": state,
        "terminal": terminal,
        "observed_at": raw["observed_at"],
        "engine": manifest.get("engine")
        or {"revision": manifest.get("source_revision")},
        "plan_sha256": digest(manifest["plan"]),
        "plan": {
            key: value
            for key, value in manifest["plan"].items()
            if not key.startswith("scoring_")
        },
        "units": manifest["units"],
        "executions": executions,
        "counts": dict(counts),
        "total": len(executions),
        "finished": sum(row["terminal"] for row in executions),
        "resource_held": raw["resource_held"],
        "execution_resources_held": execution_held,
        "retained_sandboxes_held": raw.get("retained_sandboxes_held", 0),
        "retained_sandboxes": raw.get("retained_sandboxes", []),
        "allowed_actions": actions,
        "controllers": raw.get("controllers", {}),
    }


def execution_history(batch: Path, execution_key: str) -> dict:
    from .store import BatchStore
    versions = BatchStore(batch).versions(execution_key)
    return {"execution_key": execution_key,
            "versions": sorted(snapshot(batch, execution_rows=versions)["executions"],
                               key=lambda row: row["execution_version"], reverse=True)}


def artifacts(batch: Path, path: str = "", content: bool = False) -> dict:
    allowed = {"units", "inputs", "batch.json", "selection.json", "exports"}
    if path and Path(path).parts[0] not in allowed:
        raise E2EError("ARTIFACT_OUTSIDE_PUBLIC_ROOT")
    target = inside(batch, path) if path else batch
    if target.is_symlink():
        raise E2EError("ARTIFACT_SYMLINK_UNSUPPORTED")
    if content:
        if not target.is_file() or target.stat().st_size > 1024 * 1024:
            raise E2EError("ARTIFACT_TEXT_TOO_LARGE_OR_MISSING")
        return {
            "path": path,
            "content": target.read_text(encoding="utf-8"),
            "size": target.stat().st_size,
        }
    paths = sorted(target.iterdir()) if target.is_dir() else [target]
    result = []
    for item in paths:
        if (
            item.name.startswith(".")
            or item.is_symlink()
            or (not path and item.name not in allowed)
        ):
            continue
        kind = "file"
        if item.name == "final-response.md":
            kind = "final_response"
        elif item.name.startswith("rollout-") or item.name in {
            "transcript.jsonl",
            "trace-index.json",
        }:
            kind = "trace"
        elif item.suffix == ".zip":
            kind = "backup"
        result.append(
            {
                "path": item.relative_to(batch).as_posix(),
                "name": item.name,
                "kind": kind,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else None,
                "sha256": file_sha256(item)
                if item.is_file() and not item.is_symlink()
                else None,
                "source": "native_rollout" if kind == "final_response" else "executor",
                "completeness": "directory" if item.is_dir() else "present",
            }
        )
    return {"batch_id": batch.name, "path": path, "artifacts": result}
