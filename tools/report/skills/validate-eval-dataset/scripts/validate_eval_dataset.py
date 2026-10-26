#!/usr/bin/env python3
"""WildClawBench 评测集静态契约校验入口。"""

from __future__ import annotations

import argparse
import ast
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[5]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.report.lib.eval_dataset.contracts import FAIL, PASS, REVIEW, Issue, Report, exit_code, status_for_issues
from tools.report.lib.eval_dataset.reporting import write_report
from tools.report.lib.eval_dataset.security import env_evidence, is_env_name, path_within
from tools.report.lib.eval_dataset.selectors import select_task_files
from tools.report.lib.eval_dataset.smoke import run_warmup_smoke
from tools.report.lib.eval_dataset.task_files import (
    TaskDocument,
    ast_grade_info,
    extract_env_names,
    extract_skill_names,
    parse_task_document,
    rubric_info,
    strip_codeblock,
    warmup_info,
)
from tools.report.lib.eval_dataset.website_contracts import (
    is_website_task,
    validate_website_contract,
)
from eval_general_e2e.datasets.catalog import load_mapping, load_registered_dataset, repository_path


def _issue(code: str, message: str, doc: TaskDocument, *, severity: str = FAIL, evidence: dict[str, Any] | None = None) -> Issue:
    return Issue(severity, code, message, task_id=doc.task_id, location=str(doc.path), evidence=evidence or {})


def _workspace_refs(doc: TaskDocument, workspace: Path) -> list[Path]:
    refs: set[Path] = set()
    text = doc.raw
    # Explicit relative resource paths in task prose/checks. Avoid treating
    # output paths as required inputs unless they are exec/gt/attachment files.
    for match in re.finditer(r"(?<![A-Za-z0-9_])((?:exec|gt|attachments?|fixtures?|inputs?)/[A-Za-z0-9_./-]+)", text):
        value = match.group(1).rstrip(".,:;`)")
        refs.add((workspace / value).resolve())
    for match in re.finditer(r"(?:workspace\s*/\s*[\"'])([^\"']+)", text):
        value = match.group(1)
        if any(part in value.lower() for part in ("exec", "gt", "attachment", "fixture", "input")):
            refs.add((workspace / value).resolve())
    return sorted(refs)


