from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path


logger = logging.getLogger(__name__)

WEBSITE_CHECKS_DIR = Path(__file__).resolve().parents[2] / "eval" / "checks" / "website"
CONTAINER_CHECKS_DIR = "/tmp/_wildclaw_website_checks"
CONTAINER_AUDIT_DIR = "/tmp_workspace/.grading/website"
CONTAINER_EVAL_DIR = "/tmp_workspace_eval"
WEBSITE_TASK_WORKSPACE_DIR = (
    Path(__file__).resolve().parents[2]
    / "workspace" / "extension" / "07_Website_Generation"
)


def website_check_module_name(task_definition_id: str) -> str:
    match = re.search(r"(task_\d+_.+)$", task_definition_id)
    if not match:
        raise ValueError(f"Unsupported website task id: {task_definition_id}")
    return match.group(1)


def _parse_last_json(stdout: str) -> dict | None:
    for line in reversed(stdout.strip().splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def run_website_checks(
    container_name: str,
    task_definition_id: str,
    output_dir: Path,
    *,
    timeout_seconds: float,
) -> tuple[dict | None, str]:
    """Run the repository-owned website checker inside the task container."""
    module_name = website_check_module_name(task_definition_id)
    cleanup_result = subprocess.run(
        [
            "docker", "exec", container_name, "rm", "-rf",
            CONTAINER_CHECKS_DIR, CONTAINER_AUDIT_DIR,
        ],
        capture_output=True,
        text=True,
    )
    if cleanup_result.returncode != 0:
        return None, f"EVALUATOR_CLEANUP_FAILED: {cleanup_result.stderr.strip()}"
    # Copy evaluation-only fixtures only after the agent has finished.  They
    # stay outside /tmp_workspace, so the agent cannot inspect answer assets
    # during generation.
    eval_dir = WEBSITE_TASK_WORKSPACE_DIR / module_name / "eval"
    eval_cleanup = subprocess.run(
        ["docker", "exec", container_name, "rm", "-rf", CONTAINER_EVAL_DIR],
        capture_output=True,
        text=True,
    )
    if eval_cleanup.returncode != 0:
        return None, f"EVALUATOR_EVAL_CLEANUP_FAILED: {eval_cleanup.stderr.strip()}"
    if eval_dir.is_dir():
        eval_copy = subprocess.run(
            [
                "docker", "cp", f"{eval_dir}/.",
                f"{container_name}:{CONTAINER_EVAL_DIR}/",
            ],
            capture_output=True,
            text=True,
        )
        if eval_copy.returncode != 0:
            return None, f"EVALUATOR_EVAL_COPY_FAILED: {eval_copy.stderr.strip()}"
    copy_result = subprocess.run(
        ["docker", "cp", str(WEBSITE_CHECKS_DIR), f"{container_name}:{CONTAINER_CHECKS_DIR}"],
        capture_output=True,
        text=True,
    )
    if copy_result.returncode != 0:
        return None, f"EVALUATOR_COPY_FAILED: {copy_result.stderr.strip()}"

    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-e",
                "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
                container_name,
                "python3",
                f"{CONTAINER_CHECKS_DIR}/runner.py",
                "--task-module",
                module_name,
                "--task-id",
                task_definition_id,
                "--workspace",
                "/tmp_workspace",
                "--output",
                CONTAINER_AUDIT_DIR,
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return None, f"EVALUATOR_TIMEOUT: website checks exceeded {timeout_seconds:g}s"
    finally:
        audit_dir = output_dir / "website"
        audit_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["docker", "cp", f"{container_name}:{CONTAINER_AUDIT_DIR}/.", str(audit_dir)],
            capture_output=True,
            text=True,
        )

    payload = _parse_last_json(result.stdout)
    if payload is None:
        detail = (result.stderr or result.stdout).strip()[:1000]
        return None, f"EVALUATOR_INVALID_RESULT: {detail}"
    if result.returncode != 0 and payload.get("status") != "candidate_failed":
        return payload, str(payload.get("error") or result.stderr or "website checker failed")
    return payload, ""


