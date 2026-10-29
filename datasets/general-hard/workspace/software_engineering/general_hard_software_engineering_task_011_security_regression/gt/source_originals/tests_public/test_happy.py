from pathlib import Path
import csv,io,json,sys,unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from project.routes import handle
class Happy(unittest.TestCase):
 def test_one_benign_authorized_export(self):
  source=json.loads((ROOT/'fixtures/records.json').read_text());source['records']=source['records'][:1];source['permissions']={'admin':{'scope':'tenant','columns':['id','amount'],'download':True}}
  response,state=handle(source,'admin-a','GET','/download',{'columns':['id','amount']});rows=list(csv.reader(io.StringIO(response['body'])));self.assertEqual(rows,[['id','amount'],['a1','-12.50']]);self.assertEqual(response['status'],200)
if __name__=='__main__':unittest.main()
