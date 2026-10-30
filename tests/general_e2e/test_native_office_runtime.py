from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[2] / 'tools/report/skills/general-e2e/score-general-e2e/scripts/configure_native_office.py'
spec = importlib.util.spec_from_file_location('native_office_runtime_test', SOURCE)
NATIVE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(NATIVE)


class NativeOfficeRuntimeTest(unittest.TestCase):
    def fixture(self, root):
        runtime = root/'runtime with space';(runtime/'bin').mkdir(parents=True)
        python = runtime/'bin/python';python.symlink_to(sys.executable)
        font = root/'font directory';font.mkdir()
        binary = root/'native app';output = root/'observations';output.mkdir()
        code = '''import json,os,sys,uuid,xml.etree.ElementTree as ET
from pathlib import Path
if '--version' in sys.argv:
 print('Synthetic Office 1');raise SystemExit(0)
config=Path(os.environ['FONTCONFIG_FILE']);tree=ET.parse(config)
cache=Path(tree.findtext('cachedir'));(cache/'probe').write_text('writable')
record={'args':sys.argv[1:],'env_keys':sorted(os.environ),'config':str(config),'cache':str(cache),'fonts':[n.text for n in tree.findall('dir')]}
(Path(OUTPUT)/(uuid.uuid4().hex+'.json')).write_text(json.dumps(record))
'''.replace('OUTPUT', repr(str(output)))
        binary.write_text('#!/bin/sh\nexec '+shlex.quote(sys.executable)+' -I -c '+shlex.quote(code)+' "$@"\n')
        binary.chmod(0o755)
        with patch.object(NATIVE.sys,'platform','darwin'):
            result=NATIVE.configure(runtime_python=python,binary=binary,support_root=runtime/'native support',font_directories=[font])
        return runtime, binary, output, result

    def test_sanitized_path_and_concurrent_profiles_are_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);runtime,binary,output,result=self.fixture(root)
            self.assertEqual(result['status'],'CONFIGURED_REAL_RENDER_SMOKE_REQUIRED')
            environment={'PATH':str(runtime/'bin'),'PYTHONUTF8':'1'}
            def run(arguments):
                return subprocess.run([str(runtime/'bin/soffice'),*arguments],env=environment,capture_output=True,text=True)
            explicit='-env:UserInstallation=file:///explicit-profile'
            with ThreadPoolExecutor(max_workers=2) as pool:
                jobs=[pool.submit(run,[]),pool.submit(run,[explicit])]
                self.assertEqual([j.result().returncode for j in jobs],[0,0])
            records=[json.loads(p.read_text()) for p in output.glob('*.json')]
            self.assertEqual(len(records),2)
            self.assertEqual(len({r['cache'] for r in records}),2)
            self.assertTrue(any(explicit in r['args'] for r in records))
            self.assertTrue(all(len([a for a in r['args'] if a.startswith('-env:UserInstallation=')])==1 for r in records))
            self.assertTrue(all('HOME' not in r['env_keys'] for r in records))
            self.assertTrue(all(r['fonts']==[str((root/'font directory').resolve())] for r in records))
            self.assertTrue(all(not Path(r['cache']).exists() and not Path(r['config']).exists() for r in records))
            self.assertEqual(environment,{'PATH':str(runtime/'bin'),'PYTHONUTF8':'1'})

    def test_binary_drift_fails_before_native_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);runtime,binary,output,_=self.fixture(root)
            binary.write_text(binary.read_text()+'\n# drift\n')
            run=subprocess.run([str(runtime/'bin/soffice')],env={'PATH':str(runtime/'bin')},capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertIn('NATIVE_OFFICE_BINARY_DRIFT',run.stderr)
            self.assertEqual(list(output.iterdir()),[])

    def test_existing_launcher_or_support_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);runtime,binary,output,_=self.fixture(root)
            original=(runtime/'bin/soffice').read_bytes()
            with patch.object(NATIVE.sys,'platform','darwin'),self.assertRaisesRegex(ValueError,'DESTINATION_EXISTS'):
                NATIVE.configure(runtime_python=runtime/'bin/python',binary=binary,support_root=runtime/'second support',font_directories=[root/'font directory'])
            self.assertEqual((runtime/'bin/soffice').read_bytes(),original)
            self.assertFalse((runtime/'second support').exists())


if __name__=='__main__':
    unittest.main()
