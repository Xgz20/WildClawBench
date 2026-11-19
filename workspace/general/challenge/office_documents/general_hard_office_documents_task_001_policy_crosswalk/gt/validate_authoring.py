"""Author controls, not an independent semantic Judge or Harness execution.

OOXML mutations below are deliberately faulty test specimens (including stale
formula caches). They are not workbook authoring or an alternate golden builder.
"""
import argparse
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import re
import runpy
import shutil
import tempfile
import xml.etree.ElementTree as ET
import zipfile

S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def mutate_workbook(path, changes=None, *, wrong_formulas=False, equivalent_layout=False):
    original = path.read_bytes()
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as incoming, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as outgoing:
        for info in incoming.infolist():
            raw = incoming.read(info)
            if info.filename == "xl/worksheets/sheet1.xml":
                sheet = ET.fromstring(raw)
                cells = {cell.attrib["r"]: cell for cell in sheet.iter(S + "c")}
                for address, value in (changes or {}).items():
                    cell = cells[address]
                    for child in list(cell):
                        cell.remove(child)
                    cell.attrib.pop("t", None)
                    if isinstance(value, (int, float)):
                        ET.SubElement(cell, S + "v").text = str(value)
                    elif value is not None:
                        cell.attrib["t"] = "inlineStr"
                        ET.SubElement(ET.SubElement(cell, S + "is"), S + "t").text = str(value)
                if wrong_formulas:
                    for row in range(6, 24):
                        cells["F" + str(row)].find(S + "f").text = "99999"
                if equivalent_layout:
                    columns = dict(zip("ABCDEFGHIJK", "KJIHGFEDCBA"))
                    for row in sheet.iter(S + "row"):
                        row.attrib["r"] = str(int(row.attrib["r"]) + 2)
                        for cell in row.findall(S + "c"):
                            match = re.fullmatch(r"([A-Z]+)([0-9]+)", cell.attrib["r"])
                            cell.attrib["r"] = columns.get(match[1], match[1]) + str(int(match[2]) + 2)
                            formula = cell.find(S + "f")
                            if formula is not None:
                                cell.remove(formula)
                        row[:] = sorted(row, key=lambda cell: cell.attrib.get("r", ""))
                    dimension = sheet.find(S + "dimension")
                    if dimension is not None:
                        dimension.attrib["ref"] = "A1:M27"
                raw = ET.tostring(sheet, encoding="utf-8", xml_declaration=True)
            elif info.filename == "xl/workbook.xml" and equivalent_layout:
                workbook = ET.fromstring(raw)
                workbook.find(S + "sheets")[0].attrib["name"] = "EquivalentLayout"
                raw = ET.tostring(workbook, encoding="utf-8", xml_declaration=True)
            outgoing.writestr(info, raw)
    path.write_bytes(output.getvalue())


