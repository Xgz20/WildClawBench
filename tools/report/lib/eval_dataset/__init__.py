"""评测集校验与质量审计共享库。"""

from .contracts import FAIL, PASS, REVIEW, Issue, Report, exit_code, status_for_issues
from .selectors import SelectionResult, select_task_files

SCHEMA_VERSION = 1

__all__ = [
    "FAIL",
    "PASS",
    "REVIEW",
    "Issue",
    "Report",
    "SelectionResult",
    "SCHEMA_VERSION",
    "exit_code",
    "select_task_files",
    "status_for_issues",
]