def validate_document(doc: TaskDocument, repo_root: Path, *, smoke: bool = False, warmup_image: str | None = None) -> list[Issue]:
    issues: list[Issue] = []
    if doc.frontmatter_error:
        return [_issue("FRONTMATTER_INVALID", doc.frontmatter_error, doc)]
    metadata = doc.metadata
    required_types = {"id": str, "category": str, "difficulty": str, "modality": str, "timeout_seconds": int, "grading_type": str}
    for key, expected in required_types.items():
        if key not in metadata:
            issues.append(_issue("FRONTMATTER_FIELD_MISSING", f"frontmatter 缺少字段: {key}", doc))
        elif not isinstance(metadata[key], expected) or isinstance(metadata[key], bool):
            issues.append(_issue("FRONTMATTER_FIELD_TYPE", f"frontmatter 字段类型错误: {key}", doc, evidence={"expected": expected.__name__}))
    if doc.category != doc.path.parent.name:
        issues.append(_issue("CATEGORY_MISMATCH", f"category 与父目录不一致: {doc.category} != {doc.path.parent.name}", doc))
    if doc.task_id not in doc.path.stem:
        issues.append(_issue("TASK_ID_FILENAME_MISMATCH", "task ID 未出现在文件名中", doc))
    for section in ("Prompt", "Workspace Path"):
        if not doc.section(section):
            issues.append(_issue("SECTION_MISSING", f"缺少必需章节: {section}", doc))
    # TASK_TEMPLATE_v2 requires the optional executable sections to remain in
    # every task document, even when their bodies are intentionally empty.
    # Check presence separately from content: an empty Warmup is a valid
    # no-op, while omitting the section is a format violation.
    for section in ("Skills", "Env", "Warmup"):
        if section not in doc.sections:
            issues.append(_issue("SECTION_MISSING", f"缺少模板章节: {section}", doc))

    grading_type = str(metadata.get("grading_type", ""))
    automated = strip_codeblock(doc.section("Automated Checks"))
    if grading_type in {"automated", "hybrid"}:
        ok, keys, error = ast_grade_info(automated)
        if not ok:
            issues.append(_issue("AUTOMATED_CHECKS_INVALID", error, doc))
        elif len(keys) < 1:
            issues.append(_issue("AUTOMATED_SCORE_KEYS_MISSING", "grade() 未发现稳定评分 key", doc))
    rubric = doc.section("LLM Judge Rubric")
    if grading_type in {"llm_judge", "hybrid"}:
        criteria, errors = rubric_info(rubric)
        for error in errors:
            issues.append(_issue("RUBRIC_INVALID", error, doc))
        if not criteria:
            issues.append(_issue("RUBRIC_MISSING", "评分类型要求可解析的 LLM Judge Rubric", doc))
        weights = metadata.get("grading_weights")
        if grading_type == "hybrid" and (not isinstance(weights, dict) or not weights):
            issues.append(_issue("GRADING_WEIGHTS_INVALID", "hybrid 任务缺少 grading_weights", doc))

    raw_workspace = strip_codeblock(doc.section("Workspace Path"))
    workspace = Path(raw_workspace).expanduser()
    if not workspace.is_absolute():
        workspace = (repo_root / workspace).resolve()
        if not path_within(workspace, repo_root):
            issues.append(_issue("WORKSPACE_OUTSIDE_REPO", "Workspace Path 越出仓库根目录", doc, evidence={"workspace": str(workspace)}))
    else:
        workspace = workspace.resolve()
    virtual_workspace = str(workspace) == "/tmp_workspace"
    if not virtual_workspace and not workspace.exists():
        issues.append(_issue("WORKSPACE_NOT_FOUND", f"Workspace Path 不存在: {workspace}", doc))
    elif virtual_workspace and not workspace.exists():
        issues.append(_issue("WORKSPACE_VIRTUAL", "使用评测容器虚拟 Workspace，宿主机未创建目录", doc, severity=REVIEW, evidence={"workspace": str(workspace)}))
    for ref in _workspace_refs(doc, workspace):
        if not ref.exists():
            issues.append(_issue("WORKSPACE_RESOURCE_MISSING", f"任务引用的 Workspace 文件不存在: {ref}", doc))

    skill_names = extract_skill_names(doc.section("Skills"))
    raw_skills_path = strip_codeblock(doc.section("Skills Path")) or "skills"
    skills_root = Path(raw_skills_path).expanduser()
    if not skills_root.is_absolute():
        skills_root = (repo_root / skills_root).resolve()
    for name in skill_names:
        skill_file = (skills_root / name / "SKILL.md").resolve()
        if not skill_file.is_file() or not os.access(skill_file, os.R_OK):
            issues.append(_issue("SKILL_NOT_FOUND", f"声明的 Skill 不存在或不可读: {name}", doc, evidence={"skills_path": str(skills_root), "skill": name}))

    env_names, invalid_env = extract_env_names(doc.section("Env"))
    for name in invalid_env:
        issues.append(_issue("ENV_NAME_INVALID", f"非法 Env 名称: {name}", doc))
    seen: set[str] = set()
    duplicates = [name for name in env_names if name in seen or seen.add(name)]
    if duplicates:
        issues.append(_issue("ENV_DUPLICATE", "Env 重复声明", doc, evidence={"names": sorted(set(duplicates))}))
    missing = [name for name in env_names if name not in os.environ]
    if missing:
        issues.append(_issue("ENV_MISSING", "运行环境缺少任务声明的 Env", doc, evidence={"env": env_evidence(env_names, dict(os.environ))}))

    warmup = warmup_info(doc.section("Warmup"))
    if warmup["dangerous_codes"]:
        issues.append(_issue("WARMUP_DANGEROUS", "Warmup 含宿主机危险命令模式", doc, severity=REVIEW, evidence={"codes": warmup["dangerous_codes"]}))
    for command in warmup["commands"]:
        try:
            tokens = shlex.split(command)
        except ValueError as exc:
            issues.append(_issue("WARMUP_SHELL_INVALID", str(exc), doc))
            continue
        for token in tokens[1:]:
            candidate = Path(token)
            if (token.startswith("./") or "/" in token) and not candidate.is_absolute() and candidate.suffix:
                path = (workspace / candidate).resolve()
                if not path.exists():
                    issues.append(_issue("WARMUP_REFERENCE_MISSING", f"Warmup 引用文件不存在: {token}", doc, evidence={"path": str(path)}))
    if smoke and warmup["commands"]:
        # Never mount the repository or a product workspace read-write for a
        # smoke check. The disposable container gets an empty temporary root.
        with tempfile.TemporaryDirectory(prefix="wcb-warmup-") as smoke_workspace:
            smoke_results = run_warmup_smoke(warmup["commands"], image=warmup_image or metadata.get("warmup_image") or os.environ.get("WCB_WARMUP_IMAGE"), workspace=smoke_workspace, timeout_seconds=min(int(metadata.get("timeout_seconds", 120)), 300))
        for result in smoke_results:
            if result.get("code") == "SMOKE_UNAVAILABLE":
                issues.append(_issue("SMOKE_UNAVAILABLE", result.get("message", "Warmup smoke 不可用"), doc, severity=REVIEW))
            elif result.get("status") != "passed":
                issues.append(_issue(result.get("code", "WARMUP_SMOKE_FAILED"), "Warmup 容器 smoke 执行失败", doc, evidence={"returncode": result.get("returncode"), "stderr": result.get("stderr", "")}))

    if is_website_task(doc):
        issues.extend(validate_website_contract(doc, repo_root, workspace))

    return issues