@contextmanager
def worker_environment(lock, output):
    values = {"GENERAL_E2E_OFFICE_LOCK": str(lock), "GENERAL_E2E_RULE_EVIDENCE_DIR": str(output)}
    old = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def validate(exec_root, gt_root, lock, task_path=None):
    exec_root, gt_root, lock = Path(exec_root).resolve(), Path(gt_root).resolve(), Path(lock).resolve()
    expected = json.loads((gt_root / "expected.json").read_text(encoding="utf-8"))["cases"]
    model = runpy.run_path(str(gt_root / "decision_model.py"))["decide"]
    import csv
    with (exec_root / "cases.csv").open(encoding="utf-8", newline="") as handle:
        cases = list(csv.DictReader(handle))
    comparisons = [{"case_id": record["case_id"], "match": all(model(record)[key] == label[key]
                   for key in ("rule_set", "status", "rate", "cap_cny", "grant_cny"))} for record, label in zip(cases, expected)]
    assert len(cases) == len(expected) == 18 and all(item["match"] for item in comparisons)
    variants = ["reference", "equivalent_layout", "missing_action_header", "missing_amount_header", "missing_evidence_header", "ambiguous_status_header",
                "latest_only", "blanket_transition", "invented_missing",
                "wrong_formula_correct_cache", "missing_handoff", "missing_workbook", "protected_change", "missing_gt"]
    results = {}
    with tempfile.TemporaryDirectory(prefix="h001-author-") as temporary:
        base = Path(temporary)
        for name in variants:
            root = base / name
            shutil.copytree(exec_root, root)
            shutil.copytree(gt_root, root / "gt", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "authoring_validation.json"))
            shutil.copytree(gt_root / "reference/results", root / "results")
            workbook = root / "results/applicability.xlsx"
            if name == "equivalent_layout":
                mutate_workbook(workbook, equivalent_layout=True)
            elif name == "missing_action_header":
                mutate_workbook(workbook, {"K5": None})
            elif name == "missing_amount_header":
                mutate_workbook(workbook, {"F5": None})
            elif name == "missing_evidence_header":
                mutate_workbook(workbook, {"I5": None})
            elif name == "ambiguous_status_header":
                mutate_workbook(workbook, {"G5": "办理状态"})
            elif name == "latest_only":
                mutate_workbook(workbook, {**{f"B{row}": "V2" for row in range(6, 24)},
                    **{f"D{row}": 0.7 for row in range(6, 24)}, **{f"E{row}": 4500 for row in range(6, 24)}})
            elif name == "blanket_transition":
                mutate_workbook(workbook, {**{f"B{row}": "V1-T01" for row in (11, 12, 14, 15, 16)},
                    **{f"C{row}": "可资助" for row in (11, 12, 14, 15, 16)},
                    **{f"D{row}": 0.6 for row in (11, 12, 14, 15, 16)}, **{f"E{row}": 3000 for row in (11, 12, 14, 15, 16)}})
            elif name == "invented_missing":
                mutate_workbook(workbook, {"B18": "V2", "C18": "可资助", "F18": 700, "J18": None,
                    "C22": "可资助", "F22": 600, "J22": None, "B23": "V2", "C23": "可资助", "D23": 0.7,
                    "E23": 4500, "F23": 1400, "J23": None})
            elif name == "wrong_formula_correct_cache":
                mutate_workbook(workbook, wrong_formulas=True)
                extract = runpy.run_path(str(gt_root / "native_text.py"))["extract_native_text"]
                records = [json.loads(line) for line in extract(workbook)["text"].splitlines()]
                grants = {record["locator"].rsplit("!", 1)[-1]: record.get("value") for record in records
                          if "!" in record["locator"] and record["locator"].startswith("判定结果!")}
                assert all((grants.get(f"F{index+6}") in (None, "") if label["grant_cny"] is None
                            else float(grants[f"F{index+6}"]) == label["grant_cny"]) for index, label in enumerate(expected))
            elif name == "missing_handoff":
                (root / "results/handoff.docx").unlink()
            elif name == "missing_workbook":
                workbook.unlink()
            elif name == "protected_change":
                with (root / "cases.csv").open("a", encoding="utf-8") as handle:
                    handle.write("\n")
            elif name == "missing_gt":
                (root / "gt/expected.json").unlink()
            before = {p.relative_to(root / "results").as_posix(): sha(p) for p in (root / "results").rglob("*") if p.is_file()}
            output = base / (name + "-evidence")
            with worker_environment(lock, output):
                try:
                    result = runpy.run_path(str(root / "gt/grader.py"))["grade"](root)
                except FileNotFoundError:
                    assert name == "missing_gt"
                    results[name] = {"status": "evaluation_error", "error": "FileNotFoundError", "score": None}
                    continue
            after = {p.relative_to(root / "results").as_posix(): sha(p) for p in (root / "results").rglob("*") if p.is_file()}
            assert before == after, "grader changed candidate outputs"
            if name in {"reference", "equivalent_layout"}:
                assert abs(result["overall_score"] - 1) < 1e-9, (name, result)
            else:
                assert result["overall_score"] < .999, (name, result)
            if name == "wrong_formula_correct_cache":
                assert result["business_correctness"] <= .701 and result["boundary_cases"] == 0, result
            if name in {"missing_action_header", "missing_evidence_header"}:
                assert result["business_correctness"] == result["boundary_cases"] == 1, (name, result)
            if name == "missing_action_header":
                assert result["evidence_binding"] == 1 and result["delivery_integrity"] < 1, result
            if name == "missing_evidence_header":
                assert result["evidence_binding"] == 0, result
            if name in {"missing_amount_header", "ambiguous_status_header"}:
                assert abs(result["business_correctness"] - .7) < 1e-9 and result["boundary_cases"] == 0, (name, result)
            if name == "protected_change":
                assert result["delivery_integrity"] == result["boundary_cases"] == result["evidence_binding"] == 0
            results[name] = result
        if task_path:
            root = base / "actual-md"
            shutil.copytree(exec_root, root)
            shutil.copytree(gt_root, root / "gt", ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "authoring_validation.json"))
            shutil.copytree(gt_root / "reference/results", root / "results")
            text = Path(task_path).read_text(encoding="utf-8")
            section = text.split("## Automated Checks", 1)[1].split("## LLM Judge Rubric", 1)[0]
            source = re.search(r"```python\s*\n(.*?)```", section, re.S)[1]
            namespace = {}
            exec(compile(source, "frozen-h001-task-md", "exec"), namespace)
            with worker_environment(lock, base / "actual-md-evidence"):
                results["actual_md_reference"] = namespace["grade"](workspace_path=str(root))
            assert abs(results["actual_md_reference"]["overall_score"] - 1) < 1e-9
    hashes = {p.relative_to(gt_root).as_posix(): sha(p) for p in sorted(gt_root.rglob("*"))
              if p.is_file() and p.name != "authoring_validation.json" and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    return {"schema_version": "h001-author-validation/v1", "status": "PASS", "controls": results,
            "independent_model_comparisons": comparisons, "gt_sha256": hashes,
            "office_runtime": json.loads(lock.read_text(encoding="utf-8")),
            "boundaries": "Author controls using actual trusted Calc and the frozen rule entry; no semantic Judge, four-Harness run or empirical difficulty claim."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--exec-root", required=True, type=Path)
    parser.add_argument("--gt-root", required=True, type=Path)
    parser.add_argument("--office-runtime-lock", required=True, type=Path)
    parser.add_argument("--task-path", type=Path)
    args = parser.parse_args()
    result = validate(args.exec_root, args.gt_root, args.office_runtime_lock, args.task_path)
    (args.gt_root / "authoring_validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "controls": result["controls"]}, ensure_ascii=False))
