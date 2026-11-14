"""Versioned execution contracts shared by scripts, Skills and platform adapters."""

from __future__ import annotations

from collections import Counter
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
    _web_catalog,
    _select,
    _revision,
)

API_VERSION = 1
TERMINAL_PHASES = {"COMPLETED", "FAILED", "CANCELLED"}
DEFAULT_PROFILE = {
    "id": "astudio-winarena-20261104-a",
    "harness": "astronstudio",
    "display_name": "AStudio",
    "backend": "agentcube",
    "template": "winarena-pc-20261104-a",
    "scenarios": ["general", "web"],
    "enabled": True,
    "models": [
        {"id": "auto", "display_name": "Auto（实际模型以原生回读为准）"},
        {"id": "spark-x2.5", "display_name": "Spark-X2.5"},
    ],
    # Publish combinations verified on this template. The controller currently
    # cannot select Max. Operators may publish newly verified capabilities.
    "reasoning_efforts": ["high"],
}


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
    values = read_json(Path(source))["profiles"] if source else [DEFAULT_PROFILE]
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
            "preflight",
            "runtime-preflight",
            "windows-astudio-runtime-bootstrap",
            "execution",
            "events",
            "artifacts",
            "resume",
            "cancel",
            "restore",
            "offline-export",
            "offline-parent-report-inputs",
            "headless-general-scoring",
            "canonical-general-reports",
        ],
        "scenarios": [
            {"id": "general", "display_name": "通用场景", "dataset_required": True},
            {"id": "web", "display_name": "Web站点", "dataset_required": False},
            {"id": "all", "display_name": "通用与Web", "dataset_required": True},
        ],
        "profiles": profiles(),
        "parameters": [
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


def catalog(repo: Path, scenario: str = "general", dataset: str | None = None) -> dict:
    from eval_general_e2e.datasets.bundle import (
        DATASETS,
        dataset_manifest_path,
        load_manifest_lock,
    )

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
    plan = normalize_plan(raw)
    web = canonical_script(
        repo, "web-e2e", "prepare-web-e2e-workspaces", "prepare_web_e2e_workspaces.py"
    )
    tasks, members, manifest = [], {}, None
    scene = plan["selection"]["scenario"]
    if scene in {"general", "all"}:
        general, members, manifest = _general_catalog(
            repo, plan["selection"]["dataset"]
        )
        tasks.extend(general)
    if scene in {"web", "all"}:
        tasks.extend(_web_catalog(repo, web))
    selected = _select(tasks, plan["selection"], repo, web)
    for task in selected:
        if task["scene"] == "web":
            parsed = web.parse_task(repo, task["task_id"])
            task["source"]["workspace_sha256"] = parsed["workspace_sha256"]
    if len({task["task_id"] for task in selected}) != len(selected):
        raise E2EError("CROSS_SCENE_TASK_ID_AMBIGUOUS")
    return plan, selected, members, manifest, web


def preflight(repo: Path, raw: dict, config_path: Path | None = None, *, check_runtime: bool = False) -> dict:
    plan, tasks, members, _, _ = resolve(repo, raw)
    issues = []
    published = profiles()
    for unit in plan["units"]:
        matches = [
            profile
            for profile in published
            if profile["harness"] == unit["harness"]
            and profile["template"] == unit["template"]
            and profile["enabled"]
        ]
        if len(matches) != 1:
            issues.append(
                {"code": "EXECUTOR_PROFILE_UNAVAILABLE", "unit_id": unit["unit_id"]}
            )
            continue
        profile = matches[0]
        if unit["model"] not in {model["id"] for model in profile["models"]}:
            issues.append({"code": "MODEL_NOT_PUBLISHED", "unit_id": unit["unit_id"]})
        if (
            unit.get("reasoning_effort") is not None
            and unit["reasoning_effort"] not in profile["reasoning_efforts"]
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
        if any(
            unit["timeout_override"] + 2400 > config.expire_ttl
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
        "issues": issues,
        "plan": plan,
        "plan_sha256": digest(plan),
        "selection_sha256": digest(tasks),
        "selected_task_count": len(tasks),
        "unit_count": len(plan["units"]) * len(groups),
        "planned_execution_count": len(tasks) * len(plan["units"]) * plan["runs"],
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


def snapshot(batch: Path) -> dict:
    from .engine import load_batch
    from .store import BatchStore

    manifest = load_batch(batch)
    raw = BatchStore(batch).summary()
    units = {unit["unit_id"]: unit for unit in manifest["units"]}
    tasks = {task["task_id"]: task for task in manifest["tasks"]}
    executions = []
    for row in raw["executions"]:
        execution = inside(batch, row["execution_root"])
        source = execution / "original"
        pointer = execution.parent.parent / "restores/current.json"
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
        executions.append(
            {
                "execution_key": row["key"],
                "task_id": row["task_id"],
                "name": tasks[row["task_id"]].get("name") or row["task_id"],
                "unit_id": row["unit_id"],
                "run_index": row["run_index"],
                "attempt_id": row["attempt_id"],
                "stage": row["phase"],
                "terminal": row["phase"] in TERMINAL_PHASES
                and not row["resource_held"],
                "resource_held": row["resource_held"],
                "session_id": row.get("session_id"),
                "error": error,
                "harness": units[row["unit_id"]]["harness"],
                "requested_model": units[row["unit_id"]]["model"],
                "actual_model": ready.get("actual_model")
                or binding.get("actual_model"),
                "reasoning_effort": units[row["unit_id"]].get("reasoning_effort"),
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
    state = "running"
    if counts.get("NEEDS_ATTENTION") or (
        held and all(row["stage"] in TERMINAL_PHASES for row in executions)
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
        "resource_held": held,
        "allowed_actions": actions,
        "controllers": raw.get("controllers", {}),
    }


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