def validate_extension_registry(repo_root: Path, selected: list[Path]) -> list[Issue]:
    extension = repo_root / "tasks" / "extension"
    registry = extension / "task_sources.yaml"
    def is_under_extension(path: Path) -> bool:
        try:
            path.resolve().relative_to(extension.resolve())
            return True
        except ValueError:
            return False

    if not any(is_under_extension(path) for path in selected):
        return []
    if not registry.is_file():
        return [Issue(FAIL, "EXTENSION_REGISTRY_MISSING", "扩展集缺少 tasks/extension/task_sources.yaml", location=str(registry))]
    try:
        import yaml
        value = yaml.safe_load(registry.read_text(encoding="utf-8"))
        if not isinstance(value, dict) or not isinstance(value.get("tasks"), list):
            return [Issue(FAIL, "EXTENSION_REGISTRY_INVALID", "task_sources.yaml 缺少 tasks 列表", location=str(registry))]
    except Exception as exc:
        return [Issue(FAIL, "EXTENSION_REGISTRY_INVALID", f"task_sources.yaml 无法解析: {exc}", location=str(registry))]
    return []


def validate_registered_registry(repo_root: Path, selected: list[Path]) -> list[Issue]:
    """Validate individual authored tasks without requiring unfinished siblings."""
    repo_root = repo_root.resolve()
    issues: list[Issue] = []
    cache: dict[str, tuple[Any, dict, dict] | Exception] = {}
    for selected_path in selected:
        path = selected_path.resolve()
        try:
            relative = path.relative_to(repo_root / "datasets")
        except ValueError:
            continue
        series = relative.parts[0]
        if series not in cache:
            try:
                registered = load_registered_dataset(repo_root, series)
                definition = registered.definition
                registry = load_mapping(repository_path(repo_root, definition.registry_path, label="registry"))
                entries = registry.get("tasks")
                if not isinstance(entries, list) or any(not isinstance(entry, dict) or not isinstance(entry.get("task_id"), str) for entry in entries):
                    raise ValueError("来源登记必须包含带task_id的tasks列表")
                by_id = {entry["task_id"]: entry for entry in entries}
                if len(by_id) != len(entries):
                    raise ValueError("来源登记包含重复task_id")
                mapping = load_mapping(repository_path(repo_root, definition.capability_map_path, label="capability map"))
                cache[series] = registered, by_id, mapping
            except (OSError, ValueError) as exc:
                cache[series] = exc
        cached = cache[series]
        if isinstance(cached, Exception):
            issues.append(Issue(FAIL, "DATASET_REGISTRY_INVALID", str(cached), location=str(path)))
            continue
        registered, entries, mapping = cached
        definition = registered.definition
        doc = parse_task_document(path)
        task_id = doc.task_id
        category = doc.category
        expected_task = repo_root / definition.task_root / category / f"{task_id}.md"
        if (category not in definition.category_labels or path != expected_task
                or path.resolve() != expected_task
                or not re.fullmatch(re.escape(definition.task_id_prefix + category) + r"_task_\d{3}_[a-z0-9_]+", task_id)):
            issues.append(_issue("DATASET_TASK_LAYOUT_INVALID", "任务路径、分类或数据集命名空间不一致", doc))
            continue
        tags = doc.metadata.get("tags", [])
        if isinstance(tags, str):
            tags = [tag.strip().lower() for tag in tags.split(",")]
        if (not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags) or not set(definition.include_tags).issubset(tags)
                or set(definition.exclude_tags).intersection(tags)):
            issues.append(_issue("DATASET_TAGS_INVALID", "任务缺少数据集必需标签或包含排除标签", doc))
        workspace = repo_root / definition.workspace_root / category / task_id
        declared = strip_codeblock(doc.section("Workspace Path"))
        if declared != workspace.relative_to(repo_root).as_posix() or workspace.resolve() != workspace:
            issues.append(_issue("DATASET_WORKSPACE_LAYOUT_INVALID", "Workspace必须为本数据集/分类/task_id目录", doc))
        trees = [(workspace / tree).resolve() for tree in ("exec", "gt")]
        if (any(not tree.is_relative_to(workspace) for tree in trees)
                or trees[0].is_relative_to(trees[1]) or trees[1].is_relative_to(trees[0])):
            issues.append(_issue("DATASET_MATERIAL_ISOLATION_INVALID", "exec与gt必须隔离且不能越出任务Workspace", doc))
            continue
        for tree in trees:
            for item in tree.rglob("*"):
                if item.is_symlink() and not item.resolve().is_relative_to(tree):
                    issues.append(_issue("DATASET_MATERIAL_ISOLATION_INVALID", "素材链接越出其exec或gt根目录", doc))
        for tree in ("exec", "gt"):
            if not (workspace / tree).is_dir():
                issues.append(_issue("DATASET_MATERIAL_MISSING", f"缺少{tree}目录", doc))
        if not any(item.is_file() and not item.is_symlink() and item.stat().st_size > 0
                   for item in (workspace / "gt").rglob("*") if item.name != ".gitkeep"):
            issues.append(_issue("DATASET_GT_EMPTY", "注册数据集缺少真实私有评分材料", doc))
        entry = entries.get(task_id)
        if not entry:
            issues.append(_issue("DATASET_SOURCE_MISSING", "任务未登记到本数据集来源表", doc))
        else:
            attrs = entry.get("attributes")
            network = entry.get("network")
            origin = entry.get("origin")
            if (not isinstance(attrs, dict) or any(type(attrs.get(key)) is not bool for key in ("requires_visual_input", "coding_primary"))
                    or attrs["requires_visual_input"] != (doc.metadata.get("modality") == "multimodal")
                    or not isinstance(network, dict) or not isinstance(network.get("mode"), str)
                    or network["mode"] not in {"offline", "open_public_search", "site_scoped_search", "fixed_url_verification"}
                    or not isinstance(origin, dict) or not isinstance(origin.get("production_refs"), list)):
                issues.append(_issue("DATASET_SOURCE_INVALID", "来源、视觉属性或网络属性缺失/不一致", doc))
        grading_section = doc.section("Grading Criteria")
        criteria = re.findall(r"(?m)^- \[ \] `([A-Za-z][A-Za-z0-9_-]*)`:", grading_section.split("### Judge group", 1)[0])
        rubric, _ = rubric_info(doc.section("LLM Judge Rubric"))
        rubric_keys = {item["key"] for item in rubric}
        grade_type = doc.metadata.get("grading_type")
        automated_keys = set(criteria)
        expected_map = set()
        if grade_type in {"automated", "hybrid"}:
            expected_map.update(("automated." if grade_type == "hybrid" else "") + key for key in automated_keys)
        if grade_type in {"llm_judge", "hybrid"}:
            expected_map.update("llm_judge." + key for key in rubric_keys)
        capabilities = {"code_generation", "tool_use", "data_processing", "retrieval_verification",
                        "reasoning_planning", "content_generation", "verification_delivery"}
        task_map = mapping.get(task_id)
        if (not isinstance(task_map, dict) or not expected_map or set(task_map) != expected_map
                or any(not isinstance(values, list) or not 1 <= len(values) <= 2
                       or any(not isinstance(value, str) or value not in capabilities for value in values)
                       or len(set(values)) != len(values)
                       or {"retrieval_verification", "verification_delivery"}.issubset(values)
                       for values in task_map.values())):
            issues.append(_issue("DATASET_CAPABILITY_MAP_INVALID", "能力映射需精确覆盖评分key且符合七维定义", doc))
        code = strip_codeblock(doc.section("Automated Checks"))
        if code:
            try:
                tree = ast.parse(code)
                blocked = {"anthropic", "httpx", "openai", "requests", "socket", "urllib"}
                imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
                imports.update(node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module)
                if imports & blocked:
                    issues.append(_issue("DATASET_GRADER_NETWORK_IMPORT", "规则评分不得导入网络或LLM客户端", doc))
                _, code_keys, _ = ast_grade_info(code)
                if not automated_keys.issubset(code_keys) or "overall_score" not in code_keys:
                    issues.append(_issue("DATASET_GRADER_KEYS_INVALID", "规则需显式输出全部检查点及overall_score", doc))
            except SyntaxError:
                pass  # validate_document already reports the syntax error.
    return issues


