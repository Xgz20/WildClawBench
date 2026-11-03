import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from tests.general_e2e.test_source_office_metadata import office

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT/'tools/report/skills/general-e2e/collect-general-e2e/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('trace_office_recovery', SCRIPTS/'recover_trace_office_copies.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

class TraceOfficeRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name).resolve()
        self.unit = self.root/'unit'; self.o = self.unit/'score/orchestration'; self.o.mkdir(parents=True)
        self.original = office(); self.variant = office(marker=True)
        self.ref = {'path':'bindings/01-original.bin', 'sha256':M.sha(self.original), 'size':len(self.original)}
        self.formal = self.unit/'evidence/task/trace'; self.scoring = self.o/'attempt/trace'
        for root in (self.formal, self.scoring):
            (root/'bindings').mkdir(parents=True); (root/self.ref['path']).write_bytes(self.variant)
        manifest = {'tasks':[{'task_id':'task','workspace':{'path':'execution/tasks/task/workspace','entries':[{'kind':'file','path':'input.xlsx','sha256':self.ref['sha256'],'size':self.ref['size']}]}}]}
        self.manifest = json.dumps(manifest).encode(); (self.unit/'manifest.json').write_bytes(self.manifest)
        self.archive = self.root/'execution.zip'
        with zipfile.ZipFile(self.archive,'w') as z:
            z.writestr('unit/manifest.json',self.manifest)
            z.writestr('unit/execution/tasks/task/workspace/input.xlsx',self.original)
        (self.unit/'.general-e2e').mkdir(); (self.unit/'.general-e2e/round-unit.json').write_text(json.dumps({'execution_sha256':M.sha(self.archive.read_bytes())}))
        execution = json.dumps({'evidence':{'trace_index_path':'evidence/task/trace/trace-index.json'}}).encode()
        (self.o/'execution.json').write_bytes(execution)
        (self.formal/'trace-index.json').write_text(json.dumps({'binding_evidence':[self.ref]}))
        bundle = json.dumps({'artifacts':[self.ref]}).encode(); (self.scoring/'bundle-manifest.json').write_bytes(bundle)
        attempt = json.dumps({'trace_bundle':{'path':'trace/bundle-manifest.json','sha256':M.sha(bundle)}}).encode()
        (self.o/'attempt/attempt-manifest.json').write_bytes(attempt)
        self.state = {'sources':{'unit_manifest_sha256':M.sha(self.manifest)},'tasks':[{'task_id':'task','phase':'RULES_READY','attempt_path':'attempt','attempt_manifest_sha256':M.sha(attempt),'execution_record_path':'execution.json','execution_record_sha256':M.sha(execution)}]}
        self.statepath = self.o/'orchestration-state.json'; self.save_state()
        self.out = self.unit/'evidence/trace-office-recoveries/repair'
    def save_state(self): self.statepath.write_text(json.dumps(self.state))
    def tearDown(self):
        if hasattr(os,'chflags'):
            for path in self.root.rglob('*'):
                if path.is_file() and not path.is_symlink(): os.chflags(path,0)
        self.tmp.cleanup()
    def recover(self): return M.recover(self.unit,self.o,self.archive,self.out)
    def test_exact_canonical_recovery_preserves_variants_manifests_and_state(self):
        before = self.statepath.read_bytes(); result = self.recover()
        self.assertEqual(result['status'],'PASS'); self.assertEqual(len(result['copies']),2)
        self.assertEqual(before,self.statepath.read_bytes()); self.assertEqual(self.manifest,(self.unit/'manifest.json').read_bytes())
        for root in (self.formal,self.scoring):
            self.assertEqual((root/self.ref['path']).read_bytes(),self.original)
            if hasattr(os,'chflags'): self.assertTrue((root/self.ref['path']).stat().st_flags & 2)
        for item in result['copies']: self.assertEqual(Path(item['variant']).read_bytes(),self.variant)
        with self.assertRaisesRegex(ValueError,'output exists'): self.recover()
    def test_business_changes_refused_without_mutation(self):
        bad = office(marker=True,business='changed'); (self.scoring/self.ref['path']).write_bytes(bad)
        with self.assertRaisesRegex(ValueError,'business Office'): self.recover()
        self.assertEqual((self.scoring/self.ref['path']).read_bytes(),bad); self.assertFalse(self.out.exists())
    def test_judged_or_started_task_refused(self):
        for field,value in [('phase','THREAD_RUNNING'),('thread',{'id':'judge'}),('project',{'id':'project'}),('score',{'score':0.5})]:
            old = dict(self.state['tasks'][0]); self.state['tasks'][0][field]=value; self.save_state()
            with self.assertRaisesRegex(ValueError,'already started'): self.recover()
            self.assertFalse(self.out.exists()); self.state['tasks'][0]=old
    def test_zip_and_reference_drift_refused(self):
        with self.archive.open('ab') as f: f.write(b'drift')
        with self.assertRaisesRegex(ValueError,'ZIP drift'): self.recover()
        self.assertFalse(self.out.exists())
    def test_trace_copier_seals_opaque_bin_and_preserves_bytes(self):
        path=ROOT/'tools/report/skills/general-e2e/score-general-e2e/scripts/trace_handoff.py'
        spec=importlib.util.spec_from_file_location('trace_seal',path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        source=self.root/'original.bin'; source.write_bytes(self.original)
        target=self.root/'copy.bin'; module.copy_file(str(source),str(target))
        self.assertEqual(target.read_bytes(),self.original)
        if hasattr(os,'chflags'):
            self.assertTrue(target.stat().st_flags & 2)
            with self.assertRaises(PermissionError): target.write_bytes(b'drift')
