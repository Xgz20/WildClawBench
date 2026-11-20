import unittest
from pathlib import Path
from project import query_builder
from project.db_fixture import open_database

class PublicCompatibility(unittest.TestCase):
    def setUp(self):
        self.db=open_database(Path(__file__).resolve().parents[1])
    def tearDown(self): self.db.close()
    def test_plain_customer_projection(self):
        sql,params=query_builder.build_query({'table':'customer','columns':['id','name']})
        self.assertEqual(len(self.db.execute(sql,params).fetchall()),4)
    def test_simple_filter_keeps_parameters(self):
        sql,params=query_builder.build_query({'table':'customer','columns':['id'],'where':{'column':'region','op':'eq','value':'north'}})
        self.assertEqual(set(row[0] for row in self.db.execute(sql,params)),{1,4})
        self.assertTrue(params)
    def test_unknown_table_rejected(self):
        with self.assertRaises(ValueError): query_builder.build_query({'table':'missing','columns':['id']})
    def test_unknown_projection_rejected(self):
        with self.assertRaises(ValueError): query_builder.build_query({'table':'customer','columns':['missing']})
