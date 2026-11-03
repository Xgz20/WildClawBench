import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/report/skills/general-e2e/orchestrate-general-e2e/scripts'))
import native_writer_cleanup_failure as M

class NativeWriterCleanupFailureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.a=Path(self.tmp.name).resolve()
        self.rt=SimpleNamespace(_read_json=lambda p:json.loads(p.read_text()),_sha256_file=lambda p:hashlib.sha256(p.read_bytes()).hexdigest())
        self.contract={'task_id':M.TASK,'automated_checks':'fixture source'}
        self.source=patch.object(M,'SOURCE',hashlib.sha256(b'fixture source').hexdigest());self.source.start();self.addCleanup(self.source.stop)
        self.m={'dataset':copy.deepcopy(M.DATASET),'digests':{'contract_sha256':M.CONTRACT},'runtime':{'office001_native_profile':{'profile':'office001-validated-native-writer-api/v1'}}}
        self.probe={'status':'evaluator_error','java_exit_code':0,'server_exit_code':255,'timed_out':False,'startup_error':None,'cleanup_residual':[],
            'input_bytes_unchanged':True,'candidate_rewritten':False,'native_profile_archive':None,
            'native_facts':{'status':'pass','control_opened':'true','opened':'true','body_persisted':'true','phase':'native_reopen','required_tables':'10','table_edits_persisted':'10'},
            'cleanup_actions':[{'pid':123,'signal':'SIGTERM'}],'process_identities':[{'pid':123,'command_sha256':'locked','command':'office -env:UserInstallation=file:///owned'}],'artifacts':[]}
        for name in ['editable-copy.docx','native-receipt.properties','java.stderr','native-saved.docx','candidate-native.pdf','server.stderr','server.stdout','java.stdout']:
            path=(self.a/M.PROBE).parent/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(name.encode())
            self.probe['artifacts'].append({'path':name,'size':path.stat().st_size,'sha256':self.rt._sha256_file(path)})
        self.write('rule-audit.json',{'status':'failed'});self.write('rule-review/response.json',{'retained':True});self.write('judge-infrastructure-block-v1.json',{'retained':True})
    def tearDown(self):self.tmp.cleanup()
    def write(self,name,data):
        path=self.a/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))
    def persist(self):
        self.write(M.PROBE,self.probe)
        self.write('worker/result.json',{'ok':False,'result':None,'error':{'type':'RuntimeError','message':M.PREFIX+json.dumps({'automated.c5_editability':{'status':'evaluator_error','score':None,'evidence':[self.probe]}})}})
    def test_exact_failure_retained_with_all_referenced_bytes(self):
        self.persist();paths=M.evidence(self.rt,self.a,self.m,self.contract)
        self.assertEqual(len(paths),10);self.assertTrue(all(p.is_file() for p in paths))
    def test_timeout_missing_native_success_residual_and_unbound_stops_refused(self):
        original=copy.deepcopy(self.probe)
        for key,value in [('timed_out',True),('server_exit_code',1),('cleanup_residual',[{'pid':123}]),('input_bytes_unchanged',False),('cleanup_actions',[{'pid':123,'signal':'SIGKILL'}])]:
            self.probe=copy.deepcopy(original);self.probe[key]=value;self.persist()
            with self.assertRaises(ValueError):M.evidence(self.rt,self.a,self.m,self.contract)
        self.probe=copy.deepcopy(original);self.probe['native_facts']['body_persisted']='false';self.persist()
        with self.assertRaises(ValueError):M.evidence(self.rt,self.a,self.m,self.contract)
    def test_changed_dataset_or_old_evidence_refused(self):
        self.persist();self.m['dataset']['digest']='0'*64
        with self.assertRaises(ValueError):M.evidence(self.rt,self.a,self.m,self.contract)
        self.m['dataset']=copy.deepcopy(M.DATASET);((self.a/M.PROBE).parent/'native-saved.docx').write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'EVIDENCE_DRIFT'):M.evidence(self.rt,self.a,self.m,self.contract)
