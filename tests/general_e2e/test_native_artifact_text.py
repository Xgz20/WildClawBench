"""Structural reader tests; these minimal packages are not dataset artifacts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

from src.wildclawbench_grading_core.native_text import (
    NativeTextError, extract_native_text, _cell_date,
)
from src.utils.workspace_evidence import collect_workspace_evidence


def write_docx(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>
<w:p><w:r><w:t>2026年制度</w:t><w:tab/><w:t>生效日</w:t></w:r></w:p>
<w:sdt><w:sdtContent><w:p><w:r><w:t>过渡条款T01</w:t></w:r><w:del><w:r><w:delText>已删除旧说法</w:delText></w:r></w:del></w:p></w:sdtContent></w:sdt>
<w:tbl><w:tr><w:tc><w:p><w:r><w:t>C01</w:t></w:r></w:p></w:tc><w:tc><w:p><w:r><w:t>待核实</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>''')
        archive.writestr("word/header1.xml", '<w:hdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>人事处</w:t></w:r></w:p></w:hdr>')
    return path


def write_xlsx(path: Path, *, target="worksheets/sheet1.xml") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="判定" sheetId="1" r:id="r1"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", f'<Relationships><Relationship Id="r1" Target="{target}"/></Relationships>')
        archive.writestr("xl/sharedStrings.xml", '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><r><t>资助</t></r><r><t>金额</t></r><rPh><t>excluded-phonetic</t></rPh></si></sst>')
        archive.writestr("xl/styles.xml", '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/></numFmts><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="164"/></cellXfs></styleSheet>')
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr"><is><t>可资助</t></is></c></row><row r="2"><c r="A2"><f>MIN(2000*0.6,3000)</f><v>1200</v></c><c r="B2"><f>1+2</f></c><c r="C2" s="1"><v>46023</v></c><c r="D2" t="b"><v>1</v></c><c r="E2" t="str"><f>IF(1=1,"",1)</f><v/></c></row></sheetData></worksheet>')
    return path


class NativeArtifactTextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_docx_preserves_paragraph_table_control_and_header_locators(self):
        path = write_docx(self.root / "policy.docx")
        value = extract_native_text(path)
        rows = [json.loads(line) for line in value["text"].splitlines()]
        self.assertEqual(rows[0], {"locator": "paragraph:1", "text": "2026年制度\t生效日"})
        self.assertEqual(rows[1]["text"], "过渡条款T01")
        self.assertEqual(rows[2], {"locator": "table:1/row:1/cell:1", "text": "C01"})
        self.assertEqual(rows[3]["text"], "待核实")
        self.assertIn("header1.xml", rows[4]["locator"])
        self.assertEqual(value["source_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(value["truncated"])
        self.assertNotIn("已删除旧说法", value["text"])

    def test_xlsx_keeps_cells_formula_cache_missingness_and_date_context(self):
        value = extract_native_text(write_xlsx(self.root / "applicability.xlsx"))
        rows = {row["locator"]: row for row in map(json.loads, value["text"].splitlines())}
        self.assertEqual(rows["判定!A1"]["value"], "资助金额")
        self.assertNotIn("excluded-phonetic", value["text"])
        self.assertEqual(rows["判定!A2"]["value"], "1200")
        self.assertTrue(rows["判定!A2"]["cached_value_available"])
        self.assertFalse(rows["判定!B2"]["cached_value_available"])
        self.assertIsNone(rows["判定!B2"]["value"])
        self.assertEqual(rows["判定!C2"]["interpreted_date"], "2026-01-01T00:00:00")
        self.assertIs(rows["判定!D2"]["value"], True)
        self.assertEqual(rows["判定!E2"]["value"], "")
        self.assertTrue(rows["判定!E2"]["cached_value_available"])
        self.assertIn("not recalculated", " ".join(value["limitations"]))

    def test_native_record_paging_keeps_global_positions_and_reports_truncation(self):
        path = write_docx(self.root / "policy.docx")
        whole = extract_native_text(path)
        page = extract_native_text(path, record_offset=2, record_limit=2)
        self.assertEqual(page["record_count"], 5)
        self.assertEqual(page["selected_record_count"], 2)
        self.assertEqual(page["text"].splitlines(), whole["text"].splitlines()[2:4])
        clipped = extract_native_text(path, max_chars=20)
        self.assertTrue(clipped["truncated"])
        self.assertEqual(clipped["included_chars"], 20)

    def test_number_formats_do_not_turn_currency_or_elapsed_time_into_dates(self):
        self.assertIsNone(_cell_date("1200", '[Red]"USD"0.00', False))
        self.assertIsNone(_cell_date("0.5", "[h]:mm:ss", False))
        self.assertEqual(_cell_date("60", "yyyy-mm-dd", False), "1900-02-29 (Excel serial calendar)")
        self.assertEqual(_cell_date("0", "yyyy-mm-dd", True), "1904-01-01T00:00:00")

    def test_unsafe_relationship_and_malformed_package_do_not_become_text(self):
        with self.assertRaisesRegex(NativeTextError, "relationship escapes"):
            extract_native_text(write_xlsx(self.root / "unsafe.xlsx", target="../../outside.xml"))
        path = self.root / "bad.docx"
        path.write_text("not a document")
        with self.assertRaises(NativeTextError):
            extract_native_text(path)
        path = write_docx(self.root / "safe.docx")
        linked = self.root / "linked.docx"
        linked.symlink_to(path)
        with self.assertRaisesRegex(NativeTextError, "regular file"):
            extract_native_text(linked)

    def test_missing_pdf_dependency_is_explicit_infrastructure_error(self):
        path = self.root / "document.pdf"
        path.write_bytes(b"%PDF-1.4\n")
        with patch.dict("sys.modules", {"pypdf": None}):
            with self.assertRaises(NativeTextError) as caught:
                extract_native_text(path)
        self.assertEqual(caught.exception.code, "NATIVE_TEXT_DEPENDENCY_MISSING")

    def test_legacy_workspace_reader_selects_declared_native_and_excludes_gt(self):
        path = write_docx(self.root / "results/handoff.docx")
        write_docx(self.root / "gt/private.docx")
        value = collect_workspace_evidence(str(self.root), {"required": [{"path": "results/handoff.docx"}]})
        selected = value["metadata"]["selected"]
        self.assertEqual([item["path"] for item in selected], ["results/handoff.docx"])
        self.assertEqual(selected[0]["native_extraction"]["source_sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertIn("待核实", value["text"])
        self.assertNotIn("gt/private", value["text"])

    def test_legacy_helper_files_work_without_source_checkout_imports(self):
        repo = Path(__file__).resolve().parents[2]
        modules = self.root / "modules"
        modules.mkdir()
        shutil.copy2(repo / "src/utils/workspace_evidence.py", modules / "_workspace_evidence.py")
        shutil.copy2(repo / "src/wildclawbench_grading_core/native_text.py", modules / "_native_artifact_text.py")
        workspace = self.root / "workspace"
        write_docx(workspace / "results/handoff.docx")
        code = ("import sys,json;sys.path.insert(0," + repr(str(modules)) + ");"
                "from _workspace_evidence import collect_workspace_evidence;"
                "v=collect_workspace_evidence(" + repr(str(workspace)) + ");"
                "print(json.dumps({'count':v['metadata']['selected_file_count'],'native':bool(v['metadata']['selected'][0].get('native_extraction'))}))")
        result = subprocess.run([sys.executable, "-I", "-c", code], cwd=modules, check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(result.stdout), {"count": 1, "native": True})

    def test_unreadable_declared_native_is_explicit_without_inventing_its_content(self):
        path = self.root / "results/bad.docx"
        path.parent.mkdir()
        path.write_bytes(b"invalid Office file")
        bundle = collect_workspace_evidence(str(self.root), {"required": ["results/bad.docx"]})
        self.assertEqual(bundle["metadata"]["selected_file_count"], 0)
        self.assertEqual(bundle["metadata"]["unavailable_required_native"], [{"path": "results/bad.docx", "reason": "NATIVE_TEXT_INVALID"}])
        self.assertIn("Unavailable required native evidence: results/bad.docx", bundle["text"])


if __name__ == "__main__":
    unittest.main()
