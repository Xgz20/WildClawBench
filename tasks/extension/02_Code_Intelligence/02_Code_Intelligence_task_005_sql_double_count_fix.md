---
id: 02_Code_Intelligence_task_005_sql_double_count_fix
name: Fix child-table double counting
category: 02_Code_Intelligence
timeout_seconds: 600
modality: pure-text
attachment_size_limit_mb: 5
difficulty: L2
grading_type: automated
grading_weights:
  automated: 1.0
  llm_judge: 0.0
tags:
  - custom
---

# Fix child-table double counting

## Prompt

The property report in `/tmp_workspace/project/report.sql` over-counts both leases and visits because two child tables are joined before aggregation. Fix the query so it returns one row per property, preserves properties with zero activity, and reports the real count of each child table. Legitimate duplicate child rows still count separately, so `COUNT(DISTINCT ...)` is not an acceptable shortcut.

Do not change `schema.sql`, `fixtures.sql`, or the tests. Run:

```bash
cd /tmp_workspace/project
python3 -m unittest -v
```

Then run the corrected report against the supplied fixture and write `/tmp_workspace/results/report.csv` with the query’s four columns in query order. Only modify `report.sql`, do not use the network, and do not create other result files.

## Expected Behavior

The query should aggregate each one-to-many child table before joining it to `properties`, retain all properties through left joins, convert missing child counts to zero, and return rows ordered by `property_id`. The supplied result CSV must contain the exact query header and fixture rows. Schema, fixture, tests, and project scope must remain unchanged.

## Grading Criteria

- [ ] `per_property_counts_correct`: each property has the true lease and visit count
- [ ] `zero_activity_preserved`: properties with no rows in one or both child tables remain present with zero counts
- [ ] `legitimate_duplicates_preserved`: distinct child records with equal business values are all counted
- [ ] `query_shape_order_correct`: columns, one-row-per-property shape, ordering, and query restrictions are correct
- [ ] `public_regression_passed`: supplied SQLite regression test passes unchanged
- [ ] `scope_result_delivery`: protected inputs, source scope, and exact result CSV are preserved

## Automated Checks

