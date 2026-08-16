"""评测集校验与质量审计共享库。"""

from .contracts import FAIL, PASS, REVIEW, Issue, Report, exit_code, status_for_issues


def select_task_files(*args, **kwargs):
    """延迟加载 YAML 依赖，便于只使用报告契约/安全模块。"""
    from .selectors import select_task_files as _select_task_files

    return _select_task_files(*args, **kwargs)


def __getattr__(name):
    if name == "SelectionResult":
        from .selectors import SelectionResult

        return SelectionResult
    raise AttributeError(name)

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
