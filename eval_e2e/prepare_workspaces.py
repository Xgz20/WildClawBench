"""阶段①：准备端到端评测的项目目录、双份 Prompt 与人工执行清单。

只拷源工作区的 exec/ 内容，gt/ 留在仓库（评分阶段才送进容器），
确保交付给桌面端的项目目录不含 Ground Truth。
"""
from __future__ import annotations

import argparse
import logging
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval_e2e.e2e_manifest import (  # noqa: E402
    HARNESS_NAME,
    STATUS_PENDING,
    Manifest,
    RunEntry,
    resolve_project_dir,
    save_manifest,
)
from eval_e2e.prompt_rewrite import rewrite_prompt  # noqa: E402
from src.utils.task_parser import parse_task_md  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_E2E_ROOT = "eval_out_e2e"
PROJECT_DIR_TAIL = "tmp_workspace"


def read_task_list(path: Path) -> list[str]:
    """读 task-list，忽略空行与 # 注释行。"""
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        items.append(stripped)
    return items


def copy_exec_dir(workspace_src: Path, project_dir: Path) -> None:
    """把 workspace_src/exec/ 的内容拷到 project_dir。

    gt/ 一律不拷。exec/ 不存在时（用例无输入文件）建空目录。
    """
    project_dir.mkdir(parents=True, exist_ok=True)
    exec_dir = workspace_src / "exec"
    if not exec_dir.is_dir():
        logger.warning("源工作区无 exec/，建空项目目录: %s", workspace_src)
        return
    for item in exec_dir.iterdir():
        dest = project_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def build_run_entry(
    task_file: Path,
    repo_root: Path,
    e2e_root_rel: str,
    model: str,
    reasoning_effort: str,
) -> RunEntry:
    """从 task.md 解析出一个 RunEntry，路径一律存相对仓库根的相对路径。"""
    task = parse_task_md(task_file)
    task_id = task["task_id"]
    workspace_src = Path(task["workspace_path"])
    try:
        workspace_rel = str(workspace_src.relative_to(repo_root))
    except ValueError:
        workspace_rel = str(workspace_src)
    return RunEntry(
        task_id=task_id,
        category=task.get("category", ""),
        task_file=str(task_file.relative_to(repo_root)),
        workspace_src=workspace_rel,
        project_dir=str(Path(model) / task_id / PROJECT_DIR_TAIL),
        model=model,
        reasoning_effort=reasoning_effort,
        prompt_rewritten=False,
        prompt_rewrite_map={},
        status=STATUS_PENDING,
    )


def prepare_one(
    entry: RunEntry,
    repo_root: Path,
    e2e_root: Path,
    prompt: str,
) -> None:
    """建项目目录、拷 exec/、写双份 Prompt，并把改写记录写回 entry。"""
    project_dir = resolve_project_dir(entry, e2e_root)
    workspace_src = repo_root / entry.workspace_src
    copy_exec_dir(workspace_src, project_dir)

    case_dir = project_dir.parent
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "prompt_original.txt").write_text(prompt, encoding="utf-8")

    desktop_prompt, mapping = rewrite_prompt(prompt, project_dir)
    (case_dir / "prompt_desktop.txt").write_text(desktop_prompt, encoding="utf-8")
    entry.prompt_rewritten = bool(mapping)
    entry.prompt_rewrite_map = mapping


def render_checklist(manifest: Manifest, e2e_root: Path) -> str:
    """渲染人工执行清单：每个用例一段，含项目路径、模型、Prompt 位置与打勾位。"""
    lines = [
        "# AstronCode 桌面端人工执行清单",
        "",
        f"生成时间：{manifest.created_at}",
        f"用例数：{len(manifest.runs)}",
        "",
        "每个用例：在桌面端新建项目并选择下方「项目目录」，选好模型与推理强度，",
        "把 `prompt_desktop.txt` 全文粘贴进对话框触发执行；执行完在本行打勾。",
        "",
    ]
    for idx, entry in enumerate(manifest.runs, start=1):
        project_dir = resolve_project_dir(entry, e2e_root)
        lines += [
            f"## {idx}. {entry.task_id}",
            "",
            f"- [ ] 已执行完毕",
            f"- 项目目录：`{project_dir}`",
            f"- 模型：`{entry.model}`　推理强度：`{entry.reasoning_effort}`",
            f"- Prompt：`{project_dir.parent / 'prompt_desktop.txt'}`",
            f"- Harness：`{HARNESS_NAME}`",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="准备 AstronCode 桌面端端到端评测的项目目录与人工执行清单",
    )
    parser.add_argument("--task-list", required=True,
                        help="用例清单文件（每行一个 task.md 路径，# 为注释）")
    parser.add_argument("--model", required=True, help="要评测的模型名")
    parser.add_argument("--reasoning-effort", default="medium",
                        help="推理强度（仅记录进清单，供人工在界面选择）")
    parser.add_argument("--round", default="round-1",
                        help="轮次标识（如 round-1, round-2），用于多轮实验区分")
    parser.add_argument("--e2e-root", default=DEFAULT_E2E_ROOT,
                        help=f"端到端输出根目录（默认 {DEFAULT_E2E_ROOT}）")
    parser.add_argument("--repo-root", default="",
                        help="仓库根（默认按脚本位置推断）")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    repo_root = (Path(args.repo_root).expanduser().resolve()
                 if args.repo_root else Path(__file__).resolve().parents[1])
    e2e_root = Path(args.e2e_root).expanduser()
    if not e2e_root.is_absolute():
        e2e_root = (repo_root / e2e_root).resolve()

    task_list_path = Path(args.task_list).expanduser()
    if not task_list_path.is_absolute():
        task_list_path = repo_root / task_list_path

    entries: list[RunEntry] = []
    skipped: list[str] = []
    for rel in read_task_list(task_list_path):
        task_file = Path(rel).expanduser()
        if not task_file.is_absolute():
            task_file = repo_root / task_file
        if not task_file.is_file():
            logger.error("用例文件不存在，跳过: %s", task_file)
            skipped.append(rel)
            continue
        try:
            entry = build_run_entry(task_file, repo_root, args.e2e_root,
                                    args.model, args.reasoning_effort)
            prompt = parse_task_md(task_file)["prompt"]
            prepare_one(entry, repo_root, e2e_root, prompt)
        except (OSError, ValueError) as exc:
            logger.error("准备失败，跳过 %s: %s", rel, exc)
            skipped.append(rel)
            continue
        entries.append(entry)
        logger.info("已准备 %s -> %s", entry.task_id,
                    resolve_project_dir(entry, e2e_root))

    manifest = Manifest(
        e2e_root=args.e2e_root,
        created_at=datetime.now(timezone.utc).astimezone().isoformat(),
        round=args.round,
        runs=entries,
    )
    e2e_root.mkdir(parents=True, exist_ok=True)
    manifest_path = e2e_root / "manifest.json"
    save_manifest(manifest, manifest_path)
    checklist_path = e2e_root / "执行清单.md"
    checklist_path.write_text(render_checklist(manifest, e2e_root),
                              encoding="utf-8")

    logger.info("已准备 %d 个用例，跳过 %d 个", len(entries), len(skipped))
    logger.info("manifest: %s", manifest_path)
    logger.info("人工执行清单: %s", checklist_path)
    if skipped:
        logger.warning("跳过的用例: %s", ", ".join(skipped))


if __name__ == "__main__":
    main()
