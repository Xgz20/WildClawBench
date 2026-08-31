#!/usr/bin/env python3
"""生成固定模型或固定 Harness 的逐用例跨单元比较 manifest。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from cross_eval_utils import build_manifest  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_ENTITIES = REPO_ROOT / "tools/report/data/entities.yaml"
sys.path.insert(0, str(REPO_ROOT / "tools/report/scripts"))

from report_workspace_paths import (  # noqa: E402
    build_cross_eval_comparison_id,
    resolve_cross_eval_workspace,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 WildClawBench 跨单元逐用例比较 manifest")
    parser.add_argument("--result-root", required=True, help="单个 round 结果根目录")
    parser.add_argument("--axis", required=True, choices=("model", "harness"), help="比较模型或比较 Harness")
    parser.add_argument("--fixed-model", help="Harness 对比时固定的模型 ID")
    parser.add_argument("--fixed-harness", help="模型对比时固定的 Harness ID")
    parser.add_argument("--models", nargs="+", help="模型对比的模型 ID 列表")
    parser.add_argument("--harnesses", nargs="+", help="Harness 对比的 Harness ID 列表")
    parser.add_argument("--target-model", help="模型对比的目标模型 ID，默认列表第一项")
    parser.add_argument("--target-harness", help="Harness 对比的目标 Harness ID，默认列表第一项")
    parser.add_argument("--task-id", action="append", default=[], help="只比较指定任务，可重复")
    parser.add_argument("--task-file", help="任务 ID 清单，一行一个")
    parser.add_argument("--tasks-dir", help="任务定义目录")
    parser.add_argument("--entities", default=str(DEFAULT_ENTITIES), help="实体展示名注册表")
    parser.add_argument(
        "--comparison-scope",
        choices=("same-round", "cross-round"),
        default="same-round",
        help="同 round 对比或显式跨 round 对比（默认 same-round）",
    )
    parser.add_argument("--comparison-id", help="比较工作区名称；默认按控制变量和时间生成")
    parser.add_argument("--workspace-dir", help="比较工作区完整路径；默认按比较范围自动生成")
    parser.add_argument("--reports-root", help="跨 round 报告根目录；默认由 SOURCE_MAP 推断为 <共同父目录>/reports")
    parser.add_argument("--source-map", help="跨 round 来源映射 SOURCE_MAP.tsv")
    parser.add_argument("--output", help="manifest 完整输出路径；兼容旧调用，不建议与工作区参数混用")
    args = parser.parse_args()

    if args.output and any((args.workspace_dir, args.comparison_id, args.reports_root)):
        parser.error("--output 不能与 --workspace-dir/--comparison-id/--reports-root 同时使用")

    task_ids = list(args.task_id)
    if args.task_file:
        task_ids.extend(
            line.strip()
            for line in Path(args.task_file).read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
    registry = None
    entities = Path(args.entities)
    if entities.is_file():
        import report_entities

        registry = report_entities.load_registry(entities)
    try:
        manifest = build_manifest(
            args.result_root,
            axis=args.axis,
            fixed_model=args.fixed_model,
            fixed_harness=args.fixed_harness,
            models=args.models,
            harnesses=args.harnesses,
            target_model=args.target_model,
            target_harness=args.target_harness,
            tasks_dir=args.tasks_dir,
            task_ids=task_ids,
            registry=registry,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：无法生成跨单元 manifest：{exc}", file=sys.stderr)
        return 2
    comparison_id = args.comparison_id or build_cross_eval_comparison_id(
        axis=args.axis,
        fixed_model=args.fixed_model,
        fixed_harness=args.fixed_harness,
        models=args.models,
        harnesses=args.harnesses,
        target_model=args.target_model,
        target_harness=args.target_harness,
    )
    try:
        output_override = Path(args.output).expanduser().resolve() if args.output else None
        workspace, source_map = resolve_cross_eval_workspace(
            result_root=args.result_root,
            comparison_scope=args.comparison_scope,
            comparison_id=comparison_id,
            workspace_dir=output_override.parent if output_override else args.workspace_dir,
            reports_root=args.reports_root,
            source_map=args.source_map,
        )
        output = output_override or workspace / f"cross_eval_{args.axis}_manifest.json"
    except ValueError as exc:
        parser.error(str(exc))
    manifest["comparison_scope"] = args.comparison_scope
    manifest["workspace"] = {
        "comparison_id": comparison_id,
        "source_map": str(source_map) if source_map else "",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    analysis_path = workspace / f"cross_eval_{args.axis}_analysis.json"
    quality_path = workspace / f"cross_eval_{args.axis}_analysis.quality.json"
    report_path = workspace / f"cross_eval_{args.axis}_report.md"
    print(json.dumps({
        "status": "PASS" if not manifest["issues"] else "REVIEW",
        "axis": manifest["axis"],
        "target_unit": manifest["target_unit"],
        "unit_count": len(manifest["units"]),
        "task_count": manifest["scope"]["task_count"],
        "output": str(output),
        "workspace": str(workspace),
    }, ensure_ascii=False))
    print(f"WORKSPACE_DIR={workspace}")
    print(f"MANIFEST_PATH={output}")
    print(f"ANALYSIS_PATH={analysis_path}")
    print(f"QUALITY_PATH={quality_path}")
    print(f"REPORT_PATH={report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
