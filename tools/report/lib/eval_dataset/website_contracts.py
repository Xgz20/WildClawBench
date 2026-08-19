"""Web 站点评测任务的确定性静态契约校验。"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import FAIL, Issue
from .task_files import TaskDocument


WEBSITE_TAG = "web-site-gen"
ALLOWED_PRIMARY_DIMENSIONS = {
    "content_structure",
    "interaction_function",
    "visual_layout",
}
WEBSITE_WORKSPACE_ROOT = Path("workspace/extension/07_Website_Generation")
STARTUP_CONTRACT_FRAGMENTS = (
    "package.json",
    "npm install",
    "npm run build",
    "npm run start -- --host 127.0.0.1 --port 4173",
)

_MODULE_NAME_RE = re.compile(r"(task_\d+_[A-Za-z0-9_]+)$")
_CRITERION_PREFIX_RE = re.compile(r"^###\s+Criterion\b")
_CRITERION_RE = re.compile(
    r"^###\s+Criterion\s+(\d+)\s*[:：]\s*(.*?)\s+\((.*)\)\s*$"
)
_METADATA_RE = re.compile(
    r"(?:^|,)\s*(key|primary|secondary|weight)\s*:\s*([^,]*)"
)
_DIMENSION_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SCORE_ONE_RE = re.compile(
    r"^\s*(?:\*\*)?Score\s+1\.0(?:\*\*)?\s*:", re.MULTILINE
)
_SCORE_ZERO_RE = re.compile(
    r"^\s*(?:\*\*)?Score\s+0\.0(?:\*\*)?\s*:", re.MULTILINE
)


@dataclass(frozen=True)
class WebsiteCriterion:
    number: int
    key: str
    primary: str
    secondary: str
    weight: float | None
    body: str


def _issue(
    code: str,
    message: str,
    doc: TaskDocument,
    *,
    evidence: dict[str, Any] | None = None,
) -> Issue:
    return Issue(
        FAIL,
        code,
        message,
        task_id=doc.task_id,
        location=str(doc.path),
        evidence=evidence or {},
    )


def _normalize_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        values = raw.split(",")
    elif isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        values = [raw]
    return list(
        dict.fromkeys(
            str(value).strip().lower()
            for value in values
            if str(value).strip()
        )
    )


def is_website_task(doc: TaskDocument) -> bool:
    """Return whether the task selects the Web dynamic metric profile."""
    return WEBSITE_TAG in _normalize_tags(doc.metadata.get("tags"))


def website_module_name(task_id: str) -> str | None:
    match = _MODULE_NAME_RE.search(task_id)
    return match.group(1) if match else None


def _parse_criteria(text: str) -> tuple[list[WebsiteCriterion], list[str]]:
    lines = text.splitlines()
    starts = [
        index
        for index, line in enumerate(lines)
        if _CRITERION_PREFIX_RE.match(line.strip())
    ]
    errors: list[str] = []
    criteria: list[WebsiteCriterion] = []
    if not starts:
        return [], ["LLM Judge Rubric 未声明 Criterion"]

    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        heading = lines[start].strip()
        match = _CRITERION_RE.fullmatch(heading)
        if not match:
            errors.append(f"Criterion 标题格式错误: {heading}")
            continue
        metadata_pairs = _METADATA_RE.findall(match.group(3))
        metadata = {key: value.strip() for key, value in metadata_pairs}
        duplicate_metadata = sorted(
            key
            for key in {item[0] for item in metadata_pairs}
            if sum(pair[0] == key for pair in metadata_pairs) > 1
        )
        if duplicate_metadata:
            errors.append(
                f"Criterion {match.group(1)} 元数据重复: {', '.join(duplicate_metadata)}"
            )
        raw_weight = metadata.get("weight", "")
        try:
            weight = float(raw_weight)
        except ValueError:
            weight = None
        body = "\n".join(lines[start + 1 : end]).strip()
        criteria.append(
            WebsiteCriterion(
                number=int(match.group(1)),
                key=metadata.get("key", ""),
                primary=metadata.get("primary", ""),
                secondary=metadata.get("secondary", ""),
                weight=weight,
                body=body,
            )
        )

    numbers = [criterion.number for criterion in criteria]
    expected_numbers = list(range(1, len(starts) + 1))
    if numbers != expected_numbers:
        errors.append(
            f"Criterion 编号必须从 1 连续递增: actual={numbers}, expected={expected_numbers}"
        )
    missing_bands = [
        criterion.number
        for criterion in criteria
        if not _SCORE_ONE_RE.search(criterion.body)
        or not _SCORE_ZERO_RE.search(criterion.body)
    ]
    if missing_bands:
        errors.append(
            "Criterion 必须同时声明 Score 1.0 和 Score 0.0: "
            + ", ".join(str(number) for number in missing_bands)
        )
    return criteria, errors


def _assignment_sequence(
    tree: ast.Module, name: str
) -> tuple[list[str] | None, str]:
    value_node: ast.AST | None = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        ):
            value_node = node.value
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            value_node = node.value
    if value_node is None:
        return None, f"未声明 {name}"
    try:
        value = ast.literal_eval(value_node)
    except (TypeError, ValueError, SyntaxError):
        return None, f"{name} 必须是可静态解析的字符串序列"
    if not isinstance(value, (list, tuple, set)) or not all(
        isinstance(item, str) and item for item in value
    ):
        return None, f"{name} 必须是非空字符串组成的序列"
    values = list(value)
    if len(values) != len(set(values)):
        return values, f"{name} 包含重复 key"
    return values, ""


def _entrypoint_error(tree: ast.Module, name: str) -> str:
    candidates = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == name
    ]
    if not candidates:
        return f"缺少 async {name}(page, screenshot_dir)"
    node = candidates[-1]
    if not isinstance(node, ast.AsyncFunctionDef):
        return f"{name} 必须使用 async def"
    argument_names = [
        argument.arg for argument in (*node.args.posonlyargs, *node.args.args)
    ]
    if (
        argument_names != ["page", "screenshot_dir"]
        or node.args.vararg is not None
        or node.args.kwarg is not None
        or node.args.kwonlyargs
    ):
        return f"{name} 参数必须为 (page, screenshot_dir)"
    return ""


def _uses_eval_fixtures(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and "/tmp_workspace_eval" in node.value
        for node in ast.walk(tree)
    )


def _has_eval_assets(eval_dir: Path) -> bool:
    return eval_dir.is_dir() and any(
        path.is_file() and path.name != ".gitkeep"
        for path in eval_dir.rglob("*")
    )


def validate_website_contract(
    doc: TaskDocument,
    repo_root: Path,
    workspace: Path,
) -> list[Issue]:
    """Validate one ``web-site-gen`` task without importing task code."""
    issues: list[Issue] = []
    criteria, format_errors = _parse_criteria(doc.section("LLM Judge Rubric"))
    if format_errors:
        issues.append(
            _issue(
                "WEBSITE_RUBRIC_FORMAT_INVALID",
                "Web Rubric 的 Criterion 格式不符合动态评分协议",
                doc,
                evidence={"errors": format_errors},
            )
        )

    dimension_errors: list[str] = []
    keys = [criterion.key for criterion in criteria]
    duplicate_keys = sorted({key for key in keys if key and keys.count(key) > 1})
    if duplicate_keys:
        dimension_errors.append(f"rubric key 重复: {duplicate_keys}")
    for criterion in criteria:
        if not _DIMENSION_KEY_RE.fullmatch(criterion.key):
            dimension_errors.append(
                f"Criterion {criterion.number} key 非法: {criterion.key or '<missing>'}"
            )
        if criterion.primary not in ALLOWED_PRIMARY_DIMENSIONS:
            dimension_errors.append(
                f"Criterion {criterion.number} primary 非法: {criterion.primary or '<missing>'}"
            )
        if not _DIMENSION_KEY_RE.fullmatch(criterion.secondary):
            dimension_errors.append(
                f"Criterion {criterion.number} secondary 非法: {criterion.secondary or '<missing>'}"
            )
    if dimension_errors:
        issues.append(
            _issue(
                "WEBSITE_RUBRIC_DIMENSION_INVALID",
                "Web Rubric 的 key、primary 或 secondary 维度无效",
                doc,
                evidence={"errors": dimension_errors},
            )
        )

    invalid_weights = [
        {
            "criterion": criterion.number,
            "weight": criterion.weight,
        }
        for criterion in criteria
        if criterion.weight is None or criterion.weight <= 0
    ]
    total_weight = sum(
        criterion.weight
        for criterion in criteria
        if criterion.weight is not None and criterion.weight > 0
    )
    if invalid_weights or not criteria or abs(total_weight - 1.0) > 0.001:
        issues.append(
            _issue(
                "WEBSITE_RUBRIC_WEIGHT_INVALID",
                "Web Rubric 权重必须为正数且总和为 1",
                doc,
                evidence={
                    "invalid_weights": invalid_weights,
                    "total_weight": round(total_weight, 6),
                },
            )
        )

    prompt = re.sub(r"\s+", " ", doc.section("Prompt"))
    missing_startup = [
        fragment for fragment in STARTUP_CONTRACT_FRAGMENTS if fragment not in prompt
    ]
    if missing_startup:
        issues.append(
            _issue(
                "WEBSITE_STARTUP_CONTRACT_MISSING",
                "Web Prompt 缺少标准 npm 构建或启动协议",
                doc,
                evidence={"missing": missing_startup},
            )
        )

    module_name = website_module_name(doc.task_id)
    if module_name is None:
        checker_path = repo_root / "eval/checks/website/tasks/<invalid-task-id>.py"
    else:
        checker_path = repo_root / "eval/checks/website/tasks" / f"{module_name}.py"

    layout_errors: list[str] = []
    expected_workspace = (
        repo_root / WEBSITE_WORKSPACE_ROOT / (module_name or "<invalid-task-id>")
    ).resolve()
    if workspace.resolve() != expected_workspace:
        layout_errors.append("Workspace Path 与网站评测器固定素材目录不一致")
    if not (workspace / "exec").is_dir():
        layout_errors.append("Workspace 缺少 exec/ 目录")
    if layout_errors:
        issues.append(
            _issue(
                "WEBSITE_WORKSPACE_LAYOUT_INVALID",
                "Web Workspace 布局不符合动态评分协议",
                doc,
                evidence={
                    "errors": layout_errors,
                    "actual_workspace": str(workspace),
                    "expected_workspace": str(expected_workspace),
                },
            )
        )

    if module_name is None or not checker_path.is_file():
        issues.append(
            _issue(
                "WEBSITE_CHECKER_MISSING",
                "缺少与任务 ID 对应的 Playwright 检查器模块",
                doc,
                evidence={"expected_checker": str(checker_path)},
            )
        )
        return issues

    try:
        source = checker_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(checker_path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        issues.append(
            _issue(
                "WEBSITE_CHECKER_SYNTAX_INVALID",
                "Playwright 检查器无法进行 Python AST 解析",
                doc,
                evidence={"checker": str(checker_path), "error": str(exc)},
            )
        )
        return issues

    runtime_keys = [
        criterion.key
        for criterion in criteria
        if criterion.key and criterion.primary != "visual_layout"
    ]
    visual_keys = [
        criterion.key
        for criterion in criteria
        if criterion.key and criterion.primary == "visual_layout"
    ]
    declared_runtime, runtime_error = _assignment_sequence(tree, "RUNTIME_KEYS")
    if (
        runtime_error
        or declared_runtime is None
        or set(declared_runtime) != set(runtime_keys)
        or len(declared_runtime) != len(runtime_keys)
    ):
        issues.append(
            _issue(
                "WEBSITE_RUNTIME_KEYS_MISMATCH",
                "检查器 RUNTIME_KEYS 与非视觉 Rubric key 不一致",
                doc,
                evidence={
                    "checker": str(checker_path),
                    "expected": sorted(runtime_keys),
                    "actual": sorted(declared_runtime or []),
                    "error": runtime_error,
                },
            )
        )
    declared_visual, visual_error = _assignment_sequence(tree, "VISUAL_KEYS")
    if (
        visual_error
        or declared_visual is None
        or set(declared_visual) != set(visual_keys)
        or len(declared_visual) != len(visual_keys)
    ):
        issues.append(
            _issue(
                "WEBSITE_VISUAL_KEYS_MISMATCH",
                "检查器 VISUAL_KEYS 与视觉 Rubric key 不一致",
                doc,
                evidence={
                    "checker": str(checker_path),
                    "expected": sorted(visual_keys),
                    "actual": sorted(declared_visual or []),
                    "error": visual_error,
                },
            )
        )

    entrypoint_errors = [error for error in [_entrypoint_error(tree, "run")] if error]
    if visual_keys:
        capture_error = _entrypoint_error(tree, "capture_visual")
        if capture_error:
            entrypoint_errors.append(capture_error)
    if entrypoint_errors:
        issues.append(
            _issue(
                "WEBSITE_CHECKER_ENTRYPOINT_MISSING",
                "Playwright 检查器缺少规定的异步入口",
                doc,
                evidence={"checker": str(checker_path), "errors": entrypoint_errors},
            )
        )

    if _uses_eval_fixtures(tree):
        eval_dir = expected_workspace / "eval"
        if not _has_eval_assets(eval_dir):
            issues.append(
                _issue(
                    "WEBSITE_EVAL_FIXTURE_MISSING",
                    "检查器引用 /tmp_workspace_eval，但任务没有可复制的 eval 素材",
                    doc,
                    evidence={"expected_eval_dir": str(eval_dir)},
                )
            )
    return issues
