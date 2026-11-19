"""Check physical input clauses and recompute factual comparisons before reading any reference."""
from pathlib import Path
from decimal import Decimal
from datetime import date
import argparse,csv,hashlib,json,re,runpy

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def verify(exec_root,gt_root):
    root,gt=Path(exec_root),Path(gt_root);annotation=json.loads((gt/'source_annotations.json').read_text(encoding='utf-8'));data=annotation['data']
    native=runpy.run_path(str(gt/'native_docx.py'));literals=runpy.run_path(str(gt/'native_values.py'))
    maps={};records={};protected={}
    for name,prefix,count in [('baseline_zh.docx','S',16),('draft_vi.docx','S',16),('review_vi.docx','R',12)]:
        path=root/name;document=native['read_document'](path);protected[name]=digest(path)
        by_name={mark:p for p in document['blocks'] if p['kind']=='paragraph' for mark in p['bookmarks']}
        ids={key:p['text'] for key,p in by_name.items() if re.fullmatch(prefix+r'\d{2}',key)};assert len(ids)==count
        maps[name]=ids
        for identity,text in ids.items():records[name+'#'+identity]={'source':name,'source_sha256':protected[name],'locator':by_name[identity]['locator'],'text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
        if name=='baseline_zh.docx':
            assert by_name['AUTHORITY']['text']==data['scope_zh']
            records[name+'#AUTHORITY']={'source':name,'source_sha256':protected[name],'locator':by_name['AUTHORITY']['locator'],'text':by_name['AUTHORITY']['text']}
    for row in data['sentences']:
        assert maps['baseline_zh.docx'][row['sentence_id']]==row['baseline_zh']
        assert maps['draft_vi.docx'][row['sentence_id']]==row['draft_vi']
    for row in data['review_comments']:assert maps['review_vi.docx'][row['comment_id']]==row['review_vi']
    with (root/'terms.csv').open(encoding='utf-8-sig',newline='') as handle:terms=list(csv.DictReader(handle))
    assert terms==data['terms'] and len(terms)==11;protected['terms.csv']=digest(root/'terms.csv')
    for line,row in enumerate(terms,2):records['terms.csv#'+row['term_id']]={'source':'terms.csv','source_sha256':protected['terms.csv'],'locator':'row:'+str(line),'value':row}
    zh=maps['baseline_zh.docx'];roles={row['zh']:row['role'] for row in terms if row['role'] in {'SUP-01','CLI-01'}}
    facts={row['sentence_id']:dict(row['author_declared_facts']) for row in data['sentences']}
    independently={
      'S01':{'provider_id':roles[re.fullmatch(r'(.*?)负责提供本批服务支持。',zh['S01'])[1]]},
      'S02':dict(zip(['materials_provider_id','materials_checker_id'],[roles[v] for v in re.fullmatch(r'所需数据清单由(.*?)提供，(.*?)负责核对。',zh['S02']).groups()])),
      'S03':{'amount':int(Decimal(re.search(r'人民币(\d+)元',zh['S03'])[1])),'currency':'CNY','amount_unit':'per_batch','tax_basis':'excluded'},
      'S04':dict(zip(['start_date','end_date'],[date(*map(int,t)).isoformat() for t in re.findall(r'(\d+)年(\d+)月(\d+)日',zh['S04'])])),
      'S05':{'first_response_work_hours':int(re.search(r'(\d+)工作小时',zh['S05'])[1]),'clock_origin':'intake_registration'},
      'S06':{'handling_work_days':int(re.search(r'(\d+)工作日',zh['S06'])[1]),'clock_origin':'required_documents_complete'}}
    total,pending=map(int,re.search(r'共(\d+)个项目，其中(\d+)个待核',zh['S11']).groups())
    independently['S11']={'total':total,'pending':pending,'completed':total-pending}
    for identity,values in independently.items():assert values==facts[identity],(identity,values,facts[identity])
    # Semantic source tags are author annotations, bound to exact physical text above.
    # This step does not claim to independently understand every Vietnamese proposition.
    proposal=annotation['proposals'];decisions=[]
    rv=maps['review_vi.docx']
    proposed_amount=literals['money'](rv['R03']);assert proposed_amount==[Decimal(80000)]
    proposed_end=literals['dates'](rv['R04']);assert proposed_end==['2027-11-30']
    assert literals['money'](maps['draft_vi.docx']['S03'])==[Decimal(80000000)]
    for row in data['review_comments']:
        target=facts[row['sentence_id']];changes=proposal[row['comment_id']]
        actual='applied' if all(key in target and target[key]==value for key,value in changes.items()) else 'not_applied'
        assert actual==row['author_declared_decision'];decisions.append({'comment_id':row['comment_id'],'decision':actual})
    expected=json.loads((gt/'expected.json').read_text(encoding='utf-8'))
    assert [{k:r[k] for k in ('sentence_id','facts')} for r in expected['sentences']]==[{'sentence_id':r['sentence_id'],'facts':r['author_declared_facts']} for r in data['sentences']]
    assert all(next(r for r in expected['comments'] if r['comment_id']==d['comment_id'])['computed_decision']==d['decision'] for d in decisions)
    return {'schema_version':'h008-physical-source-verification/v1','status':'PASS','protected_sha256':protected,'records':records,
      'clauses':16,'review_comments':12,'terms':11,'literal_independent_checks':independently,'decision_checks':decisions,
      'independence':'Physical DOCX/CSV extraction; Decimal/date/role mapping and integer subtraction; deterministic proposal comparison. No reference files read.',
      'limit':'Source semantic labels are author bilingual annotations bound to text. No second expert review, independent semantic Judge, four-client execution or calibrated difficulty.'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--exec-root',required=True,type=Path);p.add_argument('--gt-root',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();result=verify(a.exec_root,a.gt_root);a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':result['status'],'clauses':16,'reviews':12,'terms':11,'source_records':len(result['records'])}))
