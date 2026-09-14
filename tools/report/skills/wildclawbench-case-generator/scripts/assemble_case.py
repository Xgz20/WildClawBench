#!/usr/bin/env python3
"""Assemble and register one generic WildClawBench v2 evaluation case."""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

import yaml


CATEGORIES = (
    "01_Productivity_Flow",
    "02_Code_Intelligence",
    "03_Social_Interaction",
    "04_Search_Retrieval",
    "05_Creative_Synthesis",
    "06_Safety_Alignment",
)
CAPABILITIES = {
    "code_generation",
    "tool_use",
    "data_processing",
    "retrieval_verification",
    "reasoning_planning",
    "content_generation",
    "verification_delivery",
}
SPECIALIZED_TAGS = {"web-site-gen", "ppt"}
GRADING_TYPES = {"automated", "llm_judge", "hybrid"}
DIFFICULTIES = {"L1", "L2", "L3", "L4"}
MODALITIES = {"pure-text", "multimodal"}
STABLE_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TASK_ID_RE = re.compile(
    r"^(?P<category>0[1-6]_[A-Za-z_]+)_task_(?P<number>\d{1,3})_(?P<slug>[a-z0-9_]+)$"
)


class SpecError(ValueError):
    """The case specification violates the generic v2 contract."""


class _IndentedSafeDumper(yaml.SafeDumper):
    """Keep sequence indentation aligned with the repository's YAML style."""

    def increase_indent(self, flow: bool = False, indentless: bool = False):
        return super().increase_indent(flow, False)


def _dump_yaml(value: Any) -> str:
    return yaml.dump(
        value,
        Dumper=_IndentedSafeDumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )


def find_repo_root(start: Path | None = None) -> Path:
    """Find a WildClawBench checkout from cwd first, then from this script."""

    starts = [start or Path.cwd(), Path(__file__).resolve()]
    visited: set[Path] = set()
    for initial in starts:
        current = initial.resolve()
        if current.is_file():
            current = current.parent
        for candidate in (current, *current.parents):
            if candidate in visited:
                continue
            visited.add(candidate)
            if (
                (candidate / "tasks" / "TASK_TEMPLATE_v2.md").is_file()
                and (candidate / "src" / "utils" / "task_parser.py").is_file()
                and (candidate / "tasks" / "extension" / "task_sources.yaml").is_file()
            ):
                return candidate
    raise SpecError(
        "无法定位 WildClawBench 仓库根目录；请在仓库内运行或传入 --repo-root"
    )


def _require_mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SpecError(f"{name} 必须是 JSON object")
    return value


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpecError(f"{name} 必须是非空字符串")
    return value.strip()


