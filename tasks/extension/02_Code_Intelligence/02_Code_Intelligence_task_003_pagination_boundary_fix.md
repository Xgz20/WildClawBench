---
id: 02_Code_Intelligence_task_003_pagination_boundary_fix
name: Fix the exact-multiple pagination boundary
category: 02_Code_Intelligence
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L1
grading_type: automated
grading_weights:
  automated: 1.0
  llm_judge: 0.0
tags:
  - custom
---

# Fix the exact-multiple pagination boundary

## Prompt

The search page still shows “Next” on the last full page when the result count is an exact multiple of `per_page`, which sends users to an empty page. Fix `/tmp_workspace/project/pagination.py` without adding a separate `COUNT(*)` query or changing the public return shape.

The fetch callback supports keyword arguments `limit` and `offset`. Use one-row look-ahead, return at most `per_page` records, and keep empty, partial, and out-of-range pages working. Only modify `/tmp_workspace/project/pagination.py`, run the existing tests, and do not use the network or create result files.

Run the tests with:

```bash
cd /tmp_workspace/project
python3 -m unittest -v
```

## Expected Behavior

The implementation should request `per_page + 1` rows once at the correct offset, trim the returned records to `per_page`, and set `has_next` only when the look-ahead row exists. It should preserve the one-based page validation, callable interface, return keys, public tests, and source-file scope.

## Grading Criteria

- [ ] `exact_multiple_boundary`: exact-multiple last pages do not advertise an empty next page
- [ ] `partial_empty_boundaries`: partial, empty, and out-of-range pages return the correct bounded result
- [ ] `lookahead_and_trim_correct`: the callback receives the correct look-ahead limit and offset, and extra rows are trimmed
- [ ] `query_budget_respected`: each request uses one fetch call and no separate count operation
- [ ] `public_tests_passed`: the supplied unit tests pass unchanged
- [ ] `file_scope_api_preserved`: only the allowed source changes and the public function shape is retained

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import hashlib
    import inspect
    import json
    from pathlib import Path
    import subprocess
    import sys

    keys = [
        "exact_multiple_boundary",
        "partial_empty_boundaries",
        "lookahead_and_trim_correct",
        "query_budget_respected",
        "public_tests_passed",
        "file_scope_api_preserved",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    project = root / "project"
    source = project / "pagination.py"

    def regular(path):
        try:
            return path.is_file() and not path.is_symlink() and not path.parent.is_symlink()
        except OSError:
            return False

    try:
        expected = json.loads((root / "gt" / "expected.json").read_text(encoding="utf-8"))
        protected_ok = all(
            regular(root / relative)
            and hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest
            for relative, digest in expected["protected_file_sha256"].items()
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores
    if not regular(source):
        return scores

    driver = r'''
import importlib.util, inspect, json, pathlib, sys
project = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("candidate_pagination", project / "pagination.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class Fetch:
    def __init__(self, rows):
        self.rows = list(rows)
        self.calls = []
    def __call__(self, *, limit, offset):
        self.calls.append([limit, offset])
        return self.rows[offset:offset + limit]

result = {}
fetch = Fetch(range(1, 5))
value = module.paginate(fetch, 2, 2)
result["exact"] = value == {"items": [3, 4], "has_next": False}
result["exact_calls"] = fetch.calls == [[3, 2]]

fetch = Fetch(range(1, 6))
partial = module.paginate(fetch, 3, 2)
result["partial"] = partial == {"items": [5], "has_next": False}
result["partial_calls"] = fetch.calls == [[3, 4]]

fetch = Fetch([])
empty = module.paginate(fetch, 4, 3)
result["empty"] = empty == {"items": [], "has_next": False}
result["empty_calls"] = fetch.calls == [[4, 9]]

fetch = Fetch(range(10))
first = module.paginate(fetch, 1, 3)
result["lookahead"] = first == {"items": [0, 1, 2], "has_next": True}
result["lookahead_calls"] = fetch.calls == [[4, 0]]
try:
    module.paginate(Fetch([]), 0, 2)
except ValueError:
    result["validation"] = True
else:
    result["validation"] = False
result["signature"] = list(inspect.signature(module.paginate).parameters) == ["fetch", "page", "per_page"]
print("__RESULT__" + json.dumps(result, sort_keys=True))
'''
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", driver, str(project)],
            text=True,
            capture_output=True,
            timeout=10,
        )
        marker = next(
            line[len("__RESULT__") :]
            for line in reversed(completed.stdout.splitlines())
            if line.startswith("__RESULT__")
        )
        hidden = json.loads(marker) if completed.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, StopIteration, json.JSONDecodeError):
        hidden = {}

    scores["exact_multiple_boundary"] = float(
        bool(hidden.get("exact") and hidden.get("exact_calls"))
    )
    scores["partial_empty_boundaries"] = sum(
        bool(hidden.get(name)) for name in ("partial", "empty", "validation")
    ) / 3.0
    scores["lookahead_and_trim_correct"] = sum(
        bool(hidden.get(name))
        for name in ("lookahead", "lookahead_calls", "partial_calls")
    ) / 3.0
    scores["query_budget_respected"] = sum(
        bool(hidden.get(name))
        for name in ("exact_calls", "partial_calls", "empty_calls", "lookahead_calls")
    ) / 4.0

    try:
        public = subprocess.run(
            [sys.executable, "-m", "unittest", "-v"],
            cwd=project,
            text=True,
            capture_output=True,
            timeout=15,
        )
        scores["public_tests_passed"] = float(public.returncode == 0)
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        files = sorted(
            path.relative_to(project).as_posix()
            for path in project.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
        source_text = source.read_text(encoding="utf-8")
        scope_flags = [
            protected_ok,
            files == sorted(expected["allowed_project_files"]),
            bool(hidden.get("signature")),
            "count(" not in source_text.lower(),
        ]
        scores["file_scope_api_preserved"] = sum(scope_flags) / len(scope_flags)
    except (OSError, UnicodeError):
        pass
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

This task uses automated grading only.

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_003_pagination_boundary_fix
```

## Skills

```
```

## Env

```
```

## Warmup

```bash
```

## Additional Notes

- The project is self-contained and uses only the Python standard library.
- No result artifact is requested; the source modification is the delivery.