_ISSUE_ACTIONS = {
    "TASK_ID_NOT_FOUND": "按所选版本清单补齐该任务；制作未完成时保留building状态",
    "DATASET_DEFINITION_INVALID": "修正catalog、系列定义或版本选择参数",
    "DATASET_TASK_LAYOUT_INVALID": "统一系列命名空间、分类和完整task_id文件名",
    "DATASET_TAGS_INVALID": "补齐系列必需标签并移除排除标签",
    "DATASET_WORKSPACE_LAYOUT_INVALID": "使用dataset.yaml指定根下的分类/task_id目录",
    "DATASET_MATERIAL_ISOLATION_INVALID": "隔离exec和gt并移除越出各自素材根的链接",
    "DATASET_MATERIAL_MISSING": "补齐真实exec/gt目录",
    "DATASET_GT_EMPTY": "制作真实私有真值和评分材料，不用占位文件代替",
    "DATASET_SOURCE_MISSING": "将该任务登记到其系列来源表",
    "DATASET_SOURCE_INVALID": "复核来源、视觉依赖、编码主交付和联网属性",
    "DATASET_CAPABILITY_MAP_INVALID": "让该系列能力映射精确覆盖本题评分检查点",
    "DATASET_GRADER_NETWORK_IMPORT": "移除规则评分中的联网或LLM依赖，保留离线可核验评分",
    "DATASET_GRADER_KEYS_INVALID": "显式返回全部规则检查点与overall_score",
    "FRONTMATTER_INVALID": "修正 YAML frontmatter，并重新运行静态校验",
    "FRONTMATTER_FIELD_MISSING": "补齐框架必需的 frontmatter 字段",
    "FRONTMATTER_FIELD_TYPE": "修正 frontmatter 字段类型",
    "CATEGORY_MISMATCH": "统一 frontmatter category、目录和任务 ID",
    "TASK_ID_FILENAME_MISMATCH": "让文件名包含 frontmatter 中的 task ID",
    "SECTION_MISSING": "补齐任务必需章节",
    "AUTOMATED_CHECKS_INVALID": "补齐可静态解析的 grade()，不要依赖不可执行的作者代码",
    "AUTOMATED_SCORE_KEYS_MISSING": "在 grade() 中返回稳定评分 key",
    "RUBRIC_INVALID": "修正 rubric key、weight 或重复定义",
    "RUBRIC_MISSING": "补齐与 grading_type 匹配的 LLM Judge Rubric",
    "GRADING_WEIGHTS_INVALID": "补齐 hybrid 任务的 grading_weights",
    "WORKSPACE_OUTSIDE_REPO": "将 Workspace Path 收敛到允许的仓库/运行时范围",
    "WORKSPACE_NOT_FOUND": "创建 Workspace 或修正 Workspace Path",
    "WORKSPACE_RESOURCE_MISSING": "补齐任务引用的 exec、gt、附件或输入文件",
    "SKILL_NOT_FOUND": "补齐声明的 Skill/SKILL.md 或修正 Skill 名称",
    "ENV_NAME_INVALID": "使用合法的 POSIX 环境变量名",
    "ENV_DUPLICATE": "删除重复 Env 声明",
    "ENV_MISSING": "在评测运行环境注入声明的 Env（报告不会显示变量值）",
    "WARMUP_REFERENCE_MISSING": "补齐 Warmup 引用脚本/文件",
    "WARMUP_SHELL_INVALID": "修正 Warmup shell 语法",
    "EXTENSION_REGISTRY_MISSING": "补齐 tasks/extension/task_sources.yaml",
    "EXTENSION_REGISTRY_INVALID": "修正扩展集任务注册表",
    "WEBSITE_CHECKER_MISSING": "按任务 ID 补齐 eval/checks/website/tasks 下的 Playwright 检查器",
    "WEBSITE_CHECKER_SYNTAX_INVALID": "修正 Playwright 检查器的 Python 语法",
    "WEBSITE_CHECKER_ENTRYPOINT_MISSING": "补齐 async run(page, screenshot_dir) 和视觉截图入口",
    "WEBSITE_RUNTIME_KEYS_MISMATCH": "让 RUNTIME_KEYS 精确覆盖所有非视觉 Rubric key",
    "WEBSITE_VISUAL_KEYS_MISMATCH": "让 VISUAL_KEYS 精确覆盖所有 visual_layout Rubric key",
    "WEBSITE_RUBRIC_DIMENSION_INVALID": "修正 Web Rubric 的 key、primary 和 secondary 维度",
    "WEBSITE_RUBRIC_FORMAT_INVALID": "修正 Criterion 编号、标题和 1.0/0.0 评分档",
    "WEBSITE_RUBRIC_WEIGHT_INVALID": "将 Web Rubric 权重设为正数并确保总和为 1",
    "WEBSITE_SUB_CATEGORY_INVALID": "将 sub_category 改为网站生成场景下登记的二级场景",
    "WEBSITE_STARTUP_CONTRACT_MISSING": "在 Prompt 中说明项目创建在 /tmp_workspace，并在端口冲突时选择其他可用端口",
    "WEBSITE_WORKSPACE_LAYOUT_INVALID": "使用规定的 Web workspace 路径并补齐 exec/ 目录",
    "WEBSITE_EVAL_FIXTURE_MISSING": "为 /tmp_workspace_eval 引用补齐 workspace/eval 评测素材",
}


