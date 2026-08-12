#!/usr/bin/env python3
"""检查 WildClawBench 一轮原始评测结果的完整性、环境异常与可比性。"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import fmean

import yaml

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT))

from src.utils.anomalies import scan_run_dir  # noqa: E402
from src.utils.run_selection import select_effective_run_dirs  # noqa: E402
from src.utils.tool_metrics import parse_tool_metrics  # noqa: E402
try:
    from src.agents.codex.runner import CodexAgent  # noqa: E402
except ImportError:  # 非 Codex 部署环境仍可执行其它检查
    CodexAgent = None

SUITE_RE = re.compile(r"^\d{2}_")
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|ak)-[A-Za-z0-9_-]{8,}", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}", re.I),
    re.compile(
        r"(?i)(\b(?:[A-Z0-9]+_)*(?:API[_-]?KEY|ACCESS[_-]?TOKEN|PASSWORD|PASSWD|SECRET)"
        r"\b\s*[:=]\s*[\"']?)[^\s\"',\]]+"
    ),
    re.compile(r"(?i)(\b(?:api[_-]?key|access[_-]?token|password|passwd|secret)\b\s*[:=]\s*[\"']?)[^\s\"']+"),
)


def load_json(path: Path) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"无法读取：{exc}"
    except json.JSONDecodeError as exc:
        return None, f"JSON 解析失败：{exc}"
    return (data, None) if isinstance(data, dict) else (None, "顶层不是 JSON object")


def read_text(path: Path, max_bytes: int = 4_000_000) -> str:
    try:
        with path.open("rb") as stream:
            return stream.read(max_bytes).decode("utf-8", errors="replace")
    except OSError:
        return ""


def is_unit_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if any(path.glob("summary_all_*.json")):
        return True
    for suite in path.iterdir():
        if suite.is_dir() and SUITE_RE.match(suite.name):
            return any(task.is_dir() for task in suite.iterdir())
    return False


def discover_units(root: Path) -> list[tuple[str, str, Path]]:
    """发现双层或三层布局的 (model, harness, unit_dir)。"""
    units: list[tuple[str, str, Path]] = []

    def walk(path: Path, depth: int) -> None:
        if is_unit_dir(path):
            units.append((path.parent.name, path.name, path))
            return
        if depth >= 3:
            return
        for child in sorted(path.iterdir()):
            if child.is_dir() and child.name not in {"report-workspace", "output"}:
                walk(child, depth + 1)

    walk(root, 0)
    dedup = {str(path.resolve()): (model, harness, path) for model, harness, path in units}
    return sorted(dedup.values(), key=lambda item: (item[0], item[1], str(item[2])))


def round_root_from_units(result_root: Path, units: list[tuple[str, str, Path]]) -> Path:
    """从双层或三层 unit 反推 round 根，保证产物集中到 round 工作区。"""
    roots = set()
    for _, _, unit_dir in units:
        # 三层布局：<round>/<harness>/<model>/<harness>，首尾 harness 重复。
        if unit_dir.parent.parent.name == unit_dir.name:
            roots.add(unit_dir.parents[2].resolve())
        else:
            roots.add(unit_dir.parents[1].resolve())
    return next(iter(roots)) if len(roots) == 1 else result_root.resolve()


def find_tasks_dir(explicit: str | None) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        return path if path.is_dir() else None
    candidate = REPO_ROOT / "tasks"
    return candidate if candidate.is_dir() else None


def expected_tasks(tasks_dir: Path | None) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    if tasks_dir is None:
        return result
    roots = [tasks_dir]
    extension_root = tasks_dir / "extension"
    if extension_root.is_dir():
        roots.append(extension_root)
    task_files: list[Path] = []
    for root in roots:
        for suite in sorted(root.iterdir()):
            if suite.is_dir() and SUITE_RE.match(suite.name):
                task_files.extend(suite.glob("*.md"))
    ignored: set[str] = set()
    if task_files:
        try:
            check = subprocess.run(
                ["git", "check-ignore", "--stdin"], cwd=REPO_ROOT,
                input="\n".join(str(path.resolve()) for path in task_files) + "\n",
                capture_output=True, text=True, timeout=10,
            )
            if check.returncode in {0, 1}:
                ignored = {line.strip() for line in check.stdout.splitlines() if line.strip()}
        except (OSError, subprocess.SubprocessError):
            pass
    for path in task_files:
        if str(path.resolve()) in ignored:
            continue
        result.setdefault(path.parent.name, set()).add(path.stem)
    return result


def extension_tasks(tasks_dir: Path | None) -> set[tuple[str, str]]:
    if tasks_dir is None or not (tasks_dir / "extension").is_dir():
        return set()
    expected = expected_tasks(tasks_dir / "extension")
    return {(suite, task) for suite, tasks in expected.items() for task in tasks}


def task_filter_metadata(
    tasks_dir: Path | None,
    expected: set[tuple[str, str]],
) -> dict[tuple[str, str], dict[str, object]]:
    """读取完整性检查需要的任务筛选字段，不解析任务正文。"""
    if tasks_dir is None:
        return {}
    result: dict[tuple[str, str], dict[str, object]] = {}
    for root in (tasks_dir, tasks_dir / "extension"):
        if not root.is_dir():
            continue
        for suite_dir in sorted(root.iterdir()):
            if not suite_dir.is_dir() or not SUITE_RE.match(suite_dir.name):
                continue
            for path in suite_dir.glob("*.md"):
                key = (suite_dir.name, path.stem)
                if key not in expected:
                    continue
                content = read_text(path)
                frontmatter = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
                if not frontmatter:
                    continue
                try:
                    metadata = yaml.safe_load(frontmatter.group(1)) or {}
                except yaml.YAMLError:
                    continue
                if not isinstance(metadata, dict):
                    continue
                raw_tags = metadata.get("tags") or []
                if isinstance(raw_tags, str):
                    raw_tags = raw_tags.split(",")
                elif not isinstance(raw_tags, (list, tuple, set)):
                    raw_tags = [raw_tags]
                result[key] = {
                    "modality": str(metadata.get("modality") or "").strip(),
                    "tags": {str(tag).strip().lower() for tag in raw_tags if str(tag).strip()},
                }
    return result


def _parse_logged_tags(raw: str) -> set[str]:
    try:
        values = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return set()
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(value).strip().lower() for value in values if str(value).strip()}


def expected_tasks_for_unit(
    expected: set[tuple[str, str]],
    metadata: dict[tuple[str, str], dict[str, object]],
    run_log: str,
    evaluation_scope: dict | None = None,
) -> tuple[set[tuple[str, str]], bool]:
    """按结构化计划范围或历史 run.log 还原 unit 的预期任务集合。"""
    if (
        isinstance(evaluation_scope, dict)
        and evaluation_scope.get("schema_version") == 1
    ):
        planned = evaluation_scope.get("planned_tasks")
        if isinstance(planned, list):
            scoped = {
                (str(item.get("category") or ""), str(item.get("task_id") or ""))
                for item in planned
                if isinstance(item, dict)
                and str(item.get("category") or "")
                and str(item.get("task_id") or "")
            }
            return scoped, True

    filters: dict[str, dict[str, object]] = defaultdict(dict)
    selected_categories = {
        match.group(1)
        for match in re.finditer(
            r"Category:\s*(\S+),\s*\d+\s+tasks(?:\s|$)", run_log
        )
    }
    for match in re.finditer(
        r"Modality filter '([^']+)'\s*:\s*\d+/\d+ tasks kept in (\S+)", run_log,
    ):
        filters[match.group(2)]["modality"] = match.group(1)
    for match in re.finditer(
        r"Tag filter \(any of (\[[^\]]*\])\)\s*:\s*\d+/\d+ tasks kept in (\S+)",
        run_log,
    ):
        filters[match.group(2)]["include_tags"] = _parse_logged_tags(match.group(1))
    for match in re.finditer(
        r"Exclude-tag filter \(none of (\[[^\]]*\])\)\s*:\s*\d+/\d+ tasks kept in (\S+)",
        run_log,
    ):
        filters[match.group(2)]["exclude_tags"] = _parse_logged_tags(match.group(1))

    if not filters and not selected_categories:
        return set(expected), False

    filtered: set[tuple[str, str]] = set()
    for key in expected:
        if selected_categories and key[0] not in selected_categories:
            continue
        suite_filter = filters.get(key[0])
        task = metadata.get(key)
        if not suite_filter or task is None:
            filtered.add(key)
            continue
        modality = suite_filter.get("modality")
        tags = task.get("tags") if isinstance(task.get("tags"), set) else set()
        include_tags = suite_filter.get("include_tags")
        exclude_tags = suite_filter.get("exclude_tags")
        if modality and task.get("modality") != modality:
            continue
        if isinstance(include_tags, set) and include_tags and not (include_tags & tags):
            continue
        if isinstance(exclude_tags, set) and exclude_tags & tags:
            continue
        filtered.add(key)
    return filtered, True


def iter_json_objects(raw: str):
    decoder = json.JSONDecoder()
    index = 0
    while index < len(raw):
        while index < len(raw) and raw[index].isspace():
            index += 1
        if index >= len(raw):
            return
        try:
            value, end = decoder.raw_decode(raw, index)
        except json.JSONDecodeError:
            next_line = raw.find("\n", index)
            if next_line < 0:
                return
            index = next_line + 1
            continue
        yield value
        index = end


def transcript_path(run_dir: Path) -> Path | None:
    existing = None
    for name in ("chat_openclaw.jsonl", "chat.jsonl"):
        path = run_dir / name
        if path.is_file():
            existing = existing or path
            if path.stat().st_size > 0:
                return path
    return existing


def fallback_request_count(run_dir: Path) -> int | None:
    """runner 不可导入时，从原始 usage 事件保守估算模型往返次数。"""
    path = run_dir / "chat.jsonl"
    if not path.is_file():
        return None
    per_turn = 0
    assistant_messages = 0
    cumulative_totals: list[int] = []
    for entry in iter_json_objects(read_text(path)):
        if not isinstance(entry, dict):
            continue
        payload = entry.get("payload") or entry.get("item") or entry.get("message")
        candidates = [entry]
        if isinstance(payload, dict):
            candidates.append(payload)
        if any(obj.get("role") == "assistant" for obj in candidates):
            assistant_messages += 1
        found_per_turn = False
        for obj in candidates:
            for key in ("last_token_usage", "lastTokenUsage", "usage", "token_usage", "tokenUsage"):
                value = obj.get(key)
                if isinstance(value, dict) and any(k in value for k in ("total_tokens", "totalTokens", "input_tokens")):
                    found_per_turn = True
            info = obj.get("info")
            if isinstance(info, dict):
                last = info.get("last_token_usage") or info.get("lastTokenUsage")
                if isinstance(last, dict):
                    found_per_turn = True
                total = info.get("total_token_usage") or info.get("totalTokenUsage")
                if isinstance(total, dict):
                    raw_total = total.get("total_tokens", total.get("totalTokens", 0))
                    if isinstance(raw_total, (int, float)):
                        cumulative_totals.append(int(raw_total))
        if found_per_turn:
            per_turn += 1
        if str(entry.get("type", "")).lower() in {"token_count", "tokencount"}:
            for value in entry.values():
                if isinstance(value, dict):
                    raw_total = value.get("total_tokens", value.get("totalTokens"))
                    if isinstance(raw_total, (int, float)):
                        cumulative_totals.append(int(raw_total))
    if per_turn:
        return per_turn
    if cumulative_totals:
        advancing = sum(1 for index, value in enumerate(cumulative_totals)
                        if index == 0 or value > cumulative_totals[index - 1])
        return advancing or assistant_messages or 1
    return assistant_messages or None


def independent_request_count(run_dir: Path) -> int | None:
    """按 runner 当前权威解析逻辑从原始事件重算请求数。"""
    if CodexAgent is None:
        return fallback_request_count(run_dir)
    agent = CodexAgent.__new__(CodexAgent)
    parsed = agent._extract_usage_from_jsonl(run_dir / "chat.jsonl")
    if parsed["total_tokens"] == 0 and parsed["input_tokens"] == 0:
        session_dir = run_dir / "astroncode_sessions"
        if session_dir.is_dir():
            parsed = agent._extract_usage_from_session_dir(session_dir)
    value = parsed.get("request_count")
    return int(value) if isinstance(value, (int, float)) and value > 0 else None


def redact(value):
    """递归清理日志和错误文本中的常见凭证，路径与普通结构保持不变。"""
    if isinstance(value, str):
        result = value
        for pattern in SECRET_PATTERNS:
            result = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", result)
        return result
    if isinstance(value, dict):
        return {key: redact(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def finding(rule_id: str, severity: str, message: str, *, unit: str = "",
            task_id: str = "", run_dir: str = "", attribution: str = "evaluation_framework",
            evidence=None,
            recommendation: str = "") -> dict:
    return {
        "id": rule_id,
        "severity": severity,
        "unit": unit,
        "task_id": task_id,
        "run_dir": run_dir,
        "attribution": attribution,
        "message": redact(message),
        "evidence": redact(evidence if evidence is not None else {}),
        "recommendation": redact(recommendation),
    }


def classify_run_anomaly(item: dict, status: dict) -> tuple[str, str, str]:
    """直接消费 anomalies v2 结论；旧 item 统一要求按当前规则重扫。"""
    validity_impact = item.get("validity_impact")
    if validity_impact in {"fail", "review", "none"}:
        severity = {"fail": "error", "review": "warning", "none": "info"}[validity_impact]
        attribution = str(item.get("attribution") or "undetermined")
        action = item.get("rerun_action")
        if action == "required_after_fix":
            recommendation = "修复评测框架或运行环境后重跑受影响用例。"
        elif action == "review_first":
            recommendation = "先依据结构化证据完成人工归因，再决定是否重跑。"
        else:
            recommendation = "作为模型/Harness 运行结果保留并在报告中披露。"
        return severity, attribution, recommendation
    return (
        "warning",
        "undetermined",
        "该 item 缺少 anomalies v2 归因字段；从原始产物按当前 ruleset 重新扫描。",
    )


def scan_round(result_root: Path, tasks_dir: Path | None,
               models: set[str] | None = None,
               harnesses: set[str] | None = None) -> dict:
    units = discover_units(result_root)
    if models:
        units = [unit for unit in units if unit[0] in models]
    if harnesses:
        units = [unit for unit in units if unit[1] in harnesses]
    findings: list[dict] = []
    expected = expected_tasks(tasks_dir)
    expected_flat = {(suite, task) for suite, tasks in expected.items() for task in tasks}
    extension_flat = extension_tasks(tasks_dir)
    filter_metadata = task_filter_metadata(tasks_dir, expected_flat)
    unit_data: dict[str, dict] = {}
    env_hits_by_task: dict[tuple[str, str], list[tuple[str, str, bool]]] = defaultdict(list)
    transcript_hashes: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    if not units:
        findings.append(finding("NO_UNITS", "error", "未发现任何评测结果 unit",
                                recommendation="检查 --result-root 是否指向 round/model/unit 目录。"))

    for model, harness, unit_dir in units:
        unit = f"{model}@{harness}"
        if unit in unit_data:
            findings.append(finding("DUPLICATE_UNIT", "error", f"unit 标签重复：{unit}", unit=unit,
                                    evidence={"paths": [unit_data[unit]["path"], str(unit_dir)]}))
            unit = f"{unit}#{len(unit_data) + 1}"
        actual: set[tuple[str, str]] = set()
        task_records: dict[str, dict] = {}
        versions: Counter[str] = Counter()
        images: Counter[str] = Counter()
        scores_for_summary: list[float] = []

        for suite_dir in sorted(unit_dir.iterdir()):
            if not suite_dir.is_dir() or not SUITE_RE.match(suite_dir.name):
                continue
            for task_dir in sorted(path for path in suite_dir.iterdir() if path.is_dir()):
                task_id = task_dir.name
                task_key = f"{suite_dir.name}/{task_id}"
                actual.add((suite_dir.name, task_id))
                all_run_dirs = sorted(path for path in task_dir.iterdir() if path.is_dir())
                if not all_run_dirs:
                    findings.append(finding("NO_RUN", "error", "任务目录下没有 run", unit=unit,
                                            task_id=task_id, run_dir=str(task_dir)))
                    continue
                run_dirs = select_effective_run_dirs(all_run_dirs, scan_run_dir)
                run_scores: list[float] = []
                task_records[task_key] = {
                    "run_count": len(run_dirs),
                    "all_run_count": len(all_run_dirs),
                    "ignored_run_count": len(all_run_dirs) - len(run_dirs),
                    "timeouts": [],
                    "runs": [],
                }
                for run_dir in run_dirs:
                    status, status_error = load_json(run_dir / "execution_status.json")
                    usage, usage_error = load_json(run_dir / "usage.json")
                    score, score_error = load_json(run_dir / "score.json")
                    status = status or {}
                    usage = usage or {}
                    score = score or {}
                    path_text = str(run_dir)
                    anomaly = scan_run_dir(run_dir)
                    anomaly_attributions = {
                        item.get("attribution") for item in anomaly.get("items", [])
                    }
                    for filename, error in (("execution_status.json", status_error),
                                            ("usage.json", usage_error), ("score.json", score_error)):
                        if not error or filename == "score.json":
                            continue
                        if filename == "usage.json" and anomaly_attributions & {"model", "harness"}:
                            findings.append(finding(
                                "RESULT_FILE_INVALID", "warning",
                                f"{filename} 缺失或不可解析：{error}", unit=unit,
                                task_id=task_id, run_dir=path_text, attribution="undetermined",
                                recommendation="被测组合已前置失败；确认 usage 缺失是否符合 Harness 退出路径。",
                            ))
                        else:
                            findings.append(finding("RESULT_FILE_INVALID", "error",
                                                    f"{filename} 缺失或不可解析：{error}", unit=unit,
                                                    task_id=task_id, run_dir=path_text))
                    transcript = transcript_path(run_dir)
                    if transcript is not None and transcript.stat().st_size > 0:
                        digest = hashlib.sha256(transcript.read_bytes()).hexdigest()
                        transcript_hashes[digest].append((unit, task_key, path_text))

                    for item in anomaly.get("items", []):
                        severity, attribution, recommendation = classify_run_anomaly(item, status)
                        findings.append(finding(item.get("id", "RUN_ANOMALY"), severity,
                                                item.get("description", "run 异常"), unit=unit,
                                                task_id=task_id, run_dir=path_text,
                                                attribution=attribution,
                                                evidence=item.get("evidence"),
                                                recommendation=recommendation))
                        if (
                            item.get("attribution") == "evaluation_environment"
                            and item.get("validity_impact") == "fail"
                        ):
                            env_hits_by_task[(task_key, item.get("id", "ENVIRONMENT_FAILURE"))].append(
                                (unit, path_text, True)
                            )

                    raw_score = score.get("overall_score")
                    if isinstance(raw_score, (int, float)) and math.isfinite(float(raw_score)):
                        run_scores.append(float(raw_score))
                        if not 0 <= float(raw_score) <= 1:
                            findings.append(finding("SCORE_OUT_OF_RANGE", "error",
                                                    f"overall_score={raw_score} 不在 [0,1]", unit=unit,
                                                    task_id=task_id, run_dir=path_text))
                    elif score and not score.get("error"):
                        findings.append(finding("OVERALL_SCORE_INVALID", "error", "overall_score 缺失或非有限数",
                                                unit=unit, task_id=task_id, run_dir=path_text))

                    if status.get("harness") and status.get("harness") != harness:
                        findings.append(finding("HARNESS_ID_MISMATCH", "error",
                                                "目录 harness 与 execution_status.harness 不一致", unit=unit,
                                                task_id=task_id, run_dir=path_text,
                                                evidence={"path": harness, "status": status.get("harness")}))
                    if status.get("timed_out") and status.get("status") == "finished":
                        findings.append(finding("STATUS_CONTRADICTION", "error",
                                                "timed_out=true 但 status=finished", unit=unit,
                                                task_id=task_id, run_dir=path_text))
                    if status.get("harness_version"):
                        versions[str(status["harness_version"])] += 1
                    if status.get("image"):
                        images[str(status["image"])] += 1
                    task_records[task_key]["timeouts"].append(status.get("timeout_seconds"))

                    for key in ("total_tokens", "input_tokens", "output_tokens", "request_count",
                                "elapsed_time", "cost_usd"):
                        value = usage.get(key)
                        if value is not None and (not isinstance(value, (int, float)) or value < 0):
                            findings.append(finding("USAGE_VALUE_INVALID", "error",
                                                    f"usage.{key}={value!r} 非法", unit=unit,
                                                    task_id=task_id, run_dir=path_text))
                    independent = independent_request_count(run_dir) if harness in {"codex", "astroncode"} else None
                    recorded = usage.get("request_count")
                    if independent and isinstance(recorded, (int, float)) and recorded != independent:
                        ratio = max(independent, recorded) / max(1, min(independent, recorded))
                        severity = "error" if ratio >= 2 else "warning"
                        findings.append(finding("REQUEST_COUNT_DRIFT", severity,
                                                "usage.request_count 与原始 usage 事件重算不一致", unit=unit,
                                                task_id=task_id, run_dir=path_text,
                                                evidence={"recorded": recorded, "recomputed": independent,
                                                          "ratio": round(ratio, 2)},
                                                recommendation="先 dry-run reparse_codex_usage.py，确认后修正并重生成报告。"))
                    metrics = parse_tool_metrics(transcript, harness)
                    tool_total = metrics.get("total", 0)
                    if isinstance(recorded, (int, float)) and recorded > 0 and tool_total / recorded > 5:
                        findings.append(finding("TOOL_REQUEST_RATIO_HIGH", "warning",
                                                "工具调用数显著高于模型请求数，需核对 request_count 口径",
                                                unit=unit, task_id=task_id, run_dir=path_text,
                                                evidence={"tool_calls": tool_total, "requests": recorded,
                                                          "ratio": round(tool_total / recorded, 2)}))

                    status_elapsed = status.get("elapsed_time")
                    usage_elapsed = usage.get("elapsed_time")
                    if isinstance(status_elapsed, (int, float)) and isinstance(usage_elapsed, (int, float)):
                        delta = abs(status_elapsed - usage_elapsed)
                        if delta > max(60, status_elapsed * 0.2):
                            findings.append(finding("ELAPSED_TIME_DRIFT", "warning",
                                                    "execution_status 与 usage 的耗时差异较大", unit=unit,
                                                    task_id=task_id, run_dir=path_text,
                                                    evidence={"status": status_elapsed, "usage": usage_elapsed}))

                    hit_ids = {
                        item.get("id") for item in anomaly.get("items", [])
                        if item.get("attribution") == "evaluation_environment"
                        and item.get("validity_impact") == "fail"
                    }
                    task_records[task_key]["runs"].append({
                        "run_dir": path_text,
                        "score": raw_score,
                        "status": status.get("status"),
                        "timed_out": bool(status.get("timed_out")),
                        "environment_signals": sorted(hit_ids),
                    })
                if run_scores:
                    scores_for_summary.append(fmean(run_scores))

        run_log = read_text(unit_dir / "run.log")
        evaluation_scope, _scope_error = load_json(unit_dir / "evaluation_scope.json")
        unit_expected, has_logged_filters = expected_tasks_for_unit(
            expected_flat, filter_metadata, run_log, evaluation_scope,
        )
        declares_extension = "official + extension" in run_log.lower()
        if (
            extension_flat
            and not has_logged_filters
            and not declares_extension
            and not (actual & extension_flat)
        ):
            unit_expected = expected_flat - extension_flat
        if unit_expected:
            for suite, task_id in sorted(unit_expected - actual):
                findings.append(finding("TASK_MISSING", "error", f"缺少任务 {suite}/{task_id}",
                                        unit=unit, task_id=task_id,
                                        recommendation="补跑缺失任务后再比较或出报告。"))
            for suite, task_id in sorted(actual - unit_expected):
                findings.append(finding("TASK_UNEXPECTED", "warning", f"出现任务定义外的结果 {suite}/{task_id}",
                                        unit=unit, task_id=task_id))

        summary_files = sorted(unit_dir.glob("summary_all_*.json"))
        if not summary_files:
            findings.append(finding("SUMMARY_MISSING", "warning", "缺少 summary_all_*.json", unit=unit))
        else:
            summary, summary_error = load_json(summary_files[0])
            if summary_error:
                findings.append(finding("SUMMARY_INVALID", "error", summary_error, unit=unit))
            else:
                summary = summary or {}
                if summary.get("task_count") is not None and summary.get("task_count") != len(actual):
                    findings.append(finding("SUMMARY_TASK_COUNT_MISMATCH", "error",
                                            "summary.task_count 与目录扫描数不一致", unit=unit,
                                            evidence={"summary": summary.get("task_count"), "scanned": len(actual)}))
                recomputed = sum(scores_for_summary) / len(actual) if actual else 0.0
                if isinstance(summary.get("global_avg"), (int, float)) and abs(summary["global_avg"] - recomputed) > 0.005:
                    findings.append(finding("SUMMARY_SCORE_MISMATCH", "error",
                                            "summary.global_avg 与 run 分数重算不一致", unit=unit,
                                            evidence={"summary": summary["global_avg"],
                                                      "recomputed": round(recomputed, 6)}))
        if len(versions) > 1:
            findings.append(finding("HARNESS_VERSION_MIXED", "error", "同一 unit 混用了多个 harness 版本",
                                    unit=unit, evidence=dict(versions)))
        if len(images) > 1:
            findings.append(finding("CONTAINER_IMAGE_MIXED", "warning", "同一 unit 混用了多个容器镜像",
                                    unit=unit, evidence=dict(images)))

        unit_data[unit] = {
            "path": str(unit_dir),
            "model": model,
            "harness": harness,
            "task_count": len(actual),
            "tasks": task_records,
            "harness_versions": dict(versions),
            "images": dict(images),
        }

    # 跨 unit 公平性与共因检查。
    task_sets = {unit: set(data["tasks"]) for unit, data in unit_data.items()}
    if task_sets:
        union = set().union(*task_sets.values())
        intersection = set.intersection(*task_sets.values())
        if union != intersection:
            findings.append(finding("UNIT_TASK_SET_MISMATCH", "error", "各 unit 任务集合不一致",
                                    evidence={unit: len(tasks) for unit, tasks in task_sets.items()},
                                    recommendation="只在共同任务集上临时比较，并补跑缺失任务。"))
        for task_key in sorted(intersection):
            run_counts = {unit: data["tasks"][task_key]["run_count"] for unit, data in unit_data.items()}
            if len(set(run_counts.values())) > 1:
                findings.append(finding("RUN_COUNT_MISMATCH", "error", f"{task_key} 的评测轮数不一致",
                                        evidence=run_counts))
            timeouts = {}
            for unit, data in unit_data.items():
                values = {value for value in data["tasks"][task_key]["timeouts"] if value is not None}
                timeouts[unit] = sorted(values)
            normalized = {tuple(values) for values in timeouts.values()}
            if len(normalized) > 1:
                findings.append(finding("TIMEOUT_CONFIG_MISMATCH", "warning",
                                        f"{task_key} 在各 unit 的 timeout 配置不一致", evidence=timeouts))

    unit_count = len(unit_data)
    for (task_key, env_id), hits in sorted(env_hits_by_task.items()):
        affected_units = sorted({unit for unit, _, _ in hits})
        if unit_count >= 2 and len(affected_units) >= max(2, math.ceil(unit_count * 0.5)):
            findings.append(finding("COMMON_MODE_ENV_SIGNAL", "warning",
                                    f"{task_key} 在多数 unit 出现相同的 {env_id} 信号，仅作为共因调查线索",
                                    task_id=task_key.split("/", 1)[-1],
                                    attribution="undetermined",
                                    evidence={"affected_units": affected_units,
                                              "affected_runs": sorted({path for _, path, _ in hits}),
                                              "unit_count": unit_count, "signal": env_id},
                                    recommendation="结合代理、网关或宿主机直接证据确认是否属于共享环境共因。"))

    for digest, occurrences in transcript_hashes.items():
        task_keys = {task_key for _, task_key, _ in occurrences}
        if len(task_keys) > 1:
            findings.append(finding("DUPLICATE_TRANSCRIPT", "error", "不同任务共享完全相同的执行轨迹",
                                    evidence={"sha256": digest[:12], "occurrences": occurrences}))

    counts = Counter(item["severity"] for item in findings)
    verdict = "FAIL" if counts["error"] else ("REVIEW" if counts["warning"] else "PASS")
    findings.sort(key=lambda item: (SEVERITY_ORDER[item["severity"]], item["id"],
                                    item["unit"], item["task_id"], item["run_dir"]))
    return {
        "schema_version": 2,
        "check_type": "eval_result_validity",
        "result_root": str(result_root),
        "tasks_dir": str(tasks_dir) if tasks_dir else "",
        "scope": {
            "models": sorted(models or {model for model, _, _ in units}),
            "harnesses": sorted(harnesses or {harness for _, harness, _ in units}),
        },
        "verdict": verdict,
        "summary": {"units": len(unit_data), "errors": counts["error"],
                    "warnings": counts["warning"], "info": counts["info"],
                    "findings": len(findings)},
        "units": unit_data,
        "findings": findings,
    }


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# WildClawBench 评测结果有效性检查",
        "",
        f"- 结论：**{report['verdict']}**",
        f"- 结果根目录：`{report['result_root']}`",
        f"- 单元数：{summary['units']}",
        f"- 问题：error {summary['errors']} / warning {summary['warnings']} / info {summary['info']}",
        "",
        "## 门禁解释",
        "",
        "- `PASS`：未发现评测框架、数据或共因环境问题；可包含不影响门禁的模型/Harness 运行结果。",
        "- `REVIEW`：存在无法自动区分责任层的运行或环境信号；归因完成前不应直接发布结论。",
        "- `FAIL`：存在确定的评测框架、数据完整性、口径或共因环境故障；修复后再出报告。",
        "",
        "## 检查结果",
        "",
        "| 级别 | 归因 | 规则 | Unit | 用例 | 说明 | 处置 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in report["findings"]:
        clean = lambda value: str(value or "-").replace("|", "\\|").replace("\n", " ")
        lines.append("| " + " | ".join([
            clean(item["severity"]), clean(item.get("attribution")), clean(item["id"]), clean(item["unit"]),
            clean(item["task_id"]), clean(item["message"]), clean(item["recommendation"]),
        ]) + " |")
    if not report["findings"]:
        lines.append("| info | - | NONE | - | - | 未发现异常 | - |")
    lines += ["", "## Unit 概览", "", "| Unit | 任务数 | Harness版本 | 容器镜像 |",
              "|---|---:|---|---|"]
    for unit, data in sorted(report["units"].items()):
        lines.append(f"| {unit} | {data['task_count']} | {', '.join(data['harness_versions']) or '-'} "
                     f"| {', '.join(data['images']) or '-'} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 WildClawBench 评测结果有效性")
    parser.add_argument("--result-root", required=True, help="round/model/unit 结果目录")
    parser.add_argument("--tasks-dir", help="任务定义目录（默认仓库 tasks/）")
    parser.add_argument("--models", nargs="+", help="仅检查指定模型原始 ID")
    parser.add_argument("--harnesses", nargs="+", help="仅检查指定 Harness 原始 ID")
    parser.add_argument("--output-dir", help="默认 <round>/report-workspace/validity")
    parser.add_argument("--fail-on", choices=("never", "fail", "review"), default="never",
                        help="控制非零退出：never（默认）/fail/任意 review")
    args = parser.parse_args()

    result_root = Path(args.result_root).expanduser().resolve()
    if not result_root.is_dir():
        parser.error(f"结果目录不存在：{result_root}")
    tasks_dir = find_tasks_dir(args.tasks_dir)
    models = set(args.models or [])
    harnesses = set(args.harnesses or [])
    report = scan_round(result_root, tasks_dir, models or None, harnesses or None)
    scoped_units = discover_units(result_root)
    if models:
        scoped_units = [unit for unit in scoped_units if unit[0] in models]
    if harnesses:
        scoped_units = [unit for unit in scoped_units if unit[1] in harnesses]
    round_root = round_root_from_units(result_root, scoped_units)
    output_dir = (Path(args.output_dir).expanduser() if args.output_dir else
                  round_root / "report-workspace" / "validity")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "eval_result_validity.json"
    md_path = output_dir / "eval_result_validity.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(f"结论: {report['verdict']} | error={report['summary']['errors']} "
          f"warning={report['summary']['warnings']} | units={report['summary']['units']}")
    print(f"VALIDITY_JSON={json_path.resolve()}")
    print(f"VALIDITY_REPORT={md_path.resolve()}")
    if args.fail_on == "review" and report["verdict"] in {"REVIEW", "FAIL"}:
        return 2
    if args.fail_on == "fail" and report["verdict"] == "FAIL":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
