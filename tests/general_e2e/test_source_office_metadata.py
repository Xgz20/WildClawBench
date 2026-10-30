from io import BytesIO
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SCRIPT=Path(__file__).resolve().parents[2]/"tools/report/skills/general-e2e/collect-general-e2e/scripts/source_office_metadata.py"
spec=importlib.util.spec_from_file_location("source_office_metadata_test",SCRIPT)
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)

def office(marker=False,business="original",owner=None,external=False):
    props=[]
    if marker:props.append('<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" name="CWM'+'a'*32+'"><v:lpwstr>opaque</v:lpwstr></property>')
    if owner:props.append('<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="3" name="Owner"><v:lpwstr>'+owner+'</v:lpwstr></property>')
    custom_type=f'<Override PartName="/docProps/custom.xml" ContentType="{M.CUSTOM_TYPE}"/>' if props else ""
    custom_rel=f'<Relationship Id="custom" Type="{M.CUSTOM_REL}" Target="docProps/custom.xml"/>' if props else ""
    extra='<Relationship Id="external" Type="unrelated" Target="https://example.invalid/" TargetMode="External"/>' if external else ""
    out=BytesIO()
    with zipfile.ZipFile(out,"w") as z:
        z.writestr("xl/workbook.xml",business)
        z.writestr("[Content_Types].xml",f'<Types xmlns="{M.CT}"><Default Extension="xml" ContentType="application/xml"/>{custom_type}</Types>')
        z.writestr("_rels/.rels",f'<Relationships xmlns="{M.REL}"><Relationship Id="main" Type="document" Target="xl/workbook.xml"/>{custom_rel}{extra}</Relationships>')
        if props:z.writestr("docProps/custom.xml",f'<Properties xmlns="{M.CP}" xmlns:v="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'+"".join(props)+"</Properties>")
    return out.getvalue()

class SourceOfficeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.unit=Path(self.temp.name).resolve();self.source=self.unit/"execution/tasks/task/workspace"
        self.base=self.unit/"evidence/tasks/task/attempt";self.canonical=self.base/"candidate/workspace"
        self.source.mkdir(parents=True);self.canonical.mkdir(parents=True)
        for root in [self.source,self.canonical]:
            (root/"report.xlsx").write_bytes(office());(root/"data.csv").write_text("original data")
        self.identity={"batch_id":"batch","unit_id":"unit","task_id":"task","attempt_id":"attempt"}
        self.artifact={"identity":self.identity,"expected_sha256":M.tree_hash(M.inventory(self.canonical)),
            "candidate":{"path":self.canonical.relative_to(self.unit).as_posix()},
            "source_workspace":{"path":self.source.relative_to(self.unit).as_posix()},
            "runtime_directory_policy":{"ignored_directories":[],"forbidden_directories":[]}}
        files=[self.base/"candidate/candidate-artifact.json",self.base/"execution-record.json",self.base/"evidence-manifest.json"]
        values=[self.artifact,{"identity":self.identity,"phase":"COMPLETED","session":{"cwd":str(self.source)}},{"artifacts":[]}]
        artifacts=[]
        for path,value in zip(files,values):
            path.write_text(json.dumps(value));data=path.read_bytes()
            artifacts.append({"path":path.relative_to(self.unit).as_posix(),"sha256":M.sha(data),"size":len(data)})
        (self.unit/"receipts").mkdir();self.receipt=self.unit/"receipts/collect-evidence-receipt.json"
        self.receipt.write_text(json.dumps({"tasks":[{"task_id":"task","attempt_id":"attempt"}],"artifacts":artifacts}))
        self.output=self.unit/"evidence/source-office-metadata-variances/task/one"

    def prepare(self):
        (self.source/"report.xlsx").write_bytes(office(marker=True))
        with patch.object(M.time,"sleep"):return Path(M.prepare(self.unit,"task",self.output)["supplement"])

    def test_explicit_profile_preserves_original_receipts_and_frozen_candidate(self):
        before=self.receipt.read_bytes();canonical=(self.canonical/"report.xlsx").read_bytes()
        proof=self.prepare();result=M.verify(self.unit,"task",proof)
        self.assertTrue(result["valid"]);self.assertFalse(result["raw_source_matches_original"])
        self.assertEqual(result["canonical_sha256"],self.artifact["expected_sha256"])
        self.assertNotEqual(result["sha256"],result["canonical_sha256"])
        self.assertEqual(before,self.receipt.read_bytes());self.assertEqual(canonical,(self.canonical/"report.xlsx").read_bytes())

    def test_business_and_non_office_changes_are_not_admitted(self):
        for kind in ["business","csv","new-file","removed"]:
            with self.subTest(kind=kind):
                (self.source/"report.xlsx").write_bytes(office(marker=True,business="changed" if kind=="business" else "original"))
                if kind=="csv":(self.source/"data.csv").write_text("changed")
                elif kind=="new-file":(self.source/"extra.txt").write_text("new")
                elif kind=="removed":(self.source/"data.csv").unlink()
                with self.assertRaises(ValueError):M.compare(self.unit,"task")
                (self.source/"data.csv").write_text("original data")
                (self.source/"extra.txt").unlink(missing_ok=True)

    def test_other_custom_fields_and_relationships_are_not_metadata_exceptions(self):
        for before,after in [(office(owner="A"),office(marker=True,owner="B")),(office(),office(marker=True,external=True))]:
            with self.subTest(after=M.sha(after)),self.assertRaisesRegex(ValueError,"unrelated Office metadata"):
                M.office_delta(before,after)

    def test_stale_source_and_variant_archive_tampering_are_rejected(self):
        proof=self.prepare();archive=proof.parent/"variants.zip";raw=archive.read_bytes()
        archive.write_bytes(raw+b"tampered")
        with self.assertRaisesRegex(ValueError,"archive digest"):M.verify(self.unit,"task",proof)
        archive.write_bytes(raw);(self.source/"data.csv").write_text("changed after proof")
        with self.assertRaisesRegex(ValueError,"non-Office"):M.verify(self.unit,"task",proof)

    def test_changed_canonical_or_original_receipt_is_never_repaired_by_this_profile(self):
        proof=self.prepare();(self.canonical/"report.xlsx").write_bytes(office(marker=True))
        with self.assertRaisesRegex(ValueError,"canonical candidate drift"):M.verify(self.unit,"task",proof)
        (self.canonical/"report.xlsx").write_bytes(office());self.receipt.write_bytes(self.receipt.read_bytes()+b" ")
        with self.assertRaisesRegex(ValueError,"bindings"):M.verify(self.unit,"task",proof)

    def test_unknown_marker_and_duplicate_zip_members_fail_closed(self):
        with self.assertRaises((ValueError,KeyError)):M.office_delta(office(),office(owner="Unknown"))
        raw=BytesIO(office(marker=True))
        with zipfile.ZipFile(raw,"a") as z:z.writestr("xl/workbook.xml","duplicate")
        with self.assertRaisesRegex(ValueError,"duplicate ZIP"):M.office_delta(office(),raw.getvalue())

if __name__=="__main__":unittest.main()