def merge_website_evidence(
    rubric_criteria: list[dict],
    runtime_checks: dict,
    visual_scores: dict,
    *,
    llm_notes: str = "",
    runtime_status: str = "success",
    runtime_error: str = "",
) -> dict:
    """Merge runtime and visual evidence using the rubric's original weights.

    Build/start failures are candidate outcomes. Evaluator failures are
    framework validity failures. Both receive a placeholder zero without
    semantic fallback, while grading metadata keeps the attribution explicit.
    """
    candidate_failed = runtime_status == "candidate_failed"
    evaluator_failed = runtime_status == "evaluator_failed"
    runtime_unusable = candidate_failed or evaluator_failed
    criterion_scores: dict[str, float] = {}
    runtime_breakdown: dict[str, float] = {}
    visual_breakdown: dict[str, float] = {}
    missing_runtime: list[str] = []
    missing_visual: list[str] = []

    for criterion in rubric_criteria:
        key = str(criterion.get("key", ""))
        primary = str(criterion.get("primary", ""))
        if primary == "visual_layout":
            value = visual_scores.get(key)
            if not isinstance(value, (int, float)):
                value = 0.0
                missing_visual.append(key)
            value = max(0.0, min(1.0, float(value)))
            if runtime_unusable:
                value = 0.0
                missing_visual.append(key)
            visual_breakdown[key] = value
        else:
            raw = runtime_checks.get(key)
            value = raw.get("score") if isinstance(raw, dict) else raw
            if not isinstance(value, (int, float)):
                value = 0.0
                missing_runtime.append(key)
            value = max(0.0, min(1.0, float(value)))
            if runtime_unusable:
                value = 0.0
                missing_runtime.append(key)
            runtime_breakdown[key] = value
        criterion_scores[key] = value

    missing_runtime = list(dict.fromkeys(missing_runtime))
    missing_visual = list(dict.fromkeys(missing_visual))

    total_weight = sum(
        float(c.get("weight", 0.0))
        for c in rubric_criteria
        if isinstance(c.get("weight"), (int, float))
    )
    weighted = sum(
        criterion_scores.get(str(c.get("key", "")), 0.0) * float(c.get("weight", 0.0))
        for c in rubric_criteria
        if isinstance(c.get("weight"), (int, float))
    )
    overall = weighted / total_weight if total_weight > 0 else 0.0

    scores: dict = {
        **{f"automated.{key}": value for key, value in runtime_breakdown.items()},
        **{f"llm_judge.{key}": value for key, value in visual_breakdown.items()},
        "_grading": {
            "mode": "v2_website_dynamic",
            "status": runtime_status,
            "score_policy": (
                "candidate_failed_zero"
                if candidate_failed
                else "evaluator_failed_zero"
                if runtime_status == "evaluator_failed"
                else "runtime_evidence"
            ),
            "semantic_fallback": False,
            "runtime_error": runtime_error,
            "automated_score": (
                round(sum(runtime_breakdown.values()) / len(runtime_breakdown), 5)
                if runtime_breakdown else None
            ),
            "llm_judge_score": (
                round(sum(visual_breakdown.values()) / len(visual_breakdown), 5)
                if visual_breakdown else None
            ),
            "weights": {"criterion_weights": True},
            "missing_runtime_keys": missing_runtime,
            "missing_visual_keys": missing_visual,
        },
        "overall_score": round(overall, 4),
    }
    if llm_notes:
        scores["_grading"]["llm_notes"] = llm_notes

    from .grading import _aggregate_rubric_dimensions

    dimensions = _aggregate_rubric_dimensions(
        rubric_criteria,
        criterion_scores,
        metric_profile="web-site-gen",
        evidence_mode="browser_runtime+visual_llm",
    )
    if dimensions:
        scores["_dimensions"] = dimensions
    return scores
