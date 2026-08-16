from pathlib import Path

from tools.report.lib.eval_dataset.contracts import FAIL, PASS, REVIEW, Issue, exit_code, status_for_issues
from tools.report.lib.eval_dataset.security import sanitize_evidence
from tools.report.lib.eval_dataset.selectors import select_task_files


def _task(path: Path, task_id: str, category: str = "01_Productivity_Flow") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nid: {task_id}\ncategory: {category}\n---\n## Prompt\nhello\n", encoding="utf-8")


def test_selectors_default_deduplicate_and_manifest(tmp_path):
    repo = tmp_path / "repo"
    _task(repo / "tasks/01_Productivity_Flow/a.md", "task-a")
    _task(repo / "tasks/extension/01_Productivity_Flow/b.md", "task-b")
    manifest = tmp_path / "ids.txt"
    manifest.write_text("# comment\ntask-b\n", encoding="utf-8")
    result = select_task_files(repo, task_paths=["tasks/01_Productivity_Flow/a.md"] * 2, task_ids=[f"@{manifest}"])
    assert [path.name for path in result.files] == ["a.md", "b.md"]
    assert not result.issues


def test_selector_reports_ambiguous_id(tmp_path):
    repo = tmp_path / "repo"
    _task(repo / "tasks/a/a.md", "same", "a")
    _task(repo / "tasks/b/b.md", "same", "b")
    result = select_task_files(repo, task_ids=["same"])
    assert any(issue.code == "TASK_ID_AMBIGUOUS" for issue in result.issues)


def test_selectors_exclude_document_copies_by_default_and_allow_opt_in(tmp_path):
    repo = tmp_path / "repo"
    _task(repo / "tasks/01_Productivity_Flow/real.md", "real-task")
    _task(repo / "tasks/cn/01_Productivity_Flow/copy.md", "copy-task", "01_生产力工作流")

    result = select_task_files(repo)
    assert [path.name for path in result.files] == ["real.md"]

    included = select_task_files(repo, include_doc_copies=True)
    assert [path.name for path in included.files] == ["real.md", "copy.md"]

    by_id = select_task_files(repo, task_ids=["copy-task"])
    assert any(issue.code == "TASK_ID_NOT_FOUND" for issue in by_id.issues)
    by_id_included = select_task_files(repo, task_ids=["copy-task"], include_doc_copies=True)
    assert [path.name for path in by_id_included.files] == ["copy.md"]


def test_status_and_secret_safe_evidence():
    assert status_for_issues([]) == PASS
    assert status_for_issues([Issue(REVIEW, "X", "review")]) == REVIEW
    assert status_for_issues([Issue(FAIL, "X", "fail")]) == FAIL
    assert exit_code(PASS) == 0 and exit_code(REVIEW) == 0 and exit_code(FAIL) == 1 and exit_code(PASS, argument_error=True) == 2
    assert sanitize_evidence({"OPENROUTER_API_KEY": "sk-secret-value", "message": "Bearer abcdefghijk"}) == {"OPENROUTER_API_KEY": "[REDACTED]", "message": "[REDACTED]"}
    assert sanitize_evidence({"task_id": "task-common-zero"}) == {"task_id": "task-common-zero"}
