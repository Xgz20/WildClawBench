"""阶段③：把项目目录挂为容器 /tmp_workspace 并复用现有 run_grading 评分。

评分口径与 CLI 侧同源同码：容器内路径固定 /tmp_workspace，gt/ 在评分前单独
docker cp 进容器（复刻 eval/run_batch.py:130），grade() 参数由 parse_task_md
原样透传。
"""
from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eval_e2e.e2e_manifest import (  # noqa: E402
    STATUS_GRADED,
    RunEntry,
    load_manifest,
    resolve_project_dir,
    resolve_repo_path,
    save_manifest,
)
from src.utils.docker_utils import remove_container, start_container  # noqa: E402
from src.utils.grading import run_grading, write_error_score  # noqa: E402
from src.utils.task_parser import parse_task_md  # noqa: E402

logger = logging.getLogger(__name__)

DEFAULT_DOCKER_IMAGE = "wildclawbench-astroncode-ubuntu:v0.6"
TMP_WORKSPACE = "/tmp_workspace"


def copy_gt_into_container(task_id: str, workspace_src: Path) -> bool:
    """把源工作区的 gt/ 送进容器；无 gt/ 时跳过。"""
    gt_host = workspace_src / "gt"
    if not gt_host.is_dir():
        return False
    proc = subprocess.run(
        ["docker", "cp", str(gt_host), f"{task_id}:{TMP_WORKSPACE}/gt"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        logger.warning("[%s] gt 拷入失败: %s", task_id, proc.stderr)
        return False
    return True


def find_existing_run_dir(out_root: Path, entry: RunEntry, harness: str, round: str) -> Path | None:
    base = (out_root / "results" / harness / round / entry.model
            / entry.category / entry.task_id)
    if not base.is_dir():
        return None
    slugs = sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.name)
    return slugs[-1] if slugs else None


def grade_one(
    entry: RunEntry,
    repo_root: Path,
    e2e_root: Path,
    out_root: Path,
    docker_image: str,
    harness: str,
    round: str,
    run_dir: Path | None = None,
) -> dict:
    """单例评分：起容器 → 送 gt → run_grading → 写 score.json。异常不外抛。"""
    if run_dir is None:
        run_dir = find_existing_run_dir(out_root, entry, harness, round)
    if run_dir is None:
        return {"status": "error", "note": "结果目录不存在，请先运行 collect_runs.py"}
    run_dir.mkdir(parents=True, exist_ok=True)

    task_file = resolve_repo_path(entry.task_file, repo_root)
    workspace_src = resolve_repo_path(entry.workspace_src, repo_root)
    project_dir = resolve_project_dir(entry, e2e_root)
    task_id = entry.task_id

    try:
        task = parse_task_md(task_file)
    except (OSError, ValueError) as exc:
        write_error_score(run_dir, task_id, f"用例解析失败: {exc}")
        return {"status": "error", "note": str(exc)}

    try:
        remove_container(task_id)
        start_container(
            task_id, str(project_dir),
            extra_env=task.get("env", ""),
            docker_image=docker_image,
        )
        # 桌面端评测：把项目目录（含 agent 产物）复制到容器工作区
        logger.info("[%s] 复制项目目录到容器: %s → /tmp_workspace", task_id, project_dir)
        cp_proc = subprocess.run(
            ["docker", "cp", f"{project_dir}/.", f"{task_id}:/tmp_workspace/"],
            capture_output=True, text=True,
        )
        if cp_proc.returncode != 0:
            raise RuntimeError(f"项目目录复制失败: {cp_proc.stderr}")
        copy_gt_into_container(task_id, workspace_src)
        scores = run_grading(
            task_id=task_id,
            automated_checks=task.get("automated_checks", ""),
            output_dir=run_dir,
            extra_env=task.get("env", ""),
            transcript_container_path="",
            write_error_score=True,
            llm_judge_rubric=task.get("llm_judge_rubric", ""),
            rubric_criteria=task.get("rubric_criteria") or [],
            grading_weights=task.get("grading_weights") or {},
            metric_profile=task.get("metric_profile", ""),
            task_definition_id=task.get("task_id", ""),
            judge_evidence=task.get("judge_evidence") or {},
        )
    except Exception as exc:  # 容器/评分任何失败都落盘并继续
        logger.error("[%s] 评分失败: %s", task_id, exc)
        write_error_score(run_dir, task_id, str(exc))
        return {"status": "error", "note": str(exc)}
    finally:
        remove_container(task_id)

    entry.status = STATUS_GRADED
    return {"status": STATUS_GRADED, "scores": scores, "run_dir": str(run_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description="端到端评测阶段③：评分")
    parser.add_argument("--manifest", required=True, help="manifest.json 路径")
    parser.add_argument("--e2e-root", default="", help="项目目录根，默认取 manifest 内相对值")
    parser.add_argument("--out-root", required=True, help="结果根目录（同 collect 阶段）")
    parser.add_argument("--docker-image", default=DEFAULT_DOCKER_IMAGE)
    parser.add_argument("--only", default="", help="只处理指定 task_id")
    parser.add_argument("--resume", action="store_true", help="跳过已评分项")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    repo_root = Path(__file__).resolve().parents[1]
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_manifest(manifest_path)
    e2e_root = (Path(args.e2e_root).expanduser().resolve() if args.e2e_root
                else resolve_repo_path(manifest.e2e_root, repo_root))
    out_root = Path(args.out_root).expanduser().resolve()

    graded = failed = skipped = 0
    for entry in manifest.runs:
        if args.only and entry.task_id != args.only:
            continue
        if args.resume and entry.status == STATUS_GRADED:
            skipped += 1
            continue
        result = grade_one(entry, repo_root, e2e_root, out_root, args.docker_image, manifest.harness, manifest.round)
        if result["status"] == STATUS_GRADED:
            graded += 1
            logger.info("[%s] 评分完成", entry.task_id)
        else:
            failed += 1
            logger.warning("[%s] 评分失败: %s", entry.task_id, result.get("note", ""))

    save_manifest(manifest, manifest_path)
    logger.info("评分完成：成功 %d，失败 %d，跳过 %d", graded, failed, skipped)


if __name__ == "__main__":
    main()
