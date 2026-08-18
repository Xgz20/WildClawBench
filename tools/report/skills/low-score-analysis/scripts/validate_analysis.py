#!/usr/bin/env python3
"""校验低分分析 JSON，并允许只完成 manifest 子集的增量分析。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from analysis_quality import load_analysis, load_manifest, validate_analysis  # noqa: E402


def _default_manifest(analysis_path: Path) -> Path | None:
    name = analysis_path.name
    if not name.startswith("analysis_") or not name.endswith(".json"):
        return None
    stem = name[len("analysis_"):-len(".json")]
    return analysis_path.with_name(f"_failed_tasks_{stem}.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 WildClawBench 低分分析 JSON")
    parser.add_argument("--analysis", required=True, help="analysis JSON 路径")
    parser.add_argument("--manifest", help="对应的 _failed_tasks manifest；默认按文件名推断")
    parser.add_argument("--output", help="质量报告 JSON 输出路径")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="要求 analysis 覆盖 manifest 全部任务；默认允许 partial",
    )
    parser.add_argument(
        "--fail-on",
        choices=("error", "review", "never"),
        default="error",
        help="何种质量状态返回非零退出码；默认仅 FAIL 非零",
    )
    args = parser.parse_args()

    analysis_path = Path(args.analysis).expanduser().resolve()
    manifest_path = (
        Path(args.manifest).expanduser().resolve()
        if args.manifest else _default_manifest(analysis_path)
    )
    try:
        analysis = load_analysis(analysis_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"错误：无法读取 analysis：{exc}", file=sys.stderr)
        return 1

    expected: dict[str, dict] = {}
    source_records: list[dict] | None = None
    if manifest_path and manifest_path.is_file():
        try:
            source_records = load_manifest(manifest_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"错误：无法读取 manifest：{exc}", file=sys.stderr)
            return 1
        expected = {str(item.get("task_id")): item for item in source_records if item.get("task_id")}
    else:
        manifest_path = None

    report = validate_analysis(
        analysis,
        expected=expected,
        allow_partial=not args.require_complete,
        source_records=source_records,
    )
    report.update({
        "analysis_path": str(analysis_path),
        "manifest_path": str(manifest_path) if manifest_path else "",
        "allow_partial": not args.require_complete,
    })
    output = Path(args.output).expanduser().resolve() if args.output else analysis_path.with_suffix(".quality.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "status": report["status"],
        "coverage": report["coverage"],
        "source_snapshot": report["source_snapshot"],
        "issues": len(report["issues"]),
        "quality_path": str(output),
    }, ensure_ascii=False))
    if args.fail_on == "never":
        return 0
    if report["status"] == "FAIL":
        return 1
    if args.fail_on == "review" and report["status"] == "REVIEW":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
