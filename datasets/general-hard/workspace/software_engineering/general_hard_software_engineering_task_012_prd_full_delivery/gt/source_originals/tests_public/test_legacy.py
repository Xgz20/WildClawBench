from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project import legacy
class Legacy(unittest.TestCase):
 def test_health_shape(self):self.assertEqual(legacy.health(),{'service':'member-demo','status':'ok','api':1})
if __name__=='__main__':unittest.main()
