"""Prepare public execution inputs and private scoring sources from canonical tasks."""
from __future__ import annotations

from datetime import datetime
import io
import json
import re
from pathlib import Path
import shutil
import sys
import uuid

from . import DEFAULT_AGENTCUBE_TEMPLATE, DEFAULT_CHATGPT_DESKTOP_TEMPLATE, DEFAULT_EXECUTION_CONCURRENCY
from .artifacts import inventory, copy_stream_readonly, _protect, remove_temporary_tree
from .common import E2EError, atomic_json, digest, file_sha256, identifier, inside, load_script, read_json, utc_now
from .store import BatchStore, controller_lock
from . import preprocessing


PLAN_SCHEMA = "wildclawbench.sandbox-batch-plan/v1"
BATCH_SCHEMA = "wildclawbench.sandbox-batch/v1"


def canonical_script(repo: Path, scene: str, skill: str, script: str):
    path = repo / "tools/report/skills" / scene / skill / "scripts" / script
    return load_script(path, "wcb_sandbox_" + skill.replace("-", "_") + "_" + script.replace(".", "_"))


def _general_catalog(repo: Path, dataset: str):
    from .dataset_assets import frozen_dataset
    manifest, members = frozen_dataset(repo, dataset)
    tasks = []
    for task in manifest["tasks"]:
        tasks.append({**task, "scene": "general", "metric_profile": "general-e2e-contract-v1",
                      "dataset": {"id": manifest["dataset_id"], "digest": manifest["dataset_digest"]}})
    return tasks, {member.path.rstrip("/"): member for member in members}, manifest


def _current_general(repo: Path, dataset: str, selection: dict, web):
    from collections import Counter
    from dataclasses import replace
    from eval_general_e2e.datasets.bundle import compile_dataset
    from eval_general_e2e.datasets.catalog import load_registered_dataset
    from src.case_catalog import current_cases, dataset_entry, runnable

    entry = dataset_entry(repo, dataset)
    registered = load_registered_dataset(repo, entry["release_series"])
    tasks = _select([case for case in current_cases(repo, dataset, entry)
                     if runnable(case["tags"], selection.get("include_drafts", False))], selection, repo, web)
    task_root = entry["task_root"]
    workspace_root = task_root.replace("tasks/", "workspace/", 1)
    definition = replace(
        registered.definition,
        dataset_id=dataset + "-working",
        task_ids=tuple(case["task_id"] for case in tasks),
        created_at="1970-01-01T00:00:00Z",
        include_tags=(),
        exclude_tags=("invalid",),
        expected_task_count=len(tasks),
        expected_category_counts=Counter(case["category_key"] for case in tasks),
        expected_grading_type_counts=Counter(case["grading_type"] for case in tasks),
        expected_difficulty_counts=Counter(case["difficulty"] for case in tasks),
        expected_timeout_counts=Counter(str(case["timeout_seconds"]) for case in tasks),
        task_root=task_root,
        workspace_root=workspace_root,
        source_revision=None,
        registry_path=workspace_root.replace("workspace/", "datasets/", 1) + "/task_sources.yaml",
        frozen_source_index=None,
        current_source_paths=(),
        revision_scope=(task_root, workspace_root),
        constraints={},
    )
    # Legacy built-in families lack a registered per-task report contract.
    manifest, members = compile_dataset(repo, definition=definition)
    rows = [
        {**task, "scene": "general", "metric_profile": "general-e2e-contract-v1",
         "library_dataset": dataset,
         "dataset": {"id": manifest["dataset_id"], "digest": manifest["dataset_digest"]}}
        for task in manifest["tasks"]
    ]
    return rows, {member.path.rstrip("/"): member for member in members}, manifest


def _web_catalog(repo: Path, web, library_dataset: str | None = None):
    from eval_general_e2e.datasets.layout import is_reading_or_archived_task
    from src.case_catalog import current_cases, dataset_entry
    if library_dataset:
        entry = dataset_entry(repo, library_dataset)
        if entry["scene"] != "web" or "e2e" not in entry["modes"]:
            raise E2EError("CASE_LIBRARY_MODE_UNSUPPORTED")
        paths = [repo / row["task_path"] for row in current_cases(repo, library_dataset, entry)]
    else:
        paths = sorted((repo / "tasks").rglob("*.md"))
    tasks = []
    seen = {}
    root = repo / "tasks"
    for path in paths:
        if is_reading_or_archived_task(root, path):
            continue
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        metadata, _ = web.split_frontmatter(text, path)
        raw_tags = metadata.get("tags") or []
        tags = [str(value).strip().lower() for value in (raw_tags.split(",") if isinstance(raw_tags, str) else raw_tags)]
        if "web-site-gen" not in tags or "invalid" in tags:
            continue
        task_id = str(metadata.get("id") or path.stem)
        if task_id in seen:
            raise E2EError(f"WEB_TASK_AMBIGUOUS: {task_id}")
        seen[task_id] = path
        tasks.append({"task_id": task_id, "name": metadata.get("name") or task_id,
                      "category": metadata.get("category") or path.parent.name,
                      "modality": metadata.get("modality"), "difficulty": metadata.get("difficulty"), "tags": tags,
                      "library_dataset": library_dataset,
                      "scene": "web", "metric_profile": web.resolve_metric_profile(metadata),
                      "source": {"task_path": path.relative_to(repo).as_posix(), "task_sha256": file_sha256(path)}})
    return tasks


