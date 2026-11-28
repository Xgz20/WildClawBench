#!/usr/bin/env python3
"""Read-only case authoring protocol used by the platform; never runs user code."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.managed_cases import contracts,bundle

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('action',choices=['describe','validate','parse','render','compile','inspect-import','preview-scoring','export-system','check-runtime'])
p.add_argument('--input',type=Path);p.add_argument('--output',type=Path);p.add_argument('--sha256')
a=p.parse_args()
try:
 if a.action=='export-system':
  from src.managed_cases.system import export_case
  result=export_case(Path(__file__).resolve().parents[1],json.loads(a.input.read_text()),a.output)
 elif a.action=='describe':result={'schema':contracts.SCHEMA,'capabilities':['managed-case-source-v1','managed-judge-templates-v1'],'base_contracts':['general','web','ppt']}
 elif a.action=='compile':result=bundle.compile_source(a.input,a.sha256,a.output)
 elif a.action=='parse':result=contracts.parse_markdown(a.input.read_bytes())
 elif a.action=='inspect-import':result={'files':[{'path':name,'size':len(value),'sha256':contracts.sha(value)} for name,value in bundle.read_archive(a.input).items()]}
 else:
  value=json.loads(a.input.read_text(encoding='utf-8'))
  if a.action=='check-runtime':
   from src.managed_cases.runtime import check
   result=check(value['config'],value.get('scene',{}),value.get('documents',[]))
  elif a.action=='preview-scoring':
   document=value['document'];context={'task.prompt':document.get('sections',{}).get('Prompt',''),'task.name':document.get('metadata',{}).get('name',''),
    'rubric':contracts.rubric(document),'materials':document.get('assets',[]),'candidate':'[执行完成后绑定候选工作区]','trajectory':'[执行完成后绑定原始轨迹]',
    'rules':'[隔离检查完成后绑定结果]','output_contract':{'scores':{r['key']:0 for r in document.get('criteria',[])},'notes':'判分依据'}}
   template=document.get('scoring',{}).get('template',{})
   from src.managed_cases.scoring import FIXED_INSTRUCTIONS
   result={'schema':contracts.CONTEXT_SCHEMA,'preview_only':True,'transports':{transport:'\n\n'.join([FIXED_INSTRUCTIONS,contracts.render_template(template,transport,context),document.get('scoring',{}).get('supplement','')]) for transport in contracts.TRANSPORTS},'context':context}
  else:
   if a.action=='validate':result=contracts.validate(value['document'],value.get('scene'))
   else:
    doc=contracts.document(value['document'])
    if doc.get('criteria'):doc['sections']['LLM Judge Rubric']=contracts.rubric(doc)
    if doc.get('rules'):doc['sections']['Automated Checks']=contracts.compile_rules(doc['rules'])
    result={'markdown':contracts.render_markdown(doc)}
 print(json.dumps(result,ensure_ascii=False))
except (ValueError,OSError,KeyError,TypeError) as error:p.exit(2,str(error)+'\n')
