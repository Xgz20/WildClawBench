#!/usr/bin/env python3
"""Prepare standalone Web E2E evaluation bundles.

This script reads WildClawBench task definitions and initial workspaces only.
It deliberately does not import or call eval_e2e, run_grading, website checks,
or any WildClawBench execution/grading implementation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

try:
    import yaml
except ImportError:
    sys.exit("缺少 pyyaml，请先安装：pip install pyyaml")


SCHEMA_VERSION = "wildclawbench.web-e2e-batch/v3"
REPORT_CONFIG_SCHEMA = "wildclawbench.web-e2e-report-config/v1"
SKILL_VERSION = "4.0.0"
DETAILED_PROFILE = "web-e2e-detailed-v1"
ARTIFACTSBENCH_PROFILE = "artifactsbench-web-v1"
SUPPORTED_METRIC_PROFILES = {DETAILED_PROFILE, ARTIFACTSBENCH_PROFILE}
AESTHETIC_RUBRIC_ID = "web-aesthetic-v1"
AESTHETIC_RUBRIC_VERSION = "1.1.0"
AESTHETIC_RUBRIC_SOURCE = "https://yf2ljykclb.xfchat.iflytek.com/docx/doxrz05uveZshD5b81aHYY2HIb3"
KNOWN_HARNESSES = {
    "astronstudio": "AstronStudio",
    "codex": "Codex",
    "doubaowork": "DoubaoWork",
    "qwenwork": "QwenWork",
    "workbuddy": "WorkBuddy",
    "trae": "Trae",
}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
CRITERION_RE = re.compile(r"^###\s+Criterion\s+(\d+)\s*[:：]\s*(.*?)\s*\((.*?)\)\s*$")
META_RE = re.compile(r"(?:^|,)\s*(key|primary|secondary|weight)\s*:\s*([^,]+)\s*")
SCORING_FIXTURE_RE = re.compile(r"/tmp_workspace_eval/([A-Za-z0-9][A-Za-z0-9._/-]*)")
EVIDENCE_METHOD_RE = re.compile(r"^采证方式[：:]\s*(.+?)\s*$", re.MULTILINE)


def find_repo_root(start: Path) -> Path:
    """Find the repository root from either the canonical Skill or its symlink."""
    current = start.expanduser().resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (
            (candidate / "tasks").is_dir()
            and (candidate / "workspace").is_dir()
            and (candidate / "tools/report/skills").is_dir()
        ):
            return candidate
    raise FileNotFoundError(f"无法从 {start} 定位 WildClawBench 仓库根目录")


def rewrite_execution_text(value: str) -> tuple[str, dict[str, str]]:
    """Resolve the container workspace inside a single-task execution root."""
    rewritten = value.replace("/tmp_workspace/", "./workspace/")
    rewritten = re.sub(r"/tmp_workspace\b", "./workspace", rewritten)
    mapping = {"/tmp_workspace": "./workspace"} if rewritten != value else {}
    return rewritten, mapping


def rewrite_scoring_text(value: str) -> str:
    """Resolve task and private fixture paths inside a single-task score root."""
    rewritten = value.replace("/tmp_workspace_eval/", "./private-scoring/fixtures/")
    rewritten = re.sub(r"/tmp_workspace_eval\b", "./private-scoring/fixtures", rewritten)
    rewritten = rewritten.replace("/tmp_workspace/", "./workspace/")
    return re.sub(r"/tmp_workspace\b", "./workspace", rewritten)


def referenced_scoring_fixtures(task: dict) -> list[PurePosixPath]:
    text = "\n".join((task["expected_behavior"], task["llm_judge_rubric"]))
    result: list[PurePosixPath] = []
    for raw in SCORING_FIXTURE_RE.findall(text):
        relative = PurePosixPath(raw)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"评分素材路径非法: {task['task_id']}: {raw}")
        if relative not in result:
            result.append(relative)
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
    return digest.hexdigest()


def git_revision(repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo_root,
        capture_output=True, text=True,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def default_batch_id(now: datetime | None = None) -> str:
    current = now or datetime.now().astimezone()
    return f"web-e2e-{current.strftime('%Y%m%d-%H%M%S')}"


def read_ids(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value.startswith("@"):
            lines = Path(value[1:]).expanduser().read_text(encoding="utf-8").splitlines()
            result.extend(line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#"))
        else:
            result.append(value.strip())
    return list(dict.fromkeys(item for item in result if item))


def split_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        raise ValueError(f"题目缺少 YAML frontmatter: {path}")
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ValueError(f"题目 frontmatter 不是对象: {path}")
    return metadata, match.group(2)


def split_sections(body: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current = ""
    for line in body.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1)
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def strip_fence(value: str) -> str:
    match = re.search(r"```[^\n]*\n(.*?)\n```", value.strip(), re.DOTALL)
    return (match.group(1) if match else value).strip()


def resolve_metric_profile(metadata: dict, requested: str = "auto") -> str:
    requested = str(requested or "auto").strip().lower()
    if requested != "auto":
        if requested not in SUPPORTED_METRIC_PROFILES:
            raise ValueError(f"不支持的 metric profile: {requested}")
        return requested
    explicit = str(metadata.get("metric_profile") or "").strip().lower()
    if explicit:
        if explicit not in SUPPORTED_METRIC_PROFILES:
            raise ValueError(f"题目声明了不支持的 metric_profile: {explicit}")
        return explicit
    source = metadata.get("source") or {}
    benchmark = str(source.get("benchmark") or "") if isinstance(source, dict) else ""
    if benchmark.strip().lower() == "artifactsbench":
        return ARTIFACTSBENCH_PROFILE
    return DETAILED_PROFILE


def scoring_config(metric_profile: str) -> dict:
    if metric_profile == ARTIFACTSBENCH_PROFILE:
        return {
            "input": "raw_score",
            "raw_scale": {"minimum": 0, "maximum": 10, "step": 1},
            "normalized_scale": {"minimum": 0, "maximum": 1},
            "normalization": "raw_score / 10",
            "aggregate": "weighted_mean",
        }
    return {
        "input": "score",
        "normalized_scale": {"minimum": 0, "maximum": 1},
        "aggregate": "weighted_mean",
    }


def parse_criteria(rubric: str, path: Path, metric_profile: str = DETAILED_PROFILE) -> list[dict]:
    criteria: list[dict] = []
    current: dict | None = None
    body: list[str] = []
    for line in rubric.splitlines():
        match = CRITERION_RE.match(line.strip())
        if match:
            if current is not None:
                current["rubric"] = "\n".join(body).strip()
                criteria.append(current)
            metadata = {key: value.strip() for key, value in META_RE.findall(match.group(3))}
            try:
                weight = float(metadata.get("weight", ""))
            except ValueError as exc:
                raise ValueError(f"Rubric weight 非数字: {path}: {line}") from exc
            current = {
                "index": int(match.group(1)),
                "name": match.group(2).strip(),
                "key": metadata.get("key", ""),
                "primary": metadata.get("primary", ""),
                "secondary": metadata.get("secondary", ""),
                "weight": weight,
            }
            body = [line]
        elif current is not None:
            body.append(line)
    if current is not None:
        current["rubric"] = "\n".join(body).strip()
        criteria.append(current)
    for item in criteria:
        method_match = EVIDENCE_METHOD_RE.search(item["rubric"])
        item["evidence_method"] = method_match.group(1).strip() if method_match else ""
        item["evidence_policy"] = {
            "required_types": ["screenshot"] if "截图" in item["evidence_method"] else [],
        }
    keys = [item["key"] for item in criteria]
    if not criteria or any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError(f"Rubric criterion key 缺失或重复: {path}")
    if [item["index"] for item in criteria] != list(range(1, len(criteria) + 1)):
        raise ValueError(f"Rubric criterion 编号不连续: {path}")
    if any(item["weight"] <= 0 for item in criteria):
        raise ValueError(f"Rubric criterion 权重必须为正数: {path}")
    if metric_profile == DETAILED_PROFILE:
        if any(not item["primary"] or not item["secondary"] for item in criteria):
            raise ValueError(f"Rubric criterion 缺少维度: {path}")
        allowed_primary = {"content_structure", "interaction_function", "visual_layout"}
        invalid_primary = sorted({item["primary"] for item in criteria if item["primary"] not in allowed_primary})
        if invalid_primary:
            raise ValueError(f"Rubric criterion 一级维度非法 {invalid_primary}: {path}")
        for item in criteria:
            if not re.search(r"Score\s+1\.0", item["rubric"], re.IGNORECASE):
                raise ValueError(f"Rubric criterion 缺少 Score 1.0: {path}: {item['key']}")
            if not re.search(r"Score\s+0\.0", item["rubric"], re.IGNORECASE):
                raise ValueError(f"Rubric criterion 缺少 Score 0.0: {path}: {item['key']}")
    if abs(sum(item["weight"] for item in criteria) - 1.0) > 0.001:
        raise ValueError(f"Rubric criterion 权重之和不为 1: {path}")
    return criteria


def resolve_task_file(repo_root: Path, task_id: str) -> Path:
    matches = [
        path for path in (repo_root / "tasks").rglob(f"{task_id}.md")
        if "cn" not in path.relative_to(repo_root / "tasks").parts
    ]
    if len(matches) != 1:
        raise ValueError(f"用例 ID 应唯一命中 1 个定义，实际 {len(matches)} 个: {task_id}")
    return matches[0]


def parse_task(repo_root: Path, task_id: str, requested_profile: str = "auto") -> dict:
    path = resolve_task_file(repo_root, task_id)
    text = path.read_text(encoding="utf-8")
    metadata, body = split_frontmatter(text, path)
    metric_profile = resolve_metric_profile(metadata, requested_profile)
    sections = split_sections(body)
    tags_raw = metadata.get("tags") or []
    tags = [item.strip().lower() for item in (tags_raw.split(",") if isinstance(tags_raw, str) else tags_raw)]
    if "web-site-gen" not in tags:
        raise ValueError(f"用例不是 web-site-gen: {task_id}")
    required = ["Prompt", "Expected Behavior", "LLM Judge Rubric", "Workspace Path"]
    missing = [name for name in required if not sections.get(name, "").strip()]
    if missing:
        raise ValueError(f"用例缺少章节 {missing}: {task_id}")
    if not re.search(r"/tmp_workspace\b", sections["Prompt"]):
        raise ValueError(f"Prompt 缺少 /tmp_workspace 工作目录约束: {task_id}")
    workspace_raw = Path(strip_fence(sections["Workspace Path"]))
    workspace = workspace_raw if workspace_raw.is_absolute() else repo_root / workspace_raw
    workspace = workspace.resolve()
    exec_dir = workspace / "exec"
    if metric_profile == DETAILED_PROFILE and not exec_dir.is_dir():
        raise ValueError(f"Workspace 缺少 exec/: {task_id}: {workspace}")
    if metric_profile == ARTIFACTSBENCH_PROFILE and exec_dir.exists() and not exec_dir.is_dir():
        raise ValueError(f"Workspace exec 不是目录: {task_id}: {exec_dir}")
    criteria = parse_criteria(sections["LLM Judge Rubric"], path, metric_profile)
    workspace_seed = exec_dir if exec_dir.is_dir() else None
    return {
        "task_id": task_id,
        "name": str(metadata.get("name") or task_id),
        "difficulty": str(metadata.get("difficulty") or "unknown"),
        "prompt": sections["Prompt"],
        "expected_behavior": sections["Expected Behavior"],
        "llm_judge_rubric": sections["LLM Judge Rubric"],
        "criteria": criteria,
        "metric_profile": metric_profile,
        "scoring": scoring_config(metric_profile),
        "task_file": path,
        "task_source": path.relative_to(repo_root).as_posix(),
        "workspace": workspace,
        "exec_dir": workspace_seed,
        "eval_dir": workspace / "eval",
        "task_sha256": sha256_file(path),
        "workspace_sha256": sha256_tree(exec_dir) if workspace_seed else synthetic_empty_workspace_sha256(),
    }


def safe_copy_exec(source: Path, destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"目标已存在，拒绝覆盖: {destination}")
    shutil.copytree(source, destination)
    forbidden = {"gt", "eval"}
    leaks = [path for path in destination.rglob("*") if any(part in forbidden for part in path.relative_to(destination).parts)]
    if leaks:
        raise ValueError(f"执行 Workspace 含评分目录: {leaks[0]}")


def synthetic_empty_workspace_sha256() -> str:
    digest = hashlib.sha256()
    digest.update(b".gitkeep\0")
    digest.update(bytes.fromhex(hashlib.sha256(b"").hexdigest()))
    return digest.hexdigest()


def stage_execution_workspace(task: dict, destination: Path) -> None:
    source = task.get("exec_dir")
    if source is not None:
        safe_copy_exec(source, destination)
        return
    if destination.exists():
        raise FileExistsError(f"目标已存在，拒绝覆盖: {destination}")
    destination.mkdir(parents=True)
    (destination / ".gitkeep").write_bytes(b"")


def model_for_harness(harness: str, default_model: str, model_map: dict[str, str]) -> str:
    return model_map.get(harness, default_model)


def parse_harness_map(values: list[str], option_name: str) -> dict[str, str]:
    result = {}
    for raw in values:
        if "=" not in raw:
            raise ValueError(f"{option_name} 必须是 harness=value: {raw}")
        key, value = (item.strip() for item in raw.split("=", 1))
        if not key or not value:
            raise ValueError(f"{option_name} 必须是非空 harness=value: {raw}")
        result[key] = value
    return result


def build_report_config(
    batch_id: str,
    metric_profile: str,
    harnesses: list[str],
    default_model: str,
    model_map: dict[str, str],
    default_reasoning_effort: str,
    reasoning_effort_map: dict[str, str],
) -> dict:
    units = []
    for order, harness in enumerate(harnesses, start=1):
        model = model_for_harness(harness, default_model, model_map)
        units.append({
            "model_id": model,
            "model_display_name": model,
            "harness_id": harness,
            "harness_display_name": KNOWN_HARNESSES.get(harness, harness),
            "reasoning_effort": reasoning_effort_map.get(harness, default_reasoning_effort),
            "order": order,
        })
    return {
        "schema_version": REPORT_CONFIG_SCHEMA,
        "batch_id": batch_id,
        "metric_profile": metric_profile,
        "configuration_status": "ready" if all(item["model_id"] for item in units) else "requires_model_mapping",
        "units": units,
    }


def write_report_config(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Web E2E 批次报告配置。此文件不进入 execution/scoring 分发包。\n"
        "# 生成报告前必须补全空的 model_id；model_display_name 和 reasoning_effort 可按实际配置修改。\n"
    )
    path.write_text(
        header + yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def execution_record(batch_id: str, harness: str, harness_display: str, model: str, task_id: str) -> dict:
    return {
        "schema_version": "wildclawbench.web-e2e-execution/v1",
        "batch_id": batch_id,
        "task_id": task_id,
        "model": {"id": model, "display_name": model},
        "harness": {"id": harness, "display_name": harness_display, "version": ""},
        "execution": {
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "duration_seconds": None,
            "error": None,
        },
        "usage": {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "request_count": None,
            "cost_usd": None,
        },
        "tools": {
            "call_count": None,
            "format_accuracy": None,
        },
        "artifacts": {
            "harness_transcript": None,
        },
    }


def task_contract(
    batch_id: str,
    revision: str,
    harness: str,
    harness_display: str,
    task: dict,
    aesthetic_rubric: str | None = None,
) -> dict:
    criteria = copy.deepcopy(task["criteria"])
    for criterion in criteria:
        criterion["rubric"] = rewrite_scoring_text(criterion["rubric"])
    return {
        "schema_version": "wildclawbench.web-e2e-task-contract/v3",
        "metric_profile": task["metric_profile"],
        "scoring": copy.deepcopy(task["scoring"]),
        "identity": {
            "batch_id": batch_id,
            "source_revision": revision,
            "task_id": task["task_id"],
            "task_name": task["name"],
            "difficulty": task["difficulty"],
            "harness": {"id": harness, "display_name": harness_display},
        },
        "prompt": rewrite_scoring_text(task["prompt"]),
        "expected_behavior": rewrite_scoring_text(task["expected_behavior"]),
        "llm_judge_rubric": rewrite_scoring_text(task["llm_judge_rubric"]),
        "criteria": criteria,
        "path_rewrite_map": {
            "/tmp_workspace": "./workspace",
            "/tmp_workspace_eval": "./private-scoring/fixtures",
        },
        "report_dimensions": (
            ["overall", "difficulty"]
            if task["metric_profile"] == ARTIFACTSBENCH_PROFILE
            else ["overall", "difficulty", "primary", "secondary", "aesthetic"]
        ),
        "aesthetic_metric": (
            {
                "max_score": 100,
                "included_in_total": False,
                "status": "defined",
                "rubric_id": AESTHETIC_RUBRIC_ID,
                "rubric_version": AESTHETIC_RUBRIC_VERSION,
                "scoring_mode": "joint_screenshot_set",
                "source_url": AESTHETIC_RUBRIC_SOURCE,
                "additional_instructions": aesthetic_rubric,
            }
            if task["metric_profile"] == DETAILED_PROFILE
            else {"included_in_total": False, "status": "not_applicable"}
        ),
        "source": {
            "task_file": task["task_source"],
            "task_sha256": task["task_sha256"],
            "workspace_exec_sha256": task["workspace_sha256"],
        },
    }


def copy_referenced_fixtures(task: dict, destination: Path) -> list[str]:
    copied = []
    for relative in referenced_scoring_fixtures(task):
        source = task["eval_dir"].joinpath(*relative.parts)
        if not source.is_file():
            raise FileNotFoundError(f"Rubric 引用的评分素材不存在: {task['task_id']}: {source}")
        target = destination.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(relative.as_posix())
    return copied


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def render_checklist(batch_id: str, harness: str, tasks: list[dict], include_execution_record: bool) -> str:
    rows = [
        f"# Web E2E 执行清单：{batch_id} / {KNOWN_HARNESSES.get(harness, harness)}",
        "",
        "> 被评 Harness 选择 `execution/tasks/<task_id>/`；评分 Agent 选择 `score/tasks/<task_id>/`。每题分别新建工作空间和会话。",
        "",
        f"- Harness：{KNOWN_HARNESSES.get(harness, harness)} (`{harness}`)",
        f"- 用例数：{len(tasks)}",
        "",
    ]
    for task in tasks:
        task_id = task["task_id"]
        task_rows = [
            f"## {task_id} · {task['name']}",
            "",
            f"- [ ] 选择项目目录：`execution/tasks/{task_id}`",
            f"- [ ] 粘贴唯一 Prompt：`execution/tasks/{task_id}/PROMPT.md`",
            f"- [ ] 确认产物位于：`execution/tasks/{task_id}/workspace/`",
        ]
        if include_execution_record:
            task_rows.append(
                f"- [ ] 更新执行状态：`execution/tasks/{task_id}/execution_record.json`；未知资源字段保留 `null`"
            )
        task_rows.append("")
        rows.extend(task_rows)
    rows.extend([
        "## 评分阶段",
        "",
        "1. 把整个 Harness 根目录压缩为 execution 备份并移到根目录外。",
        "2. 将 `execution/tasks/` 整个复制到根目录已有的 `score/` 下，得到 `score/tasks/`。",
        "3. 把对应 `__scoring.zip` 解压到 Harness 根目录，选择合并目录，不能替换整个 `score/`。",
        "4. 若 ZIP 工具不能正确合并，请把 scoring ZIP 放在 Harness 根目录同级或根目录内，保持 `score/` 没有真实内容，再双击 `准备评分工作空间.command`（macOS）或 `准备评分工作空间.cmd`（Windows）；空目录和常见系统元数据可自动清理，兜底要求本机有 Python。",
        "5. 在评分智能体中导入管理员另行提供的 `score-web-e2e` 离线 Skill ZIP，每台评分客户端只安装一次。",
        "6. 每题在评分智能体中选择 `score/tasks/<task_id>/`，新建会话并触发 `$score-web-e2e`。",
        "7. 全部评分后按评分 Skill 的回传准备流程关闭服务、清理可重建的 `node_modules`，生成根目录 `submission.json` 再压缩回传。",
        "",
    ])
    return "\n".join(rows)


def zip_selected(
    source: Path,
    destination: Path,
    prefixes: tuple[str, ...],
    archive_prefix: str = "",
    empty_directories: tuple[str, ...] = (),
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in empty_directories:
            archived = f"{archive_prefix}/{relative}" if archive_prefix else relative
            archive.writestr(f"{archived.rstrip('/')}/", b"")
        for path in sorted(p for p in source.rglob("*") if p.is_file()):
            relative = path.relative_to(source).as_posix()
            if relative in prefixes or any(relative.startswith(f"{prefix}/") for prefix in prefixes):
                archived = f"{archive_prefix}/{relative}" if archive_prefix else relative
                archive.write(path, archived)


def zip_skill(source: Path, destination: Path) -> int:
    """Package one independently installable Skill, once per batch."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_count = 0
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            if "__pycache__" in path.parts or path.suffix == ".pyc" or path.name == ".DS_Store":
                continue
            archived = PurePosixPath(source.name, path.relative_to(source).as_posix()).as_posix()
            archive.write(path, archived)
            file_count += 1
    return file_count


