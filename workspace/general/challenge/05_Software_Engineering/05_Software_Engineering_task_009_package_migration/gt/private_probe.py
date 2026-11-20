from pathlib import Path
import copy
import importlib
import json
import sys

def same(a,b):
    if type(a) is not type(b):return False
    if isinstance(a,dict):return a.keys()==b.keys() and all(same(a[k],b[k]) for k in a)
    if isinstance(a,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    return a==b
target,module,data_path,config_path=sys.argv[1:]
sys.path.insert(0,target)
records=json.loads(Path(data_path).read_text())
config=json.loads(Path(config_path).read_text())
before_records=copy.deepcopy(records);before_config=copy.deepcopy(config)
result=importlib.import_module(module).run(records,config)
after_records=copy.deepcopy(records);after_config=copy.deepcopy(config)
observation={'records_before':before_records,'records_after':after_records,
             'config_before':before_config,'config_after':after_config,
             'records_unchanged':same(before_records,after_records),'config_unchanged':same(before_config,after_config),
             'scope':'observable final structure and scalar types; transient internal actions are not observed'}
print(json.dumps({'result':result,'input_observation':observation},ensure_ascii=False,sort_keys=True,allow_nan=False))
