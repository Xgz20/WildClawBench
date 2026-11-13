"""Real XLSX round-trip regression for model captions containing @."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

from tests.general_e2e.test_general_report_views import CASES


class ReportReferenceExportTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("GENERAL_E2E_NODE_MODULES"), "artifact-tool runtime not configured")
    def test_exported_references_resolve_after_reimport_without_changing_captions(self):
        labels = {"one": "Model@Client", "two": "Model_Client", "three": "Spark-X2.6@AStudio 3.5.5"}
        units = [{"unit_id": key} for key in labels]
        names = CASES.detail_sheet_names(units, labels)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "node_modules").symlink_to(Path(os.environ["GENERAL_E2E_NODE_MODULES"]), target_is_directory=True)
            (root / "input.json").write_text(json.dumps({"labels": labels, "names": names}))
            (root / "roundtrip.mjs").write_text('''
import fs from "node:fs/promises";
import {FileBlob, SpreadsheetFile, Workbook} from "@oai/artifact-tool";
const {labels,names}=JSON.parse(await fs.readFile("input.json","utf8"));
const wb=Workbook.create(), ids=Object.keys(labels);
for(let i=0;i<ids.length;i++) wb.worksheets.add(names[ids[i]]).getRange("A1:A2").values=[[i+1],[i+2]];
const summary=wb.worksheets.add("Summary");
for(let i=0;i<ids.length;i++){
 summary.getRange(`A${i+1}`).values=[[labels[ids[i]]]];
 summary.getRange(`B${i+1}`).formulas=[[`=SUM('${names[ids[i]].replaceAll("'","''")}'!A1:A2)`]];
}
wb.recalculate();
await (await SpreadsheetFile.exportXlsx(wb)).save("report.xlsx");
const restored=await SpreadsheetFile.importXlsx(await FileBlob.load("report.xlsx"));
restored.recalculate();
const actual=restored.worksheets.getItem("Summary").getRange("A1:B3").values;
if(actual.some((r,i)=>r[0]!==labels[ids[i]]||r[1]!==2*i+3))throw new Error(JSON.stringify(actual));
console.log(JSON.stringify(actual));
''')
            proc = subprocess.run([os.environ.get("GENERAL_E2E_NODE", "node"), str(root / "roundtrip.mjs")],
                                  cwd=root, capture_output=True, text=True, timeout=90)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            with zipfile.ZipFile(root / "report.xlsx") as archive:
                ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                book = ET.fromstring(archive.read("xl/workbook.xml"))
                exported_names = {s.attrib["name"] for s in book.find("s:sheets", ns)}
                self.assertTrue(set(names.values()) <= exported_names)
                formulas = [node.text for member in archive.namelist() if member.startswith("xl/worksheets/")
                            and member.endswith(".xml") for node in ET.fromstring(archive.read(member)).findall(".//s:f", ns)]
                self.assertEqual(len(formulas), 3)
                for name in names.values():
                    self.assertIn(f"SUM('{name}'!A1:A2)", formulas)


if __name__ == "__main__":
    unittest.main()
