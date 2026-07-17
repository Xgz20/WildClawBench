#!/usr/bin/env python3
"""对已有评测输出目录做异常回溯扫描。

用法：
    python3 eval/scan_anomalies.py output/astroncode
    python3 eval/scan_anomalies.py /data1/.../round1/xsparkx2agent/astroncode
输出 anomaly_report.json 到目标目录，并打印摘要表。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.anomalies import scan_batch


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1]).expanduser()
    if not root.is_dir():
        print(f"目录不存在: {root}")
        return 1
    report = scan_batch(root)
    out = root / "anomaly_report.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"扫描 {report['total_runs']} runs："
          f"异常 {report['anomalous_runs']}（error 级 {report['error_runs']}）")
    for rel, info in sorted(report["runs"].items()):
        flags = ",".join(i["id"] for i in info["items"])
        level = "❌" if info["has_error"] else "⚠️"
        print(f"  {level} {rel}: {flags}")
    print(f"报告已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
