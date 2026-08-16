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
        lines.extend(f"- {key}: {json.dumps(sanitize_evidence(value), ensure_ascii=False)}" for key, value in report.summary.items())
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
