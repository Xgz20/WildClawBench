"""Prepare public execution inputs and private scoring sources from canonical tasks."""
from __future__ import annotations

from datetime import datetime
import json
import re
from pathlib import Path
import shutil
import uuid

from . import DEFAULT_EXECUTION_CONCURRENCY
from .artifacts import inventory
from .common import E2EError, atomic_json, digest, file_sha256, identifier, inside, load_script, read_json, utc_now
from .store import BatchStore, controller_lock


PLAN_SCHEMA = "wildclawbench.sandbox-batch-plan/v1"
BATCH_SCHEMA = "wildclawbench.sandbox-batch/v1"


def canonical_script(repo: Path, scene: str, skill: str, script: str):
    path = repo / "tools/report/skills" / scene / skill / "scripts" / script
    return load_script(path, "wcb_sandbox_" + skill.replace("-", "_") + "_" + script.replace(".", "_"))


def _general_catalog(repo: Path, dataset: str):
    from eval_general_e2e.datasets.bundle import DATASETS, compile_dataset, dataset_manifest_path, load_manifest_lock
    if dataset not in DATASETS:
        raise E2EError("GENERAL_DATASET_UNKNOWN")
    manifest, members = compile_dataset(repo, definition=DATASETS[dataset])
    if manifest != load_manifest_lock(dataset_manifest_path(dataset)):
        raise E2EError("GENERAL_DATASET_SOURCE_DRIFT")
    tasks = []
    for task in manifest["tasks"]:
        tasks.append({**task, "scene": "general", "metric_profile": "general-e2e-contract-v1",
                      "dataset": {"id": dataset, "digest": manifest["dataset_digest"]}})
    return tasks, {member.path.rstrip("/"): member for member in members}, manifest


def _web_catalog(repo: Path, web):
    tasks = []
    seen = {}
    for path in sorted((repo / "tasks").rglob("*.md")):
        if "cn" in path.relative_to(repo / "tasks").parts:
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        metadata, _ = web.split_frontmatter(text, path)
        raw_tags = metadata.get("tags") or []
        tags = [str(value).strip().lower() for value in (raw_tags.split(",") if isinstance(raw_tags, str) else raw_tags)]
        if "web-site-gen" not in tags:
            continue
        task_id = str(metadata.get("id") or path.stem)
        if task_id in seen:
            raise E2EError(f"WEB_TASK_AMBIGUOUS: {task_id}")
        seen[task_id] = path
        tasks.append({"task_id": task_id, "name": metadata.get("name") or task_id,
                      "category": metadata.get("category") or path.parent.name,
                      "modality": metadata.get("modality"), "tags": tags,
                      "scene": "web", "metric_profile": web.resolve_metric_profile(metadata),
                      "source": {"task_path": path.relative_to(repo).as_posix()}})
    return tasks


def _select(tasks: list[dict], selection: dict, repo: Path, web) -> list[dict]:
    ids = web.read_ids(selection.get("task_ids") or [])
    path = selection.get("task")
    if path:
        target = Path(path).expanduser().resolve(strict=True)
        candidates = [task for task in tasks if (repo / task["source"]["task_path"]).resolve() == target]
        if len(candidates) != 1:
            raise E2EError("TASK_OUTSIDE_SELECTED_DATASET")
        ids = [candidates[0]["task_id"]]
    known = {task["task_id"] for task in tasks}
    if set(ids) - known:
        raise E2EError("TASK_IDS_UNKNOWN: " + ",".join(sorted(set(ids) - known)))
    categories = set(selection.get("categories") or []) - {"all"}
    if categories - {str(task["category"]) for task in tasks}:
        raise E2EError("TASK_CATEGORIES_UNKNOWN")
    selected = [task for task in tasks if (not ids or task["task_id"] in ids)
                and (not categories or task["category"] in categories)]
    if not path and not ids:
        include = {tag.lower() for tag in selection.get("tags") or []}
        exclude = {tag.lower() for tag in selection.get("exclude_tags") or []}
        modality = selection.get("modality")
        selected = [task for task in selected
                    if (not include or include & set(task.get("tags") or []))
                    and not exclude.intersection(task.get("tags") or [])
                    and (not modality or task.get("modality") == modality)]
    if not selected:
        raise E2EError("TASK_SELECTION_EMPTY")
    return selected


