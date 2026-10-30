import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[2]/'tools/report/skills/general-e2e/score-general-e2e/scripts/native_writer_runtime.py'
spec=importlib.util.spec_from_file_location('native_writer_runtime_test',SOURCE)
NATIVE=importlib.util.module_from_spec(spec);spec.loader.exec_module(NATIVE)


class NativeWriterRuntimeTests(unittest.TestCase):
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