def _select(tasks: list[dict], selection: dict, repo: Path, web) -> list[dict]:
    ids = web.read_ids(selection.get("task_ids") or [])
    path = selection.get("task")
    if path:
        from eval_general_e2e.datasets.layout import relocated_task
        target = relocated_task(repo, Path(path).expanduser()).resolve(strict=True)
        candidates = [task for task in tasks if relocated_task(repo, Path(task.get("task_path") or task["source"]["task_path"])).resolve() == target]
        if len(candidates) != 1:
            raise E2EError("TASK_OUTSIDE_SELECTED_DATASET")
        ids = [candidates[0]["task_id"]]
    known = {task["task_id"] for task in tasks}
    if set(ids) - known:
        from eval_general_e2e.datasets.layout import load_layout
        aliases = load_layout(repo).get("task_id_aliases", {})
        ids = [task_id if task_id in known else aliases.get(task_id, task_id) for task_id in ids]
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
            with io.BytesIO(member.data) as source:
                copy_stream_readonly(source, target, mode=member.mode)
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
    if (parsed["task_sha256"] != task["source"]["task_sha256"]
            or parsed["workspace_sha256"] != task["source"]["workspace_sha256"]):
        raise E2EError("WEB_SOURCE_CHANGED_DURING_PREPARATION")
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


def normalize_template_binding(binding: object) -> dict:
    if (not isinstance(binding, dict)
            or set(binding) != {"id", "namespace", "image_digest", "profile_id", "waa_revision"}
            or type(binding["id"]) is not int or binding["id"] < 1
            or not isinstance(binding["image_digest"], str)
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", binding["image_digest"])
            or not isinstance(binding["waa_revision"], str)
            or not re.fullmatch(r"[a-f0-9]{7,40}", binding["waa_revision"])):
        raise E2EError("AGENTCUBE_TEMPLATE_BINDING_INVALID")
    identifier(binding["namespace"], "namespace")
    identifier(binding["profile_id"], "profile_id")
    return dict(binding)