def _write_general(task: dict, members: dict, destination: Path, prepare) -> dict:
    prefix = "tasks/" + task["task_id"] + "/"
    contract = json.loads(members[task["bundle"]["execution_contract_path"]].data)
    destination.mkdir(parents=True)
    for path, member in members.items():
        if not path.startswith(prefix):
            continue
        suffix = path[len(prefix):]
        if suffix.startswith("execution/exec/"):
            suffix = "execution/workspace/" + suffix[len("execution/exec/"):]
        target = inside(destination, suffix)
        if member.kind == "directory":
            target.mkdir(parents=True, exist_ok=True)
        elif member.kind == "file":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(member.data)
            target.chmod(member.mode)
        else:
            raise E2EError("WINDOWS_EXECUTION_SYMLINK_UNSUPPORTED: " + path)
    workspace = destination / "execution/workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    prompt, mapping = prepare.map_prompt_workspace(contract["prompt"])
    entries = [prepare.ZipEntry("workspace/" + p.relative_to(workspace).as_posix(), p.read_bytes())
               for p in sorted(workspace.iterdir()) if p.is_file()]
    prompt, public_context = prepare.inline_public_context(prompt, entries, workspace_prefix="workspace/")
    (destination / "execution/PROMPT.md").write_bytes(prompt.encode("utf-8"))
    shutil.copyfile(destination / "task.md", destination / "private-scoring/task.md")
    return {"prompt_mapping": mapping, "public_context_delivery": public_context,
            "requirements": {key: contract.get(key, "") for key in ("env", "skills", "warmup")}}


def _write_web(task: dict, destination: Path, repo: Path, web) -> dict:
    parsed = web.parse_task(repo, task["task_id"])
    destination.mkdir(parents=True)
    shutil.copyfile(parsed["task_file"], destination / "task.md")
    public = destination / "execution"
    public.mkdir()
    web.stage_execution_workspace(parsed, public / "workspace")
    inventory(public / "workspace")
    # The remote client's cwd is the uploaded workspace itself. The scoring
    # contract keeps its own task-root -> ./workspace mapping.
    prompt = re.sub(r"/tmp_workspace\b", ".", parsed["prompt"])
    mapping = {"/tmp_workspace": "."} if prompt != parsed["prompt"] else {}
    (public / "PROMPT.md").write_bytes(prompt.encode("utf-8"))
    private = destination / "private-scoring"
    private.mkdir()
    neutral = {key: parsed[key] for key in ("task_id", "name", "difficulty", "prompt", "expected_behavior",
               "llm_judge_rubric", "criteria", "metric_profile", "scoring", "task_source", "task_sha256", "workspace_sha256")}
    atomic_json(private / "web-task-source.json", neutral)
    web.copy_referenced_fixtures(parsed, private / "fixtures")
    return {"prompt_mapping": mapping, "requirements": {"env": "", "skills": "", "warmup": ""}}


