from pathlib import Path
import json
import unittest
import instrumentation
import profile as matcher_profile

class PublicMatching(unittest.TestCase):
    def test_original_priority(self):
        root = Path(__file__).resolve().parents[1]
        case = json.loads((root / 'fixtures/public_smoke.json').read_text(encoding='utf-8'))
        function = matcher_profile.load_source((root / 'project/matcher.py').read_bytes())
        queries, catalog, snapshot = instrumentation.make_views(case)
        result = function(queries, catalog)
        self.assertEqual([row['matched_by'] for row in result], ['email', 'phone', 'name_region'])
        self.assertEqual(result[0]['row_ids'], ['Z-7', 'M-4'])
        self.assertEqual(result[1]['row_ids'], ['A-2', 'P-8'])
