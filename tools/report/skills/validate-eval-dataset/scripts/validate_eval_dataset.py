#!/usr/bin/env python3
"""WildClawBench 评测集静态契约校验入口。"""

from __future__ import annotations

import argparse
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
    if "Warmup" in doc.sections and not warmup["commands"]:
        issues.append(_issue("WARMUP_EMPTY", "Warmup 章节已声明但为空", doc))
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


_ISSUE_ACTIONS = {
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
    "WARMUP_EMPTY": "补齐 Warmup，或删除不需要的 Warmup 章节",
    "WARMUP_REFERENCE_MISSING": "补齐 Warmup 引用脚本/文件",
    "WARMUP_SHELL_INVALID": "修正 Warmup shell 语法",
    "EXTENSION_REGISTRY_MISSING": "补齐 tasks/extension/task_sources.yaml",
    "EXTENSION_REGISTRY_INVALID": "修正扩展集任务注册表",
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
    parser.add_argument("--output-dir")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--warmup-image")
    parser.add_argument("--fail-on", choices=("fail", "review"), default="fail")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    selection = select_task_files(REPO_ROOT, task_dirs=args.task_dir, task_paths=args.task_path, task_ids=args.task_id, default_root="tasks")
    issues = list(selection.issues)
    task_ids: list[str] = []
    for path in selection.files:
        try:
            document = parse_task_document(path)
            task_ids.append(document.task_id)
            issues.extend(validate_document(document, REPO_ROOT, smoke=args.smoke, warmup_image=args.warmup_image))
        except (OSError, UnicodeError) as exc:
            issues.append(Issue(FAIL, "TASK_READ_ERROR", str(exc), location=str(path)))
    issues.extend(validate_extension_registry(REPO_ROOT, selection.files))
    status = status_for_issues(issues)
    report = Report(1, status, {"repo": str(REPO_ROOT), "tasks": [str(path) for path in selection.files], "selectors": selection.selectors, "smoke": args.smoke}, {"task_count": len(selection.files), "issue_count": len(issues), "action_summary": build_action_summary(task_ids, issues)}, issues)
    target = write_report(report, repo_root=REPO_ROOT, kind="static", output_dir=args.output_dir)
    print(target)
    return exit_code(status, fail_on_review=args.fail_on == "review")


if __name__ == "__main__":
    raise SystemExit(main())
