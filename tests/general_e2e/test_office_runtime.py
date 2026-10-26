"""Runtime locking/isolation controls. Fake CLI tests do not prove real math."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from src.wildclawbench_grading_core.office_runtime import (
    OfficeRuntimeError, _clean_package, create_office_lock, recalculate_xlsx, validate_office_lock,
)
from tests.general_e2e.test_local_scoring_runtime import Fixture, LOCK_PATH, RUNTIME

ROOT = Path(__file__).resolve().parents[2]
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def workbook_bytes():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Sheet1" sheetId="1" r:id="r1"/></sheets><calcPr calcMode="manual"/></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1"><v>2</v></c><c r="B1"><f>A1*3</f><v>999</v></c></row></sheetData></worksheet>')
    return output.getvalue()


@unittest.skipIf(os.name == "nt", "Unix fake executable fixture; Windows native engine needs its own acceptance")
class OfficeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.binary = self.root / "fake-soffice"
        self.binary.write_text("#!" + sys.executable + "\n" + '''import sys,pathlib,zipfile,xml.etree.ElementTree as E
if '--version' in sys.argv:
    print('LibreOffice 99.0 test-fixture');raise SystemExit(0)
assert 'AWS_ACCESS_KEY_ID' not in __import__('os').environ
source=pathlib.Path(sys.argv[-1]);output=pathlib.Path(sys.argv[sys.argv.index('--outdir')+1])/source.name
namespace='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
with zipfile.ZipFile(source) as incoming,zipfile.ZipFile(output,'w') as outgoing:
    for item in incoming.infolist():
        data=incoming.read(item)
        if item.filename=='xl/worksheets/sheet1.xml':
            root=E.fromstring(data)
            for cell in root.iter(namespace+'c'):
                if cell.find(namespace+'f') is not None:
                    assert cell.find(namespace+'v') is None
                    E.SubElement(cell,namespace+'v').text='6'
            data=E.tostring(root)
        outgoing.writestr(item,data)
''')
        self.binary.chmod(0o755)
        self.lock = create_office_lock(self.binary)

    def test_formula_caches_are_removed_and_full_auto_calculation_is_forced(self):
        clean, count = _clean_package(workbook_bytes())
        self.assertEqual(count, 1)
        with zipfile.ZipFile(io.BytesIO(clean)) as archive:
            cell = ET.fromstring(archive.read("xl/worksheets/sheet1.xml")).find(f"{S}sheetData/{S}row/{S}c[@r='B1']")
            self.assertEqual(cell.find(S + "f").text, "A1*3")
            self.assertIsNone(cell.find(S + "v"))
            calc = ET.fromstring(archive.read("xl/workbook.xml")).find(S + "calcPr")
            self.assertEqual(calc.attrib["calcMode"], "auto")
            self.assertEqual(calc.attrib["forceFullCalc"], "1")

    def test_source_is_preserved_and_derived_audit_is_bound_to_locked_binary(self):
        source = self.root / "input.xlsx"; source.write_bytes(workbook_bytes())
        result = recalculate_xlsx(source, self.lock, self.root / "derived")
        self.assertEqual(source.read_bytes(), workbook_bytes())
        audit = result["audit"]
        self.assertEqual(audit["source_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(audit["executable_sha256"], self.lock["executable_sha256"])
        with self.assertRaisesRegex(OfficeRuntimeError, "OFFICE_OUTPUT_EXISTS"):
            recalculate_xlsx(source, self.lock, self.root / "derived")
        self.binary.write_text(self.binary.read_text() + "\n# changed\n")
        with self.assertRaisesRegex(OfficeRuntimeError, "OFFICE_EXECUTABLE_DRIFT"):
            validate_office_lock(self.lock)

    def test_external_data_is_not_silently_replaced_with_cached_values(self):
        data = io.BytesIO(workbook_bytes())
        output = io.BytesIO()
        with zipfile.ZipFile(data) as incoming, zipfile.ZipFile(output, "w") as outgoing:
            for item in incoming.infolist(): outgoing.writestr(item, incoming.read(item))
            outgoing.writestr("xl/externalLinks/externalLink1.xml", "<externalLink/>")
        with self.assertRaisesRegex(OfficeRuntimeError, "OFFICE_EXTERNAL_DATA_UNSUPPORTED"):
            _clean_package(output.getvalue())

    def test_missing_engine_blocks_execution_without_publishing_a_zero(self):
        fixture = Fixture(self.root / "missing-engine", scoring_runtime={"office": True})
        attempt = fixture.prepare()
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "OFFICE_RUNTIME_REQUIRED"):
            RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=10)
        self.assertFalse((attempt / "rule-component.json").exists())
        self.assertFalse((attempt / "score.json").exists())

    def test_missing_delivery_remains_a_valid_task_score_and_bootstrap_freezes_runtime(self):
        rule = "def grade(**kwargs):\n    return {'fixture': 0.0, 'overall_score': 0.0}\n"
        fixture = Fixture(self.root / "missing-delivery", rule=rule, scoring_runtime={"office": True})
        combined = self.root / "combined.json"
        RUNTIME.bootstrap_office_runtime(self.binary, combined, LOCK_PATH)
        self.assertEqual(json.loads(combined.read_text())["office_runtime"], self.lock)
        prepared = RUNTIME.prepare_attempt(unit_root=fixture.unit_root, execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package, task_id=fixture.task_id, scoring_attempt_id="missing-delivery",
            output_root=fixture.output_root, runtime_lock_path=combined)
        attempt = Path(prepared["attempt_root"])
        RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=10)
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        result = RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.assertEqual(result["score"]["result"]["total_score"], 0.0)
        self.assertTrue(RUNTIME.verify_score_attempt(attempt)["score_valid"])

    def test_explicit_runtime_must_agree_with_frozen_lock(self):
        fixture = Fixture(self.root / "conflict", scoring_runtime={"office": True})
        combined = self.root / "combined.json"
        RUNTIME.bootstrap_office_runtime(self.binary, combined, LOCK_PATH)
        prepared = RUNTIME.prepare_attempt(unit_root=fixture.unit_root, execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package, task_id=fixture.task_id, scoring_attempt_id="conflict",
            output_root=fixture.output_root, runtime_lock_path=combined)
        changed = {**self.lock, "engine_version": "LibreOffice 99.1 alternative-fixture"}
        explicit = self.root / "alternative-office.json"
        explicit.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "OFFICE_RUNTIME_CONFLICT"):
            RUNTIME.run_rules_attempt(attempt_root=Path(prepared["attempt_root"]), runtime_python=Path(sys.executable),
                timeout_seconds=10, office_runtime_lock_path=explicit)

    def test_legacy_task_does_not_acquire_an_office_dependency_from_combined_lock(self):
        fixture = Fixture(self.root / "legacy")
        combined = self.root / "combined.json"
        RUNTIME.bootstrap_office_runtime(self.binary, combined, LOCK_PATH)
        self.binary.unlink()
        prepared = RUNTIME.prepare_attempt(unit_root=fixture.unit_root, execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package, task_id=fixture.task_id, scoring_attempt_id="legacy",
            output_root=fixture.output_root, runtime_lock_path=combined)
        result = RUNTIME.run_rules_attempt(attempt_root=Path(prepared["attempt_root"]),
            runtime_python=Path(sys.executable), timeout_seconds=10)
        self.assertEqual(result["rule_component"]["score"], 1.0)
        self.assertNotIn("office_runtime", result["audit"]["worker"])

    def test_worker_inherits_frozen_office_lock_and_derived_files_are_verified(self):
        helper = (ROOT / "src/wildclawbench_grading_core/office_runtime.py").read_bytes()
        rule = '''def grade(**kwargs):
    from pathlib import Path
    import os,json,runpy,zipfile,xml.etree.ElementTree as E
    root=Path(kwargs['workspace_path'])
    lock=json.loads(Path(os.environ['GENERAL_E2E_OFFICE_LOCK']).read_text())
    result=runpy.run_path(str(root/'gt/office_runtime.py'))['recalculate_xlsx'](root/'source.xlsx',lock,Path(os.environ['GENERAL_E2E_RULE_EVIDENCE_DIR'])/'workbook')
    with zipfile.ZipFile(result['path']) as archive:
        sheet=E.fromstring(archive.read('xl/worksheets/sheet1.xml'))
    value=sheet.find('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c[@r="B1"]/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v').text
    score=float(value=='6')
    return {'recalculation':score,'overall_score':score}
'''
        fixture = Fixture(self.root / "fixture", rule=rule, scoring_runtime={"office": True}, extra_gt_files={"office_runtime.py": helper})
        (fixture.candidate / "source.xlsx").write_bytes(workbook_bytes())
        entries, digest = RUNTIME._inventory_tree(fixture.candidate)
        artifact = fixture.candidate.parent / "candidate-artifact.json"
        payload = json.loads(artifact.read_text()); payload.update(entries=entries, expected_sha256=digest); artifact.write_text(json.dumps(payload))
        payload = json.loads(fixture.execution_record.read_text()); payload["candidate"]["frozen_sha256"] = digest; fixture.execution_record.write_text(json.dumps(payload))
        combined = self.root / "runtime-with-office.json"
        payload = json.loads(LOCK_PATH.read_text()); payload["office_runtime"] = self.lock; combined.write_text(json.dumps(payload))
        prepared = RUNTIME.prepare_attempt(unit_root=fixture.unit_root, execution_record_path=fixture.execution_record,
            scoring_package=fixture.scoring_package, task_id=fixture.task_id, scoring_attempt_id="office-worker", output_root=fixture.output_root, runtime_lock_path=combined)
        attempt = Path(prepared["attempt_root"])
        result = RUNTIME.run_rules_attempt(attempt_root=attempt, runtime_python=Path(sys.executable), timeout_seconds=30)
        self.assertEqual(result["rule_component"]["score"], 1.0)
        self.assertTrue(RUNTIME._verify_office_rule_evidence(attempt, required=True))
        references, _ = RUNTIME._semantic_reference_inputs(attempt,
            json.loads((attempt / "attempt-manifest.json").read_text()), [])
        derived_paths = {item["path"] for item in references if item["type"] == "rule_derived_artifact"}
        self.assertEqual(derived_paths, {"worker/office-runtime.json", "worker/derived/workbook/recalculated.xlsx",
            "worker/derived/workbook/office-audit.json"})
        RUNTIME.prepare_semantics_attempt(attempt_root=attempt)
        RUNTIME.finalize_score_attempt(attempt_root=attempt)
        self.assertTrue(RUNTIME.verify_score_attempt(attempt)["score_valid"])
        self.binary.unlink()
        shutil.rmtree(attempt / "runtime")
        self.assertTrue(RUNTIME.verify_score_attempt(attempt, archived=True)["score_valid"])
        workbook = attempt / "worker/derived/workbook/recalculated.xlsx"
        workbook.write_bytes(b"changed")
        with self.assertRaisesRegex(RUNTIME.ScoringRuntimeError, "OFFICE_DERIVED_ARTIFACT_DRIFT"):
            RUNTIME.verify_score_attempt(attempt, archived=True)

    def test_archived_lock_still_requires_full_schema(self):
        self.binary.unlink()
        self.assertEqual(validate_office_lock(self.lock, require_executable=False), self.binary.resolve())
        invalid = {**self.lock, "executable_sha256": "invalid"}
        with self.assertRaisesRegex(OfficeRuntimeError, "OFFICE_LOCK_INVALID"):
            validate_office_lock(invalid, require_executable=False)


if __name__ == "__main__":
    unittest.main()
