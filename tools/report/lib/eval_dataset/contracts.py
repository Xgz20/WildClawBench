"""评测集校验报告的稳定数据契约。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .security import sanitize_evidence

PASS = "PASS"
REVIEW = "REVIEW"
FAIL = "FAIL"


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    task_id: str = ""
    location: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        item = asdict(self)
        item["evidence"] = sanitize_evidence(item["evidence"])
        return item


@dataclass
class Report:
    schema_version: int
    status: str
    scope: dict[str, Any]
    summary: dict[str, Any]
    issues: list[Issue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "scope": sanitize_evidence(self.scope),
            "summary": sanitize_evidence(self.summary),
            "issues": [issue.to_dict() for issue in self.issues],
        }


def status_for_issues(issues: list[Issue]) -> str:
    if any(issue.severity == FAIL or issue.severity == "error" for issue in issues):
        return FAIL
    if any(issue.severity == REVIEW or issue.severity == "warning" for issue in issues):
        return REVIEW
    return PASS


def exit_code(status: str, *, fail_on_review: bool = False, argument_error: bool = False) -> int:
    if argument_error:
        return 2
    if status == FAIL or (fail_on_review and status == REVIEW):
        return 1
    return 0
