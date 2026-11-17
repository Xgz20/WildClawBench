"""Exercise installed/importable code from an explicitly isolated target or wheel."""
from pathlib import Path
import importlib
import importlib.metadata
import importlib.resources
import json
import runpy
import sys

target,mode=sys.argv[1:3];sys.path.insert(0,target);args=sys.argv[3:]
if mode=='api':
    module=importlib.import_module(args[0]);data=json.loads(Path(args[1]).read_text());config=json.loads(Path(args[2]).read_text())
    print(json.dumps(module.run(data,config),ensure_ascii=False,sort_keys=True))
elif mode=='origin':
    import batchstamp,legacy_stamp
    print(json.dumps({'package':batchstamp.__file__,'legacy':legacy_stamp.__file__,'version':importlib.metadata.version('batchstamp-h049')},ensure_ascii=False))
elif mode=='resources':
    root=importlib.resources.files('batchstamp')/'resources'
    print(json.dumps({'defaults':json.loads((root/'defaults.json').read_text(encoding='utf-8')),'banner':(root/'banner.txt').read_text(encoding='utf-8').rstrip('\n')},ensure_ascii=False,sort_keys=True))
elif mode=='module':
    module=args[0];sys.argv=[module,*args[1:]];runpy.run_module(module,run_name='__main__')
else:raise ValueError('probe mode')