def normalize_plan(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise E2EError("BATCH_PLAN_OBJECT_REQUIRED")
    if raw.get("schema_version", PLAN_SCHEMA) != PLAN_SCHEMA:
        raise E2EError("BATCH_PLAN_SCHEMA_UNSUPPORTED")
    allowed = {"schema_version", "batch_id", "selection", "units", "runs", "execution_concurrency",
               "scoring_mode", "scoring_concurrency", "timeout_override", "failure_retention_seconds"}
    if set(raw) - allowed:
        raise E2EError("BATCH_PLAN_UNKNOWN_KEYS")
    # Legacy plans keep immediate cleanup. Platform description defaults are
    # materialized into new plans before preflight and freezing.
    retention = raw.get("failure_retention_seconds", 0)
    if type(retention) is not int or not 0 <= retention <= 86400:
        raise E2EError("FAILURE_RETENTION_SECONDS_INVALID")
    plan = {"schema_version": PLAN_SCHEMA, "batch_id": raw.get("batch_id") or
            "e2e-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8],
            "selection": raw.get("selection") or {}, "units": raw.get("units") or [],
            "failure_retention_seconds": retention,
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
    if set(selection) - {"scenario", "dataset", "task", "task_ids", "categories", "tags", "exclude_tags", "modality", "library_dataset", "include_drafts"}:
        raise E2EError("TASK_SELECTION_UNKNOWN_KEYS")
    if selection.get("scenario") not in {"general", "web", "all"}:
        raise E2EError("SCENARIO_REQUIRED")
    if "include_drafts" in selection and type(selection["include_drafts"]) is not bool:
        raise E2EError("CASE_LIBRARY_DRAFT_FLAG_INVALID")
    if selection.get("library_dataset") and selection["scenario"] == "all":
        raise E2EError("CASE_LIBRARY_SCENARIO_MISMATCH")
    if selection["scenario"] in {"general", "all"} and not (selection.get("dataset") or selection.get("library_dataset")):
        raise E2EError("GENERAL_DATASET_REQUIRED")
    if not plan["units"]:
        raise E2EError("HARNESS_UNITS_REQUIRED")
    units = []
    for raw_unit in plan["units"]:
        if not isinstance(raw_unit, dict):
            raise E2EError("HARNESS_UNIT_OBJECT_REQUIRED")
        if set(raw_unit) - {"unit_id", "harness", "backend", "model", "reasoning_effort", "template", "max_concurrency", "timeout_override", "max_mode", "workbuddy_full_access", "chatgpt_permission", "preprocessing", "prompt_directives", "template_binding"}:
            raise E2EError("HARNESS_UNIT_UNKNOWN_KEYS")
        default_template = (
            DEFAULT_CHATGPT_DESKTOP_TEMPLATE
            if raw_unit.get("harness") == "chatgpt-desktop" else DEFAULT_AGENTCUBE_TEMPLATE
        )
        unit = {"harness": raw_unit.get("harness"), "backend": raw_unit.get("backend", "agentcube"),
                "model": raw_unit.get("model"), "reasoning_effort": raw_unit.get("reasoning_effort"),
                "template": raw_unit.get("template", default_template),
                "max_concurrency": raw_unit.get("max_concurrency", plan["execution_concurrency"]),
                "timeout_override": raw_unit.get("timeout_override", plan["timeout_override"])}
        if not isinstance(unit["model"], str) or not unit["model"].strip():
            raise E2EError("TESTED_MODEL_REQUIRED")
        if unit["harness"] not in {"astronstudio", "workbuddy", "chatgpt-desktop"} or unit["backend"] != "agentcube":
            raise E2EError("SANDBOX_DRIVER_UNAVAILABLE: " + str(unit["harness"]))
        if type(unit["max_concurrency"]) is not int or unit["max_concurrency"] < 1:
            raise E2EError("UNIT_CONCURRENCY_INVALID")
        if type(unit["timeout_override"]) is not int or unit["timeout_override"] < 1:
            raise E2EError("UNIT_TIMEOUT_INVALID")
        if unit["harness"] == "chatgpt-desktop":
            if unit["reasoning_effort"] not in {None, "low", "high"}:
                raise E2EError("CHATGPT_DESKTOP_REASONING_UNSUPPORTED")
            unit["reasoning_effort"] = unit["reasoning_effort"] or "low"
            if "chatgpt_permission" in raw_unit:
                permission = raw_unit["chatgpt_permission"]
                if permission not in ("ask for approval", "full access"):
                    raise E2EError("CHATGPT_DESKTOP_PERMISSION_UNSUPPORTED")
                unit["chatgpt_permission"] = permission
            elif unit["template"] == DEFAULT_CHATGPT_DESKTOP_TEMPLATE:
                unit["chatgpt_permission"] = "full access"
        elif unit["reasoning_effort"] is not None and str(unit["reasoning_effort"]).casefold() not in {"none", "high", "max"}:
            raise E2EError("ASTUDIO_REASONING_UNSUPPORTED")
        if "chatgpt_permission" in raw_unit and unit["harness"] != "chatgpt-desktop":
            raise E2EError("CHATGPT_DESKTOP_PERMISSION_REQUIRES_CHATGPT")
        if unit["harness"] == "workbuddy":
            if unit["reasoning_effort"] not in {None,"none"}: raise E2EError("WORKBUDDY_USES_MAX_MODE_NOT_REASONING")
            if type(raw_unit.get("max_mode",False)) is not bool: raise E2EError("WORKBUDDY_MAX_MODE_INVALID")
            unit["max_mode"] = raw_unit.get("max_mode",False)
        elif "max_mode" in raw_unit: raise E2EError("MAX_MODE_REQUIRES_WORKBUDDY")
        if "workbuddy_full_access" in raw_unit:
            if unit["harness"] != "workbuddy":
                raise E2EError("FULL_ACCESS_OPTION_REQUIRES_WORKBUDDY")
            if type(raw_unit["workbuddy_full_access"]) is not bool:
                raise E2EError("WORKBUDDY_FULL_ACCESS_MUST_BE_BOOLEAN")
            unit["workbuddy_full_access"] = raw_unit["workbuddy_full_access"]
        elif unit["harness"] == "workbuddy" and unit["template"] == DEFAULT_AGENTCUBE_TEMPLATE:
            unit["workbuddy_full_access"] = True
        if "template_binding" in raw_unit:
            unit["template_binding"] = normalize_template_binding(raw_unit["template_binding"])
        environment = raw_unit.get("preprocessing")
        if environment is not None and not isinstance(environment, dict):
            raise E2EError("PREPROCESS_BINDING_INVALID")
        if raw_unit.get("prompt_directives") is not None:
            environment = dict(environment or {"default": None, "overrides": {}})
            if environment.get("prompt_directives") not in (None, raw_unit["prompt_directives"]):
                raise E2EError("PROMPT_DIRECTIVES_CONFLICT")
            environment["prompt_directives"] = raw_unit["prompt_directives"]
        if environment is not None:
            unit["preprocessing"] = preprocessing.normalize_binding(environment, unit["harness"])
        unit["unit_id"] = raw_unit.get("unit_id") or unit["harness"] + "-" + digest(unit)[:12]
        identifier(unit["unit_id"], "unit_id")
        identifier(unit["template"], "template")
        units.append(unit)
    if len({unit["unit_id"] for unit in units}) != len(units):
        raise E2EError("UNIT_ID_DUPLICATE")
    plan["units"] = units
    return plan


def prepare_batch(repo: Path, workspace: Path, raw_plan: dict, *, expected_selection_sha256: str | None = None,
                  preprocess_asset_dir: Path | None = None, expected_preprocessing_sha256: str | None = None) -> Path:
    from .protocol import resolve
    repo, workspace = repo.resolve(strict=True), workspace.expanduser().resolve()
    plan, selected, members, general_manifest, web = resolve(repo, raw_plan)
    if expected_selection_sha256 and digest(selected) != expected_selection_sha256:
        raise E2EError("CONFIRMED_SELECTION_CHANGED")
    preprocessing_selection = preprocessing.selection(plan["units"], selected)
    if expected_preprocessing_sha256 is not None and preprocessing_selection.get("preprocessing_sha256") != expected_preprocessing_sha256:
        raise E2EError("PREPROCESS_SELECTION_DRIFT")
    batch = workspace / "batches" / plan["batch_id"]
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
            preprocessing.freeze_assets(plan["units"], preprocess_asset_dir, staging / "preprocess-assets")
            prepared = []
            for task in selected:
                identifier(task["task_id"], "task_id")
                dataset_key = task.get("dataset", {}).get("id") or task["metric_profile"]
                relative = f"inputs/{dataset_key}/tasks/{task['task_id']}"
                destination = inside(staging, relative)
                extra = (_write_general(task, members, destination, general_prepare) if task["scene"] == "general"
                         else _write_web(task, destination, repo, web))
                # Freeze before recording modes/hashes. In particular, Office
                # inputs must never be exposed as writable host replicas.
                _protect(destination)
                prompt = destination / "execution/PROMPT.md"
                row = {**task, **extra, "input_root": relative, "prompt_sha256": file_sha256(prompt),
                       "public_inventory": inventory(destination / "execution/workspace"),
                       "definition_inventory": inventory(destination)}
                # The root itself is not part of its inventory; briefly enable
                # only that directory to publish the descriptor, then reseal it.
                destination.chmod(destination.stat().st_mode | 0o200)
                try:
                    atomic_json(destination / "task-definition.json", row)
                    (destination / "task-definition.json").chmod(0o444)
                finally:
                    destination.chmod(destination.stat().st_mode & ~0o222)
                prepared.append(row)
            units, bindings = [], {}
            groups = sorted({(task["scene"], task["metric_profile"]) for task in prepared})
            for base in plan["units"]:
                for scenario, profile in groups:
                    unit = {**preprocessing.public_unit(base), "scene": scenario, "metric_profile": profile}
                    unit["unit_id"] = base["unit_id"] + "-" + scenario + "-" + digest(profile)[:6]
                    unit["task_ids"] = [task["task_id"] for task in prepared if (task["scene"], task["metric_profile"]) == (scenario, profile)]
                    units.append(unit)
                    if "preprocessing" in base:
                        bindings[unit["unit_id"]] = base["preprocessing"]
                    atomic_json(staging / "units" / unit["unit_id"] / "unit.json", unit)
            from .compatibility import freeze_assets
            compatibility = freeze_assets(repo, staging, prepared, general_manifest, members)
            manifest = {"schema": BATCH_SCHEMA, "created_at": utc_now(), "plan": preprocessing.public_plan(plan),
                        "source_revision": _revision(repo), "units": units, "tasks": prepared,
                        "engine": {"api_version": 1, "root": str(repo), "python": sys.executable,
                                   "revision": _revision(repo)},
                        "compatibility": compatibility}
            if preprocessing_selection:
                manifest["preprocessing_sha256"] = preprocessing_selection["preprocessing_sha256"]
                manifest["preprocessing_bindings_sha256"] = digest(bindings)
                atomic_json(staging / "preprocessing.json", bindings)
                (staging / "preprocessing.json").chmod(0o400)
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
                remove_temporary_tree(staging)
            raise
    return batch


def _revision(repo: Path) -> str:
    from src.release import release_revision
    return release_revision(repo)
