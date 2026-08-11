"""阶段②：匹配桌面端轨迹，落成与 CLI 同构的结果目录。

结果目录布局与 CLI 侧一致：
    <out>/results/<harness>/<round>/<model>/<category>/<task_id>/<run_slug>/
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval_e2e.e2e_manifest import (  # noqa: E402
    STATUS_COLLECTED,
    STATUS_TRACE_MISSING,
    Manifest,
    RunEntry,
    load_manifest,
    resolve_project_dir,
    save_manifest,
)
from eval_e2e.trace_match import (  # noqa: E402
    DEFAULT_TRACE_ROOT,
    find_trace,
    parse_usage,
)

logger = logging.getLogger("e2e.collect")


def make_run_slug(entry: RunEntry, now: datetime) -> str:
    digest = hashlib.sha1(
        f"{entry.task_id}|{entry.model}|{now.isoformat()}".encode("utf-8")
    ).hexdigest()[:6]
    return f"{entry.model}_{now:%Y%m%d_%H%M}_{digest}"


def run_dir_for(out_root: Path, entry: RunEntry, run_slug: str, harness: str, round: str) -> Path:
    return (
        out_root / "results" / harness / round / entry.model
        / entry.category / entry.task_id / run_slug
    )


def snapshot_project(project_dir: Path, run_dir: Path) -> None:
    dest = run_dir / "task_output"
    if dest.exists():
        shutil.rmtree(dest)
    if project_dir.is_dir():
        shutil.copytree(project_dir, dest)
    else:
        dest.mkdir(parents=True, exist_ok=True)


def collect_one(
    entry: RunEntry,
    e2e_root: Path,
    out_root: Path,
    trace_root: Path,
    now: datetime,
    harness: str,
    round: str,
) -> dict:
    """采集单个 run。任何失败都记录状态并返回，不向上抛异常。"""
    project_dir = resolve_project_dir(entry, e2e_root)
    run_slug = make_run_slug(entry, now)
    run_dir = run_dir_for(out_root, entry, run_slug, harness, round)
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "manifest_entry.json").write_text(
        json.dumps(entry.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    trace_path, note = find_trace(
        trace_root, project_dir, entry.started_at, entry.finished_at
    )

    if trace_path is None:
        status = STATUS_TRACE_MISSING
        logger.warning("[%s] 轨迹未命中：%s", entry.task_id, note)
    else:
        status = STATUS_COLLECTED
        shutil.copyfile(trace_path, run_dir / "chat.jsonl")
        usage = parse_usage(trace_path)
        (run_dir / "usage.json").write_text(
            json.dumps(usage, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("[%s] 轨迹命中（%s）：%s", entry.task_id, note, trace_path)

    snapshot_project(project_dir, run_dir)

    payload = {
        "task_id": entry.task_id,
        "status": status,
        "note": note,
        "harness": harness,
        "model": entry.model,
        "reasoning_effort": entry.reasoning_effort,
        "trace_path": str(trace_path) if trace_path else "",
        "collected_at": now.isoformat(),
    }
    (run_dir / "execution_status.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    entry.status = status
    return {"status": status, "run_dir": str(run_dir), "note": note}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="阶段②：采集桌面端轨迹与产物，落成同构结果目录"
    )
    parser.add_argument("--manifest", required=True,
                        help="prepare 阶段产出的 manifest.json 路径")
    parser.add_argument("--e2e-root", default="",
                        help="项目目录根（默认取 manifest 内 e2e_root，相对仓库根解析）")
    parser.add_argument("--out-root", required=True, help="评测结果输出根目录")
    parser.add_argument("--trace-root", default=DEFAULT_TRACE_ROOT,
                        help=f"桌面端轨迹根目录（默认 {DEFAULT_TRACE_ROOT}）")
    parser.add_argument("--only", default="", help="仅采集指定 task_id")
    parser.add_argument("--resume", action="store_true",
                        help="跳过 status 已为 collected/graded 的用例")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_manifest(manifest_path)

    e2e_root = Path(args.e2e_root).expanduser() if args.e2e_root \
        else (REPO_ROOT / manifest.e2e_root)
    e2e_root = e2e_root.resolve()
    out_root = Path(args.out_root).expanduser().resolve()
    trace_root = Path(args.trace_root).expanduser()

    if not trace_root.is_dir():
        logger.error(
            "轨迹根目录不存在：%s（用 --trace-root 指定桌面端实际轨迹目录）",
            trace_root,
        )
        sys.exit(1)

    now = datetime.now()
    collected = missing = skipped = 0
    for entry in manifest.runs:
        if args.only and entry.task_id != args.only:
            continue
        if args.resume and entry.status in (STATUS_COLLECTED, STATUS_GRADED):
            skipped += 1
            continue
        result = collect_one(entry, e2e_root, out_root, trace_root, now, manifest.harness, manifest.round)
        if result["status"] == STATUS_COLLECTED:
            collected += 1
        else:
            missing += 1

    save_manifest(manifest, manifest_path)
    logger.info("采集完成：命中 %d，轨迹缺失 %d，跳过 %d",
                collected, missing, skipped)
    logger.info("结果根目录：%s", out_root)


if __name__ == "__main__":
    main()
