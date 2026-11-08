"""Canonical report snapshots use only exact selected archives and preserve variants."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
SCRIPTS=ROOT/'tools/report/skills/general-e2e/run-general-e2e/scripts'
import sys
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('_canonical_report_batch',SCRIPTS/'materialize_canonical_report_batch.py')
MODULE=importlib.util.module_from_spec(spec);spec.loader.exec_module(MODULE)


class CanonicalReportBatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source';self.source.mkdir()
        self.target=self.root/'snapshot';self.archive=self.root/'return.zip'
        self.old=self.source/'host-variant';self.old.write_bytes(b'host modified bytes')
        for name in ['manifest.json','report-config.json']:(self.source/name).write_text('{"frozen":true}')
        (self.source/'.general-e2e').mkdir();(self.source/'.general-e2e/run-general-e2e-import-index.json').write_text('{"selected":true}')
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr('return/package-manifest.json',json.dumps({'package_id':'pkg','identity':{'unit_id':'u'}}))
        self.sha=hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.index={'units':{'u':{'selected_package_id':'pkg','imports':[{'package_id':'pkg','archive_sha256':self.sha,'target':'host-variant'}]}}}
        self.manifest={'units':[{'unit_id':'u'}]}

    def test_exact_source_copy_and_selected_import_are_bound_without_touching_host(self):
        with (patch.object(MODULE.run,'manifest_for',return_value=(None,self.manifest)),
              patch.object(MODULE.run,'load_import_index',return_value=self.index),
              patch.object(MODULE.run,'import_return',return_value={'target':'canonical target'}) as imported,
              patch.object(MODULE.run,'select_import',return_value={'selected_package_id':'pkg'})):
            result=MODULE.materialize(self.source,self.target,[self.archive])
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(self.old.read_bytes(),b'host modified bytes')
        self.assertEqual((self.target/'manifest.json').read_bytes(),(self.source/'manifest.json').read_bytes())
        self.assertEqual(result['imports'][0]['archive_sha256'],self.sha)
        self.assertFalse(result['original_imports_changed'])
        imported.assert_called_once()

    def test_unknown_archive_or_existing_snapshot_is_rejected_before_import(self):
        self.index['units']['u']['imports'][0]['archive_sha256']='0'*64
        with (patch.object(MODULE.run,'manifest_for',return_value=(None,self.manifest)),
              patch.object(MODULE.run,'load_import_index',return_value=self.index),
              patch.object(MODULE.run,'import_return') as imported):
            with self.assertRaisesRegex(ValueError,'NOT_SELECTED'):
                MODULE.materialize(self.source,self.target,[self.archive])
            imported.assert_not_called();self.assertFalse(self.target.exists())
        self.target.mkdir()
        with self.assertRaisesRegex(ValueError,'TARGET_EXISTS'):
            MODULE.materialize(self.source,self.target,[self.archive])


if __name__=='__main__':unittest.main()
