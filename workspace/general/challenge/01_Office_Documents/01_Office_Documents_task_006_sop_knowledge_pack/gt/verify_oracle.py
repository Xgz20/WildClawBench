"""Re-evaluate physical inputs, before consulting declared case labels.

Uses stdlib OOXML extraction and control-flow policy_model, never reference outputs.
Independent computation does not constitute second-expert annotation review.
"""
from pathlib import Path
import argparse,csv,hashlib,json,re,runpy,zipfile
import xml.etree.ElementTree as ET

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(exec_root,gt_root):
    root,gt=Path(exec_root),Path(gt_root)
    annotations=json.loads((gt/'source_annotations.json').read_text(encoding='utf-8'))
    w='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    clauses={};index={};protected={}
    for manual in annotations['manuals']:
        source='manuals/'+manual['file'];path=root/source;protected[source]=digest(path)
        with zipfile.ZipFile(path) as archive:tree=ET.fromstring(archive.read('word/document.xml'))
        paragraphs=[''.join(n.text or '' for n in p.iter(w+'t')) for p in tree.find(w+'body').findall(w+'p')]
        for identity,title,expected in manual['clauses']:
            locations=[i for i,text in enumerate(paragraphs) if text==identity+' '+title]
            assert len(locations)==1,(source,identity,'missing/ambiguous clause')
            start=locations[0];actual=paragraphs[start+1];assert actual==expected,(identity,'physical content drift')
            assert identity not in clauses
            clauses[identity]=actual
            index[source+'#'+identity]={'source':source,'source_sha256':protected[source],
                'locator':f'paragraph:{start+2}','text_sha256':hashlib.sha256(actual.encode()).hexdigest(),'text':actual}
    assert len(clauses)==27
    authority=json.loads((root/'authority.yaml').read_text(encoding='utf-8'))
    assert authority==annotations['authority']
    protected['authority.yaml']=digest(root/'authority.yaml')
    for key,value in {**authority['controls'],'FLOW':authority['FLOW']}.items():
        index['authority.yaml#'+key]={'source':'authority.yaml','source_sha256':protected['authority.yaml'],
            'locator':'/'+('FLOW' if key=='FLOW' else 'controls/'+key),'value':value}
    numeric={'ack_hours':int(re.search(r'首次响应为(\d+)工作小时',clauses['CS02'])[1]),
             'inspection_workdays':int(re.search(r'实物验收为(\d+)工作日',clauses['QA01'])[1]),
             'payment_workdays':int(re.search(r'资金处理额度为(\d+)工作日',clauses['FI03'])[1]),
             'approval_threshold':int(re.search(r'金额不足(\d+)元',clauses['FI01'])[1])}
    cases=list(csv.DictReader((root/'incidents.csv').open(encoding='utf-8-sig',newline='')))
    protected['incidents.csv']=digest(root/'incidents.csv')
    for line,row in enumerate(cases,2):
        for key,value in list(row.items()):
            if value in ('True','False'):row[key]=value=='True'
        row['amount_cny']=int(row['amount_cny'])
        index['incidents.csv#'+row['incident_id']]={'source':'incidents.csv','source_sha256':protected['incidents.csv'],
             'locator':f'row:{line}','value':row}
    assert cases==annotations['incidents'] and len(cases)==10
    decide=runpy.run_path(str(gt/'policy_model.py'))['decide']
    computed={row['incident_id']:decide(row,authority,numeric) for row in cases}
    # Only now open author declarations and oracle, which predate the reference artifacts.
    labels=json.loads((gt/'declared_labels.json').read_text(encoding='utf-8'))['incidents']
    expected=json.loads((gt/'expected.json').read_text(encoding='utf-8'))
    for group in (labels,expected['incidents']):
        assert {row['incident_id'] for row in group}==set(computed)
        for row in group:
            modeled=computed[row['incident_id']]
            for field,actual in modeled.items():
                if field=='required_edges':
                    if field in row:assert row[field]==actual
                elif field in ('required_steps','clearance_roles','forbidden_steps'):
                    if field in row:assert set(row[field])==set(actual),(row['incident_id'],field)
                else:assert row[field]==actual,(row['incident_id'],field)
            order={node:i for i,node in enumerate(row['required_steps'])}
            assert all(order[a]<order[b] for a,b in modeled['required_edges'])
    assert numeric==expected['numeric_policy']
    return {'schema_version':'h006-physical-source-verification/v1','status':'PASS','manuals':6,'clauses':len(clauses),
        'cases':10,'numeric_policy':numeric,'declared_labels_match':True,'oracle_match':True,
        'protected_sha256':protected,'evidence_records':index,
        'independence':'Actual DOCX paragraph extraction, physical CSV/YAML and policy DAG versus pre-reference declarations; no reference artifacts read.',
        'limit':'Computational cross-check, not second-expert annotation, semantic Judge, four-client execution or empirical difficulty.'}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exec-root',required=True,type=Path)
    parser.add_argument('--gt-root',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
    a=parser.parse_args();result=verify(a.exec_root,a.gt_root)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','manuals','clauses','cases','numeric_policy')}))
