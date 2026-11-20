"""Narrow prototype happy path; full correctness requires the replay contract."""
from pathlib import Path
import importlib.util, json, unittest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('candidate_api',ROOT/'project/api.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Smoke(unittest.TestCase):
 def test_one_page_all_pending(self):
  fixture=json.loads((ROOT/'fixtures/smoke.json').read_text());result=m.query_records(fixture['records'],{},1)
  self.assertEqual(result['total'],3);self.assertEqual(result['counts'],{'all':3,'pending':3,'approved':0});self.assertEqual([x['id'] for x in result['items']],['r01','r02','r03'])
if __name__=='__main__':unittest.main()
