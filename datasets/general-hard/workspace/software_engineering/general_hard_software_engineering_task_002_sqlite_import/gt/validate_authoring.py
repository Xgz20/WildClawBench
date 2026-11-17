"""Local author controls with a separately labelled state oracle."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def deliver(root):
    gt = root / "gt"
    results = root / "results"
    results.mkdir()
    fixture = json.loads((root / "fixtures/batch.json").read_text())
    scenario = {"actions": [
        {"kind": "import", "label": "first", "batch": fixture["first"]},
        {"kind": "import", "label": "retry", "batch": fixture["first"]},
        {"kind": "import", "label": "orphan", "batch": fixture["orphan"]},
        {"kind": "import", "label": "injected", "batch": fixture["injected"], "fail_after": 2}]}
    # Candidate modules can alter process globals. Keep author demo generation
    # isolated exactly as the scoring driver is isolated from the trusted grader.
    with tempfile.TemporaryDirectory(prefix="h042-record-") as temporary:
        directory = Path(temporary)
        shutil.copy2(gt / "driver.py", directory / "driver.py")
        shutil.copy2(root / "project/store.py", directory / "store.py")
        completed = subprocess.run([sys.executable, "-I", "-B", str(directory / "driver.py")],
            input=json.dumps(scenario, ensure_ascii=False).encode(), cwd=directory, capture_output=True, timeout=15,
            env={"PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"}, check=True)
        actual = json.loads(completed.stdout)
        shutil.copy2(directory / "scratch.sqlite", results / "demo.sqlite")
    events = [{key: value for key, value in event.items() if key != "in_transaction"} for event in actual["events"]]
    (results / "db_audit.json").write_text(json.dumps({"source_sha256": digest(root / "project/store.py"), "steps": events}, ensure_ascii=False, indent=2))
    command = [sys.executable, "-m", "unittest", "-v", "test_public"]
    public = subprocess.run(command, cwd=root / "project", capture_output=True, timeout=30)
    text = "source_sha256=" + digest(root / "project/store.py") + "\nreturncode=" + str(public.returncode) + "\ncommand=" + json.dumps(command) + "\n"
    (results / "tests.txt").write_text(text + public.stdout.decode("utf-8", errors="replace") + public.stderr.decode("utf-8", errors="replace"))


def validate(exec_root, gt):
    exec_root, gt = Path(exec_root).resolve(), Path(gt).resolve()
    grader = runpy.run_path(str(gt / "grader.py"))["grade"]
    reference = (gt / "reference_solution.py").read_text()
    prefix = reference.split("def import_batch(", 1)[0]
    skip_all = prefix + '''def import_batch(conn, batch, *, fail_after=None):
    return {"inserted": {name: 0 for name in ("people", "rooms", "bookings")}, "skipped": {name: len(batch[name]) for name in ("people", "rooms", "bookings")}}
'''
    foreign_keys = reference.replace("seats INTEGER NOT NULL)", "seats INTEGER NOT NULL, FOREIGN KEY(person_id) REFERENCES people(id), FOREIGN KEY(room_id) REFERENCES rooms(id))")
    spoof_probe = foreign_keys + '''
import sqlite3
_real_connect = sqlite3.connect
class _EmptyProbe:
    def fetchall(self):
        return []
class _ConnectionProxy:
    def __init__(self, connection):
        self.connection = connection
    def execute(self, sql, *args):
        if sql.startswith("PRAGMA foreign_key_list"):
            return _EmptyProbe()
        return self.connection.execute(sql, *args)
    def __getattr__(self, name):
        return getattr(self.connection, name)
def _spoof_connect(*args, **kwargs):
    return _ConnectionProxy(_real_connect(*args, **kwargs))
sqlite3.connect = _spoof_connect
'''
    caller_commit = reference.replace('        conn.execute("RELEASE SAVEPOINT course_batch_import")\n    except',
        '        conn.execute("RELEASE SAVEPOINT course_batch_import")\n        conn.commit()\n    except')
    variants = {"reference": reference, "original_buggy": (exec_root / "project/store.py").read_text(),
                "skip_all": skip_all, "foreign_key_schema": foreign_keys, "spoof_fk_probe": spoof_probe, "caller_commit": caller_commit,
                "changed_public_test": reference, "missing_delivery": reference, "stale_evidence": reference}
    results = {}
    for name, source in variants.items():
        with tempfile.TemporaryDirectory(prefix="h042-author-") as temporary:
            root = Path(temporary)
            shutil.copytree(exec_root, root, dirs_exist_ok=True)
            shutil.copytree(gt, root / "gt", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (root / "project/store.py").write_text(source)
            deliver(root)
            if name == "changed_public_test":
                with (root / "project/test_public.py").open("a") as stream:
                    stream.write("\n# changed protected input\n")
            elif name == "missing_delivery":
                (root / "results/db_audit.json").unlink()
            elif name == "stale_evidence":
                with (root / "project/store.py").open("a") as stream:
                    stream.write("\n# final source revision\n")
            score = grader(root)
            results[name] = score
            if name == "reference":
                assert abs(score["overall_score"] - 1.0) < 1e-9, score
                (root / "gt/hidden_tests/cases.json").unlink()
                try:
                    grader(root)
                except FileNotFoundError:
                    results["missing_gt"] = {"status": "infrastructure_exception_preserved", "exception": "FileNotFoundError"}
                else:
                    raise AssertionError("Missing private state vectors became a candidate score")
            elif name in {"foreign_key_schema", "spoof_fk_probe"}:
                assert score["business_correctness"] == score["boundary_cases"] == 0, score
            elif name == "changed_public_test":
                assert score["boundary_cases"] == score["delivery_integrity"] == score["evidence_binding"] == 0, score
            elif name == "missing_delivery":
                assert score["delivery_integrity"] == 0, score
            elif name == "stale_evidence":
                assert score["evidence_binding"] == 0, score
            else:
                assert score["business_correctness"] < 1 and score["overall_score"] < 1, score
    return {"schema_version": "wildclawbench.authoring-validation/v1", "task": "H042", "status": "passed",
        "case_count": len(json.loads((gt / "hidden_tests/cases.json").read_text())), "results": results,
        "reference_sha256": digest(gt / "reference_solution.py"), "oracle_sha256": digest(gt / "hidden_tests/cases.json"),
        "grader_sha256": digest(gt / "grader.py"), "driver_sha256": digest(gt / "driver.py"),
        "scope": "Local Python/SQLite author controls only; not four-Harness or Docker rule-worker execution, independent human review or empirical difficulty calibration."}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--exec-root", required=True, type=Path)
    parser.add_argument("--gt-root", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    print(json.dumps(validate(args.exec_root, args.gt_root), ensure_ascii=False, indent=2))
