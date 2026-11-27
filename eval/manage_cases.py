#!/usr/bin/env python3
"""Read-only case authoring protocol used by the platform; never runs user code."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.managed_cases import contracts,bundle

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('action',choices=['describe','validate','parse','render','compile','inspect-import'])
p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--sha256')
a=p.parse_args()
try:
 if a.action=='describe':result={'schema':contracts.SCHEMA,'capabilities':['managed-case-source-v1','managed-judge-templates-v1'],'base_contracts':['general','web','ppt']}
 elif a.action=='compile':result=bundle.compile_source(a.input,a.sha256,a.output)
 elif a.action=='parse':result=contracts.parse_markdown(a.input.read_bytes())
 elif a.action=='inspect-import':result={'files':[{'path':name,'size':len(value),'sha256':contracts.sha(value)} for name,value in bundle.read_archive(a.input).items()]}
 else:
  value=json.loads(a.input.read_text(encoding='utf-8'))
  result=contracts.validate(value['document'],value.get('scene')) if a.action=='validate' else {'markdown':contracts.render_markdown(value['document'])}
 print(json.dumps(result,ensure_ascii=False))
except (ValueError,OSError,KeyError,TypeError) as error:p.exit(2,str(error)+'\n')
