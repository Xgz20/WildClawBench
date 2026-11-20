"""Disposable actual-Office author controls. No Harness run or semantic score is manufactured."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,copy,hashlib,json,os,re,runpy,shutil,subprocess,sys,traceback,zipfile
import xml.etree.ElementTree as ET
GT=Path(__file__).resolve().parent;BASE=GT.parent
X='{http://schemas.openxmlformats.org/spreadsheetml/2006/main}';W='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
def read(p):return json.loads(p.read_text())
def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def inventory(root):return {p.relative_to(root).as_posix():sha(p) for p in root.rglob('*') if p.is_file()}
def package(p,fn):
    with zipfile.ZipFile(p) as z:parts={n:z.read(n) for n in z.namelist()}
    fn(parts)
    with zipfile.ZipFile(p,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in parts.items():z.writestr(n,b)
def xml(p,part,fn):
    def edit(parts):
        node=ET.fromstring(parts[part]);fn(node);parts[part]=ET.tostring(node,encoding='utf-8',xml_declaration=True)
    package(p,edit)
def cell(node,address,value):
    found=node.find(f'.//{X}c[@r="{address}"]')
    if found is None:
        row=node.find(f'.//{X}row[@r="{re.search(r"[0-9]+",address)[0]}"]');assert row is not None
        found=ET.SubElement(row,X+'c',{'r':address})
    for child in list(found):found.remove(child)
    found.set('t','inlineStr');s=ET.SubElement(found,X+'is');ET.SubElement(s,X+'t').text='' if value is None else str(value)
def values(node,address):
    c=node.find(f'.//{X}c[@r="{address}"]');return ''.join(t.text or '' for t in c.iter(X+'t')) if c is not None else ''
def doc_append_execution(node,text):
    body=node.find(W+'body');heading=next(p for p in body if p.tag==W+'p' and '条件未满足暂不执行' in ''.join(t.text or '' for t in p.iter(W+'t')))
    p=ET.Element(W+'p');r=ET.SubElement(p,W+'r');ET.SubElement(r,W+'t').text=text;body.insert(list(body).index(heading),p)
def mutate(name,root):
    result=root/'results';matrix=result/'redline_matrix.xlsx';word=result/'execution.docx';unknown=result/'uncertain.json'
    cases={r['revision_id']:r for r in read(root/'gt/expected.json')['cases']}
    st={'R02':'confirmed','R03':'withdrawn','R05':'confirmed','R06':'confirmed','R07':'confirmed','R08':'confirmed','R09':'confirmed','R10':'pending','R11':'confirmed','R13':'conditional','R14':'confirmed','R16':'confirmed'}
    if name.startswith('wrong_state_'):
        identity=name.rsplit('_',1)[1];xml(matrix,'xl/worksheets/sheet1.xml',lambda n:cell(n,'E'+str(int(identity[1:])+5),st[identity]));return
    if name=='reference':return
    if name=='english_statuses':
        xml(matrix,'xl/worksheets/sheet1.xml',lambda n:[cell(n,'E'+str(int(k[1:])+5),v['status']) for k,v in cases.items()]);return
    if name=='chinese_headers':
        headers=['修订号','条款号','原文','提议','状态','执行文本','条件','依据规则','图像证据']
        xml(matrix,'xl/worksheets/sheet1.xml',lambda n:[cell(n,chr(65+i)+'5',t) for i,t in enumerate(headers)]);return
    if name=='renamed_sheets':
        xml(matrix,'xl/workbook.xml',lambda n:[s.set('name','核对'+str(i)) for i,s in enumerate(n.findall(X+'sheets/'+X+'sheet'))]);return
    if name=='reordered_rows':
        def f(n):
            data=n.find(X+'sheetData');rows=[r for r in data if int(r.get('r'))>=6];snap=[copy.deepcopy(r) for r in reversed(rows)]
            for old,new in zip(rows,snap):
                number=old.get('r');new.set('r',number)
                for c in new.findall(X+'c'):c.set('r',re.sub(r'\d+$',number,c.get('r')))
                data.remove(old);data.append(new)
        xml(matrix,'xl/worksheets/sheet1.xml',f);return
    if name in {'inline_json_evidence','reviewer_b_regions','normalized_regions','xywh_regions','sha_only_evidence','whole_page_regions','wrong_page_regions','wrong_region','semantic_wrong_observation'}:
        source=read(BASE/'independent-review/reviewer_b.json')['records'] if name=='reviewer_b_regions' else list(cases.values())
        records={r['revision_id']:copy.deepcopy(r['evidence']) for r in source}
        for identity,evidence in records.items():
            for e in evidence:
                if name=='normalized_regions':e['bbox']=[e['bbox'][i]/(1500 if i%2==0 else 2100) for i in range(4)];e['coordinate_space']='normalized_xyxy'
                if name=='xywh_regions':a,b,c,d=e['bbox'];e['bbox']=[a,b,c-a,d-b];e['coordinate_space']='pixel_xywh'
                if name=='sha_only_evidence':e.pop('bbox');e['sha256']=sha(root/e['file'])
                if name=='whole_page_regions':e['bbox']=[0,0,1500,2100]
                if name=='wrong_page_regions':e['file']='signed_pages/scan_05.png' if e['file']!='signed_pages/scan_05.png' else 'signed_pages/scan_01.png'
                if name=='wrong_region':e['bbox']=[1,1,20,20]
                if name=='semantic_wrong_observation':e['observation']='该区域证明全部修订已真实签署并完成付款。'
        xml(matrix,'xl/worksheets/sheet1.xml',lambda n:[cell(n,'I'+str(int(k[1:])+5),json.dumps(v,ensure_ascii=False)) for k,v in records.items()]);return
    if name=='bom_json':unknown.write_bytes(b'\xef\xbb\xbf'+unknown.read_bytes());return
    if name=='paraphrased_value':
        xml(matrix,'xl/worksheets/sheet1.xml',lambda n:[cell(n,'D8','单次到场服务费调整为1000元'),cell(n,'F8','单次到场服务费调整为1000元')]);return
    if name=='all_confirmed':
        xml(matrix,'xl/worksheets/sheet1.xml',lambda n:[cell(n,'E'+str(i+5),'confirmed') for i in range(1,18)]);return
    if name=='guess_amount':
        xml(matrix,'xl/worksheets/sheet1.xml',lambda n:cell(n,'D9','服务押金改为6000元。'))
        data=read(unknown);data['items'][0]['visible_text']='服务押金改为6000元。';data['items'][0]['proposed_amount']=6000;dump(unknown,data);return
    if name=='extra_unknown':
        d=read(unknown);row=copy.deepcopy(d['items'][0]);row['revision_id']='R07';d['items'].append(row);dump(unknown,d);return
    if name=='wrong_unknown_field':
        d=read(unknown);d['items'][1]['unknown_fields']=['proposed_amount'];dump(unknown,d);return
    if name=='guess_condition':
        d=read(unknown);d['items'][2]['condition']='无条件执行';d['items'][2]['condition_met']=True;dump(unknown,d)
        xml(matrix,'xl/worksheets/sheet1.xml',lambda n:cell(n,'G21','无条件执行'));return
    if name=='wrong_adopted_text':xml(matrix,'xl/worksheets/sheet1.xml',lambda n:cell(n,'F7',cases['R02']['proposed_text']));return
    if name=='wrong_confirmed_value':xml(word,'word/document.xml',lambda n:[setattr(t,'text',t.text.replace('1000','1200')) for t in n.iter(W+'t') if t.text and '1000' in t.text]);return
    if name=='conditional_in_execution':xml(word,'word/document.xml',lambda n:doc_append_execution(n,'C09 R09 '+cases['R09']['proposed_text']));return
    if name=='old_unsigned_execution':shutil.copyfile(root/'unsigned.docx',word);return
    if name=='semantic_real_approval_claim':
        xml(word,'word/document.xml',lambda n:[setattr(t,'text',t.text+'现实验收、付款和采购均已完成。') for t in n.iter(W+'t') if t.text and t.text.startswith('前置条件 一期')]);return
    if name=='duplicate_matrix_row':
        def f(n):
            data=n.find(X+'sheetData');new=copy.deepcopy(data.find(X+'row[@r="6"]'));new.set('r','23')
            for c in new.findall(X+'c'):c.set('r',re.sub(r'\d+$','23',c.get('r')))
            data.append(new)
        xml(matrix,'xl/worksheets/sheet1.xml',f);return
    if name.startswith('missing_') and name[8:] in {'matrix','word','json'}:
        {'matrix':matrix,'word':word,'json':unknown}[name[8:]].unlink();return
    if name=='malformed_json':unknown.write_text('{');return
    if name=='corrupt_word':word.write_bytes(b'not an OOXML file');return
    if name=='all_missing':shutil.rmtree(result);return
    if name=='tampered_input':(root/'authority.md').write_text((root/'authority.md').read_text()+'\nchanged');return
    if name=='missing_gt':(root/'gt/expected.json').unlink();return
    if name=='review_tamper':p=root/'gt/reviews/reviewer_a.json';p.write_text(p.read_text()+' ');return
    if name=='annotation_gate_closed':p=root/'gt/annotation_status.json';d=read(p);d['status']='pending';dump(p,d);return
    if name=='helper_drift':p=root/'gt/word_model.py';p.write_text(p.read_text()+'\n#drift\n');return
    if name=='missing_runtime':return
    raise ValueError('unimplemented control: '+name)
def child(root):
    try:scores=runpy.run_path(str(root/'gt/grader.py'))['grade'](root);dump(root.parent/'result.json',{'kind':'scores','scores':scores})
    except Exception as e:dump(root.parent/'result.json',{'kind':'evaluation_error','type':type(e).__name__,'message':str(e),'traceback':traceback.format_exc(),'score':None})
def main():
    p=argparse.ArgumentParser();p.add_argument('--child',type=Path);p.add_argument('--output-dir',type=Path);p.add_argument('--select',nargs='*');p.add_argument('--jobs',type=int,default=2);args=p.parse_args()
    if args.child:child(args.child);return
    positive=['reference','english_statuses','chinese_headers','renamed_sheets','reordered_rows','inline_json_evidence','reviewer_b_regions','normalized_regions','xywh_regions','bom_json','paraphrased_value']
    negative={**{'wrong_state_'+k:('boundary_cases',group) for k,group in {'R02':'archive_not_local','R03':'black_strike_not_red_cancel','R05':'cancelled_red_proposals','R06':'reject_with_stamps','R07':'missing_b','R08':'double_choice','R09':'condition_unmet','R10':'obscured_b','R11':'blank_choice','R13':'condition_met_scope','R14':'cancelled_red_proposals','R16':'unknown_condition'}.items()},
        **{k:('business_correctness',None) for k in ['all_confirmed','guess_amount','wrong_unknown_field','guess_condition','wrong_adopted_text','wrong_confirmed_value','conditional_in_execution','old_unsigned_execution']},
        **{k:('delivery_integrity',None) for k in ['extra_unknown','duplicate_matrix_row','missing_matrix','missing_word','missing_json','malformed_json','corrupt_word','all_missing','tampered_input']},
        **{k:('evidence_binding',None) for k in ['sha_only_evidence','whole_page_regions','wrong_page_regions','wrong_region']}}
    infrastructure=['missing_gt','review_tamper','annotation_gate_closed','helper_drift','missing_runtime']
    semantics=['semantic_wrong_observation','semantic_real_approval_claim'];all_names=positive+list(negative)+infrastructure+semantics
    names=args.select or all_names;assert set(names)<=set(all_names)
    out=args.output_dir.resolve();out.mkdir(parents=True);runtime=read(BASE/'qa/runtime/runtime-lock.json')
    dump(out/'office.json',runtime['office_runtime']);dump(out/'render.json',runtime['office_render_runtime'])
    runtime_python=BASE.parent/'h005/qa/existing-worker/venv/bin/python'
    def run(name):
        case=out/name;workspace=case/'workspace';case.mkdir();shutil.copytree(BASE/'exec',workspace)
        shutil.copytree(GT,workspace/'gt',ignore=shutil.ignore_patterns('__pycache__','*.pyc'));shutil.copytree(GT/'reference/results',workspace/'results')
        mutate(name,workspace);before=inventory(workspace)
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','GENERAL_E2E_OFFICE_LOCK':str(out/'office.json'),'GENERAL_E2E_OFFICE_RENDER_LOCK':str(out/'render.json'),
            'GENERAL_E2E_RULE_EVIDENCE_DIR':str(case/'derived')}
        if name=='missing_runtime':env.pop('GENERAL_E2E_OFFICE_RENDER_LOCK')
        process=subprocess.run([str(runtime_python),str(GT/'validate_authoring.py'),'--child',str(workspace)],env=env,capture_output=True,text=True,timeout=150)
        (case/'stdout.txt').write_text(process.stdout);(case/'stderr.txt').write_text(process.stderr)
        assert process.returncode==0,(name,process.stderr)
        result=read(case/'result.json');unchanged=inventory(workspace)==before;assert unchanged,name
        if name in infrastructure:ok=result['kind']=='evaluation_error' and result['score'] is None
        elif result['kind']!='scores':ok=False
        elif name in positive+semantics:ok=all(abs(v-1)<1e-10 for v in result['scores'].values())
        else:
            key,group=negative[name];ok=result['scores'][key]<1
            if group:ok &= read(case/'derived/h012-analysis.json')['boundary_groups'][group]<1
            if name=='all_missing':ok &= all(v==0 for v in result['scores'].values())
        summary={'name':name,'pass':ok,'kind':result['kind'],'scores':result.get('scores'),'expected_infrastructure':name in infrastructure,
            'semantic_only':name in semantics,'workspace_unchanged':unchanged}
        dump(case/'validation.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True);return summary
    results=[]
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for future in as_completed([pool.submit(run,n) for n in names]):results.append(future.result())
    report={'status':'AUTHOR_CONTROLS_PASS' if all(r['pass'] for r in results) else 'FAIL','cases':results,'count':len(results),'full_matrix':set(names)==set(all_names),
        'positive_count':len(set(names)&set(positive)),'negative_count':len(set(names)&set(negative)),'infrastructure_count':len(set(names)&set(infrastructure)),
        'semantic_only_count':len(set(names)&set(semantics)),'source_gt_sha256':inventory(GT),'source_exec_sha256':inventory(BASE/'exec'),
        'control_scope_summary':'11合法表达、33业务/边界/交付/坐标负例、5基础设施门禁、2项须语义裁判判断的规则满分反例；只属于作者验收。',
        'limit':'Actual locked Office author controls, not candidate/Harness results or independent semantic grading. Same-model blind annotations may share errors.'}
    dump(out/'validation.json',report)
    if not all(r['pass'] for r in results):raise SystemExit(1)
if __name__=='__main__':main()