```python
def grade(**kwargs) -> dict:
    import csv
    import hashlib
    import json
    from pathlib import Path
    import re
    import subprocess
    import sys

    keys = [
        "per_property_counts_correct",
        "zero_activity_preserved",
        "legitimate_duplicates_preserved",
        "query_shape_order_correct",
        "public_regression_passed",
        "scope_result_delivery",
        "overall_score",
    ]
    scores = {key: 0.0 for key in keys}
    root = Path(kwargs.get("workspace_path") or "/tmp_workspace")
    project = root / "project"
    query_path = project / "report.sql"

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
        query_text = query_path.read_text(encoding="utf-8") if regular(query_path) else ""
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError):
        return scores
    if not query_text:
        return scores

    driver = r'''
import json, pathlib, sqlite3, sys
project = pathlib.Path(sys.argv[1])
query = (project / "report.sql").read_text(encoding="utf-8")

def execute(schema, fixtures):
    connection = sqlite3.connect(":memory:")
    connection.executescript(schema)
    connection.executescript(fixtures)
    allowed = {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        getattr(sqlite3, "SQLITE_RECURSIVE", -1),
    }
    connection.set_authorizer(lambda action, a, b, c, d: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
    cursor = connection.execute(query)
    header = [item[0] for item in cursor.description]
    rows = [list(row) for row in cursor.fetchall()]
    connection.close()
    return header, rows

result = {}
try:
    public_header, public_rows = execute(
        (project / "schema.sql").read_text(encoding="utf-8"),
        (project / "fixtures.sql").read_text(encoding="utf-8"),
    )
    result["public_header"] = public_header
    result["public_rows"] = public_rows
except Exception as exc:
    result["public_error"] = type(exc).__name__

hidden_schema = """
CREATE TABLE properties(property_id INTEGER PRIMARY KEY, property_name TEXT NOT NULL);
CREATE TABLE leases(lease_id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL, tenant_name TEXT NOT NULL);
CREATE TABLE visits(visit_id INTEGER PRIMARY KEY, property_id INTEGER NOT NULL, visited_at TEXT NOT NULL);
"""
hidden_fixtures = """
INSERT INTO properties VALUES (10, 'Zero Place'), (11, 'Duplicate Values'), (12, 'Lease Only');
INSERT INTO leases VALUES (1, 11, 'Same'), (2, 11, 'Same'), (3, 12, 'Solo');
INSERT INTO visits VALUES (1, 11, '2026-01-01T00:00:00Z'), (2, 11, '2026-01-01T00:00:00Z');
"""
try:
    hidden_header, hidden_rows = execute(hidden_schema, hidden_fixtures)
    result["hidden_header"] = hidden_header
    result["hidden_rows"] = hidden_rows
except Exception as exc:
    result["hidden_error"] = type(exc).__name__
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
        checked = json.loads(marker) if completed.returncode == 0 else {}
    except (OSError, subprocess.SubprocessError, StopIteration, json.JSONDecodeError):
        checked = {}

    wanted_public = [
        [1, "Harbor House", 2, 3],
        [2, "Maple Court", 1, 0],
        [3, "Pine Studios", 0, 1],
        [4, "Riverside Empty", 0, 0],
    ]
    wanted_hidden = [
        [10, "Zero Place", 0, 0],
        [11, "Duplicate Values", 2, 2],
        [12, "Lease Only", 1, 0],
    ]
    public_rows = checked.get("public_rows")
    hidden_rows = checked.get("hidden_rows")
    scores["per_property_counts_correct"] = sum(
        [public_rows == wanted_public, hidden_rows == wanted_hidden]
    ) / 2.0
    scores["zero_activity_preserved"] = sum(
        [
            isinstance(public_rows, list) and [4, "Riverside Empty", 0, 0] in public_rows,
            isinstance(hidden_rows, list) and [10, "Zero Place", 0, 0] in hidden_rows,
            isinstance(hidden_rows, list) and [12, "Lease Only", 1, 0] in hidden_rows,
        ]
    ) / 3.0
    scores["legitimate_duplicates_preserved"] = float(
        isinstance(hidden_rows, list) and [11, "Duplicate Values", 2, 2] in hidden_rows
    )
    expected_header = expected["csv_header"]
    shape_flags = [
        checked.get("public_header") == expected_header,
        checked.get("hidden_header") == expected_header,
        isinstance(public_rows, list)
        and [row[0] for row in public_rows] == sorted(row[0] for row in public_rows),
        isinstance(public_rows, list)
        and len({row[0] for row in public_rows}) == len(public_rows),
        re.search(r"count\s*\(\s*distinct\b", query_text, re.IGNORECASE) is None,
    ]
    scores["query_shape_order_correct"] = sum(shape_flags) / len(shape_flags)

    try:
        public = subprocess.run(
            [sys.executable, "-m", "unittest", "-v"],
            cwd=project,
            text=True,
            capture_output=True,
            timeout=15,
        )
        scores["public_regression_passed"] = float(public.returncode == 0)
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        project_files = sorted(
            path.relative_to(project).as_posix()
            for path in project.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        )
        result_path = root / "results" / "report.csv"
        with result_path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            delivered = list(reader)
        result_files = sorted(
            path.name for path in (root / "results").iterdir() if path.is_file() or path.is_symlink()
        )
        delivery_flags = [
            protected_ok,
            project_files == sorted(expected["allowed_project_files"]),
            regular(query_path),
            regular(result_path),
            result_files == ["report.csv"],
            delivered == [expected_header] + expected["public_rows"],
        ]
        scores["scope_result_delivery"] = sum(delivery_flags) / len(delivery_flags)
    except (OSError, UnicodeError, csv.Error):
        pass
    scores["overall_score"] = round(
        0.25 * scores["per_property_counts_correct"]
        + 0.15 * scores["zero_activity_preserved"]
        + 0.20 * scores["legitimate_duplicates_preserved"]
        + 0.20 * scores["query_shape_order_correct"]
        + 0.10 * scores["public_regression_passed"]
        + 0.10 * scores["scope_result_delivery"],
        6,
    )
    return {key: round(value, 6) for key, value in scores.items()}
```

## LLM Judge Rubric

This task uses automated grading only.

## Workspace Path

```
workspace/extension/02_Code_Intelligence/task_005_sql_double_count_fix
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

- SQLite is provided by the Python standard library; no database server is required.
- `report.csv` is the only requested result artifact.
