import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

SOURCE=Path(__file__).resolve().parents[2]/'tools/report/skills/general-e2e/score-general-e2e/scripts/native_writer_runtime.py'
spec=importlib.util.spec_from_file_location('native_writer_runtime_test',SOURCE)
NATIVE=importlib.util.module_from_spec(spec);spec.loader.exec_module(NATIVE)


class NativeWriterRuntimeTests(unittest.TestCase):
    def test_only_proven_post_completion_owned_sigterm_can_accept_255(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);receipt=root/'native-receipt.properties';saved=root/'native-saved.docx';pdf=root/'candidate-native.pdf';source=root/'input.docx'
            source.write_bytes(b'original');saved.write_bytes(b'native saved');pdf.write_bytes(b'native PDF')
            facts={'status':'pass','control_opened':'true','opened':'true','phase':'native_reopen','body_persisted':'true','required_tables':'10','table_edits_persisted':'10'}
            receipt.write_text(''.join(k+'='+v+'\n' for k,v in facts.items()))
            inputs=[{'path':str(source),'sha256':NATIVE.sha(source)}]
            proof=NATIVE.completed_receipt_before_cleanup(receipt,Mock(poll=lambda:0),inputs,saved,pdf)
            native={'pid':123};actions=[{'pid':123,'signal':'SIGTERM'}]
            self.assertTrue(NATIVE.verified_post_completion_stop(proof,facts,receipt,actions,native,255))
            for completion,action,code in [(None,actions,255),(proof,[],255),(proof,[{'pid':124,'signal':'SIGTERM'}],255),(proof,[{'pid':123,'signal':'SIGKILL'}],255),(proof,actions,1)]:
                self.assertFalse(NATIVE.verified_post_completion_stop(completion,facts,receipt,action,native,code))
            self.assertIsNone(NATIVE.completed_receipt_before_cleanup(receipt,Mock(poll=lambda:None),inputs,saved,pdf))
            source.write_bytes(b'changed')
            self.assertIsNone(NATIVE.completed_receipt_before_cleanup(receipt,Mock(poll=lambda:0),inputs,saved,pdf))

    def test_new_profile_replays_file_hashes_and_keeps_v1_bridge(self):
        import sys
        sys.path.insert(0,str(SOURCE.parent))
        import office001_native_profile as profile
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ['native-receipt.properties','native-saved.docx','candidate-native.pdf']:(root/name).write_bytes(name.encode())
            proof={'profile':'bound-native-post-completion-cleanup/v1','receipt_sha256':NATIVE.sha(root/'native-receipt.properties'),'saved_sha256':NATIVE.sha(root/'native-saved.docx'),'pdf_sha256':NATIVE.sha(root/'candidate-native.pdf')}
            result={'server_exit_code':255,'post_completion_cleanup':proof,'timed_out':False,'startup_error':None,'cleanup_residual':[],'java_exit_code':0,'input_bytes_unchanged':True,
                'native_facts':{'status':'pass','control_opened':'true','opened':'true','phase':'native_reopen','body_persisted':'true','required_tables':'2','table_edits_persisted':'2'},
                'cleanup_actions':[{'pid':123,'signal':'SIGTERM'}],'process_identities':[{'pid':123,'command_sha256':'locked','command':'office -env:UserInstallation=file:///own/profile'}]}
            self.assertTrue(profile.shutdown_valid(result,root))
            (root/'native-saved.docx').write_bytes(b'changed');self.assertFalse(profile.shutdown_valid(result,root))
            self.assertIn("receipt.get('server_exit_code')!=0",profile.BRIDGE)
            self.assertIn('_ge2e_shutdown_valid(receipt',profile.BRIDGE_V2)

    def test_native_properties_preserve_escapes_and_unicode(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'receipt.properties'
            path.write_text('# native\nstatus=pass\nerror=type\\: a\\=b\\nnext\ntext=\\u4e2d\\u6587\n',encoding='utf-8')
            self.assertEqual(NATIVE.properties(path),{'status':'pass','error':'type: a=b\nnext','text':'中文'})

    def test_pid_reuse_never_receives_a_signal(self):
        expected={'pid':123,'started_at':'old','command_sha256':'a','command':'owned'}
        with patch.object(NATIVE,'identity',return_value={**expected,'started_at':'new'}),patch.object(NATIVE.os,'kill') as kill:
            actions=[];NATIVE.stop_bound(expected,actions)
        kill.assert_not_called();self.assertEqual(actions,[])

    def test_unapproved_caller_source_fails_before_any_native_launch(self):
        config={'schema_version':NATIVE.SCHEMA,'runner':{'sha256':'0'*64}}
        with patch.object(NATIVE.sys,'platform','darwin'),self.assertRaisesRegex(ValueError,'CALLER_IMPLEMENTATION_DRIFT'):
            NATIVE.validate_configuration(config)

    def test_existing_runtime_marker_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'bin').mkdir();python=root/'bin/python';python.write_text('synthetic')
            marker=root/'general-e2e-native-writer.json';marker.write_text('preserve')
            with patch.object(NATIVE.sys,'platform','darwin'),self.assertRaisesRegex(ValueError,'DESTINATION_EXISTS'):
                NATIVE.configure(runtime_python=python,jdk_home=root,uno_jar=root/'missing',office_configuration=root/'missing')
            self.assertEqual(marker.read_text(),'preserve');self.assertFalse((root/'native-writer-v1').exists())

    def test_environment_does_not_inherit_java_injection_or_credentials(self):
        with patch.dict(os.environ,{'JAVA_TOOL_OPTIONS':'-javaagent:untrusted','AWS_ACCESS_KEY_ID':'secret','HOME':'untrusted'}):
            env=NATIVE.environment(Path('/runtime/bin/python'))
        self.assertEqual(env['PATH'],'/runtime/bin')
        self.assertNotIn('JAVA_TOOL_OPTIONS',env);self.assertNotIn('AWS_ACCESS_KEY_ID',env);self.assertNotIn('HOME',env)


if __name__=='__main__':unittest.main()
