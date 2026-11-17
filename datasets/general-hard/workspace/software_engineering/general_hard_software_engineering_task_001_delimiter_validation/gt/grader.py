"""Offline scorer: independently labelled CLI cases and protected-input checks."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def same_json(value, expected):
    if type(value) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(value) == set(expected) and all(same_json(value[key], item) for key, item in expected.items())
    if isinstance(expected, list):
        return len(value) == len(expected) and all(same_json(left, right) for left, right in zip(value, expected))
    return value == expected


def invoke(program, case, directory):
    path = directory / "input"
    path.write_bytes(base64.b64decode(case["input_base64"], validate=True))
    result = subprocess.run([sys.executable, "-I", "-B", str(program), "--input", str(path),
        "--format", case["format"], "--course-separator", case["separator"]],
        cwd=directory, capture_output=True, timeout=4,
        env={"PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"})
    if len(result.stdout) > 1024 * 1024:
        return False
    try:
        value = json.loads(result.stdout)
    except (UnicodeError, ValueError):
        return False
    expected = case["expected"]
    if expected["ok"]:
        return result.returncode == 0 and same_json(value, expected)
    if result.returncode != 2 or not isinstance(value, dict) or set(value) != {"ok", "error"} or value["ok"] is not False:
        return False
    error = value["error"]
    if not isinstance(error, dict) or set(error) != {"code", "row", "field", "message"}:
        return False
    return (all(same_json(error[key], expected["error"][key]) for key in ("code", "row", "field"))
            and isinstance(error["message"], str) and error["code"] in error["message"])


def grade(root):
    root = Path(root).resolve()
    gt = root / "gt"
    # Missing/invalid private inputs are infrastructure errors, never zero scores.
    cases = json.loads((gt / "hidden_tests/cases.json").read_text())
    protected = json.loads((gt / "protected_sha256.json").read_text())
    contract = json.loads((gt / "artifact_contract.json").read_text())
    source = root / "project/importer.py"
    try:
        source_bytes = source.read_bytes() if source.is_file() and not source.is_symlink() and source.resolve().is_relative_to(root) else None
    except OSError:
        source_bytes = None
    pristine_test = gt / "public_test_snapshot.py"
    if not pristine_test.is_file() or not isinstance(cases, list) or len(cases) < 40:
        raise RuntimeError("H041 private scoring dependency missing or malformed")
    unchanged = all((root / name).is_file() and not (root / name).is_symlink() and sha(root / name) == digest
                    and not any(parent.is_symlink() for parent in (root / name).parents if parent != root and parent.is_relative_to(root))
                    for name, digest in protected.items())
    allowed = {*protected, "project/importer.py"}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if relative.parts[0] in {"gt", "results"} or "__pycache__" in relative.parts:
            continue
        if (path.is_file() or path.is_symlink()) and relative.as_posix() not in allowed:
            unchanged = False
    passed = {group: {key: [] for key in weights} for group, weights in contract["requirement_weights"].items()}
    public = None
    if source_bytes is not None:
        with tempfile.TemporaryDirectory(prefix="h041-rules-") as temporary:
            directory = Path(temporary)
            program = directory / "importer.py"
            program.write_bytes(source_bytes)
            for case in cases:
                try:
                    success = invoke(program, case, directory)
                except subprocess.TimeoutExpired:
                    success = False
                passed[case["group"]][case["requirement"]].append(float(success))
            shutil.copy2(pristine_test, directory / "test_public.py")
            try:
                public = subprocess.run([sys.executable, "-B", "-m", "unittest", "-v", "test_public"],
                    cwd=directory, capture_output=True, timeout=30,
                    env={"PYTHONIOENCODING": "utf-8", "PYTHONHASHSEED": "0"})
            except subprocess.TimeoutExpired:
                public = None
    def average(group):
        return sum(weight * (sum(passed[group][key]) / len(passed[group][key]) if passed[group][key] else 0.0)
                   for key, weight in contract["requirement_weights"][group].items())
    report_ok = compatibility_ok = evidence = False
    report_path = root / "results/test_report.json"
    compatibility_path = root / "results/compatibility.md"
    try:
        for path in (root / "results", compatibility_path):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("candidate report path escapes workspace")
        compatibility = compatibility_path.read_text()
        compatibility_ok = all(heading in compatibility for heading in contract["compatibility_headings"])
    except (OSError, UnicodeError, ValueError):
        compatibility_ok = False
    try:
        for path in (root / "results", report_path):
            if path.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("candidate report path escapes workspace")
        report = json.loads(report_path.read_text())
        report_ok = (isinstance(report, dict) and set(report) == set(contract["test_report_keys"])
                     and type(report["returncode"]) is int and type(report["tests_run"]) is int
                     and type(report["passed"]) is bool and isinstance(report["command"], list)
                     and all(isinstance(part, str) for part in report["command"]))
        if report_ok:
            logs_ok = True
            texts = []
            for kind in ("stdout", "stderr"):
                value = report[kind + "_path"]
                if not isinstance(value, str) or not value.startswith("results/") or ".." in Path(value).parts:
                    logs_ok = False
                    continue
                path = root / value
                if path.is_symlink() or not path.resolve().is_relative_to((root / "results").resolve()) or not path.is_file():
                    logs_ok = False
                    continue
                logs_ok = logs_ok and sha(path) == report[kind + "_sha256"]
                texts.append(path.read_text())
            log = "\n".join(texts)
            evidence = bool(logs_ok and public and public.returncode in {0, 1} and report["returncode"] == public.returncode
                and report["tests_run"] == 7 and report["passed"] is (public.returncode == 0)
                and report["source_sha256"] == sha(source)
                and report["command"][-4:] == ["-m", "unittest", "-v", "test_public"]
                and re.search(r"Ran 7 tests? in", log)
                and re.search(r"Ran 7 tests? in", public.stderr.decode("utf-8", errors="replace"))
                and (re.search(r"(?m)^OK\s*$", log) if public.returncode == 0 else re.search(r"(?m)^FAILED\b", log)))
    except (OSError, UnicodeError, ValueError, TypeError, KeyError):
        # Candidate deliverables may be missing or malformed; GT errors above
        # deliberately remain outside this exception boundary.
        report_ok = False
    scores = {"business_correctness": average("business"),
              "boundary_cases": average("boundary") if unchanged else 0.0,
              "delivery_integrity": float(source_bytes is not None and unchanged and report_ok and compatibility_ok),
              "evidence_binding": float(unchanged and evidence)}
    scores["overall_score"] = sum(scores[key] * weight for key, weight in contract["weights"].items())
    return scores