def package_score_skill(args: argparse.Namespace) -> dict:
    """Build only the independently installable scoring Skill ZIP."""
    repo_root = Path(args.repo_root).expanduser().resolve()
    output_root = Path(args.output_dir).expanduser().resolve()
    batch_id = str(getattr(args, "batch_id", "") or default_batch_id()).strip()
    if not SLUG_RE.fullmatch(batch_id):
        raise ValueError(f"批次 ID 不是安全 slug: {batch_id}")
    scoring_skill = repo_root / "tools/report/skills/score-web-e2e"
    if not (scoring_skill / "SKILL.md").is_file():
        raise FileNotFoundError(f"缺少评分 Skill: {scoring_skill}")
    package_path = output_root / f"{batch_id}__score-web-e2e-skill.zip"
    if package_path.exists():
        raise FileExistsError(f"评分 Skill 包已存在，拒绝覆盖: {package_path}")
    file_count = zip_skill(scoring_skill, package_path)
    return {
        "path": package_path,
        "file_count": file_count,
        "sha256": sha256_file(package_path),
    }


def prepare(args: argparse.Namespace) -> Path:
    repo_root = Path(args.repo_root).expanduser().resolve()
    output_root = Path(args.output_dir).expanduser().resolve()
    batch_id = str(getattr(args, "batch_id", "") or default_batch_id()).strip()
    if not SLUG_RE.fullmatch(batch_id):
        raise ValueError(f"批次 ID 不是安全 slug: {batch_id}")
    args.batch_id = batch_id
    batch_root = output_root / batch_id
    if batch_root.exists():
        raise FileExistsError(f"批次目录已存在，拒绝覆盖: {batch_root}")
    task_ids = read_ids(args.task_id)
    harnesses = list(dict.fromkeys(args.harness))
    if not task_ids:
        raise ValueError("至少提供一个 --task-id")
    if not harnesses:
        raise ValueError("至少提供一个 --harness")
    for harness in harnesses:
        if not SLUG_RE.fullmatch(harness):
            raise ValueError(f"Harness ID 不是安全 slug: {harness}")
    model_map = parse_harness_map(getattr(args, "model_map", []), "--model-map")
    reasoning_effort_map = parse_harness_map(
        getattr(args, "reasoning_effort_map", []),
        "--reasoning-effort-map",
    )
    default_model = str(getattr(args, "model", "") or "").strip()
    default_reasoning_effort = str(getattr(args, "reasoning_effort", "") or "").strip()
    aesthetic_rubric = None
    if args.aesthetic_rubric:
        aesthetic_rubric = Path(args.aesthetic_rubric).expanduser().read_text(encoding="utf-8").strip()
        if not aesthetic_rubric:
            raise ValueError("--aesthetic-rubric 文件为空")

    requested_profile = str(getattr(args, "metric_profile", "auto") or "auto").strip().lower()
    tasks = [parse_task(repo_root, task_id, requested_profile) for task_id in task_ids]
    metric_profiles = {task["metric_profile"] for task in tasks}
    if len(metric_profiles) != 1:
        raise ValueError(f"同一批次不能混合 metric profile: {sorted(metric_profiles)}")
    metric_profile = next(iter(metric_profiles))
    if aesthetic_rubric and metric_profile != DETAILED_PROFILE:
        raise ValueError("artifactsbench-web-v1 不使用独立美观度指标，不能传 --aesthetic-rubric")
    for task in tasks:
        if "/tmp_workspace_eval" in task["prompt"]:
            raise ValueError(f"Prompt 不得暴露私有评分素材路径: {task['task_id']}")
    scoring_skill = repo_root / "tools/report/skills/score-web-e2e"
    if not (scoring_skill / "SKILL.md").is_file():
        raise FileNotFoundError(f"缺少评分 Skill: {scoring_skill}")
    report_skill = repo_root / "tools/report/skills/report-web-e2e"
    if not (report_skill / "SKILL.md").is_file():
        raise FileNotFoundError(f"缺少报告 Skill: {report_skill}")
    created_at = datetime.now(timezone.utc).isoformat()
    revision = git_revision(repo_root)
    include_execution_record = bool(getattr(args, "include_execution_record", False))
    package_rows = []
    batch_root.mkdir(parents=True)
    score_skill_package = batch_root / "packages" / f"{args.batch_id}__score-web-e2e-skill.zip"
    zip_skill(scoring_skill, score_skill_package)
    package_rows.append({
        "harness": None,
        "package_type": "score_skill",
        "path": score_skill_package.relative_to(batch_root).as_posix(),
        "sha256": sha256_file(score_skill_package),
    })
    report_skill_package = batch_root / "packages" / f"{args.batch_id}__report-web-e2e-skill.zip"
    zip_skill(report_skill, report_skill_package)
    package_rows.append({
        "harness": None,
        "package_type": "report_skill",
        "path": report_skill_package.relative_to(batch_root).as_posix(),
        "sha256": sha256_file(report_skill_package),
    })
    report_config_path = batch_root / f"{args.batch_id}__report-config.yaml"
    report_config = build_report_config(
        args.batch_id,
        metric_profile,
        harnesses,
        default_model,
        model_map,
        default_reasoning_effort,
        reasoning_effort_map,
    )
    write_report_config(report_config_path, report_config)

    for harness in harnesses:
        harness_dir = batch_root / "harnesses" / harness
        package_root_name = f"{args.batch_id}__{harness}"
        harness_display = KNOWN_HARNESSES.get(harness, harness)
        model = model_for_harness(harness, default_model, model_map)
        entries = []
        for task in tasks:
            task_id = task["task_id"]
            execution_dir = harness_dir / "execution" / "tasks" / task_id
            score_dir = harness_dir / "score" / "tasks" / task_id
            stage_execution_workspace(task, execution_dir / "workspace")
            effective_prompt, prompt_rewrite_map = rewrite_execution_text(task["prompt"])
            (execution_dir / "PROMPT.md").write_text(effective_prompt + "\n", encoding="utf-8")
            if include_execution_record:
                write_json(
                    execution_dir / "execution_record.json",
                    execution_record(args.batch_id, harness, harness_display, model, task_id),
                )
            write_json(
                score_dir / "private-scoring" / "task_contract.json",
                task_contract(
                    args.batch_id,
                    revision,
                    harness,
                    harness_display,
                    task,
                    aesthetic_rubric,
                ),
            )
            copy_referenced_fixtures(
                task,
                score_dir / "private-scoring" / "fixtures",
            )
            (score_dir / ".web-e2e-scoring-ready").write_text(
                f"{args.batch_id}\n{task_id}\n", encoding="utf-8"
            )
            entries.append({
                "task_id": task_id,
                "task_name": task["name"],
                "difficulty": task["difficulty"],
                "metric_profile": task["metric_profile"],
                "execution_dir": f"execution/tasks/{task_id}",
                "prompt_file": f"execution/tasks/{task_id}/PROMPT.md",
                "prompt_rewrite_map": prompt_rewrite_map,
                "task_sha256": task["task_sha256"],
                "workspace_exec_sha256": task["workspace_sha256"],
            })
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "skill_version": SKILL_VERSION,
            "batch_id": args.batch_id,
            "created_at": created_at,
            "source_revision": revision,
            "metric_profile": metric_profile,
            "package_root": package_root_name,
            "scoring_archive": f"{args.batch_id}__{harness}__scoring.zip",
            "execution_record_included": include_execution_record,
            "harness": {"id": harness, "display_name": harness_display},
            "tasks": entries,
        }
        write_json(harness_dir / "manifest.json", manifest)
        (harness_dir / "执行清单.md").write_text(
            render_checklist(args.batch_id, harness, tasks, include_execution_record), encoding="utf-8"
        )
        helper_source = repo_root / "tools/report/skills/prepare-web-e2e-workspaces/scripts/prepare_scoring_workspace.py"
        helper_dir = harness_dir / "tools"
        helper_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(helper_source, helper_dir / helper_source.name)
        assets_dir = repo_root / "tools/report/skills/prepare-web-e2e-workspaces/assets"
        for filename in ("准备评分工作空间.command", "准备评分工作空间.cmd"):
            target = harness_dir / filename
            shutil.copy2(assets_dir / filename, target)
            if filename.endswith(".command"):
                target.chmod(0o755)
        execution_package = batch_root / "packages" / f"{args.batch_id}__{harness}__execution.zip"
        scoring_package = batch_root / "packages" / f"{args.batch_id}__{harness}__scoring.zip"
        zip_selected(
            harness_dir,
            execution_package,
            (
                "manifest.json",
                "执行清单.md",
                "execution",
                "tools/prepare_scoring_workspace.py",
                "准备评分工作空间.command",
                "准备评分工作空间.cmd",
            ),
            archive_prefix=package_root_name,
            empty_directories=("score",),
        )
        zip_selected(
            harness_dir,
            scoring_package,
            ("score",),
        )
        for package_type, package_path in (("execution", execution_package), ("scoring", scoring_package)):
            package_rows.append({
                "harness": harness,
                "package_type": package_type,
                "path": package_path.relative_to(batch_root).as_posix(),
                "sha256": sha256_file(package_path),
            })

    write_json(batch_root / "batch_manifest.json", {
        "schema_version": SCHEMA_VERSION,
        "skill_version": SKILL_VERSION,
        "batch_id": args.batch_id,
        "created_at": created_at,
        "source_revision": revision,
        "metric_profile": metric_profile,
        "task_ids": task_ids,
        "harnesses": harnesses,
        "score_skill_archive": score_skill_package.relative_to(batch_root).as_posix(),
        "report_skill_archive": report_skill_package.relative_to(batch_root).as_posix(),
        "report_config": report_config_path.relative_to(batch_root).as_posix(),
        "report_config_ready": report_config["configuration_status"] == "ready",
        "execution_record_included": include_execution_record,
        "packages": package_rows,
    })
    return batch_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="准备独立 Web 站点端到端评测工作空间")
    parser.add_argument("--task-id", action="append", default=[], help="用例 ID；可重复，或传 @文件")
    parser.add_argument("--harness", action="append", default=[], help="Harness ID；可重复")
    parser.add_argument(
        "--metric-profile",
        default="auto",
        choices=("auto", DETAILED_PROFILE, ARTIFACTSBENCH_PROFILE),
        help="评分指标 Profile；auto 根据题目 source.benchmark 识别",
    )
    parser.add_argument(
        "--score-skill-only",
        action="store_true",
        help="只在 output-dir 生成独立评分 Skill ZIP；不需要 task-id 或 harness",
    )
    parser.add_argument(
        "--batch-id",
        default="",
        help="批次 ID；不传时按本机时间生成 web-e2e-YYYYMMDD-HHMMSS",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model", default="", help="全部 Harness 默认模型 ID")
    parser.add_argument("--model-map", action="append", default=[], help="按 Harness 覆盖模型：harness=model")
    parser.add_argument("--reasoning-effort", default="", help="全部 Harness 默认推理强度，仅写入批次报告配置")
    parser.add_argument(
        "--reasoning-effort-map",
        action="append",
        default=[],
        help="按 Harness 覆盖推理强度：harness=effort，仅写入批次报告配置",
    )
    parser.add_argument(
        "--include-execution-record",
        action="store_true",
        help="可选：在每个执行工作空间生成 execution_record.json；默认不生成",
    )
    parser.add_argument("--aesthetic-rubric", default="", help="可选：内置美观度标准之外的批次补充说明 Markdown")
    parser.add_argument("--repo-root", default=str(find_repo_root(Path(__file__))))
    return parser


def main() -> None:
    args = build_parser().parse_args()
    try:
        if args.score_skill_only:
            result = package_score_skill(args)
        else:
            batch_root = prepare(args)
    except (OSError, ValueError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    if args.score_skill_only:
        print(json.dumps({
            "status": "PASS",
            "path": str(result["path"]),
            "file_count": result["file_count"],
            "sha256": result["sha256"],
        }, ensure_ascii=False))
        return
    print(f"PASS: {batch_root}")


if __name__ == "__main__":
    main()
