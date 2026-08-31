#!/usr/bin/env python3
"""渲染已校验的跨单元结构化分析 Markdown。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from cross_eval_utils import render_markdown, validate_analysis  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="渲染跨单元逐用例分析 Markdown")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--output", help="Markdown 输出；默认与 analysis 同目录并命名为 cross_eval_<axis>_report.md")
    args = parser.parse_args()
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"错误：无法读取 JSON：{exc}", file=sys.stderr)
        return 2
    quality = validate_analysis(manifest, analysis)
    if quality["status"] == "FAIL":
        print(f"错误：分析质量校验失败，共 {len(quality['issues'])} 个问题", file=sys.stderr)
        return 1
    if args.output:
        output = Path(args.output).expanduser().resolve()
    else:
        analysis_path = Path(args.analysis).expanduser().resolve()
        name = analysis_path.name
        output_name = (
            name[:-len("_analysis.json")] + "_report.md"
            if name.endswith("_analysis.json") else analysis_path.stem + "_report.md"
        )
        output = analysis_path.with_name(output_name)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_markdown(manifest, analysis), encoding="utf-8")
    print(f"Markdown 已生成：{output}")
    if quality["status"] == "REVIEW":
        print("提示：分析质量为 REVIEW，请在发布前人工复核。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
