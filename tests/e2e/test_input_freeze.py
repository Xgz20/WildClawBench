import io,json,os
from pathlib import Path
from types import SimpleNamespace
import tempfile,unittest
from unittest.mock import patch

from src.e2e.preparation import prepare_batch
from src.e2e.artifacts import inventory
from src.e2e.common import read_json


class InputFreezeTests(unittest.TestCase):
    def test_failure_after_freezing_cleans_only_its_staging_and_keeps_original_error(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);repo=Path(__file__).resolve().parents[2]
            task={'task_id':'t','scene':'general','metric_profile':'general-e2e-contract-v1',
                  'dataset':{'id':'fixture','digest':'a'*64},'source':{},'bundle':{}}
            plan={'batch_id':'failed-freeze','selection':{},'units':[{'unit_id':'u','harness':'astronstudio'}],'runs':1,'execution_concurrency':1}
            def materialize(task,members,destination,prepare):
                (destination/'execution/workspace').mkdir(parents=True)
                (destination/'execution/PROMPT.md').write_text('fixture')
                (destination/'execution/workspace/input.xlsx').write_bytes(b'fixture')
                return {}
            with patch('src.e2e.protocol.resolve',return_value=(plan,[task],{},None,None)),patch('src.e2e.preparation.canonical_script'),patch('src.e2e.preparation._write_general',side_effect=materialize),patch('src.e2e.compatibility.freeze_assets',side_effect=RuntimeError('original freeze failure')):
                with self.assertRaisesRegex(RuntimeError,'original freeze failure'):
                    prepare_batch(repo,base,plan)
            self.assertFalse(list((base/'batches').iterdir()))

    def test_published_public_and_private_office_inputs_are_readonly_before_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);repo=Path(__file__).resolve().parents[2]
            task={'task_id':'frozen-office','scene':'general','metric_profile':'general-e2e-contract-v1',
                  'dataset':{'id':'fixture','digest':'a'*64},'source':{},'bundle':{'execution_contract_path':'tasks/frozen-office/execution/contract.json'}}
            payloads={'task.md':b'fixture task','execution/contract.json':json.dumps({'prompt':'inspect /tmp_workspace/input.xlsx'}).encode(),
                      'execution/exec/input.xlsx':b'public-office-bytes','private-scoring/gt/reference.xlsx':b'private-office-bytes'}
            members={f'tasks/frozen-office/{name}':SimpleNamespace(kind='file',mode=0o644,data=data) for name,data in payloads.items()}
            plan={'batch_id':'readonly-inputs','selection':{},'units':[{'unit_id':'u','harness':'astronstudio'}],'runs':1,'execution_concurrency':1}
            prepare=SimpleNamespace(map_prompt_workspace=lambda p:(p,{}),inline_public_context=lambda p,e,**kw:(p,{}),ZipEntry=lambda *args:args)
            try:
                with patch('src.e2e.protocol.resolve',return_value=(plan,[task],members,{},None)),patch('src.e2e.preparation.canonical_script',return_value=prepare),patch('src.e2e.compatibility.freeze_assets',return_value={}):
                    batch=prepare_batch(repo,base,plan)
                definition=read_json(batch/'batch.json')['tasks'][0];root=batch/definition['input_root']
                observed=[row for row in inventory(root) if row['path']!='task-definition.json']
                self.assertEqual(observed,definition['definition_inventory'])
                self.assertEqual((root/'execution/workspace/input.xlsx').read_bytes(),b'public-office-bytes')
                self.assertEqual((root/'private-scoring/gt/reference.xlsx').read_bytes(),b'private-office-bytes')
                self.assertTrue(all(not row['mode']&0o222 for row in observed))
                self.assertFalse((root/'task-definition.json').stat().st_mode&0o222)
                if os.geteuid()!=0:
                    with self.assertRaises(PermissionError):(root/'execution/workspace/input.xlsx').write_bytes(b'host metadata mutation')
                    with self.assertRaises(PermissionError):(root/'execution/workspace/.DS_Store').write_bytes(b'host metadata')
            finally:
                for path in base.rglob('*'):
                    if path.is_dir():path.chmod(0o700)
