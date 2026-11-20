import unittest
from project.config import migrate_config, merge_configs

class PublicCompatibility(unittest.TestCase):
    def test_positive_legacy_timeout(self):
        self.assertEqual(migrate_config({'timeout_ms':2500})['network']['timeout_seconds'],2.5)
    def test_default_only(self):
        self.assertEqual(merge_configs({'pipeline':{'workers':4}})['pipeline']['workers'],4)
    def test_positive_user_override(self):
        self.assertEqual(merge_configs({'network':{'timeout_seconds':3}},None,{'network':{'timeout_seconds':7}})['network']['timeout_seconds'],7)
    def test_version_and_positive_cache(self):
        value=migrate_config({'cache_enabled':True})
        self.assertEqual(value['config_version'],2)
        self.assertIs(value['cache']['enabled'],True)
