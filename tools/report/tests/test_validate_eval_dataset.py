from pathlib import Path
import importlib.util

from tools.report.lib.eval_dataset.task_files import parse_task_document


_SPEC = importlib.util.spec_from_file_location(
    "validate_eval_dataset_script",
    Path(__file__).resolve().parents[1] / "skills/validate-eval-dataset/scripts/validate_eval_dataset.py",
)
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
validate_document = _MODULE.validate_document
build_action_summary = _MODULE.build_action_summary


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_static_validator_reports_contract_and_resource_failures(tmp_path):
    repo = tmp_path / "repo"
    task = _write(
        repo / "tasks/01_Productivity_Flow/01_Productivity_Flow_bad.md",
        """---
id: 01_Productivity_Flow_bad
category: 99_Wrong
difficulty: L1
modality: pure-text
timeout_seconds: 30
grading_type: automated
---
## Prompt
Do it
## Workspace Path
workspace/extension/01_Productivity_Flow
## Skills
missing-skill
## Env
BAD-NAME
## Warmup
```bash
./scripts/not-there.sh
```
## Automated Checks
```python
def not_grade(): pass
```
""",
    )
    issues = validate_document(parse_task_document(task), repo)
    codes = {issue.code for issue in issues}
    assert {"CATEGORY_MISMATCH", "AUTOMATED_CHECKS_INVALID", "SKILL_NOT_FOUND", "ENV_NAME_INVALID", "WORKSPACE_NOT_FOUND"} <= codes


def test_empty_sections_are_not_treated_as_values(tmp_path):
    repo = tmp_path / "repo"
    task = _write(
        repo / "tasks/c/c.md",
        """---
id: c
category: c
difficulty: L1
modality: pure-text
timeout_seconds: 30
grading_type: llm_judge
---
## Prompt
Do it
## Workspace Path
/tmp_workspace
## Skills
```
```
## Env
```
```
## Warmup
```bash
```
## LLM Judge Rubric
### Criterion 1: quality (key: quality, weight: 1.0)
**Score 1.0**: good
""",
    )
    issues = validate_document(parse_task_document(task), repo)
    assert not any(issue.code == "SKILL_NOT_FOUND" for issue in issues)
    assert not any(issue.code == "ENV_NAME_INVALID" for issue in issues)
    assert any(issue.code == "WARMUP_EMPTY" for issue in issues)


def test_static_action_summary_groups_fix_and_review_tasks():
    from tools.report.lib.eval_dataset.contracts import Issue, FAIL, REVIEW

    summary = build_action_summary(
        ["task-fix", "task-review", "task-pass"],
        [
            Issue(FAIL, "ENV_MISSING", "missing", task_id="task-fix"),
            Issue(REVIEW, "WARMUP_DANGEROUS", "review", task_id="task-review"),
        ],
    )
    assert summary["counts"] == {"tasks_to_fix": 1, "tasks_for_review": 1, "tasks_pass": 1}
    assert summary["tasks_to_fix"][0]["task_id"] == "task-fix"
    assert summary["tasks_for_review"][0]["task_id"] == "task-review"
