"""Independent state-vector tests; the candidate never supplies expected states."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same(value, expected):
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(same(value[key], item) for key, item in expected.items())
    if isinstance(expected, list):
        return len(value) == len(expected) and all(same(left, right) for left, right in zip(value, expected))
    return value == expected


ENV = {"PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"}


def invoke(directory, scenario):
    # Every scenario starts from an independent DB, including external readers.
    database = directory / "scratch.sqlite"
    for path in directory.glob("scratch.sqlite*"):
        path.unlink()
    completed = subprocess.run([sys.executable, "-I", "-B", str(directory / "driver.py")],
        input=json.dumps(scenario, ensure_ascii=False).encode(), cwd=directory, capture_output=True, timeout=5, env=ENV)
    if completed.returncode or len(completed.stdout) > 1024 * 1024:
        return None
    try:
        actual = json.loads(completed.stdout)
    except (UnicodeError, ValueError):
        return None
    if not isinstance(actual, dict) or not database.is_file() or database.is_symlink():
        return None
    # Inspect the persisted DB in the trusted scoring process. A candidate's
    # Python module cannot hide forbidden DDL by spoofing its own PRAGMA probe.
    conn = None
    try:
        conn = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
        tables = ("people", "rooms", "bookings")
        actual["schema"] = {table: [[row[1], row[2], row[3], row[5]] for row in conn.execute(f"PRAGMA table_info({table})")] for table in tables}
        actual["foreign_keys"] = {table: conn.execute(f"PRAGMA foreign_key_list({table})").fetchall() for table in tables}
        actual["triggers"] = conn.execute("SELECT name FROM sqlite_master WHERE type='trigger'").fetchall()
        actual["tables"] = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    except sqlite3.DatabaseError:
        return None
    finally:
        if conn is not None:
            conn.close()
    return actual


def grade(root):
    root = Path(root).resolve()
    gt = root / "gt"
    # Invalid private dependencies intentionally raise outside candidate handling.
    cases = json.loads((gt / "hidden_tests/cases.json").read_text())
    contract = json.loads((gt / "artifact_contract.json").read_text())
    protected = json.loads((gt / "protected_sha256.json").read_text())
    for name in ("driver.py", "public_test_snapshot.py", "public_fixture_snapshot.json"):
        if not (gt / name).is_file():
            raise RuntimeError("H042 scoring dependency missing: " + name)
    driver_bytes = (gt / "driver.py").read_bytes()
    public_bytes = (gt / "public_test_snapshot.py").read_bytes()
    fixture = json.loads((gt / "public_fixture_snapshot.json").read_text())
    if not isinstance(cases, list) or len(cases) < 30:
        raise RuntimeError("H042 private state vectors missing")
    source = root / "project/store.py"
    try:
        source_bytes = source.read_bytes() if source.is_file() and not source.is_symlink() and source.resolve().is_relative_to(root) else None
    except OSError:
        source_bytes = None
    unchanged = all((root / name).is_file() and not (root / name).is_symlink() and digest(root / name) == sha
                    and not any(parent.is_symlink() for parent in (root / name).parents if parent != root and parent.is_relative_to(root))
                    for name, sha in protected.items())
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] in {"results", "gt"} or "__pycache__" in relative.parts:
            continue
        if (path.is_file() or path.is_symlink()) and relative.as_posix() not in {*protected, "project/store.py"}:
            unchanged = False
    values = {group: {key: [] for key in weights} for group, weights in contract["requirement_weights"].items()}
    schemas, demo, public = [], None, None
    if source_bytes is not None:
        with tempfile.TemporaryDirectory(prefix="h042-rules-") as temporary:
            directory = Path(temporary)
            (directory / "store.py").write_bytes(source_bytes)
            (directory / "driver.py").write_bytes(driver_bytes)
            for case in cases:
                try:
                    actual = invoke(directory, case["scenario"])
                except subprocess.TimeoutExpired:
                    actual = None
                valid = isinstance(actual, dict) and set(actual) == {"events", "schema", "foreign_keys", "triggers", "tables"}
                values[case["group"]][case["requirement"]].append(float(valid and same(actual["events"], case["expected_events"])))
                if valid:
                    schemas.append(same(actual["schema"], contract["schema"])
                        and actual["tables"] == ["bookings", "people", "rooms"]
                        and actual["triggers"] == [] and actual["foreign_keys"] == {table: [] for table in contract["schema"]})
            scenario = {"actions": [
                {"kind": "import", "label": "first", "batch": fixture["first"]},
                {"kind": "import", "label": "retry", "batch": fixture["first"]},
                {"kind": "import", "label": "orphan", "batch": fixture["orphan"]},
                {"kind": "import", "label": "injected", "batch": fixture["injected"], "fail_after": 2}]}
            try:
                actual_demo = invoke(directory, scenario)
                if isinstance(actual_demo, dict) and isinstance(actual_demo.get("events"), list):
                    demo = [{key: value for key, value in event.items() if key != "in_transaction"} for event in actual_demo["events"]]
            except subprocess.TimeoutExpired:
                pass
            (directory / "test_public.py").write_bytes(public_bytes)
            try:
                public = subprocess.run([sys.executable, "-B", "-m", "unittest", "-v", "test_public"],
                    cwd=directory, capture_output=True, timeout=30, env=ENV)
            except subprocess.TimeoutExpired:
                pass
    schema_ok = bool(schemas) and all(schemas)
    def aggregate(group):
        return sum(weight * (sum(values[group][key]) / len(values[group][key]) if values[group][key] else 0.0)
                   for key, weight in contract["requirement_weights"][group].items())
    delivery = evidence = False
    try:
        for path in (root / "results", root / "results/db_audit.json", root / "results/tests.txt"):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("invalid candidate artifact path")
        audit = json.loads((root / "results/db_audit.json").read_text())
        text = (root / "results/tests.txt").read_text()
        lines = text.splitlines()
        delivery = bool(source_bytes is not None and unchanged and isinstance(audit, dict)
                        and set(audit) == {"source_sha256", "steps"} and demo is not None
                        and same(audit["steps"], demo) and len(lines) >= 3)
        claimed_hash = lines[0].split("=", 1)[1] if lines[0].startswith("source_sha256=") else None
        claimed_code = int(lines[1].split("=", 1)[1]) if lines[1].startswith("returncode=") else None
        command = json.loads(lines[2].split("=", 1)[1]) if lines[2].startswith("command=") else None
        evidence = bool(unchanged and source_bytes is not None and audit.get("source_sha256") == digest(source) == claimed_hash
            and isinstance(command, list) and command[-4:] == ["-m", "unittest", "-v", "test_public"]
            and public and claimed_code == public.returncode and public.returncode in {0, 1}
            and re.search(r"Ran 9 tests? in", text)
            and re.search(r"Ran 9 tests? in", public.stderr.decode("utf-8", errors="replace"))
            and (re.search(r"(?m)^OK\s*$", text) if public.returncode == 0 else re.search(r"(?m)^FAILED\b", text)))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, IndexError):
        pass
    scores = {"business_correctness": aggregate("business") if schema_ok else 0.0,
              "boundary_cases": aggregate("boundary") if unchanged and schema_ok else 0.0,
              "delivery_integrity": float(delivery), "evidence_binding": float(evidence)}
    scores["overall_score"] = sum(scores[key] * weight for key, weight in contract["weights"].items())
    return scores
