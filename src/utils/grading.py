from __future__ import annotations

import json
import logging
import math
import os
import subprocess
import tempfile
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()
TMP_WORKSPACE = os.environ.get("TMP_WORKSPACE", "/tmp_workspace")

def _write_score(output_dir: Path, task_id: str, scores: dict) -> None:
    score_path = output_dir / "score.json"
    score_path.parent.mkdir(parents=True, exist_ok=True)
    score_path.write_text(
        json.dumps(scores, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("[%s] Grading results written to → %s", task_id, score_path)


def _error_score(output_dir: Path, task_id: str, message: str) -> dict:
    scores = {"overall_score": 0.0, "error": message}
    _write_score(output_dir, task_id, scores)
    return scores


def _grading_error(
    output_dir: Path,
    task_id: str,
    message: str,
    write_error_score: bool,
) -> dict:
    if write_error_score:
        return _error_score(output_dir, task_id, message)
    return {"error": message}


def write_error_score(output_dir: Path, task_id: str, message: str) -> dict:
    return _error_score(output_dir, task_id, message)


def run_grading(
    task_id: str,
    automated_checks: str,
    output_dir: Path,
    extra_env: str = "",
    lobster_env: list[str] | None = None,
    transcript_container_path: str = "",
    write_error_score: bool = False,
    *,
    llm_judge_rubric: str = "",
    rubric_criteria: list[dict] | None = None,
    grading_weights: dict | None = None,
) -> dict:
    """Dispatch grading by task format.

    - v2 (has parsed rubric_criteria): run rule checks and the declarative LLM
      rubric separately, then weight-combine (see _grade_* helpers below).
    - legacy (no rubric section): exec the single grade() function verbatim.

    The presence of `rubric_criteria` is the only switch; existing tasks have
    none and therefore keep their exact prior behaviour.
    """
    if rubric_criteria:
        return _run_grading_v2(
            task_id=task_id,
            automated_checks=automated_checks,
            output_dir=output_dir,
            extra_env=extra_env,
            lobster_env=lobster_env,
            transcript_container_path=transcript_container_path,
            write_error_score=write_error_score,
            llm_judge_rubric=llm_judge_rubric,
            rubric_criteria=rubric_criteria,
            grading_weights=grading_weights or {},
        )
    return _run_grading_legacy(
        task_id,
        automated_checks,
        output_dir,
        extra_env=extra_env,
        lobster_env=lobster_env,
        transcript_container_path=transcript_container_path,
        write_error_score=write_error_score,
    )


def _run_grading_legacy(
    task_id: str,
    automated_checks: str,
    output_dir: Path,
    extra_env: str = "",
    lobster_env: list[str] | None = None,
    transcript_container_path: str = "",
    write_error_score: bool = False,
) -> dict:
    """Legacy grading path: exec the task's single grade() function verbatim.

    Behaviour is byte-for-byte the pre-v2 run_grading. Tasks with no
    `## LLM Judge Rubric` section route here (see run_grading dispatcher),
    so all 60 existing tasks are unaffected.
    """
    logger.info("[%s] Starting in-container grading...", task_id)

    loader_src = Path(__file__).with_name("transcript_loader.py")
    if not loader_src.exists():
        logger.error("[%s] transcript loader module not found: %s", task_id, loader_src)
        return _grading_error(
            output_dir,
            task_id,
            f"transcript loader module not found: {loader_src}",
            write_error_score,
        )

    shim_src = Path(__file__).with_name("judge_shim.py")

    runner_code = "\n".join([
        "import json",
        # Route inline `openai` judge calls whose model is `anthropic/*` to the
        # Anthropic Messages API (judge endpoint). Non-fatal if unavailable.
        "try:",
        "    import _judge_shim; _judge_shim.install()",
        "except Exception as _shim_exc:",
        "    import sys as _sys; print('judge_shim install failed:', _shim_exc, file=_sys.stderr)",
        "from _transcript_loader import load_transcript",
        f"_transcript = load_transcript({json.dumps(transcript_container_path)})",
        "",
        automated_checks,
        "",
        f'result = grade(transcript=_transcript, workspace_path="{TMP_WORKSPACE}")',
        "print(json.dumps(result))",
    ]) + "\n"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(runner_code)
        runner_host = f.name

    try:
        r_loader = subprocess.run(
            ["docker", "cp", str(loader_src), f"{task_id}:/tmp/_transcript_loader.py"],
            capture_output=True, text=True,
        )
        if r_loader.returncode != 0:
            logger.error("[%s] docker cp transcript loader failed: %s", task_id, r_loader.stderr)
            return _grading_error(
                output_dir,
                task_id,
                f"docker cp transcript loader failed: {r_loader.stderr}",
                write_error_score,
            )

        if shim_src.exists():
            r_shim = subprocess.run(
                ["docker", "cp", str(shim_src), f"{task_id}:/tmp/_judge_shim.py"],
                capture_output=True, text=True,
            )
            if r_shim.returncode != 0:
                logger.warning("[%s] docker cp judge shim failed: %s", task_id, r_shim.stderr)
        else:
            logger.warning("[%s] judge shim module not found: %s", task_id, shim_src)

        r = subprocess.run(
            ["docker", "cp", runner_host, f"{task_id}:/tmp/_grade_runner.py"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            logger.error("[%s] docker cp failed: %s", task_id, r.stderr)
            return _grading_error(
                output_dir,
                task_id,
                f"docker cp failed: {r.stderr}",
                write_error_score,
            )

        env_args: list[str] = []
        for line in extra_env.splitlines():
            key = line.strip()
            if not key or key.startswith("#"):
                continue
            value = os.environ.get(key, "")
            env_args += ["-e", f"{key}={value}"]
            masked = (value[:4] + "***") if value else "(empty)"
            logger.info("[%s] Injecting grading env: %s=%s", task_id, key, masked)

        for key in (lobster_env or []):
            value = os.environ.get(key, "")
            if not value:
                logger.warning("[%s] Grading lobster env key %s not found, skipping", task_id, key)
                continue
            env_args += ["-e", f"{key}={value}"]
            masked = value[:4] + "***"
            logger.info("[%s] Injecting grading lobster env: %s=%s", task_id, key, masked)

        # Judge routing: expose the Anthropic-format judge endpoint to the
        # in-container judge_shim (see src/utils/judge_shim.py). These are not
        # part of a task's `## Env` section, so inject them explicitly whenever
        # set on the host. JUDGE_MODEL is re-injected here as a safety net in
        # case a task omits it from its `## Env` list.
        for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL", "JUDGE_MODEL"):
            value = os.environ.get(key, "").strip()
            if not value:
                continue
            env_args += ["-e", f"{key}={value}"]
            masked = (value[:4] + "***") if key.endswith("KEY") else value
            logger.info("[%s] Injecting grading judge env: %s=%s", task_id, key, masked)

        r = subprocess.run(
            ["docker", "exec", *env_args, task_id, "python3", "/tmp/_grade_runner.py"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            logger.error("[%s] Grading script execution failed: %s", task_id, r.stderr)
            return _grading_error(
                output_dir,
                task_id,
                f"grade script failed: {r.stderr}",
                write_error_score,
            )

        try:
            scores = json.loads(r.stdout.strip())
        except json.JSONDecodeError:
            scores = None
            for line in reversed(r.stdout.strip().splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        scores = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            if scores is None:
                logger.error("[%s] Failed to parse grading result, no valid JSON found in stdout\nstdout: %s", task_id, r.stdout[:500])
                return _grading_error(
                    output_dir,
                    task_id,
                    "json parse failed: no valid JSON in stdout",
                    write_error_score,
                )

    finally:
        Path(runner_host).unlink(missing_ok=True)

    _write_score(output_dir, task_id, scores)
    return scores


# ===========================================================================
# v2 grading: separated rule checks + declarative LLM rubric
# ===========================================================================

_ALLOWED_RUBRIC_SCORES = frozenset({0.0, 0.25, 0.5, 0.75, 1.0})


def _exec_container_grade(
    task_id: str,
    automated_checks: str,
    extra_env: str,
    lobster_env: list[str] | None,
    transcript_container_path: str,
) -> tuple[dict | None, str]:
    """Run a task's rule-only grade() inside its container.

    Returns (scores_dict, error_msg). On success error_msg is "". Reuses the
    same loader/shim/docker-exec machinery as the legacy path, but returns the
    parsed dict instead of writing score.json (the v2 combiner writes once).
    """
    loader_src = Path(__file__).with_name("transcript_loader.py")
    if not loader_src.exists():
        return None, f"transcript loader module not found: {loader_src}"
    shim_src = Path(__file__).with_name("judge_shim.py")

    runner_code = "\n".join([
        "import json",
        "try:",
        "    import _judge_shim; _judge_shim.install()",
        "except Exception as _shim_exc:",
        "    import sys as _sys; print('judge_shim install failed:', _shim_exc, file=_sys.stderr)",
        "from _transcript_loader import load_transcript",
        f"_transcript = load_transcript({json.dumps(transcript_container_path)})",
        "",
        automated_checks,
        "",
        f'result = grade(transcript=_transcript, workspace_path="{TMP_WORKSPACE}")',
        "print(json.dumps(result))",
    ]) + "\n"

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(runner_code)
        runner_host = f.name

    try:
        r_loader = subprocess.run(
            ["docker", "cp", str(loader_src), f"{task_id}:/tmp/_transcript_loader.py"],
            capture_output=True, text=True,
        )
        if r_loader.returncode != 0:
            return None, f"docker cp transcript loader failed: {r_loader.stderr}"
        if shim_src.exists():
            subprocess.run(
                ["docker", "cp", str(shim_src), f"{task_id}:/tmp/_judge_shim.py"],
                capture_output=True, text=True,
            )
        r = subprocess.run(
            ["docker", "cp", runner_host, f"{task_id}:/tmp/_grade_runner.py"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None, f"docker cp failed: {r.stderr}"

        env_args = _build_grading_env_args(task_id, extra_env, lobster_env)
        r = subprocess.run(
            ["docker", "exec", *env_args, task_id, "python3", "/tmp/_grade_runner.py"],
            capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            return None, f"grade script failed: {r.stderr}"
        scores = _parse_grade_stdout(r.stdout)
        if scores is None:
            return None, "json parse failed: no valid JSON in stdout"
        return scores, ""
    finally:
        Path(runner_host).unlink(missing_ok=True)


def _build_grading_env_args(
    task_id: str, extra_env: str, lobster_env: list[str] | None
) -> list[str]:
    """Assemble `-e KEY=VALUE` docker args for grading (task env + judge routing)."""
    env_args: list[str] = []
    for line in extra_env.splitlines():
        key = line.strip()
        if not key or key.startswith("#"):
            continue
        value = os.environ.get(key, "")
        env_args += ["-e", f"{key}={value}"]
        masked = (value[:4] + "***") if value else "(empty)"
        logger.info("[%s] Injecting grading env: %s=%s", task_id, key, masked)
    for key in (lobster_env or []):
        value = os.environ.get(key, "")
        if not value:
            continue
        env_args += ["-e", f"{key}={value}"]
    for key in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
                "JUDGE_MODEL", "OPENROUTER_API_KEY", "OPENROUTER_BASE_URL"):
        value = os.environ.get(key, "").strip()
        if value:
            env_args += ["-e", f"{key}={value}"]
    return env_args


def _parse_grade_stdout(stdout: str) -> dict | None:
    """Extract the last valid JSON object from grade runner stdout."""
    try:
        return json.loads(stdout.strip())
    except json.JSONDecodeError:
        for line in reversed(stdout.strip().splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
    return None


def _combine_v2(
    auto_score: float | None,
    auto_breakdown: dict,
    llm_score: float,
    llm_breakdown: dict,
    llm_notes: str,
    grading_weights: dict,
) -> dict:
    """Weight-combine rule and LLM sub-scores into a v2 score.json dict.

    If a task has no rule part (auto_score is None), the LLM score is used
    directly (weight collapses to LLM-only). Breakdown keys are prefixed by
    source so the report tool and capability map can reference stable keys.
    """
    w_auto = float(grading_weights.get("automated", 0.5))
    w_llm = float(grading_weights.get("llm_judge", 0.5))

    if auto_score is None:
        overall = llm_score
        w_auto = 0.0
    else:
        total_w = w_auto + w_llm
        if total_w <= 0:
            w_auto = w_llm = 0.5
            total_w = 1.0
        overall = (auto_score * w_auto + llm_score * w_llm) / total_w

    scores: dict = {}
    for k, v in auto_breakdown.items():
        scores[f"automated.{k}"] = v
    for k, v in llm_breakdown.items():
        scores[f"llm_judge.{k}"] = v
    scores["_grading"] = {
        "mode": "v2_hybrid" if auto_score is not None else "v2_llm_only",
        "automated_score": round(auto_score, 5) if auto_score is not None else None,
        "llm_judge_score": round(llm_score, 5),
        "weights": {"automated": w_auto, "llm_judge": w_llm},
    }
    if llm_notes:
        scores["_grading"]["llm_notes"] = llm_notes
    scores["overall_score"] = round(max(0.0, min(1.0, overall)), 4)
    return scores


def _exec_container_python(
    task_id: str, runner_code: str, transcript_container_path: str,
) -> tuple[dict | None, str]:
    """Copy loader+shim+runner into the container, exec, return parsed JSON.

    Generic sibling of _exec_container_grade for judge runners (which read the
    transcript and call the judge shim). Returns (parsed_dict, error_msg).
    """
    loader_src = Path(__file__).with_name("transcript_loader.py")
    shim_src = Path(__file__).with_name("judge_shim.py")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as f:
        f.write(runner_code)
        runner_host = f.name
    try:
        if loader_src.exists():
            subprocess.run(
                ["docker", "cp", str(loader_src), f"{task_id}:/tmp/_transcript_loader.py"],
                capture_output=True, text=True,
            )
        if shim_src.exists():
            subprocess.run(
                ["docker", "cp", str(shim_src), f"{task_id}:/tmp/_judge_shim.py"],
                capture_output=True, text=True,
            )
        r = subprocess.run(
            ["docker", "cp", runner_host, f"{task_id}:/tmp/_judge_runner.py"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return None, f"docker cp judge runner failed: {r.stderr}"
        env_args = _build_grading_env_args(task_id, "", None)
        r = subprocess.run(
            ["docker", "exec", *env_args, task_id, "python3", "/tmp/_judge_runner.py"],
            capture_output=True, text=True, timeout=180,
        )
        if r.returncode != 0:
            return None, f"judge runner failed: {r.stderr}"
        parsed = _parse_grade_stdout(r.stdout)
        if parsed is None:
            return None, "judge returned no valid JSON"
        return parsed, ""
    finally:
        Path(runner_host).unlink(missing_ok=True)


def _normalize_rubric_score(value: object) -> float | None:
    """Return a canonical five-level rubric score, or reject the value.

    Judge criteria use a discrete scale. Values outside the scale are rejected
    instead of rounded or clamped so malformed judge output cannot receive
    unintended partial credit. ``bool`` is rejected explicitly because it is
    a subclass of ``int`` in Python.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        score = float(value)
    except (OverflowError, ValueError):
        return None
    if not math.isfinite(score) or score not in _ALLOWED_RUBRIC_SCORES:
        return None
    return score


def _align_rubric_scores(
    task_id: str, raw: dict, rubric_criteria: list[dict],
) -> tuple[float, dict, str]:
    """Map judge-returned scores onto canonical keys (defensive alignment)."""
    raw_scores = raw.get("scores", {}) if isinstance(raw, dict) else {}
    if not isinstance(raw_scores, dict):
        raw_scores = {}
    raw_items = list(raw_scores.items())
    breakdown: dict = {}
    for i, crit in enumerate(rubric_criteria):
        key = crit["key"]
        val = None
        if key in raw_scores:                      # 1. exact match
            val = raw_scores[key]
        elif i < len(raw_items):                   # 2. positional fallback
            got_key, got_val = raw_items[i]
            val = got_val
            logger.warning(
                "[%s] judge key mismatch: expected '%s', using positional '%s'",
                task_id, key, got_key,
            )
        score = _normalize_rubric_score(val)
        if score is not None:
            breakdown[key] = score
        else:                                      # 3. unresolved/invalid -> 0
            breakdown[key] = 0.0
            if val is None:
                logger.error("[%s] judge missing criterion '%s', scored 0.0", task_id, key)
            else:
                logger.error(
                    "[%s] judge returned invalid score %r for criterion '%s'; "
                    "allowed scores are 1, 0.75, 0.5, 0.25, 0; scored 0.0",
                    task_id, val, key,
                )

    total_w = sum(c["weight"] for c in rubric_criteria)
    if total_w > 0:
        score = sum(breakdown[c["key"]] * c["weight"] for c in rubric_criteria) / total_w
    else:
        score = sum(breakdown.values()) / len(breakdown) if breakdown else 0.0
    notes = str(raw.get("notes", "")) if isinstance(raw, dict) else ""
    return score, breakdown, notes


def _build_rubric_judge_prompt(rubric_criteria: list[dict], rubric_text: str) -> str:
    """Judge prompt that forces scores under the author-defined canonical keys."""
    keys = [c["key"] for c in rubric_criteria]
    keys_json = ", ".join(f'"{k}": 0.0' for k in keys)
    return (
        "You are a strict grading assistant. Score the agent's performance "
        "against the rubric below, using the agent transcript as evidence.\n\n"
        "Return ONLY a JSON object, no prose, no code fences, in EXACTLY this shape:\n"
        f'{{"scores": {{{keys_json}}}, "notes": "<brief reason>"}}\n\n'
        f"CRITICAL: the \"scores\" object MUST contain EXACTLY these keys: {keys}\n"
        "Do NOT rename, translate, omit, or add keys. Each criterion score MUST be "
        "exactly one of these five numeric values: 1, 0.75, 0.5, 0.25, or 0. "
        "Do not return any other score; invalid values are rejected and scored as 0.\n\n"
        "## Grading Rubric\n"
        f"{rubric_text}\n"
    )


def _grade_llm_rubric(
    task_id: str,
    rubric_text: str,
    rubric_criteria: list[dict],
    transcript_container_path: str,
) -> tuple[float, dict, str]:
    """Run the declarative LLM rubric in-container; align to canonical keys.

    Returns (llm_score, breakdown_by_canonical_key, notes). llm_score is the
    weight-normalised mean of criterion scores. Key alignment is defensive:
    exact match -> positional fallback (warn) -> 0.0 + error, never silently
    dropping a criterion.
    """
    prompt = _build_rubric_judge_prompt(rubric_criteria, rubric_text)
    judge_model = os.environ.get("JUDGE_MODEL", "openai/gpt-5.4")

    # In-container judge runner: reads transcript + agent-produced text
    # artifacts (rubrics commonly grade output files like results.md, not just
    # the transcript), calls the judge via the OpenAI shim, prints raw JSON.
    ws_reader = (
        "_ws = Path(%s)\n"
        "_files = []\n"
        "_exts = ('.md','.txt','.json','.csv','.py','.yaml','.yml','.html')\n"
        "if _ws.is_dir():\n"
        "    for _p in sorted(_ws.rglob('*')):\n"
        "        if not (_p.is_file() and _p.suffix.lower() in _exts):\n"
        "            continue\n"
        "        if 'gt' in _p.relative_to(_ws).parts:\n"  # skip ground-truth
        "            continue\n"
        "        try:\n"
        "            _c = _p.read_text(encoding='utf-8', errors='ignore')[:8000]\n"
        "        except Exception:\n"
        "            continue\n"
        "        _files.append('### ' + str(_p.relative_to(_ws)) + '\\n' + _c)\n"
        "        if len(_files) >= 12:\n"
        "            break\n"
        "_ws_text = '\\n\\n'.join(_files)\n"
    ) % json.dumps(TMP_WORKSPACE)

    runner_code = (
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "try:\n"
        "    import _judge_shim; _judge_shim.install()\n"
        "except Exception as _e:\n"
        "    print('judge_shim install failed:', _e, file=sys.stderr)\n"
        "from _transcript_loader import load_transcript\n"
        f"_t = load_transcript({json.dumps(transcript_container_path)})\n"
        "_summary = json.dumps(_t, ensure_ascii=False)[:20000]\n"
        + ws_reader +
        "from openai import OpenAI\n"
        "client = OpenAI(api_key=os.environ.get('OPENROUTER_API_KEY',''),"
        " base_url=os.environ.get('OPENROUTER_BASE_URL',''))\n"
        f"_prompt = {json.dumps(prompt)}\n"
        "_msg = _prompt + '\\n\\n## Agent Workspace Files\\n' + _ws_text"
        " + '\\n\\n## Agent Transcript (JSON)\\n' + _summary\n"
        "try:\n"
        f"    resp = client.chat.completions.create(model={json.dumps(judge_model)},"
        " max_tokens=800, messages=[{'role':'user','content':_msg}],"
        " response_format={'type':'json_object'})\n"
        "    print(resp.choices[0].message.content)\n"
        "except Exception as _e:\n"
        "    print(json.dumps({'scores': {}, 'notes': 'judge_call_failed: ' + str(_e)}))\n"
    )

    raw, err = _exec_container_python(task_id, runner_code, transcript_container_path)
    if err:
        logger.error("[%s] LLM rubric judge failed: %s", task_id, err)
        # all criteria -> 0, so failure is visible (and score-impacting)
        return 0.0, {c["key"]: 0.0 for c in rubric_criteria}, f"judge failed: {err}"

    return _align_rubric_scores(task_id, raw, rubric_criteria)


def _run_grading_v2(
    *,
    task_id: str,
    automated_checks: str,
    output_dir: Path,
    extra_env: str,
    lobster_env: list[str] | None,
    transcript_container_path: str,
    write_error_score: bool,
    llm_judge_rubric: str,
    rubric_criteria: list[dict],
    grading_weights: dict,
) -> dict:
    """v2 path: rule checks + declarative LLM rubric, weight-combined.

    Produces a score.json where rule checkpoints are prefixed `automated.`
    and LLM criteria `llm_judge.` (canonical keys), plus a `_grading` block
    recording sub-scores and weights. overall_score is the weighted mean.
    """
    logger.info("[%s] Starting v2 grading (rules + rubric)...", task_id)

    # ---- rule part (optional; may be empty for pure-LLM tasks) ----
    auto_score, auto_breakdown = 0.0, {}
    has_rules = bool(automated_checks.strip())
    if has_rules:
        raw, err = _exec_container_grade(
            task_id, automated_checks, extra_env, lobster_env,
            transcript_container_path,
        )
        if err:
            logger.error("[%s] v2 rule grading failed: %s", task_id, err)
            return _grading_error(output_dir, task_id, err, write_error_score)
        auto_breakdown = {k: v for k, v in raw.items()
                          if isinstance(v, (int, float)) and k != "overall_score"}
        auto_score = raw.get("overall_score")
        if not isinstance(auto_score, (int, float)):
            auto_score = (sum(auto_breakdown.values()) / len(auto_breakdown)
                          if auto_breakdown else 0.0)

    # ---- LLM rubric part ----
    llm_score, llm_breakdown, llm_notes = _grade_llm_rubric(
        task_id, llm_judge_rubric, rubric_criteria, transcript_container_path,
    )

    # ---- combine ----
    scores = _combine_v2(
        auto_score if has_rules else None, auto_breakdown,
        llm_score, llm_breakdown, llm_notes, grading_weights,
    )
    _write_score(output_dir, task_id, scores)
    return scores


def format_scores(task_id: str, scores: dict) -> str:
    if "error" in scores and not any(
        isinstance(v, (int, float)) for v in scores.values()
    ):
        return f"[{task_id}] Grading error: {scores['error']}"
    lines = [f"\n{'='*60}", f"  {task_id}", f"{'='*60}"]

    for k, v in scores.items():
        if isinstance(v, (int, float)):
            bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
            lines.append(f"  {bar} {v:.2f}  {k}")

    lines.append("=" * 60)
    return "\n".join(lines)

def print_summary(results: list[dict], category: str, output_dir: Path, model_name: str) -> None:
    print(f"\n{'#'*60}")
    print(f"  Summary Report — {category}")
    print(f"{'#'*60}")

    all_scores: dict[str, float] = {}
    for r in results:
        task_id = r["task_id"]
        scores = r['scores']
        if not scores:
            if r.get("error"):
                print(f"  ✗ {task_id}: {r['error']}")
            else:
                print(f"  - {task_id}: No scores")
            continue
        numeric_dict = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
        
        if not numeric_dict:
            if "error" in scores:
                print(f"  ✗ {task_id}: Grading error {scores['error']}")
            else:
                print(f"  - {task_id}: No valid numeric scores")
            continue

        avg = sum(numeric_dict.values()) / len(numeric_dict)
        status = "!" if r.get("error") or scores.get("error") else "✓"
        note = ""
        if r.get("error"):
            note = f" agent_error={r['error']}"
        elif scores.get("error"):
            note = f" grading_error={scores['error']}"
        print(f"  {status} {task_id}: avg {avg:.2f}  ({len(numeric_dict)} items){note}")

        final_score_val = numeric_dict.get('overall_score', avg)
        all_scores[task_id] = final_score_val

    if all_scores:
        print(f"\n  Final scores per task:")
        for k, score in sorted(all_scores.items()):
            bar = "█" * int(score * 10) + "░" * (10 - int(score * 10))
            print(f"    {bar} {score:.2f}  {k}")

    print(f"\n  Token usage and cost per task:")
    print(f"    {'Task ID':<55} {'Output Tokens':>12} {'Cost(USD)':>12}")
    print(f"    {'-'*55} {'-'*12} {'-'*12}")
    total_output_tokens = 0
    total_cost_usd = 0.0
    for r in sorted(results, key=lambda x: x["task_id"]):
        usage = r.get("usage", {})
        out_tok = usage.get("output_tokens", 0)
        cost = usage.get("cost_usd", 0.0)
        total_output_tokens += out_tok
        total_cost_usd += cost
        print(f"    {r['task_id']:<55} {out_tok:>12} {cost:>11.4f}$")
    print(f"    {'Total':<55} {total_output_tokens:>12} {total_cost_usd:>11.4f}$")

    summary_path = output_dir / category / f"summary_{model_name}.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n  Summary written to → {summary_path}")
    print("#" * 60)

def extract_usage_from_jsonl(jsonl_path: Path) -> dict:
    totals = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
        "total_tokens": 0,
        "cost_usd": 0.0,
        "request_count": 0,
    }
    if not jsonl_path.exists():
        return totals
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "message":
            continue
        msg = entry.get("message", {})
        if msg.get("role") != "assistant":
            continue
        totals["request_count"] += 1
        usage = msg.get("usage", {})
        totals["input_tokens"]       += usage.get("input",       0)
        totals["output_tokens"]      += usage.get("output",      0)
        totals["cache_read_tokens"]  += usage.get("cacheRead",   0)
        totals["cache_write_tokens"] += usage.get("cacheWrite",  0)
        totals["total_tokens"]       += usage.get("totalTokens", 0)
        cost = usage.get("cost", {})
        totals["cost_usd"] += cost.get("total", 0.0)
    totals["cost_usd"] = round(totals["cost_usd"], 6)
    return totals

def print_global_summary(results: list[dict], output_dir: Path, model_name: str) -> None:
    from src.utils.multirun_stats import aggregate_runs
    from eval.run_batch import PASS_THRESHOLD

    print(f"\n{'#'*60}")
    print(f"  Global Summary Report — ALL CATEGORIES")
    print(f"{'#'*60}")

    # 按 task_id_ori 分组（多轮下同一任务有多个 result）
    grouped: dict[str, list[dict]] = {}
    for r in results:
        tid_ori = r.get("task_id_ori", r["task_id"])  # 兼容旧 result 无 task_id_ori
        grouped.setdefault(tid_ori, []).append(r)

    total_tasks = len(grouped)
    scored_tasks = 0
    missing_score_tasks = 0
    total_score = 0.0

    # 多轮统计（runs > 1 时）
    per_task_stats: dict[str, dict] = {}
    runs_per_task = max((len(runs) for runs in grouped.values()), default=1)

    for tid_ori, runs in grouped.items():
        # 收集有效 overall_score
        scores_list = []
        for r in runs:
            scores = r.get("scores", {})
            numeric = {
                k: v
                for k, v in scores.items()
                if isinstance(v, (int, float))
            } if scores else {}
            if not numeric:
                continue
            # 提取 overall_score
            final = numeric.get("overall_score", sum(numeric.values()) / len(numeric) if numeric else 0)
            scores_list.append(final)

        if not scores_list:
            missing_score_tasks += 1
            continue

        # 单轮/多轮分支
        if runs_per_task > 1:
            stats = aggregate_runs(scores_list, PASS_THRESHOLD)
            per_task_stats[tid_ori] = stats
            total_score += stats["mean"]
            scored_tasks += 1
        else:
            # 单轮：直接取值（保持现有逻辑）
            total_score += scores_list[0]
            scored_tasks += 1

    global_avg = 0.0
    if total_tasks > 0:
        global_avg = total_score / total_tasks
        bar = "█" * int(global_avg * 10) + "░" * (10 - int(global_avg * 10))
        print(f"\n  Completed tasks: {scored_tasks} / {total_tasks}")
        print(f"  Tasks without a valid score.json: {missing_score_tasks}")
        if missing_score_tasks > 0:
            print("  Possible causes: task execution failed, such as OOM, or grading failed.")
        print(f"  Global average: {bar} {global_avg:.4f}")
        if runs_per_task > 1:
            print(f"  Runs per task: {runs_per_task}")
    else:
        print("  No tasks found")

    total_out_tok = sum(r.get("usage", {}).get("output_tokens", 0) for r in results)
    total_cost    = sum(r.get("usage", {}).get("cost_usd",      0.0) for r in results)
    print(f"  Total output tokens: {total_out_tok}   Total cost: ${total_cost:.4f}")

    # 构建 summary JSON
    summary_data = {
        "global_avg": global_avg if total_tasks else None,
        "task_count": total_tasks,
        "scored_task_count": scored_tasks,
        "missing_score_task_count": missing_score_tasks,
        "results": results,
    }

    # 多轮时追加 multirun 段
    if runs_per_task > 1 and per_task_stats:
        # 宏观统计：mean_of_means / mean_pass_at_k / mean_pass_hat_k
        mean_pass_at_k = sum(s["pass_at_k"] for s in per_task_stats.values()) / len(per_task_stats)
        mean_pass_hat_k = sum(s["pass_hat_k"] for s in per_task_stats.values()) / len(per_task_stats)
        summary_data["multirun"] = {
            "runs_per_task": runs_per_task,
            "pass_threshold": PASS_THRESHOLD,
            "per_task": per_task_stats,
            "macro": {
                "mean_of_means": global_avg,  # 已经是跨 task 的 mean
                "mean_pass_at_k": mean_pass_at_k,
                "mean_pass_hat_k": mean_pass_hat_k,
            }
        }

    summary_path = output_dir / f"summary_all_{model_name}.json"
    summary_path.write_text(
        json.dumps(summary_data, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    print(f"\n  Global summary written to → {summary_path}")
    print("#" * 60)
