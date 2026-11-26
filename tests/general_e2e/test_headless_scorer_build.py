from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class HeadlessScorerBuildTests(unittest.TestCase):
    def test_prepare_context_is_standalone_and_does_not_persist_proxy(self):
        with tempfile.TemporaryDirectory() as temporary:
            context = Path(temporary) / 'context'
            subprocess.run(['bash', str(ROOT / 'docker/e2e-scorer/build.sh'), '--prepare-only',
                            '--context', str(context), '--http-proxy', 'http://private-proxy:8888'],
                           check=True, capture_output=True)
            manifest = json.loads((context / 'build-manifest.json').read_text())
            self.assertEqual(manifest['inputs']['WITH_OFFICE'], '1')
            self.assertEqual(manifest['inputs']['CODEX_VERSION'], '0.171.0')
            self.assertTrue((context / 'runtime-skill/bundled-components.json').is_file())
            self.assertTrue((context / 'build-prepared.sh').is_file())
            self.assertFalse(any(b'private-proxy' in path.read_bytes() for path in context.rglob('*') if path.is_file()))
            self.assertNotIn('.env', (context / '.dockerignore').read_text().splitlines()[1:])

    def test_prepared_build_checks_office_offline_and_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'build-prepared.sh').write_bytes((ROOT / 'docker/e2e-scorer/build-prepared.sh').read_bytes())
            (root / 'build-inputs.env').write_text('IMAGE_TAG=test:office\nDOCKER_CONTEXT=default\nWITH_OFFICE=1\n' +
                ''.join(key + '=test\n' for key in ('EVAL_BASE_IMAGE', 'NODE_RUNTIME_IMAGE', 'CODEX_VERSION',
                                                  'DSH_VERSION', 'NPM_REGISTRY', 'PIP_INDEX_URL')))
            docker = root / 'docker'
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
                              'case "$*" in *" run "*) exit "${FAIL_VALIDATION:-0}" ;; esac\n')
            docker.chmod(0o755)
            environment = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'], 'CALLS': str(root / 'calls')}
            subprocess.run(['bash', str(root / 'build-prepared.sh')], env=environment, check=True, capture_output=True)
            calls = (root / 'calls').read_text().splitlines()
            self.assertIn('--tag test:office-runtime', calls[0])
            self.assertIn('SCORER_BASE_IMAGE=test:office-runtime', calls[1])
            self.assertIn('--network none', calls[2])
            self.assertTrue(calls[2].endswith('--office'))
            self.assertNotIn('--volume', calls[2])
            (root / 'calls').unlink()
            result = subprocess.run(['bash', str(root / 'build-prepared.sh')],
                                    env={**environment, 'FAIL_VALIDATION': '7'}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('image inspect', (root / 'calls').read_text())
            self.assertFalse((root / 'runtime-validation.json').exists())
            self.assertFalse((root / 'image-receipt.txt').exists())

    def test_version_labels_follow_build_args(self):
        dockerfile = (ROOT / 'docker/e2e-scorer/Dockerfile').read_text()
        self.assertIn('org.astron.eval.codex.version="${CODEX_VERSION}"', dockerfile)
        self.assertIn('org.astron.eval.dsh.version="${DSH_VERSION}"', dockerfile)


if __name__ == '__main__':
    unittest.main()
