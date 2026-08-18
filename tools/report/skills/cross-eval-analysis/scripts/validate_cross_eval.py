#!/usr/bin/env python3
"""校验跨单元分析 Workflow 输出。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from cross_eval_utils import validate_analysis  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="校验跨单元分析 JSON")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--output", help="质量报告输出 JSON")
    parser.add_argument("--fail-on-review", action="store_true")
    args = parser.parse_args()

    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        analysis = json.loads(Path(args.analysis).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"错误：无法读取 JSON：{exc}", file=sys.stderr)
        return 2
    quality = validate_analysis(manifest, analysis)
    output = Path(args.output).expanduser().resolve() if args.output else Path(args.analysis).with_suffix(".quality.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(quality, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "status": quality["status"],
        "issues": len(quality["issues"]),
        "output": str(output),
    }, ensure_ascii=False))
    if quality["status"] == "FAIL" or (args.fail_on_review and quality["status"] == "REVIEW"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
