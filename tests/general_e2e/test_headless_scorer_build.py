from __future__ import annotations

import json
import os
import runpy
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class HeadlessScorerBuildTests(unittest.TestCase):
    def test_image_validation_requires_a_real_browser_directory(self):
        validate = runpy.run_path(str(ROOT / 'docker/e2e-scorer/validate_runtime.py'))['browser_directory']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);real = root / 'real';real.mkdir()
            alias = root / 'alias';alias.symlink_to(real, target_is_directory=True)
            file = root / 'file';file.write_text('not a browser directory')
            with patch.dict(os.environ, {'PLAYWRIGHT_BROWSERS_PATH': str(real)}):
                self.assertEqual(validate(), str(real.resolve()))
            for value in (str(alias), str(file), str(root / 'missing'), 'relative'):
                with self.subTest(value=value), patch.dict(os.environ, {'PLAYWRIGHT_BROWSERS_PATH': value}), \
                     self.assertRaisesRegex(RuntimeError, 'SCORER_BROWSER_DIRECTORY_INVALID'):
                    validate()

    def test_prepare_context_is_standalone_and_does_not_persist_proxy(self):
        with tempfile.TemporaryDirectory() as temporary:
            context = Path(temporary) / 'context'
            subprocess.run(['bash', str(ROOT / 'docker/e2e-scorer/build.sh'), '--prepare-only',
                            '--context', str(context), '--http-proxy', 'http://private-proxy:8888'],
                           check=True, capture_output=True)
            manifest = json.loads((context / 'build-manifest.json').read_text())
            self.assertEqual(manifest['inputs']['WITH_OFFICE'], '1')
            self.assertEqual(manifest['inputs']['CODEX_VERSION'], '0.171.0')
            self.assertEqual(manifest['inputs']['IMAGE_TAG'], 'wildclawbench-e2e-scorer:v0.2-amd64')
            self.assertEqual(manifest['inputs']['PLATFORM'], 'linux/amd64')
            self.assertEqual(manifest['inputs']['CLAUDE_CODE_VERSION'], '2.1.330')
            self.assertEqual(manifest['harnesses'], ['codex', 'deepseek-harness', 'claudecode'])
            self.assertTrue((context / 'runtime-skill/bundled-components.json').is_file())
            self.assertTrue((context / 'build-prepared.sh').is_file())
            self.assertFalse(any(b'private-proxy' in path.read_bytes() for path in context.rglob('*') if path.is_file()))
            self.assertNotIn('.env', (context / '.dockerignore').read_text().splitlines()[1:])

    def test_platforms_have_separate_tags_and_build_contexts(self):
        builder = runpy.run_path(str(ROOT / 'tools/e2e-build/build_headless_scorer.py'))
        import argparse
        for platform in ['linux/amd64', 'linux/arm64']:
            args = argparse.Namespace(version='v0.2', platform=platform, tag=None, context=None,
                eval_base_image=None, node_runtime_image=None, codex_version=None, dsh_version=None,
                claude_code_version=None)
            builder['resolve_version'](args)
            arch = platform.split('/')[1]
            self.assertEqual(args.tag, 'wildclawbench-e2e-scorer:v0.2-' + arch)
            self.assertEqual(args.context, ROOT / '.cache/headless-scorer-build/v0.2' / arch)
        for tag in ['wildclawbench-e2e-scorer:v0.2', 'wildclawbench-e2e-scorer:v0.2-arm64',
                    'wildclawbench-e2e-scorer:v0.2-arm64-runtime']:
            args.tag = tag
            args.platform = 'linux/amd64'
            with self.assertRaisesRegex(ValueError, 'overwrite'):
                builder['resolve_version'](args)

    def test_v2_prepared_build_checks_architecture_before_offline_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'build-prepared.sh').write_bytes((ROOT / 'docker/e2e-scorer/v2/build-prepared.sh').read_bytes())
            (root / 'build-inputs.env').write_text('IMAGE_TAG=test:amd64\nDOCKER_CONTEXT=default\nWITH_OFFICE=1\nPLATFORM=linux/amd64\n' +
                ''.join(key + '=test\n' for key in ('EVAL_BASE_IMAGE', 'NODE_RUNTIME_IMAGE', 'CODEX_VERSION',
                    'DSH_VERSION', 'CLAUDE_CODE_VERSION', 'NPM_REGISTRY', 'PIP_INDEX_URL', 'DEBIAN_MIRROR', 'DEBIAN_SECURITY_MIRROR')))
            docker = root / 'docker'
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
                'case "$*" in *"{{.Os}}/{{.Architecture}}"*) echo "${OBSERVED_PLATFORM:-linux/amd64}" ;; esac\n')
            docker.chmod(0o755)
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'], 'CALLS': str(root / 'calls')}
            subprocess.run(['bash', str(root / 'build-prepared.sh')], env=env, check=True, capture_output=True)
            calls = (root / 'calls').read_text().splitlines()
            self.assertTrue(all('--platform linux/amd64' in row for row in calls if ' build ' in row or ' run ' in row))
            self.assertTrue(any('--claude-code-version test --platform linux/amd64 --office' in row for row in calls))
            (root / 'calls').unlink()
            result = subprocess.run(['bash', str(root / 'build-prepared.sh')],
                env={**env, 'OBSERVED_PLATFORM': 'linux/arm64'}, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'SCORER_PLATFORM_MISMATCH', result.stderr)
            self.assertFalse(any(' run ' in row for row in (root / 'calls').read_text().splitlines()))
            self.assertFalse((root / 'runtime-validation.json').exists())

    def test_prepared_build_checks_office_offline_and_stops_on_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'build-prepared.sh').write_bytes((ROOT / 'docker/e2e-scorer/build-prepared.sh').read_bytes())
            (root / 'build-inputs.env').write_text('IMAGE_TAG=test:office\nDOCKER_CONTEXT=default\nWITH_OFFICE=1\n' +
                ''.join(key + '=test\n' for key in ('EVAL_BASE_IMAGE', 'NODE_RUNTIME_IMAGE', 'CODEX_VERSION',
                                                  'DSH_VERSION', 'NPM_REGISTRY', 'PIP_INDEX_URL',
                                                  'DEBIAN_MIRROR', 'DEBIAN_SECURITY_MIRROR')))
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

    def test_legacy_version_remains_buildable_and_new_version_cannot_retag_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            context = Path(temporary) / 'context'
            command = ['bash', str(ROOT / 'docker/e2e-scorer/build.sh'), '--prepare-only',
                       '--version', 'v0.1', '--context', str(context)]
            subprocess.run(command, check=True, capture_output=True)
            manifest = json.loads((context / 'build-manifest.json').read_text())
            self.assertEqual(manifest['inputs']['IMAGE_TAG'], 'wildclawbench-e2e-scorer:codex-0.171.0-office-v2')
            self.assertNotIn('CLAUDE_CODE_VERSION', manifest['inputs'])
            self.assertEqual((context / 'Dockerfile').read_bytes(), (ROOT / 'docker/e2e-scorer/Dockerfile').read_bytes())
            for extra in [['--version', 'v0.2', '--tag', manifest['inputs']['IMAGE_TAG']],
                          ['--codex-version', 'unexpected'], ['--version', 'missing']]:
                result = subprocess.run(command + extra, capture_output=True)
                self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
