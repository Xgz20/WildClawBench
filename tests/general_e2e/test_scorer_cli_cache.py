import json
from pathlib import Path
import runpy
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
prepare = runpy.run_path(str(ROOT / 'tools/e2e-build/scorer_cli_cache.py'))['prepare_cli_cache']


class ScorerCliCacheTests(unittest.TestCase):
    def test_cache_is_bound_to_versions_platform_registry_and_excludes_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            versions = {'@openai/codex':'0.172.0','@deepseek-ai/dsh':'0.2.2-rc.5'}
            metadata = {'schema_version':'wildclawbench.scorer-cli-cache/v1','platform':'linux/amd64',
                        'registry':'https://registry.test','versions':versions}
            (source/'cache-info.json').write_text(json.dumps(metadata))
            (source/'_cacache/content-v2').mkdir(parents=True)
            (source/'_cacache/content-v2/package').write_bytes(b'public package')
            (source/'_cacache/tmp').mkdir();(source/'_cacache/tmp/partial').write_bytes(b'unfinished')
            (source/'_logs').mkdir();(source/'_logs/private').write_bytes(b'private log')
            target=root/'target';target.mkdir()
            result=prepare(target,platform='linux/amd64',registry='https://registry.test',versions=versions,source=source)
            self.assertEqual(result['files'],2)
            self.assertFalse((target/'npm-cache/_logs').exists())
            self.assertFalse((target/'npm-cache/_cacache/tmp').exists())
            for overrides in [{'platform':'linux/arm64'}, {'registry':'https://other.test'}, {'versions':{'@openai/codex':'old'}}]:
                with self.assertRaisesRegex(ValueError,'INPUT_MISMATCH'):
                    prepare(target,source=source,**{'platform':'linux/amd64','registry':'https://registry.test','versions':versions,**overrides})

    def test_cache_rejects_links_outside_the_public_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'source';source.mkdir();target=root/'target';target.mkdir()
            metadata={'schema_version':'wildclawbench.scorer-cli-cache/v1','platform':'linux/amd64','registry':'https://registry.test','versions':{}}
            (source/'cache-info.json').write_text(json.dumps(metadata));(source/'_cacache').mkdir()
            outside=root/'private';outside.write_text('private')
            (source/'_cacache/link').symlink_to(outside)
            with self.assertRaisesRegex(ValueError,'SYMLINK'):
                prepare(target,platform='linux/amd64',registry='https://registry.test',versions={},source=source)


if __name__ == '__main__':
    unittest.main()
