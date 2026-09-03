"""确定性报告路径与 JSON/Markdown 渲染。"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .contracts import Report
from .security import sanitize_evidence


def scope_hash(scope: dict[str, Any], rule_version: str = "1") -> str:
    payload = json.dumps({"scope": scope, "rules": rule_version}, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def default_output_dir(repo_root: Path, kind: str) -> Path:
    return Path(repo_root).resolve() / "report-workspace" / "eval-dataset" / kind


def _markdown(report: Report) -> str:
    lines = [f"# Eval Dataset {report.status}", "", f"- Schema: `{report.schema_version}`", f"- Scope: `{json.dumps(sanitize_evidence(report.scope), ensure_ascii=False, sort_keys=True)}`", "", "## Summary", ""]
    if report.summary:
        verbose_keys = {"action_summary", "common_zero_candidates", "model_comparison", "harness_comparison", "difficulty", "stability", "task_scores"}
        for key, value in report.summary.items():
            if key in verbose_keys:
                continue
            lines.append(f"- {key}: {json.dumps(sanitize_evidence(value), ensure_ascii=False)}")
    action_summary = report.summary.get("action_summary") if isinstance(report.summary, dict) else None
    if isinstance(action_summary, dict):
        lines.extend(["", "## 结论摘要", ""])
        if action_summary.get("decision"):
            lines.append(f"**处理建议：** {sanitize_evidence(action_summary['decision'])}")
            lines.append("")
        counts = action_summary.get("counts", {})
        if counts:
            lines.append("| 类别 | 数量 |")
            lines.append("|---|---:|")
            if "results_to_rerun" in action_summary or "framework_issues" in action_summary:
                count_rows = (
                    ("results_to_rerun", "需要重跑/补齐的结果"),
                    ("framework_issues", "需要修复的框架或审计输入"),
                    ("tasks_to_fix", "需要修改的评测用例"),
                    ("tasks_for_review", "需要人工审核的评测用例"),
                    ("tasks_pass", "未发现问题的评测用例"),
                )
            else:
                # 兼容 validate-eval-dataset 等仍使用三类处置的报告。
                count_rows = (
                    ("tasks_to_fix", "需要修改"),
                    ("tasks_for_review", "需要人工审核"),
                    ("tasks_pass", "未发现问题"),
                )
            for key, label in count_rows:
                lines.append(f"| {label} | {counts.get(key, 0)} |")

        if "results_to_rerun" in action_summary:
            items = action_summary.get("results_to_rerun") or []
            lines.extend(["", "### 需要重跑或补齐的结果", ""])
            if not items:
                lines.append("- 无")
            else:
                lines.append("| 用例 | Unit | 问题 | 建议 |")
                lines.append("|---|---|---|---|")
                for item in items:
                    task_id = sanitize_evidence(item.get("task_id", ""))
                    unit = sanitize_evidence(item.get("unit", ""))
                    reason = item.get("issue_codes") or []
                    recommendation = item.get("recommendations") or ""
                    if isinstance(reason, list):
                        reason = "、".join(str(value) for value in reason)
                    if isinstance(recommendation, list):
                        recommendation = "；".join(str(value) for value in recommendation)
                    lines.append(
                        f"| `{task_id}` | `{unit}` | {sanitize_evidence(reason)} | "
                        f"{sanitize_evidence(recommendation)} |"
                    )

        if "framework_issues" in action_summary:
            items = action_summary.get("framework_issues") or []
            lines.extend(["", "### 需要修复的框架或审计输入", ""])
            if not items:
                lines.append("- 无")
            else:
                lines.append("| 问题 | 级别 | 位置 | 建议 |")
                lines.append("|---|---|---|---|")
                for item in items:
                    code = sanitize_evidence(item.get("issue_code", ""))
                    severity = sanitize_evidence(item.get("severity", ""))
                    location = sanitize_evidence(item.get("location", ""))
                    recommendation = sanitize_evidence(
                        item.get("recommendation") or item.get("message", "")
                    )
                    lines.append(
                        f"| `{code}` | {severity} | `{location}` | {recommendation} |"
                    )

        for key, heading, columns in (
            ("tasks_to_fix", "需要修改的评测用例", ("task_id", "issue_codes", "recommendations")),
            ("tasks_for_review", "需要人工审核的评测用例", ("task_id", "reasons", "recommendation")),
        ):
            items = action_summary.get(key) or []
            lines.extend(["", f"### {heading}", ""])
            if not items:
                lines.append("- 无")
                continue
            lines.append("| 用例 | 问题/原因 | 建议 |")
            lines.append("|---|---|---|")
            for item in items:
                task_id = sanitize_evidence(item.get("task_id", ""))
                reason = item.get("issue_codes") or item.get("reasons") or []
                recommendation = item.get("recommendations") or item.get("recommendation") or ""
                if isinstance(reason, list):
                    reason = "、".join(str(value) for value in reason)
                if isinstance(recommendation, list):
                    recommendation = "；".join(str(value) for value in recommendation)
                lines.append(f"| `{task_id}` | {sanitize_evidence(reason)} | {sanitize_evidence(recommendation)} |")
        if action_summary.get("global_actions"):
            lines.extend(["", "### 全局问题", ""])
            lines.extend(f"- {sanitize_evidence(item)}" for item in action_summary["global_actions"])

    model_comparison = report.summary.get("model_comparison") if isinstance(report.summary, dict) else None
    if isinstance(model_comparison, dict):
        lines.extend(["", "## 模型区分度", ""])
        lines.append("| 模型 A | 模型 B | 共同任务数 | 平均分差 | 平均绝对分差 | 可区分比例 |")
        lines.append("|---|---|---:|---:|---:|---:|")
        for item in model_comparison.get("pairwise", []):
            lines.append(f"| `{item.get('left', '')}` | `{item.get('right', '')}` | {item.get('common_tasks', 0)} | {item.get('mean_gap', 0):.4f} | {item.get('mean_abs_gap', 0):.4f} | {item.get('separable_rate', 0):.1%} |")
        if not model_comparison.get("pairwise"):
            lines.append("- 无共同模型任务可比较。")

    harness_comparison = report.summary.get("harness_comparison") if isinstance(report.summary, dict) else None
    if isinstance(harness_comparison, dict):
        lines.extend(["", "## Harness 敏感性", ""])
        harnesses = harness_comparison.get("harnesses", [])
        lines.append(f"- Harness 数量：{len(harnesses)}（{', '.join(f'`{item}`' for item in harnesses)}）")
        if len(harnesses) < 2:
            lines.append("- 当前无法评估 Harness 敏感性：至少需要两个 Harness 的控制变量结果。")
        else:
            lines.append(f"- 可比较 Harness 对数：{len(harness_comparison.get('pairwise', []))}")

    difficulty = report.summary.get("difficulty") if isinstance(report.summary, dict) else None
    if isinstance(difficulty, dict):
        lines.extend(["", "## 难度与梯度", ""])
        lines.append(f"- 已统计任务数：{len(difficulty.get('tasks', {}))}")
        lines.append(f"- 难度倒挂对数：{len(difficulty.get('inversions', []))}")

    candidates = report.summary.get("common_zero_candidates") if isinstance(report.summary, dict) else None
    if isinstance(candidates, list):
        lines.extend(["", "## 多模型共同低分候选", ""])
        if not candidates:
            lines.append("- 当前没有满足共同低分候选阈值的任务。")
        else:
            lines.append("| 用例 | model@harness 数 | 轨迹假设 | 轨迹信号 |")
            lines.append("|---|---:|---|---|")
            for item in candidates:
                signals = item.get("trace_signal_counts", {})
                signal_text = ", ".join(f"{key}={value}" for key, value in signals.items() if value)
                lines.append(f"| `{sanitize_evidence(item.get('task_id', ''))}` | {item.get('unit_count', 0)} | {sanitize_evidence(item.get('hypothesis', ''))} | `{sanitize_evidence(signal_text)}` |")

    lines.extend(["", "## Issues", ""])
    if not report.issues:
        lines.append("- None")
    else:
        for issue in report.issues:
            task = f" [{issue.task_id}]" if issue.task_id else ""
            location = f" ({issue.location})" if issue.location else ""
            lines.append(f"- **{issue.severity}** `{issue.code}`{task}{location}: {sanitize_evidence(issue.message)}")
            if issue.evidence:
                lines.append(f"  - evidence: `{json.dumps(sanitize_evidence(issue.evidence), ensure_ascii=False, sort_keys=True)}`")
    return "\n".join(lines) + "\n"


def write_report(report: Report, *, repo_root: Path, kind: str, output_dir: str | Path | None = None, run_scope: dict[str, Any] | None = None) -> Path:
    base = Path(output_dir).expanduser().resolve() if output_dir else default_output_dir(repo_root, kind)
    scope = run_scope or report.scope
    target = base / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{scope_hash(scope)}"
    target.mkdir(parents=True, exist_ok=True)
    (target / "report.json").write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target / "report.md").write_text(_markdown(report), encoding="utf-8")
    return target
