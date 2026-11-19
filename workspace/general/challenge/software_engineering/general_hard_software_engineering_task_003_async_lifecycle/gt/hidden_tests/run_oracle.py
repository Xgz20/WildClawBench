"""Run trusted observable scenarios against a copied candidate program."""
import argparse,hashlib,json,os,sys,time,traceback,unittest
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_lifecycle

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
class Result(unittest.TestResult):
    def __init__(self):super().__init__();self.rows=[];self.current=None
    def startTest(self,test):
        super().startTest(test);name=test._testMethodName;ident=name.split('_')[1];self.current={'id':ident,'owner':'business_correctness' if ident.startswith('B') else 'boundary_cases','method':name,'passed':True,'errors':[],'observations':[],'scenario_executed':False}
    def addFailure(self,test,err):
        super().addFailure(test,err);self.current['passed']=False;self.current['errors'].append(self._exc_info_to_string(err,test))
    def addError(self,test,err):
        super().addError(test,err);self.current['passed']=False;self.current['errors'].append(self._exc_info_to_string(err,test))
    def stopTest(self,test):
        self.current['observations']=getattr(test,'details',[]);self.current['stage']=getattr(test,'stage','unknown');self.current['scenario_executed']=self.current['stage']=='scenario';self.rows.append(self.current);super().stopTest(test)
def main():
    p=argparse.ArgumentParser();p.add_argument('--program',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args();test_lifecycle.PROGRAM=args.program
    before=sha(args.program/'project/worker.py');suite=unittest.defaultTestLoader.loadTestsFromTestCase(test_lifecycle.LifecycleTests);r=Result();suite.run(r)
    out={'schema_version':'h043-independent-execution/v1','source_sha256':before,'source_after_sha256':sha(args.program/'project/worker.py'),'test_files_sha256':{Path(__file__).name:sha(__file__),'test_lifecycle.py':sha(Path(__file__).with_name('test_lifecycle.py'))},'python':{'version':sys.version,'executable':sys.executable},'tests_attempted':r.testsRun,'cases':r.rows,'passed':r.wasSuccessful(),'network_or_real_service':False,'scope':'Actual candidate import + async protocol callbacks. Observations are actual; no reference implementation or source-patch string oracle.'}
    args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str)+'\n');print(json.dumps({'tests_attempted':r.testsRun,'passed':r.wasSuccessful(),'source_sha256':before,'case_passes':{x['id']:x['passed'] for x in r.rows}},ensure_ascii=False));return 0 if r.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