def build_action_summary(task_ids: list[str], issues: list[Issue]) -> dict[str, Any]:
    grouped: dict[str, list[Issue]] = {}
    global_actions: list[str] = []
    for issue in issues:
        if issue.task_id:
            grouped.setdefault(issue.task_id, []).append(issue)
        else:
            action = _ISSUE_ACTIONS.get(issue.code, issue.message)
            if action not in global_actions:
                global_actions.append(action)
    to_fix: list[dict[str, Any]] = []
    to_review: list[dict[str, Any]] = []
    for task_id in sorted(set(task_ids) | set(grouped)):
        task_issues = grouped.get(task_id, [])
        if not task_issues:
            continue
        fail_issues = [issue for issue in task_issues if issue.severity in {FAIL, "error"}]
        review_issues = [issue for issue in task_issues if issue.severity in {REVIEW, "warning"}]
        codes = sorted({issue.code for issue in task_issues})
        actions = list(dict.fromkeys(_ISSUE_ACTIONS.get(code, "检查该用例对应的校验问题") for code in codes))
        item = {"task_id": task_id, "issue_codes": codes, "recommendations": actions, "locations": sorted({issue.location for issue in task_issues if issue.location})}
        if fail_issues:
            to_fix.append(item)
        elif review_issues:
            to_review.append({"task_id": task_id, "reasons": codes, "recommendation": "人工确认该预置条件或安全边界是否符合实际评测环境"})
    if to_fix:
        decision = "先修复需要修改的用例，再重新运行静态校验。"
    elif to_review:
        decision = "静态契约未发现确定性错误，但需要人工确认 REVIEW 用例。"
    else:
        decision = "选定范围内未发现静态校验问题。"
    return {
        "decision": decision,
        "counts": {"tasks_to_fix": len(to_fix), "tasks_for_review": len(to_review), "tasks_pass": max(0, len(set(task_ids)) - len(to_fix) - len(to_review))},
        "tasks_to_fix": to_fix,
        "tasks_for_review": to_review,
        "tasks_pass": sorted(set(task_ids) - {item["task_id"] for item in to_fix} - {item["task_id"] for item in to_review}),
        "global_actions": global_actions,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-dir", action="append", default=[])
    parser.add_argument("--task-path", action="append", default=[])
    parser.add_argument("--task-id", action="append", default=[])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--dataset-id")
    parser.add_argument("--release-id")
    parser.add_argument("--include-doc-copies", action="store_true", help="显式包含 tasks/cn 等仅供阅读的中文副本")
    parser.add_argument("--output-dir")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--warmup-image")
    parser.add_argument("--fail-on", choices=("fail", "review"), default="fail")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    selection = select_task_files(repo_root, task_dirs=args.task_dir, task_paths=args.task_path, task_ids=args.task_id, default_root="tasks", include_doc_copies=args.include_doc_copies, dataset_id=args.dataset_id, release_id=args.release_id)
    issues = list(selection.issues)
    task_ids: list[str] = []
    website_task_ids: list[str] = []
    for path in selection.files:
        try:
            document = parse_task_document(path)
            task_ids.append(document.task_id)
            if is_website_task(document):
                website_task_ids.append(document.task_id)
            issues.extend(validate_document(document, repo_root, smoke=args.smoke, warmup_image=args.warmup_image))
        except (OSError, UnicodeError) as exc:
            issues.append(Issue(FAIL, "TASK_READ_ERROR", str(exc), location=str(path)))
    issues.extend(validate_extension_registry(repo_root, selection.files))
    issues.extend(validate_registered_registry(repo_root, selection.files))
    if args.dataset_id and not (args.task_dir or args.task_path or args.task_id) and not any(issue.severity == FAIL for issue in issues):
        from eval_general_e2e.datasets.bundle import compile_dataset, load_manifest_lock
        try:
            selected = load_registered_dataset(repo_root, args.dataset_id, release_id=args.release_id)
            locked = load_manifest_lock(selected.manifest_path) if selected.status == "frozen" else None
            manifest, _ = compile_dataset(repo_root, definition=selected.definition,
                source_revision=locked["source"]["revision"] if locked else "static-validation-only")
            if locked is not None and manifest != locked:
                raise ValueError("冻结版本题面、素材或评分来源发生变化，必须发布新版本")
        except (OSError, ValueError) as exc:
            issues.append(Issue(FAIL, "DATASET_RELEASE_CONTRACT_INVALID", str(exc)))
    status = status_for_issues(issues)
    report = Report(1, status, {"repo": str(repo_root), "tasks": [str(path) for path in selection.files], "selectors": selection.selectors, "include_doc_copies": args.include_doc_copies, "dataset_id": args.dataset_id, "release_id": args.release_id, "smoke": args.smoke}, {"task_count": len(selection.files), "website_task_count": len(website_task_ids), "issue_count": len(issues), "action_summary": build_action_summary(task_ids, issues)}, issues)
    target = write_report(report, repo_root=repo_root, kind="static", output_dir=args.output_dir)
    print(target)
    return exit_code(status, fail_on_review=args.fail_on == "review")


if __name__ == "__main__":
    raise SystemExit(main())
