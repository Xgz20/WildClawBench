"""Author-owned controls; no model/Harness run or difficulty calibration."""
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
    results = root / "results"
    results.mkdir()
    command = [sys.executable, "-m", "unittest", "-v", "test_public"]
    completed = subprocess.run(command, cwd=root / "project", capture_output=True, timeout=30)
    (results / "public.stdout").write_bytes(completed.stdout)
    (results / "public.stderr").write_bytes(completed.stderr)
    report = {"source_sha256": digest(root / "project/importer.py"), "command": command,
        "returncode": completed.returncode, "tests_run": 7, "passed": completed.returncode == 0,
        "stdout_path": "results/public.stdout", "stdout_sha256": digest(results / "public.stdout"),
        "stderr_path": "results/public.stderr", "stderr_sha256": digest(results / "public.stderr")}
    (results / "test_report.json").write_text(json.dumps(report))
    (results / "compatibility.md").write_text("## 修复\n按配置、解码、CSV语法、表头与记录顺序分流错误，课程内部错误按契约优先级选择。\n## 兼容\n保留姓名、课程原文和逻辑记录顺序；支持BOM、CRLF、TSV和引号内换行。\n## 验证范围\n本次为作者控制，公开测试与独立表驱动样本均由评分器重新验证，尚无被测模型/Harness实测。\n")


def validate(exec_root, gt):
    exec_root, gt = Path(exec_root).resolve(), Path(gt).resolve()
    grader = runpy.run_path(str(gt / "grader.py"))["grade"]
    reference = (gt / "reference_solution.py").read_text()
    output = {}
    variants = {
        "reference": reference,
        "original_buggy": (exec_root / "project/importer.py").read_text(),
        "swallow_errors": 'import json\nprint(json.dumps({"ok": True, "records": [], "stats": {"students": 0, "enrollments": 0}}))\n',
        "csv_only": reference.replace('data, args.format, args.course_separator', 'data, "csv", args.course_separator'),
        "changed_public_test": reference,
        "missing_delivery": reference,
        "stale_evidence": reference,
    }
    for name, source in variants.items():
        with tempfile.TemporaryDirectory(prefix="h041-author-") as temporary:
            root = Path(temporary)
            shutil.copytree(exec_root, root, dirs_exist_ok=True)
            shutil.copytree(gt, root / "gt", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            (root / "project/importer.py").write_text(source)
            deliver(root)
            if name == "changed_public_test":
                with (root / "project/test_public.py").open("a") as stream:
                    stream.write("\n# modified after repair\n")
            if name == "missing_delivery":
                (root / "results/compatibility.md").unlink()
            if name == "stale_evidence":
                with (root / "project/importer.py").open("a") as stream:
                    stream.write("\n# final source changed after recording the public test run\n")
            scores = grader(root)
            output[name] = scores
            if name == "reference":
                assert scores["overall_score"] > 0.999999, scores
                (root / "gt/hidden_tests/cases.json").unlink()
                try:
                    grader(root)
                except FileNotFoundError:
                    output["missing_gt"] = {"status": "infrastructure_exception_preserved", "exception": "FileNotFoundError"}
                else:
                    raise AssertionError("Missing GT incorrectly became a candidate score")
            elif name == "changed_public_test":
                assert scores["boundary_cases"] == scores["delivery_integrity"] == scores["evidence_binding"] == 0, scores
            elif name == "missing_delivery":
                assert scores["delivery_integrity"] == 0, scores
            elif name == "stale_evidence":
                assert scores["evidence_binding"] == 0, scores
            else:
                assert scores["business_correctness"] < 1 and scores["overall_score"] < 1, scores
    return {"schema_version": "wildclawbench.authoring-validation/v1", "task": "H041", "status": "passed",
        "case_count": 49, "results": output, "reference_sha256": digest(gt / "reference_solution.py"),
        "oracle_sha256": digest(gt / "hidden_tests/cases.json"), "grader_sha256": digest(gt / "grader.py"),
        "scope": "Local Python author controls only; not Docker rule-worker verification, four-Harness execution or empirical difficulty proof."}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--exec-root", required=True, type=Path)
    parser.add_argument("--gt-root", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    print(json.dumps(validate(args.exec_root, args.gt_root), ensure_ascii=False, indent=2))
