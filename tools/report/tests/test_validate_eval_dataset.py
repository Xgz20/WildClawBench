from __future__ import annotations

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


def _website_task(
    repo: Path,
    *,
    prompt: str | None = None,
    rubric: str | None = None,
    workspace: str = "workspace/extension/07_Website_Generation/task_012_sample_site",
) -> Path:
    prompt = prompt or (
        "Create the site with package.json, then run npm install and npm run build. "
        "It must support npm run start -- --host 127.0.0.1 --port 4173."
    )
    rubric = rubric or """### Criterion 1: Runtime (key: runtime_key, primary: content_structure, secondary: basic_content, weight: 0.5)
Score 1.0: pass
Score 0.0: fail

### Criterion 2: Visual (key: visual_key, primary: visual_layout, secondary: page_layout, weight: 0.5)
Score 1.0: pass
Score 0.0: fail"""
    return _write(
        repo / "tasks/extension/07_Website_Generation/07_Website_Generation_task_012_sample_site.md",
        f"""---
id: 07_Website_Generation_task_012_sample_site
category: 07_Website_Generation
difficulty: L1
modality: pure-text
timeout_seconds: 900
grading_type: llm_judge
tags:
  - custom
  - web-site-gen
---
## Prompt
{prompt}
## Workspace Path
{workspace}
## Skills
## Env
## Warmup
## LLM Judge Rubric
{rubric}
""",
    )


def _website_checker(repo: Path, source: str | None = None) -> Path:
    source = source or """RUNTIME_KEYS = [\"runtime_key\"]
VISUAL_KEYS = [\"visual_key\"]

async def run(page, screenshot_dir):
    return {}

async def capture_visual(page, screenshot_dir):
    return []
"""
    return _write(
        repo / "eval/checks/website/tasks/task_012_sample_site.py",
        source,
    )


def _website_workspace(repo: Path, *, eval_asset: bool = False) -> Path:
    workspace = repo / "workspace/extension/07_Website_Generation/task_012_sample_site"
    (workspace / "exec").mkdir(parents=True, exist_ok=True)
    if eval_asset:
        _write(workspace / "eval/fixture.txt", "fixture")
    return workspace


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
    assert not any(issue.code == "WARMUP_EMPTY" for issue in issues)
    assert not any(issue.code == "SECTION_MISSING" and "Warmup" in issue.message for issue in issues)


def test_missing_warmup_section_is_a_format_failure(tmp_path):
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
## Env
## LLM Judge Rubric
### Criterion 1: quality (key: quality, weight: 1.0)
**Score 1.0**: good
""",
    )
    issues = validate_document(parse_task_document(task), repo)
    assert any(issue.code == "SECTION_MISSING" and "Warmup" in issue.message for issue in issues)


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


def test_valid_website_contract_passes_static_profile(tmp_path):
    repo = tmp_path / "repo"
    task = _website_task(repo)
    _website_checker(repo)
    _website_workspace(repo)

    issues = validate_document(parse_task_document(task), repo)

    assert not any(issue.code.startswith("WEBSITE_") for issue in issues)


def test_website_contract_requires_checker_module(tmp_path):
    repo = tmp_path / "repo"
    task = _website_task(repo)
    _website_workspace(repo)

    issues = validate_document(parse_task_document(task), repo)

    assert "WEBSITE_CHECKER_MISSING" in {issue.code for issue in issues}


def test_website_contract_checks_checker_ast_entrypoints_and_keys(tmp_path):
    repo = tmp_path / "repo"
    task = _website_task(repo)
    _website_workspace(repo)
    _website_checker(
        repo,
        """RUNTIME_KEYS = [\"wrong_runtime\"]
VISUAL_KEYS = []

def run(page, screenshot_dir):
    return {}
""",
    )

    issues = validate_document(parse_task_document(task), repo)
    codes = {issue.code for issue in issues}

    assert {
        "WEBSITE_CHECKER_ENTRYPOINT_MISSING",
        "WEBSITE_RUNTIME_KEYS_MISMATCH",
        "WEBSITE_VISUAL_KEYS_MISMATCH",
    } <= codes


def test_website_contract_rejects_checker_syntax_error(tmp_path):
    repo = tmp_path / "repo"
    task = _website_task(repo)
    _website_workspace(repo)
    _website_checker(repo, "RUNTIME_KEYS = [")

    issues = validate_document(parse_task_document(task), repo)

    assert "WEBSITE_CHECKER_SYNTAX_INVALID" in {issue.code for issue in issues}


def test_website_contract_checks_rubric_startup_and_workspace_layout(tmp_path):
    repo = tmp_path / "repo"
    task = _website_task(
        repo,
        prompt="Create a website.",
        workspace="workspace/extension/07_Website_Generation/wrong_workspace",
        rubric="""### Criterion 2: Invalid (key: Bad-Key, primary: unsupported, secondary: , weight: 0)
Score 1.0: pass""",
    )
    _website_checker(repo)
    (repo / "workspace/extension/07_Website_Generation/wrong_workspace").mkdir(parents=True)

    issues = validate_document(parse_task_document(task), repo)
    codes = {issue.code for issue in issues}

    assert {
        "WEBSITE_RUBRIC_DIMENSION_INVALID",
        "WEBSITE_RUBRIC_FORMAT_INVALID",
        "WEBSITE_RUBRIC_WEIGHT_INVALID",
        "WEBSITE_STARTUP_CONTRACT_MISSING",
        "WEBSITE_WORKSPACE_LAYOUT_INVALID",
    } <= codes


def test_website_contract_requires_declared_eval_fixtures(tmp_path):
    repo = tmp_path / "repo"
    task = _website_task(repo)
    _website_workspace(repo)
    _website_checker(
        repo,
        """RUNTIME_KEYS = [\"runtime_key\"]
VISUAL_KEYS = [\"visual_key\"]
EVAL = \"/tmp_workspace_eval\"

async def run(page, screenshot_dir):
    return {\"fixture\": EVAL}

async def capture_visual(page, screenshot_dir):
    return []
""",
    )

    issues = validate_document(parse_task_document(task), repo)

    assert "WEBSITE_EVAL_FIXTURE_MISSING" in {issue.code for issue in issues}