def normalize_plan(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise E2EError("BATCH_PLAN_OBJECT_REQUIRED")
    if raw.get("schema_version", PLAN_SCHEMA) != PLAN_SCHEMA:
        raise E2EError("BATCH_PLAN_SCHEMA_UNSUPPORTED")
    allowed = {"schema_version", "batch_id", "selection", "units", "runs", "execution_concurrency",
               "scoring_mode", "scoring_concurrency", "timeout_override"}
    if set(raw) - allowed:
        raise E2EError("BATCH_PLAN_UNKNOWN_KEYS")
    plan = {"schema_version": PLAN_SCHEMA, "batch_id": raw.get("batch_id") or
            "e2e-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8],
            "selection": raw.get("selection") or {}, "units": raw.get("units") or [],
            "runs": raw.get("runs", 1), "execution_concurrency": raw.get("execution_concurrency", DEFAULT_EXECUTION_CONCURRENCY),
            "scoring_mode": raw.get("scoring_mode", "streaming"), "scoring_concurrency": raw.get("scoring_concurrency", 3),
            "timeout_override": raw.get("timeout_override", 10800)}
    identifier(plan["batch_id"], "batch_id")
    for name in ("runs", "execution_concurrency", "scoring_concurrency", "timeout_override"):
        if type(plan[name]) is not int or plan[name] < 1:
            raise E2EError(name.upper() + "_INVALID")
    if plan["scoring_concurrency"] > 8 or plan["scoring_mode"] not in {"streaming", "batch"}:
        raise E2EError("SCORING_CONFIGURATION_INVALID")
    selection = plan["selection"]
    if not isinstance(selection, dict) or not isinstance(plan["units"], list):
        raise E2EError("BATCH_PLAN_SELECTION_OR_UNITS_INVALID")
    if set(selection) - {"scenario", "dataset", "task", "task_ids", "categories", "tags", "exclude_tags", "modality"}:
        raise E2EError("TASK_SELECTION_UNKNOWN_KEYS")
    if selection.get("scenario") not in {"general", "web", "all"}:
        raise E2EError("SCENARIO_REQUIRED")
    if selection["scenario"] in {"general", "all"} and not selection.get("dataset"):
        raise E2EError("GENERAL_DATASET_REQUIRED")
    if not plan["units"]:
        raise E2EError("HARNESS_UNITS_REQUIRED")
    units = []
    for raw_unit in plan["units"]:
        if not isinstance(raw_unit, dict):
            raise E2EError("HARNESS_UNIT_OBJECT_REQUIRED")
        if set(raw_unit) - {"unit_id", "harness", "backend", "model", "reasoning_effort", "template", "max_concurrency", "timeout_override"}:
            raise E2EError("HARNESS_UNIT_UNKNOWN_KEYS")
        unit = {"harness": raw_unit.get("harness"), "backend": raw_unit.get("backend", "agentcube"),
                "model": raw_unit.get("model"), "reasoning_effort": raw_unit.get("reasoning_effort"),
                "template": raw_unit.get("template", "winarena-pc-20261104-a"),
                "max_concurrency": raw_unit.get("max_concurrency", plan["execution_concurrency"]),
                "timeout_override": raw_unit.get("timeout_override", plan["timeout_override"])}
        if not isinstance(unit["model"], str) or not unit["model"].strip():
            raise E2EError("TESTED_MODEL_REQUIRED")
        if unit["harness"] != "astronstudio" or unit["backend"] != "agentcube":
            raise E2EError("SANDBOX_DRIVER_UNAVAILABLE: " + str(unit["harness"]))
        if type(unit["max_concurrency"]) is not int or unit["max_concurrency"] < 1:
            raise E2EError("UNIT_CONCURRENCY_INVALID")
        if type(unit["timeout_override"]) is not int or unit["timeout_override"] < 1:
            raise E2EError("UNIT_TIMEOUT_INVALID")
        if unit["reasoning_effort"] is not None and str(unit["reasoning_effort"]).casefold() not in {"none", "high", "max"}:
            raise E2EError("ASTUDIO_REASONING_UNSUPPORTED")
        unit["unit_id"] = raw_unit.get("unit_id") or unit["harness"] + "-" + digest(unit)[:12]
        identifier(unit["unit_id"], "unit_id")
        identifier(unit["template"], "template")
        units.append(unit)
    if len({unit["unit_id"] for unit in units}) != len(units):
        raise E2EError("UNIT_ID_DUPLICATE")
    plan["units"] = units
    return plan


def prepare_batch(repo: Path, workspace: Path, raw_plan: dict) -> Path:
    repo, workspace = repo.resolve(strict=True), workspace.expanduser().resolve()
    plan = normalize_plan(raw_plan)
    batch = workspace / "batches" / plan["batch_id"]
    web = canonical_script(repo, "web-e2e", "prepare-web-e2e-workspaces", "prepare_web_e2e_workspaces.py")
    tasks, members, general_manifest = [], {}, None
    scene = plan["selection"]["scenario"]
    if scene in {"general", "all"}:
        general, members, general_manifest = _general_catalog(repo, plan["selection"]["dataset"])
        tasks.extend(general)
    if scene in {"web", "all"}:
        tasks.extend(_web_catalog(repo, web))
    selected = _select(tasks, plan["selection"], repo, web)
    if len({task["task_id"] for task in selected}) != len(selected):
        raise E2EError("CROSS_SCENE_TASK_ID_AMBIGUOUS")
    general_prepare = canonical_script(repo, "general-e2e", "prepare-general-e2e-workspaces", "prepare_general_e2e_workspaces.py")
    workspace.mkdir(parents=True, exist_ok=True)
    with controller_lock(workspace, "prepare-" + plan["batch_id"]):
        if batch.exists():
            raise E2EError("BATCH_ALREADY_EXISTS_USE_RESUME")
        root_manifest = workspace / "workspace.json"
        if not root_manifest.exists():
            try:
                atomic_json(root_manifest, {"schema": "wildclawbench.e2e-workspace/v1", "created_at": utc_now()}, create=True)
            except FileExistsError:
                pass
        if read_json(root_manifest).get("schema") != "wildclawbench.e2e-workspace/v1":
            raise E2EError("WORKSPACE_SCHEMA_UNSUPPORTED")
        staging = batch.with_name("." + batch.name + ".prepare-" + uuid.uuid4().hex)
        staging.mkdir(parents=True)
        try:
            prepared = []
            for task in selected:
                identifier(task["task_id"], "task_id")
                dataset_key = task.get("dataset", {}).get("id") or task["metric_profile"]
                relative = f"inputs/{dataset_key}/tasks/{task['task_id']}"
                destination = inside(staging, relative)
                extra = (_write_general(task, members, destination, general_prepare) if task["scene"] == "general"
                         else _write_web(task, destination, repo, web))
                prompt = destination / "execution/PROMPT.md"
                row = {**task, **extra, "input_root": relative, "prompt_sha256": file_sha256(prompt),
                       "public_inventory": inventory(destination / "execution/workspace"),
                       "definition_inventory": inventory(destination)}
                atomic_json(destination / "task-definition.json", row)
                prepared.append(row)
            units = []
            groups = sorted({(task["scene"], task["metric_profile"]) for task in prepared})
            for base in plan["units"]:
                for scenario, profile in groups:
                    unit = {**base, "scene": scenario, "metric_profile": profile}
                    unit["unit_id"] = base["unit_id"] + "-" + scenario + "-" + digest(profile)[:6]
                    unit["task_ids"] = [task["task_id"] for task in prepared if (task["scene"], task["metric_profile"]) == (scenario, profile)]
                    units.append(unit)
                    atomic_json(staging / "units" / unit["unit_id"] / "unit.json", unit)
            from .compatibility import freeze_assets
            compatibility = freeze_assets(repo, staging, prepared, general_manifest, members)
            manifest = {"schema": BATCH_SCHEMA, "created_at": utc_now(), "plan": plan,
                        "source_revision": _revision(repo), "units": units, "tasks": prepared,
                        "compatibility": compatibility}
            atomic_json(staging / "batch.json", manifest)
            atomic_json(staging / "selection.json", {"requested": plan["selection"], "tasks": [{
                "task_id": task["task_id"], "scene": task["scene"], "dataset": task.get("dataset"),
                "source": task["source"], "prompt_sha256": task["prompt_sha256"]} for task in prepared]})
            items = []
            # Round-robin units share one bounded sandbox pool.
            for run_index in range(1, plan["runs"] + 1):
                for task_index in range(max(len(unit["task_ids"]) for unit in units)):
                    for unit in units:
                        if task_index >= len(unit["task_ids"]):
                            continue
                        task_id = unit["task_ids"][task_index]
                        key = f"{unit['unit_id']}/run-{run_index:04d}/{task_id}"
                        attempt = "exec-" + uuid.uuid4().hex
                        items.append({"key": key, "unit_id": unit["unit_id"], "run_index": run_index,
                                      "task_id": task_id, "attempt_id": attempt,
                                      "execution_root": f"units/{unit['unit_id']}/runs/run-{run_index:04d}/tasks/{task_id}/executions/{attempt}"})
            BatchStore(staging).initialize(manifest, items)
            staging.rename(batch)
        except BaseException:
            if staging.exists():
                shutil.rmtree(staging)
            raise
    return batch


def _revision(repo: Path) -> str:
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
