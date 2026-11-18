from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[2] / "tools/report/skills/general-e2e/report-general-e2e/scripts/selected_report.py"
SPEC = importlib.util.spec_from_file_location("selected_report_sources_tested", SCRIPT)
REPORT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = REPORT
SPEC.loader.exec_module(REPORT)


class SelectedReportSourcesTest(unittest.TestCase):
    def test_report_output_boundary_is_explicit_new_and_does_not_follow_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace=Path(temp);batch=workspace/'private'/'batch';batch.mkdir(parents=True)
            reports=workspace/'reports';reports.mkdir();target=reports/'final'
            with self.assertRaisesRegex(ValueError,'OUTPUT_UNSAFE'):
                REPORT.report_output_path(target,workspace,batch)
            self.assertEqual(REPORT.report_output_path(target,workspace,batch,reports),target.resolve())
            self.assertEqual(REPORT.report_output_path(batch/'legacy',workspace,batch),(batch/'legacy').resolve())
            target.mkdir()
            with self.assertRaisesRegex(ValueError,'OUTPUT_UNSAFE'):
                REPORT.report_output_path(target,workspace,batch,reports)
            actual=reports/'actual';actual.mkdir();link=reports/'link';link.symlink_to(actual,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'OUTPUT_UNSAFE'):
                REPORT.report_output_path(link/'new',workspace,batch,reports)
            with self.assertRaisesRegex(ValueError,'ROOT_UNSAFE'):
                REPORT.report_output_path(link/'new',workspace,batch,link)
            with self.assertRaisesRegex(ValueError,'OUTPUT_UNSAFE'):
                REPORT.report_output_path(workspace/'escape',workspace,batch,reports)
            with self.assertRaisesRegex(ValueError,'ROOT_UNSAFE'):
                REPORT.report_output_path(workspace/'new',batch,batch,reports)

    def test_explicit_report_root_requires_report_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError,'REPORT_OUTPUT_ROOT_REQUIRES_REPORT_OUTPUT'):
                REPORT.main(['--workspace-root',temp,'--batch-root',temp,'--source-index',temp+'/source.json',
                             '--task-index',temp+'/tasks.json','--report-output-root',temp])

    def test_lineage_keeps_each_package_and_binds_archive_to_its_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            REPORT.ROOT=Path(temp)
            package=Path(temp)/"package";package.mkdir()
            payload=b'{"verified":"manifest"}'
            manifest_sha=hashlib.sha256(payload).hexdigest()
            archive=Path(temp)/"return.zip"
            with zipfile.ZipFile(archive,"w") as z:z.writestr("return/package-manifest.json",payload)
            entry={"package_id":"id","target":str(package),"package_manifest_sha256":manifest_sha,
                   "archive":str(archive),"archive_sha256":hashlib.sha256(archive.read_bytes()).hexdigest()}
            manifest={"package_id":"id","sources":{"submission_sha256":"1"*64}}
            row=REPORT.source_package_lineage(entry,manifest,"u")
            self.assertEqual(row["package_id"],"id")
            self.assertEqual(row["submission_sha256"],"1"*64)
            self.assertEqual(row["archive_sha256"],entry["archive_sha256"])
            with self.assertRaisesRegex(ValueError,"PACKAGE_ID_DRIFT"):
                REPORT.source_package_lineage({**entry,"package_id":"other"},manifest,"u")
            with zipfile.ZipFile(archive,"w") as z:z.writestr("return/package-manifest.json",b"other")
            with self.assertRaisesRegex(ValueError,"ARCHIVE_SHA_DRIFT"):
                REPORT.source_package_lineage(entry,manifest,"u")
            entry["archive_sha256"]=hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,"ARCHIVE_PACKAGE_BINDING"):
                REPORT.source_package_lineage(entry,manifest,"u")

    def test_sealing_requires_a_new_report_output(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'SEAL_REQUIRES_REPORT_OUTPUT'):
                REPORT.main(['--workspace-root',temp,'--batch-root',temp,'--source-index',temp+'/source.json',
                             '--task-index',temp+'/tasks.json','--seal-output-dir',temp+'/sealed'])

    def test_explicit_data_output_root_does_not_change_source_verification_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/"source";source.mkdir()
            output = Path(temp)/"admin";output.mkdir()
            path = output/"verified.json"
            with self.assertRaisesRegex(ValueError, "DATA_OUTPUT_UNSAFE"):
                REPORT.data_output_path(path, source)
            self.assertEqual(REPORT.data_output_path(path, source, output), path.resolve())
            path.write_text("existing")
            with self.assertRaisesRegex(ValueError, "DATA_OUTPUT_UNSAFE"):
                REPORT.data_output_path(path, source, output)
            with self.assertRaisesRegex(ValueError, "DATA_OUTPUT_UNSAFE"):
                REPORT.data_output_path(Path(temp)/"escape.json", source, output)
            REPORT.ROOT = source.resolve()
            with self.assertRaisesRegex(ValueError, "PACKAGE_OUTSIDE_ROOT"):
                REPORT.verify_source_package(output, "0"*64, "unit", ["task"])
    def test_source_config_uses_frozen_unit_and_rejects_client_or_model_drift(self):
        target={"unit_id":"unit","harness":{"id":"doubaowork","version":"2.31.10"},"model":{"requested_id":"current"},"execution_mode":"automatic"}
        REPORT.verify_source_unit_config({"unit":target},target)
        for key,value in [("harness",{"id":"doubaowork","version":"other"}),("model",{"requested_id":"other"}),("execution_mode","manual"),("unit_id","other")]:
            with self.assertRaisesRegex(ValueError,"UNIT_CONFIG_DRIFT"):
                REPORT.verify_source_unit_config({"unit":{**target,key:value}},target)

    def test_partial_units_use_frozen_per_unit_scope_and_never_cartesian_padding(self):
        batch={"task_ids":["a","b","c"],"units":[{"unit_id":"original","task_ids":["a","c"]},
                {"unit_id":"recovery","task_ids":["b"]}]}
        units,scopes,active=REPORT.declared_unit_task_scopes(batch,["original","recovery"])
        self.assertEqual(active,["a","b","c"])
        self.assertEqual({(u,t) for u,tasks in scopes.items() for t in tasks},
                         {("original","a"),("original","c"),("recovery","b")})
        self.assertEqual(REPORT.declared_unit_task_scopes(batch,["recovery"])[2],["b"])
        for bad in [["outside"],["c","a"],["a","a"],[]]:
            batch["units"][0]["task_ids"]=bad
            with self.assertRaisesRegex(ValueError,"DECLARED_UNIT_TASK_SCOPE"):
                REPORT.declared_unit_task_scopes(batch,["original"])

    def test_mixed_versions_require_explicit_null_target_and_preserve_other_identity(self):
        source={"unit_id":"u","harness":{"id":"astronstudio","platform":"windows-x86_64","version":"observed"},
                "model":{"requested_id":"spark"},"execution_mode":"automatic"}
        target={**source,"harness":{**source["harness"],"version":None}}
        with self.assertRaisesRegex(ValueError,"UNIT_CONFIG_DRIFT"):
            REPORT.verify_source_unit_config({"unit":source},target)
        REPORT.verify_source_unit_config({"unit":source},target,allow_mixed_version=True)
        with self.assertRaisesRegex(ValueError,"TARGET_MUST_BE_UNKNOWN"):
            REPORT.verify_source_unit_config({"unit":source},source,allow_mixed_version=True)
        changed={**source,"harness":{**source["harness"],"platform":"other"}}
        with self.assertRaisesRegex(ValueError,"UNIT_CONFIG_DRIFT"):
            REPORT.verify_source_unit_config({"unit":changed},target,allow_mixed_version=True)

    def test_multiple_sources_require_an_explicit_package_for_each_task(self):
        sources = {"original": {"task_ids": ["a", "b"]}, "recovery": {"task_ids": ["b"]}}
        with self.assertRaisesRegex(ValueError, "SOURCE_PACKAGE_REQUIRED"):
            REPORT.select_source_package(sources, {}, "b")
        self.assertIs(REPORT.select_source_package(sources, {"source_package_id": "recovery"}, "b"), sources["recovery"])
        for choice, task, error in [("unknown", "b", "PACKAGE_UNKNOWN"), ("recovery", "a", "OUTSIDE_SOURCE_SCOPE")]:
            with self.assertRaisesRegex(ValueError, error):
                REPORT.select_source_package(sources, {"source_package_id": choice}, task)
        self.assertIs(REPORT.select_source_package({"original": sources["original"]}, {}, "a"), sources["original"])

    def test_recaptured_resources_bind_selected_record_receipt_and_manifest(self):
        for variant in ['valid','profile','record','receipt','metric']:
            with self.subTest(variant=variant),tempfile.TemporaryDirectory() as temp:
                root=Path(temp).resolve();unit=root/'unit';unit.mkdir();identity={'batch_id':'b','unit_id':'u','task_id':'task','attempt_id':'attempt'}
                prior=unit/'evidence/tasks/task/attempt/evidence-manifest.json';prior.parent.mkdir(parents=True);prior.write_text(json.dumps({'identity':identity,'artifacts':[]}))
                folder=unit/'evidence/trace-recaptures/fix/task';folder.mkdir(parents=True);metric=folder/'resource.json';metric.write_text('{}');relative=metric.relative_to(unit).as_posix();execution={'identity':identity,'dataset':{'id':'d','digest':'f'},'resource_metrics_path':relative};record=folder/'execution-record.json';record.write_text(json.dumps(execution));snapshot=root/'scoring-record.json';snapshot.write_bytes(record.read_bytes())
                def ref(path):return {'path':path.relative_to(unit).as_posix(),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':path.stat().st_size}
                manifest=folder/'evidence-manifest.json';manifest.write_text(json.dumps({'identity':identity,'collection':{'execution_record_path':record.relative_to(unit).as_posix(),'trace_utf8_redecode':{'profile':'wrong' if variant=='profile' else 'bound-qwen-native-utf8-redecode/v1','collection_receipt_path':'receipts/recapture.json'}},'artifacts':[ref(metric)]}));receipt=unit/'receipts/recapture.json';receipt.parent.mkdir();receipt.write_text(json.dumps({'stage':'collect-evidence','scope':{'batch_id':'b','unit_id':'u'},'dataset':execution['dataset'],'artifacts':[ref(record),ref(manifest)]}))
                if variant=='record':snapshot.write_text('{"changed":true}')
                elif variant=='receipt':d=json.loads(receipt.read_text());d['artifacts'][1]['sha256']='0'*64;receipt.write_text(json.dumps(d))
                elif variant=='metric':metric.write_text('{"drift":true}')
                if variant=='valid':self.assertEqual(REPORT.checked_metric_path(unit,execution,snapshot),metric)
                else:
                    with self.assertRaises(ValueError):REPORT.checked_metric_path(unit,execution,snapshot)

    def test_duplicate_or_empty_source_lists_are_rejected(self):
        for value, error in [([], "PACKAGES_INVALID"), ([{"package_id": "same"}, {"package_id": "same"}], "PACKAGE_DUPLICATE")]:
            with self.assertRaisesRegex(ValueError, error):
                REPORT.source_package_items({"packages": value})

    def test_subset_sources_still_require_sha_unit_and_ordered_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            REPORT.ROOT = Path(temp).resolve()
            root = Path(temp) / "package"
            root.mkdir()
            path = root / "package-manifest.json"
            def check(scope, unit="unit", allow_subset=True, digest=None):
                path.write_text(json.dumps({"identity": {"unit_id": unit, "task_ids": scope}, "entries": []}))
                expected = digest or hashlib.sha256(path.read_bytes()).hexdigest()
                return REPORT.verify_source_package(root, expected, "unit", ["a", "b", "c"], allow_subset=allow_subset)
            check(["b"])
            for scope in [[], ["unknown"], ["b", "b"], ["c", "a"]]:
                with self.assertRaisesRegex(ValueError, "PACKAGE_SCOPE"):
                    check(scope)
            with self.assertRaisesRegex(ValueError, "PACKAGE_SCOPE"):
                check(["b"], unit="another")
            with self.assertRaisesRegex(ValueError, "PACKAGE_SCOPE"):
                check(["b"], allow_subset=False)
            with self.assertRaisesRegex(ValueError, "MANIFEST_DRIFT"):
                check(["b"], digest="0" * 64)


if __name__ == "__main__":
    unittest.main()
