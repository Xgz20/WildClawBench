from pathlib import Path
import json
import sys
import tomllib
import unittest
ROOT=Path(__file__).resolve().parents[1]
project=ROOT/'project';meta=tomllib.loads((project/'pyproject.toml').read_text())
directory=meta.get('tool',{}).get('setuptools',{}).get('package-dir',{}).get('','.')
sys.path.insert(0,str(project/directory))
from batchstamp.core import run
class PublicCompatibility(unittest.TestCase):
    def test_positive_threshold(self):
        result=run([{'id':'x','amount':9,'region':'cn'}],{'min_amount':5});self.assertEqual(result['ids'],['x'])
    def test_explicit_positive_scale(self):
        result=run([{'id':'x','amount':9,'region':'cn'}],{'scale':2});self.assertEqual(result['total'],18)
    def test_resource_banner(self):
        self.assertIn('离线',run([],{} )['banner'])