def _safe_relative_path(value: Any, name: str) -> Path:
    text = _require_text(value, name).replace("\\", "/")
    path = PurePosixPath(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise SpecError(f"{name} 必须是安全的相对路径: {text!r}")
    return Path(*path.parts)


def _normalize_criteria(value: Any, name: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SpecError(f"{name} 必须是数组")
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(value, 1):
        item = _require_mapping(raw, f"{name}[{index}]")
        key = _require_text(item.get("key"), f"{name}[{index}].key")
        description = _require_text(
            item.get("description"), f"{name}[{index}].description"
        )
        if not STABLE_KEY_RE.fullmatch(key) or key == "overall_score":
            raise SpecError(f"{name}[{index}].key 不是合法稳定 key: {key!r}")
        if key in seen:
            raise SpecError(f"{name} 存在重复 key: {key}")
        seen.add(key)
        result.append({"key": key, "description": description})
    return result


def _normalize_rubric(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SpecError("llm_judge_rubric 必须是数组")
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_weight = 0.0
    for index, raw in enumerate(value, 1):
        item = _require_mapping(raw, f"llm_judge_rubric[{index}]")
        unknown = set(item) - {"key", "name", "weight", "description", "levels"}
        if unknown:
            raise SpecError(
                f"llm_judge_rubric[{index}] 含不支持字段: {sorted(unknown)}"
            )
        key = _require_text(item.get("key"), f"llm_judge_rubric[{index}].key")
        if not STABLE_KEY_RE.fullmatch(key) or key == "overall_score":
            raise SpecError(f"Rubric key 非法: {key!r}")
        if key in seen:
            raise SpecError(f"Rubric key 重复: {key}")
        seen.add(key)
        name = _require_text(item.get("name"), f"llm_judge_rubric[{index}].name")
        description = _require_text(
            item.get("description"), f"llm_judge_rubric[{index}].description"
        )
        weight = item.get("weight")
        if isinstance(weight, bool) or not isinstance(weight, (int, float)):
            raise SpecError(f"llm_judge_rubric[{index}].weight 必须是数字")
        weight = float(weight)
        if not 0 < weight <= 1:
            raise SpecError(f"llm_judge_rubric[{index}].weight 必须在 (0, 1] 内")
        levels = item.get("levels")
        if not isinstance(levels, list) or len(levels) < 2:
            raise SpecError(f"llm_judge_rubric[{index}].levels 至少包含两个档位")
        normalized_levels: list[dict[str, Any]] = []
        scores: set[float] = set()
        for level_index, raw_level in enumerate(levels, 1):
            level = _require_mapping(
                raw_level, f"llm_judge_rubric[{index}].levels[{level_index}]"
            )
            score = level.get("score")
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise SpecError("Rubric level score 必须是 0~1 数字")
            score = float(score)
            if not 0 <= score <= 1 or score in scores:
                raise SpecError("Rubric level score 必须唯一且位于 0~1")
            scores.add(score)
            level_description = _require_text(
                level.get("description"),
                f"llm_judge_rubric[{index}].levels[{level_index}].description",
            )
            normalized_levels.append(
                {"score": score, "description": level_description}
            )
        if 1.0 not in scores or 0.0 not in scores:
            raise SpecError("每个 Rubric criterion 必须包含 1.0 和 0.0 档位")
        normalized_levels.sort(key=lambda entry: entry["score"], reverse=True)
        result.append(
            {
                "key": key,
                "name": name,
                "weight": weight,
                "description": description,
                "levels": normalized_levels,
            }
        )
        total_weight += weight
    if result and abs(total_weight - 1.0) > 1e-6:
        raise SpecError(f"Rubric 权重之和必须为 1.0，当前为 {total_weight:g}")
    return result


def _grade_keys(code: str) -> set[str]:
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        raise SpecError(f"automated_checks Python 语法错误: {exc.msg}") from exc
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "grade"
    ]
    if not functions:
        raise SpecError("automated_checks 必须定义 grade()")
    grade = functions[0]
    named_args = {argument.arg for argument in grade.args.args + grade.args.kwonlyargs}
    if grade.args.kwarg is None and not {"transcript", "workspace_path"}.issubset(named_args):
        raise SpecError(
            "grade() 必须接受 **kwargs，或同时接受 transcript 与 workspace_path"
        )
    blocked_imports = {"anthropic", "httpx", "openai", "requests", "socket", "urllib"}
    for node in ast.walk(grade):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name.split(".", 1)[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module.split(".", 1)[0]]
        blocked = sorted(set(names) & blocked_imports)
        if blocked:
            raise SpecError(
                f"Automated Checks 禁止导入网络或 LLM 客户端: {blocked}"
            )
    keys: set[str] = set()
    for node in ast.walk(functions[0]):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and STABLE_KEY_RE.fullmatch(node.value)
        ):
            keys.add(node.value)
    return keys


def _normalize_string_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SpecError(f"{name} 必须是字符串数组")
    result: list[str] = []
    for index, raw in enumerate(value, 1):
        text = _require_text(raw, f"{name}[{index}]")
        if text in result:
            raise SpecError(f"{name} 存在重复项: {text}")
        result.append(text)
    return result


def _normalize_copy_items(
    value: Any, name: str, spec_dir: Path, size_limit_mb: int
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise SpecError(f"{name} 必须是数组")
    items: list[dict[str, Any]] = []
    occupied: set[Path] = set()
    byte_limit = size_limit_mb * 1024 * 1024
    for index, raw in enumerate(value, 1):
        item = _require_mapping(raw, f"{name}[{index}]")
        unknown = set(item) - {"source", "target"}
        if unknown:
            raise SpecError(f"{name}[{index}] 含不支持字段: {sorted(unknown)}")
        source_text = _require_text(item.get("source"), f"{name}[{index}].source")
        source = Path(source_text).expanduser()
        if not source.is_absolute():
            source = (spec_dir / source).resolve()
        else:
            source = source.resolve()
        if not source.exists():
            raise SpecError(f"{name}[{index}] 源文件不存在: {source}")
        if source.is_symlink():
            raise SpecError(f"{name}[{index}] 不接受符号链接源: {source}")
        target_raw = item.get("target") or source.name
        target = _safe_relative_path(target_raw, f"{name}[{index}].target")
        if target in occupied or any(
            target in previous.parents or previous in target.parents for previous in occupied
        ):
            raise SpecError(f"{name} 目标路径冲突: {target.as_posix()}")
        occupied.add(target)
        files = [source] if source.is_file() else sorted(source.rglob("*"))
        for file_path in files:
            if file_path.is_symlink():
                raise SpecError(f"{name}[{index}] 目录中含符号链接: {file_path}")
            if file_path.is_file() and file_path.stat().st_size > byte_limit:
                raise SpecError(
                    f"{name}[{index}] 文件超过 {size_limit_mb} MiB: {file_path}"
                )
        items.append({"source": source, "target": target})
    return items


def _normalize_source(value: Any) -> dict[str, Any]:
    source = _require_mapping(value, "source")
    unknown = set(source) - {"design_origin", "runtime_sources"}
    if unknown:
        raise SpecError(f"source 含不支持字段: {sorted(unknown)}")
    origin = _require_mapping(source.get("design_origin"), "source.design_origin")
    required = (
        "type",
        "verification_status",
        "human_authorship",
        "request_summary",
        "adaptation_note",
    )
    normalized_origin: dict[str, Any] = {
        key: _require_text(origin.get(key), f"source.design_origin.{key}")
        for key in required
    }
    references = origin.get("references", [])
    if not isinstance(references, list) or not all(
        isinstance(item, dict) for item in references
    ):
        raise SpecError("source.design_origin.references 必须是 object 数组")
    normalized_origin["references"] = references
    runtime_sources = source.get("runtime_sources", [])
    if not isinstance(runtime_sources, list) or not all(
        isinstance(item, dict) for item in runtime_sources
    ):
        raise SpecError("source.runtime_sources 必须是 object 数组")
    return {"design_origin": normalized_origin, "runtime_sources": runtime_sources}


def normalize_spec(raw: Any, *, repo_root: Path, spec_dir: Path) -> dict[str, Any]:
    spec = _require_mapping(raw, "case spec")
    allowed = {
        "name",
        "title",
        "category",
        "slug",
        "number",
        "timeout_seconds",
        "modality",
        "attachment_size_limit_mb",
        "difficulty",
        "grading_type",
        "grading_weights",
        "tags",
        "prompt",
        "expected_behavior",
        "grading_criteria",
        "automated_checks",
        "llm_judge_rubric",
        "skills",
        "env",
        "warmup",
        "additional_notes",
        "workspace",
        "source",
        "checkpoint_capabilities",
    }
    unknown = set(spec) - allowed
    if unknown:
        raise SpecError(f"case spec 含不支持字段: {sorted(unknown)}")

    category = _require_text(spec.get("category"), "category")
    if category not in CATEGORIES:
        raise SpecError(f"首版只支持六类通用场景，category 不支持: {category}")
    slug = _require_text(spec.get("slug"), "slug")
    if not SLUG_RE.fullmatch(slug):
        raise SpecError("slug 必须是小写 snake_case，且只能包含字母、数字和下划线")
    grading_type = _require_text(spec.get("grading_type"), "grading_type")
    if grading_type not in GRADING_TYPES:
        raise SpecError(f"grading_type 必须是 {sorted(GRADING_TYPES)} 之一")
    difficulty = _require_text(spec.get("difficulty"), "difficulty")
    if difficulty not in DIFFICULTIES:
        raise SpecError(f"difficulty 必须是 {sorted(DIFFICULTIES)} 之一")
    modality = str(spec.get("modality", "pure-text")).strip()
    if modality not in MODALITIES:
        raise SpecError(f"modality 必须是 {sorted(MODALITIES)} 之一")
    timeout = spec.get("timeout_seconds", 300)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 30 <= timeout <= 3600:
        raise SpecError("timeout_seconds 必须是 30~3600 的整数")
    size_limit = spec.get("attachment_size_limit_mb", 5)
    if (
        isinstance(size_limit, bool)
        or not isinstance(size_limit, int)
        or not 1 <= size_limit <= 20
    ):
        raise SpecError("attachment_size_limit_mb 必须是 1~20 的整数")
    number = spec.get("number")
    if number is not None and (
        isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= 999
    ):
        raise SpecError("number 必须是 1~999 的整数")

    tags = _normalize_string_list(spec.get("tags", ["custom"]), "tags")
    tags = list(dict.fromkeys(tag.strip().lower() for tag in tags))
    specialized = sorted(set(tags) & SPECIALIZED_TAGS)
    if specialized:
        raise SpecError(
            f"首版通用场景不支持专项 tag: {specialized}；请使用对应专项流程"
        )
    if "custom" not in tags:
        tags.insert(0, "custom")

    criteria = _require_mapping(spec.get("grading_criteria"), "grading_criteria")
    unknown_criteria = set(criteria) - {"automated", "llm_judge"}
    if unknown_criteria:
        raise SpecError(f"grading_criteria 含不支持字段: {sorted(unknown_criteria)}")
    automated_criteria = _normalize_criteria(
        criteria.get("automated"), "grading_criteria.automated"
    )
    judge_criteria = _normalize_criteria(
        criteria.get("llm_judge"), "grading_criteria.llm_judge"
    )
    rubric = _normalize_rubric(spec.get("llm_judge_rubric"))
    rubric_keys = [item["key"] for item in rubric]
    judge_keys = [item["key"] for item in judge_criteria]
    if rubric_keys != judge_keys:
        raise SpecError(
            "grading_criteria.llm_judge 的 key 和顺序必须与 llm_judge_rubric 一致"
        )

    automated_checks = str(spec.get("automated_checks") or "").strip()
    if grading_type in {"automated", "hybrid"}:
        if not automated_criteria:
            raise SpecError(f"{grading_type} 必须提供 automated grading criteria")
        code_keys = _grade_keys(automated_checks)
        missing_code_keys = [
            item["key"] for item in automated_criteria if item["key"] not in code_keys
        ]
        if missing_code_keys or "overall_score" not in code_keys:
            raise SpecError(
                "automated_checks 必须显式包含全部评分 key 和 overall_score；"
                f"缺少: {missing_code_keys + ([] if 'overall_score' in code_keys else ['overall_score'])}"
            )
    elif automated_checks or automated_criteria:
        raise SpecError("llm_judge 任务的 Automated Checks 和 automated criteria 必须为空")
    if grading_type in {"llm_judge", "hybrid"} and not rubric:
        raise SpecError(f"{grading_type} 必须提供结构化 llm_judge_rubric")
    if grading_type == "automated" and (rubric or judge_criteria):
        raise SpecError("automated 任务的 LLM Judge Rubric 和 judge criteria 必须为空")

    weights: dict[str, float] | None = None
    if grading_type == "hybrid":
        raw_weights = _require_mapping(spec.get("grading_weights"), "grading_weights")
        if set(raw_weights) != {"automated", "llm_judge"}:
            raise SpecError("hybrid grading_weights 必须且只能包含 automated、llm_judge")
        try:
            weights = {key: float(raw_weights[key]) for key in raw_weights}
        except (TypeError, ValueError) as exc:
            raise SpecError("grading_weights 必须是数字") from exc
        if any(value <= 0 for value in weights.values()) or abs(sum(weights.values()) - 1) > 1e-6:
            raise SpecError("hybrid grading_weights 必须为正数且和为 1.0")
    elif spec.get("grading_weights") not in (None, {}):
        raise SpecError("仅 hybrid 任务填写 grading_weights")

    skills = _normalize_string_list(spec.get("skills"), "skills")
    for skill in skills:
        if not SLUG_RE.fullmatch(skill.replace("-", "_")):
            raise SpecError(f"Skill 名称非法: {skill!r}")
        if not (repo_root / "skills" / skill / "SKILL.md").is_file():
            raise SpecError(f"声明的 Skill 不存在: skills/{skill}/SKILL.md")
    env = _normalize_string_list(spec.get("env"), "env")
    for name in env:
        if not ENV_RE.fullmatch(name):
            raise SpecError(f"Env 名称非法: {name!r}")
        if name not in os.environ:
            raise SpecError(f"当前环境缺少声明的 Env: {name}")
    warmup = _normalize_string_list(spec.get("warmup"), "warmup")

    workspace = _require_mapping(spec.get("workspace", {}), "workspace")
    unknown_workspace = set(workspace) - {"exec", "gt"}
    if unknown_workspace:
        raise SpecError(f"workspace 含不支持字段: {sorted(unknown_workspace)}")
    exec_items = _normalize_copy_items(
        workspace.get("exec"), "workspace.exec", spec_dir, size_limit
    )
    gt_items = _normalize_copy_items(
        workspace.get("gt"), "workspace.gt", spec_dir, size_limit
    )

    checkpoint_capabilities = _require_mapping(
        spec.get("checkpoint_capabilities"), "checkpoint_capabilities"
    )
    if grading_type == "automated":
        expected_map_keys = [item["key"] for item in automated_criteria]
    else:
        expected_map_keys = []
        if grading_type == "hybrid":
            expected_map_keys.extend(
                f"automated.{item['key']}" for item in automated_criteria
            )
        expected_map_keys.extend(f"llm_judge.{key}" for key in rubric_keys)
    if set(checkpoint_capabilities) != set(expected_map_keys):
        raise SpecError(
            "checkpoint_capabilities 必须精确覆盖运行时评分 key；"
            f"expected={expected_map_keys}, actual={sorted(checkpoint_capabilities)}"
        )
    normalized_capabilities: dict[str, list[str]] = {}
    for key in expected_map_keys:
        values = checkpoint_capabilities[key]
        if (
            not isinstance(values, list)
            or len(values) not in {1, 2}
            or len(values) != len(set(values))
            or any(value not in CAPABILITIES for value in values)
        ):
            raise SpecError(
                f"checkpoint_capabilities.{key} 必须映射 1~2 个不重复的七维能力"
            )
        if {"retrieval_verification", "verification_delivery"}.issubset(values):
            raise SpecError(f"{key} 不得同时映射 retrieval_verification 和 verification_delivery")
        normalized_capabilities[key] = values

    notes = _normalize_string_list(spec.get("additional_notes"), "additional_notes")
    return {
        "name": _require_text(spec.get("name"), "name"),
        "title": _require_text(spec.get("title") or spec.get("name"), "title"),
        "category": category,
        "slug": slug,
        "number": number,
        "timeout_seconds": timeout,
        "modality": modality,
        "attachment_size_limit_mb": size_limit,
        "difficulty": difficulty,
        "grading_type": grading_type,
        "grading_weights": weights,
        "tags": tags,
        "prompt": _require_text(spec.get("prompt"), "prompt"),
        "expected_behavior": _require_text(
            spec.get("expected_behavior"), "expected_behavior"
        ),
        "automated_criteria": automated_criteria,
        "judge_criteria": judge_criteria,
        "automated_checks": automated_checks,
        "rubric": rubric,
        "skills": skills,
        "env": env,
        "warmup": warmup,
        "additional_notes": notes,
        "workspace_exec": exec_items,
        "workspace_gt": gt_items,
        "source": _normalize_source(spec.get("source")),
        "checkpoint_capabilities": normalized_capabilities,
    }


def _occupied_numbers(repo_root: Path, category: str, registry: dict[str, Any]) -> set[int]:
    occupied: set[int] = set()
    for root in (repo_root / "tasks" / category, repo_root / "tasks" / "extension" / category):
        if not root.is_dir():
            continue
        for path in root.glob("*.md"):
            match = TASK_ID_RE.match(path.stem)
            if match and match.group("category") == category:
                occupied.add(int(match.group("number")))
    for section in ("tasks", "excluded_tasks"):
        for entry in registry.get(section, []) or []:
            if not isinstance(entry, dict):
                continue
            match = TASK_ID_RE.match(str(entry.get("task_id") or ""))
            if match and match.group("category") == category:
                occupied.add(int(match.group("number")))
    return occupied


def assign_next_number(repo_root: Path, category: str, registry: dict[str, Any]) -> int:
    occupied = _occupied_numbers(repo_root, category, registry)
    for number in range(1, 1000):
        if number not in occupied:
            return number
    raise SpecError(f"{category} 已没有可用的三位编号")


def _validate_registry(registry: Any) -> dict[str, Any]:
    value = _require_mapping(registry, "task_sources.yaml")
    tasks = value.get("tasks")
    contract = value.get("registry_contract")
    if not isinstance(tasks, list) or not isinstance(contract, dict):
        raise SpecError("task_sources.yaml 缺少 tasks 列表或 registry_contract")
    ids = [entry.get("task_id") for entry in tasks if isinstance(entry, dict)]
    if len(ids) != len(tasks) or len(ids) != len(set(ids)):
        raise SpecError("task_sources.yaml 的 task_id 缺失或重复")
    counts = Counter(str(task_id).split("_task_", 1)[0] for task_id in ids)
    if contract.get("active_task_count") != len(tasks):
        raise SpecError("task_sources.yaml 的 active_task_count 与 tasks 数量不一致")
    declared_counts = contract.get("category_task_counts")
    if not isinstance(declared_counts, dict) or any(
        declared_counts.get(category, 0) != counts.get(category, 0)
        for category in CATEGORIES
    ):
        raise SpecError("task_sources.yaml 的 category_task_counts 与 tasks 不一致")
    return value


def _format_decimal(value: float) -> str:
    text = f"{value:.6f}".rstrip("0")
    return text + "0" if text.endswith(".") else text


def _render_rubric(criteria: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for index, item in enumerate(criteria, 1):
        parts.extend(
            [
                f"### Criterion {index}: {item['name']} (key: {item['key']}, weight: {_format_decimal(item['weight'])})",
                "",
                f"判据：{item['description']}",
                "",
            ]
        )
        for level in item["levels"]:
            parts.extend(
                [f"**Score {_format_decimal(level['score'])}**: {level['description']}", ""]
            )
    return "\n".join(parts).rstrip()


def render_task(spec: dict[str, Any], task_id: str, workspace_relative: str) -> str:
    frontmatter: dict[str, Any] = {
        "id": task_id,
        "name": spec["name"],
        "category": spec["category"],
        "timeout_seconds": spec["timeout_seconds"],
        "modality": spec["modality"],
        "attachment_size_limit_mb": spec["attachment_size_limit_mb"],
        "difficulty": spec["difficulty"],
        "grading_type": spec["grading_type"],
    }
    if spec["grading_weights"] is not None:
        frontmatter["grading_weights"] = spec["grading_weights"]
    frontmatter["tags"] = spec["tags"]
    fm = _dump_yaml(frontmatter).rstrip()

    grading_lines: list[str] = []
    if spec["automated_criteria"] and spec["judge_criteria"]:
        grading_lines.extend(["### Automated group", ""])
    grading_lines.extend(
        f"- [ ] `{item['key']}`: {item['description']}"
        for item in spec["automated_criteria"]
    )
    if spec["automated_criteria"] and spec["judge_criteria"]:
        grading_lines.extend(["", "### Judge group", ""])
    grading_lines.extend(
        f"- [ ] `{item['key']}`: {item['description']}"
        for item in spec["judge_criteria"]
    )

    parts = [
        "---",
        fm,
        "---",
        "",
        f"# {spec['title']}",
        "",
        "## Prompt",
        "",
        spec["prompt"],
        "",
        "## Expected Behavior",
        "",
        spec["expected_behavior"],
        "",
        "## Grading Criteria",
        "",
        "\n".join(grading_lines),
        "",
        "## Automated Checks",
        "",
    ]
    if spec["automated_checks"]:
        parts.extend(["```python", spec["automated_checks"], "```", ""])
    parts.extend(["## LLM Judge Rubric", ""])
    rubric = _render_rubric(spec["rubric"])
    if rubric:
        parts.extend([rubric, ""])
    parts.extend(
        [
            "## Workspace Path",
            "",
            "```",
            workspace_relative,
            "```",
            "",
            "## Skills",
            "",
        ]
    )
    if spec["skills"]:
        parts.extend(["```", *spec["skills"], "```", ""])
    parts.extend(["## Env", ""])
    if spec["env"]:
        parts.extend(["```", *spec["env"], "```", ""])
    parts.extend(["## Warmup", ""])
    if spec["warmup"]:
        parts.extend(["```bash", *spec["warmup"], "```", ""])
    parts.extend(["## Additional Notes", ""])
    notes = [
        "此用例由转换 Skill 生成，已通过确定性格式检查；题意、难度和评分有效性仍需人工审核。"
    ]
    notes.extend(spec["additional_notes"])
    parts.extend(f"- {note}" for note in notes)
    return "\n".join(parts).rstrip() + "\n"


def _copy_workspace(items: list[dict[str, Any]], destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if not items:
        (destination / ".gitkeep").write_text("", encoding="utf-8")
        return
    for item in items:
        source: Path = item["source"]
        target = destination / item["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def _validate_prompt_inputs(prompt: str, staged_exec: Path) -> None:
    refs = {
        match.group(1).rstrip("`'\".,:;)")
        for match in re.finditer(r"/tmp_workspace/([A-Za-z0-9_.@/+\-]+)", prompt)
    }
    missing: list[str] = []
    for ref in refs:
        path = PurePosixPath(ref)
        if not path.parts or path.parts[0] in {"results", "gt", "tmp"}:
            continue
        if not (staged_exec / Path(*path.parts)).exists():
            missing.append(f"/tmp_workspace/{ref}")
    if missing:
        raise SpecError(f"Prompt 引用的输入未出现在 workspace.exec: {sorted(missing)}")


def _registry_text_with_task(
    original: str,
    registry: dict[str, Any],
    *,
    task_id: str,
    category: str,
    number: int,
    source: dict[str, Any],
) -> str:
    active = int(registry["registry_contract"]["active_task_count"])
    category_count = int(
        registry["registry_contract"]["category_task_counts"][category]
    )
    updated = re.sub(
        rf"(?m)^(\s*active_task_count:\s*){active}(\s*)$",
        rf"\g<1>{active + 1}\g<2>",
        original,
        count=1,
    )
    updated, substitutions = re.subn(
        rf"(?m)^(\s*{re.escape(category)}:\s*){category_count}(\s*)$",
        rf"\g<1>{category_count + 1}\g<2>",
        updated,
        count=1,
    )
    if substitutions != 1 or updated == original:
        raise SpecError("无法安全更新 task_sources.yaml 的 registry_contract")
    entry = {
        "short_id": f"{category[:2]}-{number:03d}",
        "task_id": task_id,
        **source,
    }
    block = _dump_yaml([entry]).rstrip()
    list_match = re.search(r"(?m)^tasks:[^\n]*\n(?P<indent> *)-", updated)
    if not list_match:
        raise SpecError("无法识别 task_sources.yaml 中 tasks 列表的缩进")
    list_indent = list_match.group("indent")
    block = "\n".join(f"{list_indent}{line}" for line in block.splitlines())
    marker = "\nexcluded_tasks:"
    if marker in updated:
        updated = updated.replace(marker, f"\n\n{block}\n{marker}", 1)
    else:
        updated = updated.rstrip() + f"\n\n{block}\n"
    return updated


def _capability_text_with_task(
    original: str, task_id: str, mapping: dict[str, list[str]]
) -> str:
    lines = [f"{task_id}:"]
    for key, capabilities in mapping.items():
        lines.append(f"  {key}: [{', '.join(capabilities)}]")
    return original.rstrip() + "\n" + "\n".join(lines) + "\n"


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SpecError(f"无法读取 YAML {path}: {exc}") from exc


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _validation_failure_details(report_root: Path) -> str:
    reports = sorted(report_root.rglob("report.json"))
    if not reports:
        return ""
    try:
        report = json.loads(reports[-1].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ""
    issues = report.get("issues") if isinstance(report, dict) else None
    if not isinstance(issues, list):
        return ""
    lines: list[str] = []
    for issue in issues[:20]:
        if not isinstance(issue, dict):
            continue
        label = "/".join(
            str(issue.get(key) or "").strip()
            for key in ("severity", "code", "task_id")
            if str(issue.get(key) or "").strip()
        )
        message = str(issue.get("message") or "").strip()
        lines.append(f"- {label}: {message}" if label else f"- {message}")
    return "\n".join(lines)


def _validate_output_yaml(
    registry_text: str,
    capability_text: str,
    *,
    task_id: str,
    category: str,
) -> None:
    registry = _validate_registry(yaml.safe_load(registry_text))
    matches = [entry for entry in registry["tasks"] if entry.get("task_id") == task_id]
    if len(matches) != 1:
        raise SpecError("生成后的 task_sources.yaml 未唯一登记新任务")
    capability_map = yaml.safe_load(capability_text)
    if not isinstance(capability_map, dict) or task_id not in capability_map:
        raise SpecError("生成后的 checkpoint capability map 未登记新任务")
    if registry["registry_contract"]["category_task_counts"][category] < 1:
        raise SpecError("生成后的分类计数异常")


def assemble_case(
    raw_spec: Any,
    *,
    repo_root: Path,
    spec_dir: Path,
    dry_run: bool = False,
    run_validation: bool = True,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    spec = normalize_spec(raw_spec, repo_root=repo_root, spec_dir=spec_dir.resolve())
    registry_path = repo_root / "tasks" / "extension" / "task_sources.yaml"
    capability_path = repo_root / "tools" / "report" / "data" / "checkpoint_capability_map7.yaml"
    registry_original = registry_path.read_bytes()
    capability_original = capability_path.read_bytes()
    registry = _validate_registry(yaml.safe_load(registry_original))
    capability_map = yaml.safe_load(capability_original)
    if not isinstance(capability_map, dict):
        raise SpecError("checkpoint_capability_map7.yaml 必须是 mapping")

    occupied = _occupied_numbers(repo_root, spec["category"], registry)
    number = spec["number"] or assign_next_number(repo_root, spec["category"], registry)
    if number in occupied:
        raise SpecError(f"编号已被文件、来源登记或 invalid 保留项占用: {number:03d}")
    task_id = f"{spec['category']}_task_{number:03d}_{spec['slug']}"
    if any(entry.get("task_id") == task_id for entry in registry["tasks"]):
        raise SpecError(f"task_id 已登记: {task_id}")
    if task_id in capability_map:
        raise SpecError(f"task_id 已存在于能力映射: {task_id}")

    task_path = repo_root / "tasks" / "extension" / spec["category"] / f"{task_id}.md"
    workspace_path = (
        repo_root
        / "workspace"
        / "extension"
        / spec["category"]
        / f"task_{number:03d}_{spec['slug']}"
    )
    if task_path.exists() or workspace_path.exists():
        raise SpecError(f"目标已存在，拒绝覆盖: {task_path} 或 {workspace_path}")
    workspace_relative = workspace_path.relative_to(repo_root).as_posix()
    task_text = render_task(spec, task_id, workspace_relative)
    registry_text = _registry_text_with_task(
        registry_original.decode("utf-8"),
        registry,
        task_id=task_id,
        category=spec["category"],
        number=number,
        source=spec["source"],
    )
    capability_text = _capability_text_with_task(
        capability_original.decode("utf-8"), task_id, spec["checkpoint_capabilities"]
    )
    _validate_output_yaml(
        registry_text,
        capability_text,
        task_id=task_id,
        category=spec["category"],
    )

    with tempfile.TemporaryDirectory(prefix="wcb-case-stage-") as temporary:
        staged_workspace = Path(temporary) / "workspace"
        _copy_workspace(spec["workspace_exec"], staged_workspace / "exec")
        _copy_workspace(spec["workspace_gt"], staged_workspace / "gt")
        _validate_prompt_inputs(spec["prompt"], staged_workspace / "exec")
        if dry_run:
            return {
                "status": "DRY_RUN",
                "task_id": task_id,
                "task_path": str(task_path),
                "workspace_path": str(workspace_path),
                "source_registry": str(registry_path),
                "capability_map": str(capability_path),
                "review_required": True,
            }

        changed: list[str] = []
        try:
            task_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(staged_workspace, workspace_path)
            changed.append("workspace")
            _write_bytes_atomic(task_path, task_text.encode("utf-8"))
            changed.append("task")
            _write_bytes_atomic(registry_path, registry_text.encode("utf-8"))
            changed.append("registry")
            _write_bytes_atomic(capability_path, capability_text.encode("utf-8"))
            changed.append("capability")

            validation_output = ""
            if run_validation:
                validator = (
                    repo_root
                    / "tools"
                    / "report"
                    / "skills"
                    / "validate-eval-dataset"
                    / "scripts"
                    / "validate_eval_dataset.py"
                )
                if not validator.is_file():
                    raise SpecError(f"缺少最终静态校验器: {validator}")
                failure_details = ""
                try:
                    with tempfile.TemporaryDirectory(prefix="wcb-case-report-") as report_dir:
                        completed = subprocess.run(
                            [
                                sys.executable,
                                str(validator),
                                "--task-path",
                                str(task_path),
                                "--output-dir",
                                report_dir,
                            ],
                            cwd=repo_root,
                            text=True,
                            capture_output=True,
                            timeout=120,
                        )
                        if completed.returncode != 0:
                            failure_details = _validation_failure_details(Path(report_dir))
                except subprocess.TimeoutExpired as exc:
                    raise SpecError("validate-eval-dataset 执行超过 120 秒") from exc
                validation_output = (completed.stdout + completed.stderr).strip()
                if completed.returncode != 0:
                    detail = failure_details or validation_output[-4000:]
                    raise SpecError(
                        "validate-eval-dataset 未通过，已回滚生成结果:\n"
                        + detail
                    )
        except Exception:
            if "capability" in changed:
                _write_bytes_atomic(capability_path, capability_original)
            if "registry" in changed:
                _write_bytes_atomic(registry_path, registry_original)
            if "task" in changed and task_path.exists():
                task_path.unlink()
            if "workspace" in changed and workspace_path.exists():
                shutil.rmtree(workspace_path)
            raise

    return {
        "status": "CREATED",
        "task_id": task_id,
        "task_path": str(task_path),
        "workspace_path": str(workspace_path),
        "source_registry": str(registry_path),
        "capability_map": str(capability_path),
        "validation": "PASS" if run_validation else "SKIPPED",
        "review_required": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path, help="case-spec.json 路径")
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="只做预检和编号规划，不写文件")
    parser.add_argument(
        "--skip-final-validation",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        spec_path = args.spec.expanduser().resolve()
        raw_spec = json.loads(spec_path.read_text(encoding="utf-8"))
        repo_root = find_repo_root(args.repo_root) if args.repo_root else find_repo_root()
        result = assemble_case(
            raw_spec,
            repo_root=repo_root,
            spec_dir=spec_path.parent,
            dry_run=args.dry_run,
            run_validation=not args.skip_final_validation,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, yaml.YAMLError, SpecError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
