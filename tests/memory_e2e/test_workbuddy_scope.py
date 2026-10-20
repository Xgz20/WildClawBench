import copy
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from eval_memory_e2e.workbuddy_scope import current_native_uid, minimal_model_config, APP
from eval_memory_e2e.io import MemoryEvaluationError
from eval_memory_e2e.io import publish,sha
from eval_memory_e2e.workbuddy_scope import load,freeze,bind_batch


class WorkBuddyScopeTests(unittest.TestCase):
    def unit(self,root):
        import eval_memory_e2e.workbuddy_scope as mod
        for name in ['app-home','tmp','candidate','app-home/admission-probe']:(root/name).mkdir(parents=True,exist_ok=True)
        spec={'contract':mod.CONTRACT,'root':str(root),'app_home':str(root/'app-home'),'temp':str(root/'tmp'),
              'candidate':str(root/'candidate'),'os_home':'/Users/SYNTHETIC','installation':{'fixture':True},'sources':{},
              'scope_helper_sha256':sha(Path(mod.__file__).read_bytes()),'unit_id':'synthetic-unit','case_id':'MEM-cleanup-001',
              'repetition':2,'account_fingerprint':'synthetic-account'}
        publish(root/'scope.json',spec)
        for name in ['gateway.json','main-spawn-spec.json','backend.sb','center.sb','desktop-bootstrap-ready.json',
                     'model-selection-prepared.json','app-home/admission-probe/result.json','runtime-observation.json','app-home/models.json']:
            publish(root/name,{})
        return spec

    def test_frozen_unit_cannot_change_model_file_case_or_batch_root(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve()/'unit';root.mkdir();self.unit(root)
            with patch('eval_memory_e2e.workbuddy_scope.machine_paths',return_value={'debug':root.parent,'home':Path('/Users/SYNTHETIC')}), \
                 patch('eval_memory_e2e.workbuddy_scope.installation_witness',return_value={'fixture':True}):
                frozen=freeze(root/'scope.json')
                profile={'memory_protocol':{'formal_scoring_allowed':False}}
                self.assertEqual(bind_batch(profile,root,frozen,['MEM-cleanup-001'],1)['repetition'],2)
                for batch,cases,repeats in [(root/'other',['MEM-cleanup-001'],1),(root,['OTHER'],1),(root,['MEM-cleanup-001'],2)]:
                    with self.assertRaises(MemoryEvaluationError):bind_batch(profile,batch,frozen,cases,repeats)
                (root/'app-home/models.json').write_text('{"changed":true}')
                with self.assertRaises(MemoryEvaluationError):load(root/'scope.json',frozen)

    def test_precreated_unit_batch_is_single_use_and_keeps_the_explicit_repetition(self):
        from eval_memory_e2e.batch import prepare,default_profiles
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw).resolve()/'unit';root.mkdir();self.unit(root)
            with patch('eval_memory_e2e.workbuddy_scope.machine_paths',return_value={'debug':root.parent,'home':Path('/Users/SYNTHETIC')}), \
                 patch('eval_memory_e2e.workbuddy_scope.installation_witness',return_value={'fixture':True}):
                profile=default_profiles()['WorkBuddy'];profile.update(workbuddy_scope=freeze(root/'scope.json'),memory_protocol={'formal_scoring_allowed':False})
                kwargs=dict(batch_id='unit-batch',seed='synthetic',harnesses=['WorkBuddy'],profiles={'WorkBuddy':profile},
                  dataset_path=Path(__file__).resolve().parents[2]/'tasks/memory-e2e/canaries/scoped-forgetting-v3.1.json')
                prepare(root,**kwargs)
                import json
                manifest=json.loads((root/'manifest.json').read_text());self.assertEqual(manifest['first_repetition'],2)
                self.assertEqual({e['run'] for e in manifest['episodes']},{2})
                with self.assertRaises(MemoryEvaluationError):prepare(root,**kwargs)

    def test_only_the_requested_provider_is_imported_without_other_settings(self):
        wanted = {'id': 'xopglm52', 'name': 'xopglm52', 'url': 'https://synthetic.invalid/v1/chat/completions',
                  'apiKey': 'SYNTHETIC-NOT-A-CREDENTIAL', 'supportsToolCall': True,
                  'reasoning': {'defaultEffort': 'high', 'supportedEfforts': ['high'], 'canDisableThinking': True},
                  'supportsReasoning': True, 'useCustomProtocol': True}
        source = [wanted, {'id': 'another-provider', 'name': 'not imported'}]
        before = copy.deepcopy(source)
        self.assertEqual(minimal_model_config(source), [wanted])
        self.assertEqual(source, before)

    def test_unknown_model_instruction_duplicate_or_missing_auth_is_rejected(self):
        base = {'id': 'xopglm52', 'name': 'xopglm52', 'url': 'https://synthetic.invalid/v1',
                'apiKey': 'SYNTHETIC-NOT-A-CREDENTIAL', 'supportsToolCall': True}
        cases = [[dict(base, systemPrompt='must not be imported')], [base, base], [dict(base, apiKey='')],
                 [dict(base, apiKey='${SYNTHETIC_ENV}')], [dict(base, reasoning={'instructions': 'must not be imported'})]]
        for source in cases:
            with self.subTest(source_keys=[list(x) for x in source]):
                with self.assertRaises(MemoryEvaluationError):
                    minimal_model_config(source)

    def test_native_account_metadata_requires_the_exact_ordinary_home_argument(self):
        binary = str(APP / 'Contents/Resources/app.asar.unpacked/cli/vendor/sandbox/5.8.6/sandbox-cli')
        ordinary = Path('/Users/SYNTHETIC/.workbuddy')
        rows = '\n'.join([binary + ' --uid correct --app_home ' + str(ordinary),
                          binary + ' --uid private --app_home ' + str(ordinary) + '-another-unit'])
        with patch('eval_memory_e2e.workbuddy_scope.machine_paths', return_value={'workbuddy': ordinary}), \
                patch('eval_memory_e2e.workbuddy_scope.subprocess.check_output', return_value=rows):
            self.assertEqual(current_native_uid(), 'correct')
        with patch('eval_memory_e2e.workbuddy_scope.machine_paths', return_value={'workbuddy': ordinary}), \
                patch('eval_memory_e2e.workbuddy_scope.subprocess.check_output', return_value=rows.splitlines()[1]):
            self.assertIsNone(current_native_uid(optional=True))
            with self.assertRaises(MemoryEvaluationError):
                current_native_uid()
