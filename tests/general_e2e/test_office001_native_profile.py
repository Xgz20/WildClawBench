from copy import deepcopy
from pathlib import Path
import ast
import hashlib
import unittest

from eval_general_e2e.datasets.bundle import _strip_codeblock
from tests.general_e2e.frozen_sources import parse_frozen_task_source as _parse_task_source
from tests.general_e2e.test_local_scoring_runtime import RUNTIME, REPO_ROOT

NATIVE=RUNTIME.office001_native_profile


class OfficeNativeProfileTests(unittest.TestCase):
    def source(self):
        _,sections,_=_parse_task_source(next((REPO_ROOT/'tasks/general_e2e').rglob(NATIVE.TASK+'.md')))
        return _strip_codeblock(sections['Automated Checks'])

    def manifest(self):
        configuration={'runner':{'sha256':NATIVE.RUNTIME_SOURCE_SHA},
                       'java_source':{'sha256':NATIVE.JAVA_SOURCE_SHA},
                       'jar':{'sha256':RUNTIME.office001_native_profile.native_writer_runtime.JAR_SHA256}}
        marker={'profile':NATIVE.PROFILE,'contract_sha256':NATIVE.CONTRACT_SHA,'source_sha256':NATIVE.SOURCE_SHA,
                'evidence_directory':NATIVE.EVIDENCE,'configuration':configuration,
                'configuration_content_sha256':NATIVE.canonical(configuration),
                'configuration_file':{'path':'/frozen/configuration.json','sha256':'a'*64},
                'launcher':{'path':'/frozen/native-launcher','sha256':'b'*64}}
        return {'identity':{'task_id':NATIVE.TASK},'digests':{'contract_sha256':NATIVE.CONTRACT_SHA},
                'runtime':{'office001_native_profile':marker}}

    def test_legacy_source_and_all_original_numeric_functions_stay_unchanged(self):
        source=self.source()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),NATIVE.SOURCE_SHA)
        legacy={'identity':{'task_id':NATIVE.TASK}}
        self.assertEqual(RUNTIME._effective_rule_source(legacy,source),(source,None))
        fixed,receipt=RUNTIME._effective_rule_source(self.manifest(),source)
        compile(fixed,'<native-profile>','exec')
        self.assertEqual(receipt['correction_id'],NATIVE.PROFILE)
        old=ast.parse(source).body;new=ast.parse(fixed).body
        original_part=deepcopy(new[:len(old)])
        for node in original_part:
            if isinstance(node,ast.FunctionDef) and node.name=='_ge2e_original_office_grade':node.name='grade'
            if isinstance(node,ast.FunctionDef) and node.name=='_ge2e_original_office_native_probe':node.name='native_probe'
        self.assertEqual([ast.dump(n) for n in original_part],[ast.dump(n) for n in old])
        self.assertEqual(sum(isinstance(n,ast.FunctionDef) and n.name=='grade' for n in new),1)
        self.assertFalse(receipt['candidate_rewritten'])

    def test_generated_evidence_is_new_marker_only_without_contract_mutation(self):
        source=self.source();contract={'task_id':NATIVE.TASK,'automated_checks':source}
        before=deepcopy(contract)
        self.assertEqual(RUNTIME._required_generated_evidence(contract),[])
        self.assertEqual(RUNTIME._required_generated_evidence(contract,manifest=self.manifest()),[NATIVE.EVIDENCE])
        self.assertEqual(contract,before)

    def test_source_contract_and_runtime_implementation_tampering_fail_closed(self):
        source=self.source()
        for edit in [lambda m:m['digests'].update(contract_sha256='0'*64),
                     lambda m:m['runtime']['office001_native_profile'].update(source_sha256='0'*64),
                     lambda m:m['runtime']['office001_native_profile']['configuration']['runner'].update(sha256='0'*64)]:
            manifest=self.manifest();edit(manifest)
            with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._effective_rule_source(manifest,source)
        with self.assertRaises(RUNTIME.ScoringRuntimeError):RUNTIME._effective_rule_source(self.manifest(),source+'\n')

    def test_unrelated_contract_never_discovers_a_native_runtime(self):
        self.assertIsNone(NATIVE.marker({'task_id':'other','automated_checks':''},'0'*64))

    def test_cold_start_profile_pins_actual_source_and_preserves_old_profiles(self):
        actual=Path(NATIVE.native_writer_runtime.__file__).parent/'native_writer/NativeDocxEditProbe.java'
        self.assertEqual(NATIVE.sha(actual),NATIVE.JAVA_SOURCE_SHA_V3)
        self.assertNotEqual(NATIVE.JAVA_SOURCE_SHA,NATIVE.JAVA_SOURCE_SHA_V3)
        for profile,runner,java in [
            (NATIVE.PROFILE,NATIVE.RUNTIME_SOURCE_SHA,NATIVE.JAVA_SOURCE_SHA),
            (NATIVE.PROFILE_V2,NATIVE.RUNTIME_SOURCE_SHA_V2,NATIVE.JAVA_SOURCE_SHA),
            (NATIVE.PROFILE_V3,NATIVE.RUNTIME_SOURCE_SHA_V2,NATIVE.JAVA_SOURCE_SHA_V3),
        ]:
            manifest=self.manifest();frozen=manifest['runtime']['office001_native_profile']
            frozen['profile']=profile
            frozen['configuration']['runner']['sha256']=runner
            frozen['configuration']['java_source']['sha256']=java
            frozen['configuration_content_sha256']=NATIVE.canonical(frozen['configuration'])
            fixed,receipt=RUNTIME._effective_rule_source(manifest,self.source())
            self.assertEqual(receipt['correction_id'],profile)
            if profile!=NATIVE.PROFILE:
                self.assertIn('_ge2e_shutdown_valid(receipt',fixed)
            frozen['configuration']['java_source']['sha256']=(NATIVE.JAVA_SOURCE_SHA if profile==NATIVE.PROFILE_V3 else NATIVE.JAVA_SOURCE_SHA_V3)
            frozen['configuration_content_sha256']=NATIVE.canonical(frozen['configuration'])
            with self.assertRaises(RUNTIME.ScoringRuntimeError):
                RUNTIME._effective_rule_source(manifest,self.source())


if __name__=='__main__':unittest.main()
